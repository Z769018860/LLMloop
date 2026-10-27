"""Native/source/model checks for unroll-free prepend-list certificates."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap import ListHeapProgram


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    samples = []
    for n in (-3,0,1,2,8,100,1000,1000000):
        size = max(0,n)
        for count in sorted({0,min(1,size),size//2,size} | ({17} if size>17 else set())):
            samples.append((n,count))
    # Independent malloc/free instrumentation counts actual liveness and forces
    # each selected first-failure position. It does not assume allocations succeed.
    prefix = '''#include <stdlib.h>
#include <stdio.h>
static int fixture_attempts,fixture_successes,fixture_live,fixture_fail;
static void *fixture_calloc(size_t n,size_t s){
    fixture_attempts++;
    if(fixture_attempts==fixture_fail){return NULL;}
    void *p=calloc(n,s);
    if(p){fixture_successes++;fixture_live++;}
    return p;
}
static void fixture_free(void *p){if(p){fixture_live--;free(p);}}
#define calloc fixture_calloc
#define free fixture_free
'''
    rows=[]
    with tempfile.TemporaryDirectory(prefix='list-heap-native-') as temp:
        path=Path(temp)
        for mode,file in [('fold_free','clang_list_sum.c'),('escape','clang_list_escape.c')]:
            source=(ROOT/'examples'/file).read_text()
            report=analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
                'proof':{'backend':'list','parameter_bounds':{'n':[-3,1000000]}}})
            if report['status']!='PROVED_DEFINED_CLANG_LIST_HEAP':
                raise AssertionError(report)
            normalized=report['normalization']['source']
            model=ListHeapProgram(normalized,parameter_bounds={'n':[-3,1000000]})
            expected=[];statements=[]
            for n,count in samples:
                r=model.report({'n':n},count)
                size=max(0,n)
                fail=count+1 if count<size else 0
                attempts=count+1 if count<size else size
                value=count*(count-1)//2
                if mode=='fold_free':
                    if r['evaluation']['value']!=value:
                        raise AssertionError(r)
                    call='long long value=entry('+str(n)+');int live_after=fixture_live;'
                    live=0
                else:
                    if r['evaluation']['live_nodes_after_return']!=count:
                        raise AssertionError(r)
                    # Check order and every payload, not just a commutative sum.
                    call='struct Node *p=entry('+str(n)+');int live_after=fixture_live;long long value=0;int seen=0,want='+str(count-1)+';while(p){if(seen>='+str(count)+'||p->value!=want){return 10;}struct Node *next=p->next;value+=p->value;fixture_free(p);p=next;seen++;want--;}if(seen!='+str(count)+'){return 11;}'
                    live=count
                expected.append([value,count,live,attempts])
                statements.append('{fixture_attempts=0;fixture_successes=0;fixture_live=0;fixture_fail='+str(fail)+';'+call+'if(fixture_live!=0){return 12;}printf("%lld %d %d %d\\n",value,fixture_successes,live_after,fixture_attempts);}')
            harness='\n#undef calloc\n#undef free\nint main(void){'+''.join(statements)+'return 0;}\n'
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={}
                for tag,code in [('original',source),('normalized',normalized)]:
                    c_file=path/(mode+tag+'.c');exe=path/(mode+tag+opt)
                    c_file.write_text(prefix+code+harness)
                    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(c_file),'-o',str(exe)],check=True,capture_output=True,timeout=60)
                    run=subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=60)
                    if run.stderr:raise AssertionError(run.stderr)
                    outputs[tag]=[[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                if outputs['original']!=outputs['normalized'] or outputs['original']!=expected:
                    raise AssertionError((mode,opt,outputs,expected))
                runs.append({'optimization':opt,'original':outputs['original'],'normalized':outputs['normalized'],'model':expected})
                print(f'{mode} {opt}: {len(samples)} source/normalized/model heap correspondences passed',flush=True)
            rows.append({'mode':mode,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'normalization':report['normalization'],'certificate':report['certificate'],
                'samples':[{'n':n,'successful_allocations':m} for n,m in samples],
                'output_columns':['value_or_payload_sum','successful_allocations','live_nodes_after_entry','allocation_attempts'],
                'runs':runs})
    result={'passed':True,'correspondences':len(samples)*len(rows)*2,'cases':rows,
        'compiler':subprocess.run(['cc','--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{result["correspondences"]} total heap correspondences passed')


if __name__=='__main__':
    main()
