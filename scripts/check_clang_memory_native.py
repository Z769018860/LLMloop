"""Original C / normalized C / proved models, with forced allocator failures.

ASan/UBSan and live-object accounting supplement abstract proofs. LeakSanitizer
is disabled because this runtime denies its /proc task scan; live counts are
checked explicitly for these owned-allocation examples. Finite samples
are not proofs of arbitrary C or physical allocation capacity.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import sys
from llmloop.api import analyze_request
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.typed_memory import TypedCMemory
from llmloop.typed_nested import TypedCNested
from build_clang_memory_cases import ALLOC,ARRAY,CALL,TABLE,ESCAPE,HEAP,STRUCT,RECURSE,MEMORY_NESTED,LIST,BRANCHES,CONTROL,TRANSIENT

PREAMBLE='''#include <stdio.h>
#include <stdlib.h>
static long remaining=-1;static long live_objects=0;static long allocated=0;
static void *scenario_malloc(size_t bytes){if(remaining==0){return NULL;}if(remaining>0){remaining--;}void *p=malloc(bytes);if(p){live_objects++;allocated++;}return p;}
static void scenario_free(void *p){if(p){live_objects--;}free(p);}
#define malloc scenario_malloc
#define free scenario_free
'''


def compile_and_run(path,tag,source,scenarios,opt):
    code=path/(tag+opt+'.c');exe=path/(tag+opt)
    # Sequence the entry call before reading accounting globals: C argument
    # evaluation order is unspecified, so the result needs an explicit temporary.
    harness='\n#undef malloc\n#undef free\nint main(void){'
    for inputs,budget in scenarios:
        args=','.join(str(v) for v in inputs.values())
        harness+=f'{{remaining={budget};allocated=0;live_objects=0;long long value=(long long)entry({args});printf("%lld %ld %ld\\n",value,allocated,live_objects);}}'
    harness+='return 0;}'
    code.write_text(PREAMBLE+source+harness)
    subprocess.run(['cc','-std=c11',opt,'-Werror=implicit-function-declaration','-Werror=incompatible-pointer-types','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(code),'-o',str(exe)],check=True,capture_output=True)
    outcome=subprocess.run([str(exe)],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
    assert outcome.returncode==0,(tag,opt,outcome.stderr)
    return [tuple(map(int,row.split())) for row in outcome.stdout.splitlines()]


def main():
    specs=[('array',ARRAY,'memory',{'n':[0,2]},[{'n':n} for n in range(3)],{}),
           ('call',CALL,'calls',{'n':[0,3]},[{'n':n} for n in range(4)],{}),
           ('table',TABLE,'calls',{'n':[0,3]},[{'n':n} for n in range(4)],{}),
           ('escape',ESCAPE,'calls',{'n':[0,3]},[{'n':n} for n in range(4)],{}),
           ('dynamic',HEAP,'memory',{'n':[1,4]},[{'n':n} for n in range(1,5)],{'max_steps':256}),
           ('record',STRUCT,'memory',{'n':[0,3]},[{'n':n} for n in range(4)],{}),
           ('recursive',RECURSE,'calls',{'n':[0,3]},[{'n':n} for n in range(4)],{'max_call_depth':5,'allow_recursion':True}),
           ('memory_nested',MEMORY_NESTED,'memory_nested',{'n':[0,1000000]},[{'n':n} for n in [0,1,7,1000000]],{})]
    for name,body in BRANCHES:
        specs.append(('branch_'+name,'long long entry(int n,int t){long long x=0;for(int i=0;i<n;i++){'+body+'}return x;}','nested',{'n':[0,1000],'t':[0,100]},[{'n':n,'t':t} for n,t in [(0,0),(1,0),(7,3),(20,0),(20,100),(1000,100)]],{}))
    for name,source in [('control',CONTROL),('transient',TRANSIENT)]:specs.append((name,source,'nested',{'n':[0,1000000]},[{'n':n} for n in [0,1,2,3,7,1000000]],{}))
    selected=sys.argv[1] if len(sys.argv)>1 else None
    if selected is None:
        for name in [row[0] for row in specs]+['owned_list','faults','declarator_controls']:
            subprocess.run([sys.executable,__file__,name],check=True)
        return
    specs=[row for row in specs if row[0]==selected]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,source,backend,bounds,points,extra in specs:
            r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','proof':{'backend':backend,'parameter_bounds':bounds,**extra}})
            assert r['status'].startswith('PROVED_DEFINED_CLANG'),r
            normalized=r['normalization']['source']
            if backend in ('memory','calls'):
                cls=TypedCFGCalls if backend=='calls' else TypedCFGHeap
                engine=cls(normalized,function='entry',parameter_bounds=bounds,**extra)
                scenarios=[(p,budget) for p in points for budget in [-1,0]]
                expected=[engine.evaluate_return(p,allocation_success=budget!=0).as_long() for p,budget in scenarios]
            else:
                cls=TypedCMemory if backend=='memory_nested' else TypedCNested
                engine=cls(normalized,'auto',function='entry',parameter_bounds=bounds)
                scenarios=[(p,-1) for p in points];expected=[engine.report(p)['evaluation']['value'] for p in points]
            for opt in ['-O0','-O2']:
                original=compile_and_run(path,name+'original',source,scenarios,opt)
                translated=compile_and_run(path,name+'normalized',normalized,scenarios,opt)
                assert original==translated,(name,opt,original,translated)
                assert [v[0] for v in original]==expected,(name,opt,original,expected)
                assert all(v[2]==0 for v in original),(name,'owned object leak',original)
                print(f'{name} original / normalized / proved model, allocator outcomes, ASan+UBSan {opt}: {len(expected)}/{len(expected)} matched',flush=True)
        if selected=='owned_list':
            # A dynamically escaping list is summarized independently of its length.
            r=analyze_request({'source':LIST,'frontend':'clang_proof','function':'entry','proof':{'backend':'heap_summary','parameter_bounds':{'n':[-3,1000000]}}})
            assert r['status']=='PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY',r
            ghost=r['heap_shape_certificate']['successful_prefix_length']
            fold=TypedCNested(r['scalar_fold_source'],'auto',parameter_bounds={'n':[-3,1000000],ghost:[0,1000000]})
            scenarios=[({'n':n},budget) for n in [-3,0,1,2,7,64,1000000] for budget in [0,1,3,-1]]
            expected=[]
            for p,budget in scenarios:
                count=max(0,p['n']);successes=count if budget==-1 else min(count,budget)
                expected.append((fold.report({**p,ghost:successes})['evaluation']['value'],successes,0))
            for opt in ['-O0','-O2']:
                original=compile_and_run(path,'list_original',LIST,scenarios,opt)
                translated=compile_and_run(path,'list_normalized',r['normalization']['source'],scenarios,opt)
                assert original==translated==expected,(opt,original,translated,expected)
                print(f'escaping owned list with partial allocation failure / reverse fold / all objects freed {opt}: {len(expected)}/{len(expected)} matched',flush=True)
        if selected=='declarator_controls':
            controls=[('vla_parameter','int helper(int n,int a[n++]){return n;}int entry(int n){int a[8]={0};return helper(n,a);}',3),
                      ('vla_typedef','int entry(int n){typedef int V[n++];return n;}',3),
                      ('aligned_record','typedef int I __attribute__((aligned(16)));struct R{char c;I x;};int entry(int n){return sizeof(struct R);}',32)]
            for opt in ['-O0','-O2']:
                for name,source,expected in controls:
                    r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','proof':{'backend':'calls','parameter_bounds':{'n':[1,2]}}})
                    assert r['status']=='UNKNOWN',r
                    assert compile_and_run(path,name,source,[({'n':2},-1)],opt)==[(expected,0,0)]
                print(f'unsupported original declarator behavior retained as proof rejection {opt}: {len(controls)}/{len(controls)} matched',flush=True)
        if selected=='faults':
            faults=[('heap_uaf',ALLOC+'int entry(int n){int *p=malloc(sizeof(int));if(!p){return 0;}p[0]=n;free(p);return p[0];}','heap-use-after-free'),
                    ('stack_oob','int entry(int n){int a[2]={0};return a[n+1];}','out of bounds')]
            for name,source,diagnostic in faults:
                r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','proof':{'backend':'memory','parameter_bounds':{'n':[2,2]}}});assert r['status']=='UNKNOWN',r
                code=path/(name+'.c');exe=path/name;code.write_text('#include <stdlib.h>\n'+source+'\nint main(void){return entry(2);}')
                subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(code),'-o',str(exe)],check=True,capture_output=True)
                outcome=subprocess.run([str(exe)],capture_output=True,text=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
                assert outcome.returncode!=0 and diagnostic in outcome.stderr,(name,outcome.stderr)
            print(f'proof rejection / intentional ASan+UBSan fault correspondences: {len(faults)}/{len(faults)} matched',flush=True)

if __name__=='__main__':main()
