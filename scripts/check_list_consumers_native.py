"""Native ownership, eager-argument and weighted-fold differential controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap_calls import ListHeapCallsProgram
if __package__:
    from .check_list_payload_maps_native import run_native, samples, FLIP, MAPPER
else:
    from check_list_payload_maps_native import run_native, samples, FLIP, MAPPER


RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int n){struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'


def source(actual='delta+260',formal='unsigned char',step='(long long)q->value*scale',returned='total+scale',extra=False,stages=False,narrow=False):
    params=formal+' scale'+(',int offset' if extra else '')
    consumer=('unsigned char' if narrow else 'long long')+' consume(struct Node*q,'+params+'){long long total=0;while(q){struct Node*tail=q->next;total+='+step+';free(q);q=tail;}return '+returned+';}'
    call='consume(head,'+actual+(','+'delta-1' if extra else '')+')'
    return '#include <stdlib.h>\n'+RECORD+BUILD+(MAPPER+FLIP if stages else '')+consumer+'long long entry(int n,int delta){struct Node*head=build(n);'+('map(head,delta);head=flip(head);' if stages else '')+'return '+('(signed char)' if narrow else '')+call+';}'


def fixtures():
    cases=[]
    def add(name,code,formula,scale,offset=lambda d:0,finish=lambda d:0,upper=1000000,ascending=False,payload_offset=lambda d:0):
        base='__list_scan*(__list_scan-1)//2' if ascending else '__list_scan*(2*__list_length-__list_scan-1)//2'
        cases.append(dict(name=name,source=code,summary={'__list_scan':{'__list_call_total':formula(base)}},scale=scale,offset=offset,finish=finish,upper=upper,ascending=ascending,payload_offset=payload_offset))
    add('narrow_weight',source(),lambda b:'((delta+260)%256)*('+b+')',lambda d:(d+260)%256,finish=lambda d:(d+260)%256)
    add('signed_weight',source('delta+255','signed char'),lambda b:'(delta-1)*('+b+')',lambda d:d-1,finish=lambda d:d-1)
    add('boolean_weight',source('delta-2','_Bool'),lambda b:'(0 if delta==2 else 1)*('+b+')',lambda d:int(d!=2),finish=lambda d:int(d!=2))
    add('lp64_long_weight',source('4294967297LL','long'),lambda b:'4294967297*('+b+')',lambda d:4294967297,finish=lambda d:4294967297,upper=1000)
    add('weighted_offset',source(step='(long long)q->value*scale+offset',returned='total+scale+offset',extra=True),lambda b:'((delta+260)%256)*('+b+')+__list_scan*(delta-1)',lambda d:(d+260)%256,offset=lambda d:d-1,finish=lambda d:(d+260)%256+d-1)
    add('multiple_payload_reads',source(step='(long long)q->value*scale+q->value'),lambda b:'(((delta+260)%256)+1)*('+b+')',lambda d:(d+260)%256+1,finish=lambda d:(d+260)%256)
    add('return_narrowing',source(narrow=True),lambda b:'((delta+260)%256)*('+b+')',lambda d:(d+260)%256,finish=lambda d:(d+260)%256)
    piece='3 if delta==0 else (12 if delta==1 else (6 if delta==2 else (4 if delta==3 else (-12 if delta==-1 else (-6 if delta==-2 else -4)))))'
    guarded=lambda d:3 if d==0 else int(12/d)
    add('guarded_argument',source('delta ? 12/delta : 3','int'),lambda b:'('+piece+')*('+b+')',guarded,finish=guarded)
    add('unused_parameter',source(step='q->value',returned='total'),lambda b:b,lambda d:1)
    add('map_reverse_consume',source(stages=True,step='(long long)q->value*scale+offset',returned='total+scale',extra=True),lambda b:'((delta+260)%256)*(('+b+')+__list_scan*delta)+__list_scan*(delta-1)',lambda d:(d+260)%256,offset=lambda d:d-1,finish=lambda d:(d+260)%256,ascending=True,payload_offset=lambda d:d)
    return cases


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];correspondences=0;negative=[]
    with tempfile.TemporaryDirectory(prefix='list-consumers-native-') as directory:
        path=Path(directory)
        for case in fixtures():
            name=case['name'];code=case['source']
            request={'source':code,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,case['upper']],'delta':[-3,3]},'loop_summaries':case['summary']}}
            proof=analyze_request(request)
            if proof['status']!='PROVED_DEFINED_CLANG_LIST_CALLS':raise AssertionError((name,proof))
            normalized=proof['normalization']['source']
            model=ListHeapCallsProgram(normalized,function='entry',parameter_bounds=request['proof']['parameter_bounds'],loop_summaries=case['summary'])
            forms=[('original',code),('normalized',normalized),('composed',model.composed_source)]
            statements=[];expected=[];scenarios=[]
            for delta in (-3,0,2):
                for n,count in samples(case['upper']):
                    weight=case['scale'](delta);offset=case['offset'](delta);payload_offset=case['payload_offset'](delta)
                    value=(count*(count-1)//2+count*payload_offset)*weight+count*offset+case['finish'](delta)
                    if name=='return_narrowing':
                        value%=256
                        if value>=128:value-=256
                    result=model.report({'n':n,'delta':delta},count)
                    if result['evaluation']['value']!=value:raise AssertionError((name,result,value))
                    size=max(0,n);fail=count+1 if count<size else 0;attempts=count+1 if count<size else size
                    expected.append([value,count,0,attempts,count])
                    scenarios.append({'n':n,'delta':delta,'successful_allocations':count,'weight':weight,'offset':offset,'return_offset':case['finish'](delta),'payload_offset':payload_offset,'expected':value})
                    statements.append('{fixture_offset='+str(payload_offset)+'LL;fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(case['ascending']))+';long long value=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            check='static long long fixture_offset;static void fixture_check_payload(void*p,int index){if((long long)((struct Node*)p)->value!=(long long)index+fixture_offset){abort();}}'
            harness=check+'int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,text in forms:
                    native=run_native(path,text,harness,name+tag,opt)
                    if native.returncode or native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                    outputs[tag]=[[int(v) for v in line.split()] for line in native.stdout.splitlines()]
                if any(v!=expected for v in outputs.values()):raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'independent_expected':expected});correspondences+=len(expected)
                print(name,opt,len(expected),'argument/value/payload/ownership groups passed',flush=True)
            rows.append({'case':name,'request':request,'source_sha256':hashlib.sha256(code.encode()).hexdigest(),'normalization':proof['normalization'],'certificate':proof['certificate'],'scenarios':scenarios,'runs':runs,'source_forms':[tag for tag,_ in forms],'every_payload_free_identity_and_order_checked':True})
        controls=[
            ('empty_unused_division',source('1/delta','int',step='q->value',returned='total'),0,0,0,'division by zero','List consumer call argument source proof failed'),
            ('failure_unused_overflow',source('delta+1','int',step='q->value',returned='total'),2147483647,1,1,'signed integer overflow','List consumer call argument source proof failed'),
            ('empty_unused_shift',source('1<<delta','int',step='q->value',returned='total'),32,0,0,'shift exponent','List consumer call argument source proof failed'),
            ('step_overflow',source('delta','int',step='q->value*2147483647',returned='total'),0,3,0,'signed integer overflow','List fold source proof failed'),
            ('empty_return_division',source('delta','int',step='q->value',returned='total/scale'),0,0,0,'division by zero','List fold source proof failed'),
        ]
        for name,code,delta,n,fail,diagnostic,reason in controls:
            request={'source':code,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[n,n],'delta':[delta,delta]}}}
            proof=analyze_request(request)
            if proof['status']!='UNKNOWN' or proof.get('c_overflow_verified') or proof.get('reason')!=reason:raise AssertionError((name,proof))
            harness='static void fixture_check_payload(void*p,int index){(void)p;(void)index;}int main(void){fixture_fail='+str(fail)+';printf("%lld\\n",entry('+str(n)+','+str(delta)+'));return 0;}'
            for opt in ('-O0','-O2'):
                for tag,text in [('original',code),('normalized',proof['normalization']['source'])]:
                    native=run_native(path,text,harness,name+tag,opt)
                    if native.returncode==0 or diagnostic not in native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                    negative.append({'case':name,'request':request,'proof_status':proof['status'],'source_proof':proof['source_proof'],'source_form':tag,'optimization':opt,'exit_code':native.returncode,'diagnostic':native.stderr})
    result={'passed':True,'case_count':len(rows),'correspondence_groups':correspondences,'native_output_matches':3*correspondences,'model_matches':correspondences//2,'expected_ubsan_failures':len(negative),'cases':rows,'negative_controls':negative,'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls')}),flush=True)


if __name__=='__main__':main()
