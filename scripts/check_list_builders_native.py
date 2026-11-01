"""Independent original/Clang/composed builder binding and ownership oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap_calls import ListHeapCallsProgram
if __package__:
    from .check_list_reversal_native import PREFIX
    from .check_list_payload_maps_native import FLIP, MAPPER
else:
    from check_list_reversal_native import PREFIX
    from check_list_payload_maps_native import FLIP, MAPPER


RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int count,TYPE bias){struct Node*head=0;for(int i=0;i<count;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=PAYLOAD;p->next=head;head=p;}return head;}'
DRAIN='long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;'


def source(count='n+1',bias='delta+260',kind='unsigned char',payload='i+bias',escape=False,pipeline=False,internal=False):
    builder=BUILD.replace('TYPE',kind).replace('PAYLOAD',payload)
    if internal:
        builder=builder.replace('if(!p){return head;}','if(!p){break;}')
        builder=builder.rsplit('return head;}',1)[0]+'struct Node*cursor=head;while(cursor){cursor->value=cursor->value+1;cursor=cursor->next;}return head;}'
    extras=MAPPER+FLIP if pipeline else ''
    suffix='map(head,delta);head=flip(head);' if pipeline else ''
    entry=('struct Node*' if escape else 'long long ')+'entry(int n,int delta){struct Node*head=build('+count+','+bias+');'+suffix+('return head;' if escape else DRAIN)+'}'
    return '#include <stdlib.h>\n'+RECORD+builder+extras+entry


def fixtures():
    rows=[]
    def add(name,code,count,bias,closed,ascending=False,escape=False,upper=999999):
        base='__list_scan*(__list_scan-1)//2' if ascending else '__list_scan*(2*__list_length-__list_scan-1)//2'
        rows.append(dict(name=name,source=code,count=count,bias=bias,ascending=ascending,escape=escape,upper=upper,summary={'__list_scan':{'total':base+'+__list_scan*('+closed+')'}}))
    add('converted_payload',source(),lambda n:n+1,lambda n,d:(d+260)%256,'(delta+260)%256')
    add('narrow_count',source('(unsigned char)(n+260)','delta+1','int'),lambda n:(n+260)%256,lambda n,d:d+1,'delta+1',upper=100)
    add('guarded_count',source('n ? 12/n : 3','0','int'),lambda n:int(12/n) if n else 3,lambda n,d:0,'0')
    add('long_count_conversion',source('4294967297LL','delta+1','int'),lambda n:1,lambda n,d:d+1,'delta+1')
    add('boolean_payload',source(bias='delta-2',kind='_Bool'),lambda n:n+1,lambda n,d:int(d!=2),'0 if delta==2 else 1')
    add('signed_payload',source(bias='delta+255',kind='signed char'),lambda n:n+1,lambda n,d:d-1,'delta-1')
    add('correlated_actuals',source('n+1','n+2','int','i/(bias-count)'),lambda n:n+1,lambda n,d:0,'0')
    add('map_reverse',source(pipeline=True),lambda n:n+1,lambda n,d:(d+260)%256+d,'(delta+260)%256+delta',ascending=True)
    add('escaping_ownership',source(escape=True),lambda n:n+1,lambda n,d:(d+260)%256,'(delta+260)%256',escape=True)
    add('internal_map',source(internal=True),lambda n:n+1,lambda n,d:(d+260)%256+1,'(delta+260)%256+1')
    return rows


def run_native(path,code,harness,name,opt):
    prefix=PREFIX.replace('1000000','1000001')
    prefix=prefix.replace('static void fixture_free(void *p){','static void fixture_check_payload(void*,int);\nstatic void fixture_free(void *p){')
    prefix=prefix.replace('fixture_freed++;fixture_live--;free(p);','fixture_check_payload(p,index);fixture_freed++;fixture_live--;free(p);')
    target=path/(name+'.c');exe=path/(name+opt)
    target.write_text(prefix+code+'\n#undef calloc\n#undef free\n'+harness)
    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(target),'-o',str(exe)],check=True,capture_output=True,timeout=60)
    return subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];groups=0;models=0;negative=[]
    with tempfile.TemporaryDirectory(prefix='list-builders-native-') as directory:
        path=Path(directory)
        for case in fixtures():
            request={'source':case['source'],'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,case['upper']],'delta':[-3,3]},'loop_summaries':case['summary']}}
            proof=analyze_request(request)
            if proof['status']!='PROVED_DEFINED_CLANG_LIST_CALLS':raise AssertionError((case['name'],proof))
            normalized=proof['normalization']['source']
            engine=ListHeapCallsProgram(normalized,function='entry',parameter_bounds=request['proof']['parameter_bounds'],loop_summaries=case['summary'])
            forms=[('original',case['source']),('normalized',normalized),('composed',engine.composed_source)]
            statements=[];expected=[];scenarios=[]
            for delta in (-3,0,2):
                for n in sorted({-3,0,1,2,6,20,100,case['upper']}):
                    size=max(0,case['count'](n))
                    for m in sorted({0,min(1,size),size//2,size}|({17} if size>17 else set())):
                        bias=case['bias'](n,delta);value=m*(m-1)//2+m*bias
                        result=engine.report({'n':n,'delta':delta},m)
                        if result['status']!='PROVED_DEFINED_TYPED_C_LIST_CALLS':raise AssertionError(result)
                        if result['evaluation']['all_success_case']!=(m==size):raise AssertionError((case['name'],n,m,result))
                        if not case['escape'] and result['evaluation']['value']!=value:raise AssertionError((case['name'],n,m,result,value))
                        models+=1
                        fail=m+1 if m<size else 0;attempts=m+1 if m<size else size
                        if case['escape']:
                            call='struct Node*p=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;long long value=0;int seen=0;while(p){if(seen>='+str(m)+'||p!=fixture_nodes['+str(m)+'-1-seen]){return 10;}struct Node*next=p->next;void*want=(seen+1<'+str(m)+')?fixture_nodes['+str(m)+'-2-seen]:NULL;if((void*)next!=want){return 11;}value+=p->value;fixture_free(p);p=next;seen++;}if(seen!='+str(m)+'){return 12;}'
                        else:
                            call='long long value=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;'
                        expected.append([value,m,m if case['escape'] else 0,attempts,m])
                        scenarios.append({'n':n,'delta':delta,'converted_count':case['count'](n),'successful_allocations':m,'expected_payload_offset':bias,'expected':value})
                        statements.append('{fixture_bias='+str(bias)+';fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(case['ascending']))+';'+call+'if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            harness='static long long fixture_bias;static void fixture_check_payload(void*p,int index){if((long long)((struct Node*)p)->value!=index+fixture_bias){abort();}}int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in forms:
                    native=run_native(path,code,harness,case['name']+tag,opt)
                    if native.returncode or native.stderr:raise AssertionError((case['name'],tag,opt,native.returncode,native.stderr))
                    outputs[tag]=[[int(x) for x in line.split()] for line in native.stdout.splitlines()]
                if any(x!=expected for x in outputs.values()):raise AssertionError((case['name'],opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'independent_expected':expected});groups+=len(expected)
                print(case['name'],opt,len(expected),'count/payload/identity/order/value groups passed',flush=True)
            rows.append({'case':case['name'],'request':request,'source_sha256':hashlib.sha256(case['source'].encode()).hexdigest(),'normalization':proof['normalization'],'certificate':proof['certificate'],'scenarios':scenarios,'runs':runs,'every_payload_and_free_identity_checked':True,'escape_footprint_checked':case['escape']})
        controls=[('empty_unused_division','0','1/delta',0,0,0,'division by zero'),('first_failure_unused_overflow','n','delta+1',1,2147483647,1,'signed integer overflow'),('empty_unused_shift','0','1<<delta',0,32,0,'shift exponent'),('count_overflow','delta+1','0',0,2147483647,0,'signed integer overflow')]
        for name,count,bias,n,delta,fail,diagnostic in controls:
            code=source(count,bias,'int','i')
            request={'source':code,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[n,n],'delta':[delta,delta]}}}
            proof=analyze_request(request)
            if proof['status']!='UNKNOWN' or proof.get('reason')!='List builder call argument source proof failed':raise AssertionError((name,proof))
            harness='static void fixture_check_payload(void*p,int index){(void)p;(void)index;}int main(void){fixture_fail='+str(fail)+';printf("%lld\\n",entry('+str(n)+','+str(delta)+'));return 0;}'
            for opt in ('-O0','-O2'):
                for tag,text in [('original',code),('normalized',proof['normalization']['source'])]:
                    native=run_native(path,text,harness,name+tag,opt)
                    if native.returncode==0 or diagnostic not in native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                    negative.append({'case':name,'source_form':tag,'optimization':opt,'exit_code':native.returncode,'diagnostic':native.stderr,'source_proof':proof['source_proof']})
    result={'passed':True,'case_count':len(rows),'correspondence_groups':groups,'native_output_matches':groups*3,'model_matches':models,'expected_ubsan_failures':len(negative),'cases':rows,'negative_controls':negative,'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls')}),flush=True)


if __name__=='__main__':main()
