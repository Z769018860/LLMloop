"""Original/Clang-normalized/expanded/model C call-sequencing oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.typed_cfg_calls import TypedCFGCalls


ROOT=Path(__file__).resolve().parents[1]


def fixtures():
    mixed=(ROOT/'examples/clang_sequenced_calls.c').read_text()
    do='int test(int *p,int i,int n){p[0]+=1;return i<n;}int entry(int n){int a[1]={0};int i=0;int total=0;do{i++;if(i==1){continue;}total+=i;}while(test(a,i,n));return total+10*a[0];}'
    short='int divide(int n){return 12/n;}int entry(int n){return n && divide(n);}'
    conditional='unsigned int high(void){return 4294967295U;}int low(void){return -1;}int entry(int n){return (n ? high() : low()) > 0;}'
    narrow='unsigned char narrow(int n){return n;}int plus(int n){return n+1;}int entry(int n){return plus(narrow(n));}'
    heap='#include <stdlib.h>\nint read(int *p){return p[0]+5;}int release(int *p){free(p);return 7;}int entry(int n){int *p=calloc(1,sizeof(int));int z=p && read(p);if(!p){return -1;}int x=n ? release(p) : 0;if(n){return x+z;}int r=read(p);free(p);return r+z;}'
    comma='int bump(int *p,int x){p[0]+=x;return p[0];}int entry(int n){int a[1]={0};n && bump(a,2);int x=(bump(a,3),bump(a,5));return a[0]+x;}'
    return [
        ('mixed_for',mixed,[-2,8],list(range(-2,9)),False,lambda n,ok:13 if n==0 else 17+3*n if n<0 else n*(n-1)//2-(1 if n>=2 else 0)+5*n+17),
        ('do_continue',do,[0,8],list(range(9)),False,lambda n,ok:max(1,n)*(max(1,n)+1)//2-1+10*max(1,n)),
        ('short_division',short,[0,12],list(range(13)),False,lambda n,ok:int(n!=0)),
        ('conditional_common_type',conditional,[0,1],[0,1],False,lambda n,ok:1),
        ('nested_narrowing',narrow,[0,512],[0,1,2,127,128,254,255,256,257,510,511,512],False,lambda n,ok:n%256+1),
        ('conditional_heap_free',heap,[-2,8],list(range(-2,9)),True,lambda n,ok:-1 if not ok else 6 if n==0 else 8),
        ('discarded_and_comma',comma,[-2,8],list(range(-2,9)),False,lambda n,ok:16 if n==0 else 20),
    ]


PREFIX='''#include <stdlib.h>
#include <stdio.h>
static int fixture_fail,fixture_attempts,fixture_live;
static void *fixture_calloc(size_t n,size_t s){
    fixture_attempts++;
    if(fixture_fail){return NULL;}
    void *p=calloc(n,s);
    if(p){fixture_live++;}
    return p;
}
static void fixture_free(void *p){if(p){fixture_live--;free(p);}}
#define calloc fixture_calloc
#define free fixture_free
'''


def compile_run(path,code,harness,name,opt):
    source=path/(name+'.c');exe=path/(name+opt)
    source.write_text(PREFIX+code+'\n#undef calloc\n#undef free\n'+harness)
    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(exe)],capture_output=True,check=True,timeout=60)
    return subprocess.run([str(exe)],capture_output=True,text=True,timeout=60)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];negative=[];correspondences=0
    with tempfile.TemporaryDirectory(prefix='sequenced-calls-native-') as temp:
        path=Path(temp)
        for name,source,bounds,inputs,allocates,expected_value in fixtures():
            request={'source':source,'function':'entry','frontend':'clang_proof',
                'proof':{'backend':'calls','parameter_bounds':{'n':bounds},'max_steps':512,'max_paths':64}}
            report=analyze_request(request)
            if report['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':raise AssertionError((name,report))
            normalized=report['normalization']['source'];expanded=report['call_model']['expanded_source']
            model=TypedCFGCalls(normalized,function='entry',parameter_bounds={'n':bounds},max_steps=512,max_paths=64)
            samples=[];expected=[];statements=[]
            for n in inputs:
                for ok in ((False,True) if allocates else (True,)):
                    value=expected_value(n,ok)
                    actual=model.evaluate_return({'n':n},ok).as_long()
                    if actual!=value:raise AssertionError((name,n,ok,actual,value))
                    samples.append({'n':n,'all_allocations_succeed':ok})
                    expected.append([value,int(allocates),0])
                    statements.append('{fixture_fail='+str(int(not ok))+';fixture_attempts=0;fixture_live=0;int value=entry('+str(n)+');printf("%d %d %d\\n",value,fixture_attempts,fixture_live);if(fixture_live){return 12;}}')
            harness='int main(void){'+''.join(statements)+'return 0;}'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in [('original',source),('normalized',normalized),('expanded',expanded)]:
                    run=compile_run(path,code,harness,name+tag,opt)
                    if run.returncode or run.stderr:raise AssertionError((name,tag,opt,run.returncode,run.stderr))
                    outputs[tag]=[[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                if any(output!=expected for output in outputs.values()):raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'model':expected})
                correspondences+=len(samples)
                print(f'{name} {opt}: {len(samples)} original/normalized/expanded/model checks passed',flush=True)
            rows.append({'case':name,'request':request,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'normalization':report['normalization'],'call_model':report['call_model'],'certificate':report['certificate'],
                'samples':samples,'output_columns':['return_value','allocation_attempts','live_allocations_after_return'],'runs':runs})
        faults=[
            ('active_overflow','int bad(int n){return n+2147483647;}int entry(int n){return n && bad(n);}',1,'signed integer overflow'),
            ('active_division','int bad(int n){return 12/n;}int entry(int n){return n || bad(n);}',0,'division by zero'),
        ]
        for name,source,n,diagnostic in faults:
            request={'source':source,'function':'entry','frontend':'clang_proof',
                'proof':{'backend':'calls','parameter_bounds':{'n':[n,n]}}}
            report=analyze_request(request)
            if report['status']!='UNKNOWN' or report.get('c_overflow_verified',False):raise AssertionError(report)
            runs=[]
            for opt in ('-O0','-O2'):
                for tag,code in [('original',source),('normalized',report['normalization']['source']),('expanded',report['call_model']['expanded_source'])]:
                    run=compile_run(path,code,'int main(void){printf("%d\\n",entry('+str(n)+'));return 0;}',name+tag,opt)
                    if run.returncode==0 or diagnostic not in run.stderr:raise AssertionError((name,tag,opt,run))
                    runs.append({'optimization':opt,'source_kind':tag,'exit_code':run.returncode,'diagnostic':run.stderr})
            negative.append({'case':name,'request':request,'proof_status':report['status'],'failed_obligation':report.get('failed_obligation'),'runs':runs})
            print(f'{name}: UNKNOWN plus 6 expected UBSan failures confirmed',flush=True)
    result={'passed':True,'correspondences':correspondences,'negative_native_runs':sum(len(row['runs']) for row in negative),
        'cases':rows,'negative_controls':negative,'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(exist_ok=True,parents=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{correspondences} correspondences and {result["negative_native_runs"]} expected unsafe runs passed')


if __name__=='__main__':main()
