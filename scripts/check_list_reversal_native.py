"""Native allocation-identity, traversal/free-order and typed-value oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap import ListHeapProgram
from llmloop.list_heap_calls import ListHeapCallsProgram


ROOT=Path(__file__).resolve().parents[1]
REVERSE='struct Node *prev=0;while(head){struct Node *next=head->next;head->next=prev;prev=head;head=next;}head=prev;'
ASCENDING={'__list_scan':{'total':'0 if __list_scan==0 else (__list_scan-2)*2147483647'}}
DESCENDING={'__list_scan':{'total':'0 if __list_scan==0 else (__list_scan*2147483647 if __list_scan<__list_length else (__list_length-2)*2147483647)'}}


def fixtures():
    flat=(ROOT/'examples/clang_list_reverse.c').read_text()
    calls=(ROOT/'examples/clang_list_reverse_calls.c').read_text()
    escape=(ROOT/'examples/clang_list_reverse_escape.c').read_text()
    samples=[]
    for n in (-3,0,1,2,8,100,1000,1000000):
        size=max(0,n)
        for count in sorted({0,min(1,size),size//2,size}|({17} if size>17 else set())):samples.append((n,count))
    internal=calls.replace('if (!p) { return head; }','if (!p) { break; }',1)
    internal=internal.replace('    return head;\n}',REVERSE+'\n    return head;\n}',1)
    ordinary=[
        ('flat_fold',flat,'list',False,1,False),
        ('helper_fold',calls,'list_calls',False,1,False),
        ('escape',escape,'list_calls',True,1,False),
        ('double_escape',escape.replace('head = reverse(head);','head = reverse(head);head = reverse(head);'),'list_calls',True,2,False),
        ('triple_fold',calls.replace('head = reverse(head);','head = reverse(head);head = reverse(head);head = reverse(head);'),'list_calls',False,3,False),
        ('builder_and_helper',internal,'list_calls',False,2,False),
        ('narrow_consumer',calls.replace('static long long consume(', 'static unsigned char consume('),'list_calls',False,1,True),
    ]
    cases=[{'case':name,'source':source,'backend':backend,'escapes':escapes,'stages':stages,
            'bounds':[-3,1000000],'samples':samples,'narrow':narrow,'boundary':False,'summaries':'auto'}
           for name,source,backend,escapes,stages,narrow in ordinary]
    boundary=flat.replace('p->value = i;', 'p->value = (i==0 ? -2147483647 : 2147483647);').replace('long long entry(', 'int entry(').replace('long long total = 0;', 'int total = 0;')
    cases.append({'case':'order_sensitive_safe','source':boundary,'backend':'list','escapes':False,
                  'stages':1,'bounds':[0,3],'samples':[(3,m) for m in range(4)],'narrow':False,'boundary':True,'summaries':ASCENDING})
    return cases,boundary


PREFIX='''#include <stdlib.h>
#include <stdio.h>
static int fixture_attempts,fixture_count,fixture_live,fixture_fail;
static int fixture_freed,fixture_ascending;
static void *fixture_nodes[1000000];
static void *fixture_calloc(size_t n,size_t s){
    fixture_attempts++;
    if(fixture_attempts==fixture_fail){return NULL;}
    void *p=calloc(n,s);
    if(p){if(fixture_count>=1000000){abort();}fixture_nodes[fixture_count++]=p;fixture_live++;}
    return p;
}
static void fixture_free(void *p){
    if(p){
        int index=fixture_ascending?fixture_freed:fixture_count-1-fixture_freed;
        if(index<0||index>=fixture_count||p!=fixture_nodes[index]){abort();}
        fixture_freed++;fixture_live--;free(p);
    }
}
#define calloc fixture_calloc
#define free fixture_free
'''


def run_native(path,code,harness,name,opt):
    source=path/(name+'.c');exe=path/(name+opt)
    source.write_text(PREFIX+code+'\n#undef calloc\n#undef free\n'+harness)
    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(exe)],check=True,capture_output=True,timeout=60)
    return subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    cases,boundary=fixtures();rows=[];comparisons=0
    with tempfile.TemporaryDirectory(prefix='list-reversal-native-') as directory:
        path=Path(directory)
        for case in cases:
            name=case['case'];source=case['source'];ascending=case['stages']%2==1
            request={'source':source,'function':'entry','frontend':'clang_proof','proof':{
                'backend':case['backend'],'parameter_bounds':{'n':case['bounds']},'loop_summaries':case['summaries']}}
            report=analyze_request(request)
            status='PROVED_DEFINED_CLANG_LIST_HEAP' if case['backend']=='list' else 'PROVED_DEFINED_CLANG_LIST_CALLS'
            if report['status']!=status:raise AssertionError((name,report))
            if report['heap_summary']['orientation']!=('ascending' if ascending else 'descending'):raise AssertionError(report)
            normalized=report['normalization']['source']
            model_class=ListHeapProgram if case['backend']=='list' else ListHeapCallsProgram
            model=model_class(normalized,function='entry',parameter_bounds={'n':case['bounds']},loop_summaries=case['summaries'])
            forms=[('original',source),('normalized',normalized)]
            if case['backend']=='list_calls':forms.append(('composed',report['certificate']['composition']['composed_source']))
            statements=[];expected=[]
            for n,count in case['samples']:
                result=model.report({'n':n},count)
                size=max(0,n);fail=count+1 if count<size else 0;attempts=count+1 if count<size else size
                value=(0 if count==0 else (count-2)*2147483647) if case['boundary'] else count*(count-1)//2
                if case['narrow']:value%=256
                live=count if case['escapes'] else 0
                if case['escapes']:
                    call='struct Node *p=entry('+str(n)+');int live_after=fixture_live;long long value=0;int seen=0;while(p){int index=fixture_ascending?seen:'+str(count)+'-1-seen;if(seen>='+str(count)+'||p!=fixture_nodes[index]||p->value!=index){return 10;}struct Node *next=p->next;void *want_next=(seen+1<'+str(count)+')?fixture_nodes[fixture_ascending?index+1:index-1]:NULL;if((void *)next!=want_next){return 11;}value+=p->value;fixture_free(p);p=next;seen++;}if(seen!='+str(count)+'){return 12;}'
                    if result['evaluation']['live_nodes_after_return']!=count:raise AssertionError(result)
                else:
                    call='long long value=entry('+str(n)+');int live_after=fixture_live;'
                    if result['evaluation']['value']!=value:raise AssertionError((name,result,value))
                expected.append([value,count,live,attempts,count])
                statements.append('{fixture_attempts=0;fixture_count=0;fixture_live=0;fixture_freed=0;fixture_fail='+str(fail)+';fixture_ascending='+str(int(ascending))+';'+call+'if(fixture_live!=0){return 13;}printf("%lld %d %d %d %d\\n",value,fixture_count,live_after,fixture_attempts,fixture_freed);}')
            harness='int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in forms:
                    run=run_native(path,code,harness,name+tag,opt)
                    if run.returncode or run.stderr:raise AssertionError((name,tag,opt,run.returncode,run.stderr))
                    outputs[tag]=[[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                if any(output!=expected for output in outputs.values()):raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'model':expected});comparisons+=len(expected)
                print(f'{name} {opt}: {len(expected)} identity/order/value correspondences passed',flush=True)
            rows.append({'case':name,'request':request,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'normalization':report['normalization'],'certificate':report['certificate'],
                'samples':[{'n':n,'successful_allocations':m} for n,m in case['samples']],
                'source_forms':[tag for tag,_ in forms],'allocation_identity_and_free_order_checked':True,
                'output_columns':['value_or_payload_sum','successful_allocations','live_nodes_after_entry','allocation_attempts','frees_after_harness'],
                'runs':runs})
        # Removing reversal leaves the same mathematical sum but overflows in
        # its descending prefix. This control uses the actual source order.
        start=boundary.index('    struct Node *prev = 0;')
        stop=boundary.index('    head = prev;',start)+len('    head = prev;')
        unsafe=boundary[:start]+boundary[stop:]
        request={'source':unsafe,'function':'entry','frontend':'clang_proof','proof':{
            'backend':'list','parameter_bounds':{'n':[0,3]},'loop_summaries':DESCENDING}}
        rejected=analyze_request(request)
        if rejected['status']!='UNKNOWN' or rejected.get('c_overflow_verified',False):raise AssertionError(rejected)
        negative=[]
        harness='int main(void){fixture_ascending=0;fixture_fail=0;printf("%lld\\n",(long long)entry(3));return 0;}'
        for opt in ('-O0','-O2'):
            for tag,code in [('original',unsafe),('normalized',rejected['normalization']['source'])]:
                run=run_native(path,code,harness,'unsafe'+tag,opt)
                if run.returncode==0 or 'signed integer overflow' not in run.stderr:raise AssertionError(run)
                negative.append({'source_form':tag,'optimization':opt,'exit_code':run.returncode,'diagnostic':run.stderr})
        print('Unreversed order control: UNKNOWN and 4 expected UBSan failures confirmed',flush=True)
    result={'passed':True,'correspondences':comparisons,'cases':rows,
        'order_sensitive_negative':{'request':request,'proof_status':rejected['status'],'runs':negative},
        'negative_native_runs':len(negative),'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{comparisons} correspondences and {len(negative)} expected unsafe runs passed')


if __name__=='__main__':main()
