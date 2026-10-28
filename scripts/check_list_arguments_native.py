"""Native differentials for eager pure arguments and callee integer conversions."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap_calls import ListHeapCallsProgram
if __package__:
    from .check_list_payload_maps_native import helpers, MAPPER, run_native, samples
else:
    from check_list_payload_maps_native import helpers, MAPPER, run_native, samples


def summary(offset,ascending):
    base='__list_scan*(__list_scan-1)//2' if ascending else '__list_scan*(2*__list_length-__list_scan-1)//2'
    return {'__list_scan':{'__list_call_total':base+'+__list_scan*('+offset+')'}}


def fixtures():
    cases=[]
    def add(name,actual,formal,oracle,formula,escape=False,ascending=True,unused=False,multiple=False,wide=False):
        stage='map(head,'+actual+');'+('head=flip(head);' if ascending else '')
        source=helpers(stage,escape).replace('void map(struct Node*q,int d)','void map(struct Node*q,'+formal+' d)')
        if unused:source=source.replace('q->value=q->value+d;','q->value=q->value;')
        if multiple:
            source=source.replace('unsigned char d)','unsigned char d,int other)').replace('q->value+d','q->value+d+other')
        if wide:source=source.replace('int value','long long value')
        cases.append(dict(name=name,source=source,oracle=oracle,formula=formula,escape=escape,ascending=ascending))
    add('expression','delta+1','int',lambda d:d+1,'delta+1')
    add('unsigned_char_parameter','delta+260','unsigned char',lambda d:(d+260)%256,'(delta+260)%256')
    add('unsigned_short_parameter','delta+65540','unsigned short',lambda d:(d+65540)%65536,'(delta+65540)%65536',ascending=False)
    add('boolean_parameter','delta-2','_Bool',lambda d:int(d!=2),'0 if delta==2 else 1',escape=True,ascending=False)
    add('guarded_division','delta ? 12/delta : 3','int',lambda d:3 if d==0 else int(12/d),'3 if delta==0 else (12 if delta==1 else (6 if delta==2 else (4 if delta==3 else (-12 if delta==-1 else (-6 if delta==-2 else -4)))))',escape=True)
    add('signed_char_parameter','delta+255','signed char',lambda d:d-1,'delta-1',ascending=False)
    add('mixed_arguments','delta+260,delta+1','unsigned char',lambda d:(d+260)%256+d+1,'(delta+260)%256+delta+1',multiple=True)
    add('unused_defined_argument','delta+260','unsigned char',lambda d:0,'0',unused=True)
    add('long_parameter_lp64','4294967297LL','long',lambda d:4294967297,'4294967297',wide=True,ascending=False)
    return cases


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];correspondences=0;negatives=[]
    with tempfile.TemporaryDirectory(prefix='list-arguments-native-') as directory:
        path=Path(directory)
        for case in fixtures():
            name=case['name'];source=case['source'];summaries=summary(case['formula'],case['ascending'])
            request={'source':source,'function':'entry','frontend':'clang_proof','proof':{
                'backend':'list_calls','parameter_bounds':{'n':[-3,1000000],'delta':[-3,3]},'loop_summaries':summaries}}
            report=analyze_request(request)
            if report['status']!='PROVED_DEFINED_CLANG_LIST_CALLS':raise AssertionError((name,report))
            normalized=report['normalization']['source']
            model=ListHeapCallsProgram(normalized,function='entry',parameter_bounds={'n':[-3,1000000],'delta':[-3,3]},loop_summaries=summaries)
            forms=[('original',source),('normalized',normalized),('composed',model.composed_source)]
            statements=[];expected=[];scenarios=[]
            for delta in (-3,0,2):
                for n,count in samples(1000000):
                    offset=case['oracle'](delta);value=count*(count-1)//2+count*offset
                    proof=model.report({'n':n,'delta':delta},count)
                    if not case['escape'] and proof['evaluation']['value']!=value:raise AssertionError((name,proof,value))
                    size=max(0,n);fail=count+1 if count<size else 0;attempts=count+1 if count<size else size
                    if case['escape']:
                        call='struct Node*p=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;long long value=0;int seen=0;while(p){int index=fixture_ascending?seen:'+str(count)+'-1-seen;if(seen>='+str(count)+'||p!=fixture_nodes[index]){return 10;}struct Node*next=p->next;void*want=(seen+1<'+str(count)+')?fixture_nodes[fixture_ascending?index+1:index-1]:NULL;if((void*)next!=want){return 11;}value+=p->value;fixture_free(p);p=next;seen++;}if(seen!='+str(count)+'){return 12;}'
                    else:call='long long value=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;'
                    expected.append([value,count,count if case['escape'] else 0,attempts,count])
                    scenarios.append({'n':n,'delta':delta,'successful_allocations':count,'independent_converted_map_offset':offset})
                    statements.append('{fixture_offset='+str(offset)+'LL;fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(case['ascending']))+';'+call+'if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            check='static long long fixture_offset;static void fixture_check_payload(void*p,int index){if((long long)((struct Node*)p)->value!=(long long)index+fixture_offset){abort();}}'
            harness=check+'int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in forms:
                    native=run_native(path,code,harness,name+tag,opt)
                    if native.returncode or native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                    outputs[tag]=[[int(v) for v in line.split()] for line in native.stdout.splitlines()]
                if any(values!=expected for values in outputs.values()):raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'independent_expected':expected});correspondences+=len(expected)
                print(name,opt,len(expected),'argument/payload/identity/value correspondences passed',flush=True)
            rows.append({'case':name,'request':request,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                         'normalization':report['normalization'],'certificate':report['certificate'],'scenarios':scenarios,
                         'source_forms':[tag for tag,_ in forms],'every_payload_and_free_identity_checked':True,'runs':runs})
        for name,actual,delta,n,fail,diagnostic in [
            ('empty_unused_division','1/delta',0,0,0,'division by zero'),
            ('allocation_failure_unused_overflow','delta+1',2147483647,1,1,'signed integer overflow'),
            ('empty_unused_shift','1<<delta',32,0,0,'shift exponent'),
        ]:
            source=helpers('map(head,'+actual+');',True).replace('q->value=q->value+d;','q->value=q->value;')
            request={'source':source,'function':'entry','frontend':'clang_proof','proof':{
                'backend':'list_calls','parameter_bounds':{'n':[n,n],'delta':[delta,delta]}}}
            report=analyze_request(request)
            if report['status']!='UNKNOWN' or report.get('c_overflow_verified') or report.get('reason')!='List map call argument source proof failed':raise AssertionError((name,report))
            harness='static void fixture_check_payload(void*p,int index){(void)p;(void)index;}int main(void){fixture_fail='+str(fail)+';printf("%p\\n",(void*)entry('+str(n)+','+str(delta)+'));return 0;}'
            # A composed witness is conditional on successful eager-argument
            # proofs. Never claim equivalence for these rejected programs.
            for opt in ('-O0','-O2'):
                for tag,code in [('original',source),('normalized',report['normalization']['source'])]:
                    native=run_native(path,code,harness,name+tag,opt)
                    if native.returncode==0 or diagnostic not in native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                    negatives.append({'case':name,'request':request,'proof_status':report['status'],'argument_proof':report['source_proof'],
                                      'source_form':tag,'optimization':opt,'exit_code':native.returncode,'diagnostic':native.stderr})
    result={'passed':True,'correspondences':correspondences,'negative_native_runs':len(negatives),'cases':rows,'negative_controls':negatives,
            'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(correspondences,'correspondences and',len(negatives),'expected unsafe eager-argument runs passed',flush=True)


if __name__=='__main__':main()
