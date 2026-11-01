"""Source/Clang/composed stateful-fold oracles, ownership checks and UB controls."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.integer_polynomial_audit import replay_integer_polynomial_audit
from llmloop.list_heap_calls import ListHeapCallsProgram
if __package__:
    from .check_list_builders_native import run_native
    from .check_list_payload_maps_native import FLIP, MAPPER
else:
    from check_list_builders_native import run_native
    from check_list_payload_maps_native import FLIP, MAPPER


RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*build(int n){struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){return head;}p->value=i;p->next=head;head=p;}return head;}'


def source(initial='long long total=seed;long long count=0;',updates='count+=1;total+=q->value+count;',returned='total+count',reverse=False,pipeline=False,narrow=False):
    consumer=('unsigned char' if narrow else 'long long')+' consume(struct Node*q,int seed){'+initial+'while(q){struct Node*tail=q->next;'+updates+'free(q);q=tail;}return '+returned+';}'
    extras=(MAPPER if pipeline else '')+(FLIP if reverse or pipeline else '')
    stages=('map(head,delta);' if pipeline else '')+('head=flip(head);' if reverse or pipeline else '')
    entry='long long entry(int n,int delta){struct Node*head=build('+('n+1' if pipeline else 'n')+');'+stages+'return '+('(signed char)' if narrow else '')+'consume(head,'+('delta+1' if pipeline else 'delta')+');}'
    return '#include <stdlib.h>\n'+RECORD+BUILD+consumer+extras+entry


def fixtures():
    rows=[];k='__list_scan';m='__list_length'
    def add(name,code,oracle,summary='auto',upper=1000000,ascending=False,pipeline=False):
        rows.append(dict(name=name,source=code,oracle=oracle,summary=summary,upper=upper,ascending=ascending,pipeline=pipeline))
    add('ordered_count',source(),lambda m,d:d+m*m+m)
    prefix=lambda m,d,ascending:d*(m+1)+m*(m-1)//2+m*(m-1)*(m+1)//(6 if ascending else 3)
    for reverse in (False,True):
        add('prefix_ascending' if reverse else 'prefix_descending',source('long long total=seed;long long history=0;','total+=q->value;history+=total;','total+history',reverse=reverse),lambda m,d,r=reverse:prefix(m,d,r),ascending=reverse)
    parity='delta-'+k+'//2 if '+k+'%2==0 else -delta+'+m+'-1-'+k+'//2'
    add('feedback_assignment',source('long long total=seed;','total=-total+q->value;','total'),lambda m,d:d-m//2 if m%2==0 else -d+m-1-m//2,{k:{'__list_call_total':parity}})
    b='((delta+260)%256)'
    add('narrow_ordered_store',source('unsigned char first=seed+260;long long total=first+1;','first+=1;total+=first;','total+first'),lambda m,d:2*((d+260)%256)+1+m*((d+260)%256)+m*(m+1)//2+m,{k:{'__list_call_first':'(delta+260+'+k+')%256','__list_call_total':b+'+1+'+k+'*'+b+'+'+k+'*('+k+'+1)//2'}},upper=20)
    add('boolean_feedback',source('_Bool flag=seed;','flag=!flag;','flag'),lambda m,d:(int(d!=0)+m)%2,{k:{'__list_call_flag':'((0 if delta==0 else 1)+'+k+')%2'}})
    add('sixteen_ordered_updates',source('long long total=seed;','total+=1;'*16,'total'),lambda m,d:d+16*m)
    add('lp64_long_state',source('long total=4294967297LL;','total+=1;','total'),lambda m,d:4294967297+m,{k:{'__list_call_total':'4294967297+'+k}})
    def narrow(m,d):
        value=(d+m*m+m)%256
        return value if value<128 else value-256
    add('callee_caller_return_conversion',source(narrow=True),narrow)
    add('builder_map_reverse_prefix',source('long long total=seed;long long history=0;','total+=q->value;history+=total;','total+history',pipeline=True),lambda m,d:prefix(m,d+1,True)+d*m+d*m*(m+1)//2,upper=999999,ascending=True,pipeline=True)
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];groups=0;models=0;negative=[];audits_replayed=0;unobserved=[]
    with tempfile.TemporaryDirectory(prefix='stateful-list-native-') as directory:
        path=Path(directory)
        for case in fixtures():
            request={'source':case['source'],'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[-3,case['upper']],'delta':[-3,3]},'loop_summaries':case['summary']}}
            proof=analyze_request(request)
            if proof['status']!='PROVED_DEFINED_CLANG_LIST_CALLS':raise AssertionError((case['name'],proof))
            normalized=proof['normalization']['source']
            engine=ListHeapCallsProgram(normalized,function='entry',parameter_bounds=request['proof']['parameter_bounds'],loop_summaries=case['summary'])
            audits=[o['certificate'] for o in proof['certificate']['fold_proof']['certificate']['obligations'] if o.get('certificate',{}).get('method')=='exact integer-valued polynomial successor audit']
            if not all(replay_integer_polynomial_audit(a) for a in audits):raise AssertionError('Arithmetic audit replay failed')
            audits_replayed+=len(audits)
            forms=[('original',case['source']),('normalized',normalized),('composed',engine.composed_source)]
            statements=[];expected=[];scenarios=[]
            for delta in (-3,0,2):
                for n in sorted(x for x in {-3,0,1,2,6,20,100,case['upper']} if x<=case['upper']):
                    size=max(0,n+int(case['pipeline']))
                    for length in sorted({0,min(1,size),size//2,size}|({17} if size>17 else set())):
                        value=case['oracle'](length,delta)
                        result=engine.report({'n':n,'delta':delta},length)
                        if result['status']!='PROVED_DEFINED_TYPED_C_LIST_CALLS' or result['evaluation']['value']!=value:raise AssertionError((case['name'],result,value))
                        models+=1
                        fail=length+1 if length<size else 0;attempts=length+1 if length<size else size
                        offset=delta if case['pipeline'] else 0
                        expected.append([value,length,0,attempts,length])
                        scenarios.append({'n':n,'delta':delta,'successful_allocations':length,'expected':value})
                        statements.append('{fixture_offset='+str(offset)+';fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(case['ascending']))+';long long value=entry('+str(n)+','+str(delta)+');int live_after=fixture_live;if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            harness='static long long fixture_offset;static void fixture_check_payload(void*p,int index){if((long long)((struct Node*)p)->value!=index+fixture_offset){abort();}}int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in forms:
                    native=run_native(path,code,harness,case['name']+tag,opt)
                    if native.returncode or native.stderr:raise AssertionError((case['name'],tag,opt,native.returncode,native.stderr))
                    outputs[tag]=[[int(x) for x in line.split()] for line in native.stdout.splitlines()]
                if any(v!=expected for v in outputs.values()):raise AssertionError((case['name'],opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'independent_expected':expected});groups+=len(expected)
                print(case['name'],opt,len(expected),'state/value/payload/free-order groups passed',flush=True)
            rows.append({'case':case['name'],'request':request,'source_sha256':hashlib.sha256(case['source'].encode()).hexdigest(),'normalization':proof['normalization'],'certificate':proof['certificate'],'scenarios':scenarios,'runs':runs,'every_payload_and_free_identity_checked':True,'arithmetic_audits_replayed':len(audits)})
        controls=[
            ('empty_initializer_division','long long total=1/seed;','total+=q->value;','total',0,0,0,'division by zero','auto'),
            ('unused_initializer_division','long long first=1/seed;long long total=0;','total+=q->value;','total',0,0,0,'division by zero','auto'),
            ('overwritten_state_overflow','int total=1;','total=2147483647;total+=1;total=0;','total',1,2,0,'signed integer overflow',{'__list_scan':{'__list_call_total':'1 if __list_scan==0 else 0'}}),
            ('observable_state_overflow','int total=1;int saved=0;','total=2147483647;total+=1;saved=total;total=0;','saved',1,2,0,'signed integer overflow',{'__list_scan':{'__list_call_total':'1 if __list_scan==0 else 0','__list_call_saved':'0'}}),
            ('masked_state_division','int total=1;','total=0*(total/seed);','total',1,0,0,'division by zero',{'__list_scan':{'__list_call_total':'1'}}),
            ('signed_minimum_negation','int total=seed;','total=-total;','total',1,-2147483648,0,'negation of',{'__list_scan':{'__list_call_total':'delta'}}),
            ('empty_return_division','long long total=0;','total+=q->value;','total/seed',1,0,1,'division by zero','auto'),
        ]
        for name,initial,updates,returned,n,delta,fail,diagnostic,summary in controls:
            code=source(initial,updates,returned)
            request={'source':code,'function':'entry','frontend':'clang_proof','proof':{'backend':'list_calls','parameter_bounds':{'n':[n,n],'delta':[delta,delta]},'loop_summaries':summary}}
            proof=analyze_request(request)
            if proof['status']!='UNKNOWN' or proof.get('reason')!='List fold source proof failed':raise AssertionError((name,proof))
            if 'defined' not in proof.get('source_proof',{}).get('failed_obligation',''):
                raise AssertionError((name,'Negative control must fail original operation definedness, not its candidate',proof['source_proof'].get('failed_obligation')))
            harness='static void fixture_check_payload(void*p,int index){(void)p;(void)index;}int main(void){fixture_fail='+str(fail)+';printf("%lld\\n",entry('+str(n)+','+str(delta)+'));return 0;}'
            for opt in ('-O0','-O2'):
                for tag,text in [('original',code),('normalized',proof['normalization']['source'])]:
                    native=run_native(path,text,harness,name+tag,opt)
                    observation={'case':name,'source_form':tag,'optimization':opt,'exit_code':native.returncode,'diagnostic':native.stderr,'source_proof':proof['source_proof']}
                    if native.returncode==0:
                        if name not in ('overwritten_state_overflow','masked_state_division','unused_initializer_division') or native.stderr:
                            raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                        observation['scope']='Sanitizer did not observe this discarded/masked undefined computation; source proof still rejects it'
                        unobserved.append(observation)
                    else:
                        if diagnostic not in native.stderr:raise AssertionError((name,tag,opt,native.returncode,native.stderr))
                        negative.append(observation)
    result={'passed':True,'case_count':len(rows),'correspondence_groups':groups,'native_output_matches':groups*3,'model_matches':models,'expected_ubsan_failures':len(negative),'unobserved_ubsan_controls':len(unobserved),'negative_source_controls':len(controls),'arithmetic_audits_replayed':audits_replayed,'cases':rows,'negative_controls':negative,'sanitizer_frontiers':unobserved,'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','sanitizer_frontiers')}),flush=True)


if __name__=='__main__':main()
