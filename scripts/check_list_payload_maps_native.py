"""Compare source/Clang/composed maps against independent typed payload oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap import ListHeapProgram
from llmloop.list_heap_calls import ListHeapCallsProgram
if __package__:
    from .check_list_reversal_native import PREFIX
else:
    from check_list_reversal_native import PREFIX


RECORD='struct Node{int value;struct Node*next;};'
BUILD='struct Node*head=0;for(int i=0;i<n;i++){struct Node*p=calloc(1,sizeof(struct Node));if(!p){break;}p->value=i;p->next=head;head=p;}'
MAP='struct Node*cursor=head;while(cursor){cursor->value=cursor->value+delta;cursor=cursor->next;}'
REVERSE='struct Node*prev=0;while(head){struct Node*next=head->next;head->next=prev;prev=head;head=next;}head=prev;'
FOLD='long long total=0;while(head){struct Node*tail=head->next;total+=head->value;free(head);head=tail;}return total;'
BUILDER='struct Node*build(int n){'+BUILD.replace('if(!p){break;}','if(!p){return head;}')+'return head;}'
MAPPER='void map(struct Node*q,int d){while(q){q->value=q->value+d;q=q->next;}}'
TWICE='void twice(struct Node*q){while(q){q->value=q->value*2;q=q->next;}}'
FLIP='struct Node*flip(struct Node*head){'+REVERSE.rsplit('head=prev;',1)[0]+'return prev;}'
CONSUMER='long long consume(struct Node*head){'+FOLD+'}'
NARROW_SUM='__list_scan*(2*__list_length-__list_scan-13)+256*(__list_scan if __list_length<=6 else (0 if __list_scan<=__list_length-6 else __list_scan-__list_length+6))'


def flat(stages=MAP,escape=False):
    return '#include <stdlib.h>\n'+RECORD+('struct Node*' if escape else 'long long ')+'entry(int n,int delta){'+BUILD+stages+('return head;' if escape else FOLD)+'}'


def helpers(stages,escape=False,twice=False):
    return '#include <stdlib.h>\n'+RECORD+BUILDER+MAPPER+FLIP+(TWICE if twice else '')+('' if escape else CONSUMER)+('struct Node*' if escape else 'long long ')+'entry(int n,int delta){struct Node*head=build(n);'+stages+('return head;' if escape else 'return consume(head);')+'}'


def samples(upper):
    answer=[]
    for n in sorted({-3,0,1,2,6,7,20,100,upper}):
        if n>upper:continue
        size=max(0,n)
        for count in sorted({0,min(1,size),size//2,size}|({17} if size>17 else set())):
            answer.append((n,count))
    return answer


def fixtures():
    cases=[]
    def add(name,source,backend,escape,ascending,oracle,c_formula,upper=1000000,summary='auto'):
        cases.append(dict(name=name,source=source,backend=backend,escape=escape,ascending=ascending,
                          oracle=oracle,c_formula=c_formula,upper=upper,summary=summary))
    add('inline',flat(),'list',False,False,lambda i:i+3,'index+3')
    add('map_reverse_consume',helpers('map(head,delta);head=flip(head);'),'list_calls',False,True,lambda i:i+3,'index+3')
    add('reverse_map_escape',helpers('head=flip(head);map(head,delta);',True),'list_calls',True,True,lambda i:i+3,'index+3')
    add('map_reverse_twice',helpers('map(head,delta);head=flip(head);twice(head);',twice=True),'list_calls',False,True,lambda i:2*(i+3),'2*(index+3)')
    internal='struct Node*build(int n){'+BUILD+MAP.replace('+delta','+1')+'return head;}'
    source=helpers('head=flip(head);map(head,delta);').replace(BUILDER,internal)
    add('builder_internal_map',source,'list_calls',False,True,lambda i:i+4,'index+4')
    stages=MAP.replace('+delta','+250')+MAP.replace('cursor','other').replace('+delta','*2')
    narrow=lambda i:(((i%256)+250)%256*2)%256
    add('narrow_escape',flat(stages,True).replace('int value','unsigned char value'),'list',True,False,narrow,'(((index%256)+250)%256*2)%256',100)
    add('narrow_fold',flat(stages).replace('int value','unsigned char value'),'list',False,False,narrow,'(((index%256)+250)%256*2)%256',100,{'__list_scan':{'total':NARROW_SUM}})
    constant=flat(stages).replace('int value','unsigned char value').replace('p->value=i;','p->value=300;')
    add('narrow_builder_assignment',constant,'list',False,False,lambda i:76,'76',100,{'__list_scan':{'total':'76*__list_scan'}})
    unsigned=flat(MAP.replace('+delta','+4294967295U'),True).replace('int value','unsigned int value')
    add('unsigned_wrap',unsigned,'list',True,False,lambda i:(i-1)%(2**32),'((unsigned int)index)-1U')
    return cases


def run_native(path,code,harness,name,opt):
    # Observe every payload before source free or harness free, as well as
    # allocation identity/order. A finite test harness is not the proof bound.
    prefix=PREFIX.replace('static void fixture_free(void *p){','static void fixture_check_payload(void*,int);\nstatic void fixture_free(void *p){')
    prefix=prefix.replace('fixture_freed++;fixture_live--;free(p);','fixture_check_payload(p,index);fixture_freed++;fixture_live--;free(p);')
    source=path/(name+'.c');exe=path/(name+opt)
    source.write_text(prefix+code+'\n#undef calloc\n#undef free\n'+harness)
    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(exe)],check=True,capture_output=True,timeout=60)
    return subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];comparisons=0;negative=[]
    with tempfile.TemporaryDirectory(prefix='list-map-native-') as directory:
        path=Path(directory)
        for case in fixtures():
            source=case['source'];name=case['name']
            request={'source':source,'function':'entry','frontend':'clang_proof','proof':{
                'backend':case['backend'],'parameter_bounds':{'n':[-3,case['upper']],'delta':[-3,3]},'loop_summaries':case['summary']}}
            report=analyze_request(request)
            expected_status='PROVED_DEFINED_CLANG_LIST_CALLS' if case['backend']=='list_calls' else 'PROVED_DEFINED_CLANG_LIST_HEAP'
            if report['status']!=expected_status:raise AssertionError((name,report))
            normalized=report['normalization']['source']
            cls=ListHeapCallsProgram if case['backend']=='list_calls' else ListHeapProgram
            model=cls(normalized,function='entry',parameter_bounds={'n':[-3,case['upper']],'delta':[-3,3]},loop_summaries=case['summary'])
            forms=[('original',source),('normalized',normalized)]
            if case['backend']=='list_calls':forms.append(('composed',model.composed_source))
            statements=[];expected=[]
            for n,count in samples(case['upper']):
                value=sum(case['oracle'](i) for i in range(count))
                result=model.report({'n':n,'delta':3},count)
                if not case['escape'] and result['evaluation']['value']!=value:raise AssertionError((name,result,value))
                size=max(0,n);fail=count+1 if count<size else 0;attempts=count+1 if count<size else size
                if case['escape']:
                    call='struct Node*p=entry('+str(n)+',3);int live_after=fixture_live;long long value=0;int seen=0;while(p){int index=fixture_ascending?seen:'+str(count)+'-1-seen;if(seen>='+str(count)+'||p!=fixture_nodes[index]){return 10;}struct Node*next=p->next;void*want=(seen+1<'+str(count)+')?fixture_nodes[fixture_ascending?index+1:index-1]:NULL;if((void*)next!=want){return 11;}value+=p->value;fixture_free(p);p=next;seen++;}if(seen!='+str(count)+'){return 12;}'
                else:
                    call='long long value=entry('+str(n)+',3);int live_after=fixture_live;'
                expected.append([value,count,count if case['escape'] else 0,attempts,count])
                statements.append('{fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(case['ascending']))+';'+call+'if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            check='static void fixture_check_payload(void*p,int index){if((long long)((struct Node*)p)->value!=(long long)('+case['c_formula']+')){abort();}}'
            harness=check+'int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in forms:
                    run=run_native(path,code,harness,name+tag,opt)
                    if run.returncode or run.stderr:raise AssertionError((name,tag,opt,run.returncode,run.stderr))
                    outputs[tag]=[[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                if any(values!=expected for values in outputs.values()):raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'independent_expected':expected});comparisons+=len(expected)
                print(name,opt,len(expected),'payload/identity/order/value correspondences passed',flush=True)
            rows.append({'case':name,'request':request,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                         'normalization':report['normalization'],'certificate':report['certificate'],
                         'samples':[{'n':n,'successful_allocations':m} for n,m in samples(case['upper'])],
                         'source_forms':[tag for tag,_ in forms],'every_node_payload_and_free_identity_checked':True,
                         'expected_payload_in_C':case['c_formula'],'runs':runs})
        for name,expression,diagnostic in [('overwritten_overflow','cursor->value+2147483647','signed integer overflow'),('division_zero','cursor->value/delta','division by zero')]:
            stage=MAP.replace('cursor->value+delta',expression)
            if name=='overwritten_overflow':stage+=MAP.replace('cursor','second').replace('second->value+delta','0')
            source=flat(stage,True)
            request={'source':source,'function':'entry','frontend':'clang_proof','proof':{'backend':'list','parameter_bounds':{'n':[0,2],'delta':[0,0]}}}
            report=analyze_request(request)
            if report['status']!='UNKNOWN' or report.get('c_overflow_verified'):raise AssertionError(report)
            harness='static void fixture_check_payload(void*p,int index){(void)p;(void)index;}int main(void){struct Node*p=entry(2,0);printf("%d\\n",p->value);return 0;}'
            for opt in ('-O0','-O2'):
                for tag,code in [('original',source),('normalized',report['normalization']['source'])]:
                    run=run_native(path,code,harness,name+tag,opt)
                    if run.returncode==0 or diagnostic not in run.stderr:raise AssertionError((name,tag,opt,run.returncode,run.stderr))
                    negative.append({'case':name,'request':request,'proof_status':report['status'],'source_form':tag,
                                     'optimization':opt,'exit_code':run.returncode,'diagnostic':run.stderr})
    result={'passed':True,'correspondences':comparisons,'negative_native_runs':len(negative),'cases':rows,'negative_controls':negative,
            'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(comparisons,'correspondences and',len(negative),'expected unsafe runs passed',flush=True)


if __name__=='__main__':main()
