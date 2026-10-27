"""Original/Clang-normalized/composed/model list-call correspondence checks."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.list_heap_calls import ListHeapCallsProgram


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
    shared = (ROOT/'examples/clang_list_calls.c').read_text()
    cases = [
        ('local_fold',(ROOT/'examples/clang_list_call_sum.c').read_text(),False,False,0),
        ('helper_fold',shared,False,False,0),
        ('forward',(ROOT/'examples/clang_list_call_escape.c').read_text(),True,False,0),
        ('narrow_return',shared.replace('static long long consume(', 'static unsigned char consume('),False,True,0),
        ('permuted_arguments',shared.replace('build(int count)', 'build(int bias,int count)').replace('p->value = i;', 'p->value = i+bias;').replace('entry(int n)', 'entry(int n,int delta)').replace('build(n)', 'build(delta,n)'),False,False,9),
    ]
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
    rows = []
    with tempfile.TemporaryDirectory(prefix='list-calls-native-') as temp:
        path = Path(temp)
        for name, source, escapes, narrow, bias in cases:
            bounds = {'n':[-3,1000000],**({'delta':[0,100]} if bias else {})}
            report = analyze_request({'source':source,'function':'entry','frontend':'clang_proof',
                'proof':{'backend':'list_calls','parameter_bounds':bounds}})
            if report['status'] != 'PROVED_DEFINED_CLANG_LIST_CALLS':
                raise AssertionError(report)
            normalized = report['normalization']['source']
            composed = report['certificate']['composition']['composed_source']
            model = ListHeapCallsProgram(normalized,function='entry',parameter_bounds=bounds)
            expected = []
            statements = []
            for n,count in samples:
                result = model.report({'n':n,**({'delta':bias} if bias else {})},count)
                size = max(0,n)
                fail = count+1 if count<size else 0
                attempts = count+1 if count<size else size
                value = count*(count-1)//2+bias*count
                if narrow:
                    value %= 256
                call_args = str(n)+(','+str(bias) if bias else '')
                if escapes:
                    if result['evaluation']['live_nodes_after_return'] != count:
                        raise AssertionError(result)
                    # Check every value and next-edge traversal, then release
                    # the transferred footprint from the independent caller.
                    call = 'struct Node *p=entry('+call_args+');int live_after=fixture_live;long long value=0;int seen=0,want='+str(count-1)+';while(p){if(seen>='+str(count)+'||p->value!=want){return 10;}struct Node *next=p->next;value+=p->value;fixture_free(p);p=next;seen++;want--;}if(seen!='+str(count)+'){return 11;}'
                    live = count
                else:
                    if result['evaluation']['value'] != value:
                        raise AssertionError(result)
                    call = 'long long value=entry('+call_args+');int live_after=fixture_live;'
                    live = 0
                expected.append([value,count,live,attempts])
                statements.append('{fixture_attempts=0;fixture_successes=0;fixture_live=0;fixture_fail='+str(fail)+';'+call+'if(fixture_live!=0){return 12;}printf("%lld %d %d %d\\n",value,fixture_successes,live_after,fixture_attempts);}')
            harness = '\n#undef calloc\n#undef free\nint main(void){'+''.join(statements)+'return 0;}\n'
            runs = []
            for opt in ('-O0','-O2'):
                outputs = {}
                for tag, code in [('original',source),('normalized',normalized),('composed',composed)]:
                    c_file = path/(name+tag+'.c')
                    exe = path/(name+tag+opt)
                    c_file.write_text(prefix+code+harness)
                    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(c_file),'-o',str(exe)],check=True,capture_output=True,timeout=60)
                    run = subprocess.run([str(exe)],check=True,capture_output=True,text=True,timeout=60)
                    if run.stderr:
                        raise AssertionError(run.stderr)
                    outputs[tag] = [[int(v) for v in line.split()] for line in run.stdout.splitlines()]
                if any(value != expected for value in outputs.values()):
                    raise AssertionError((name,opt,outputs,expected))
                runs.append({'optimization':opt,**outputs,'model':expected})
                print(f'{name} {opt}: {len(samples)} original/normalized/composed/model correspondences passed',flush=True)
            rows.append({'case':name,'source':source,'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'parameter_bounds':bounds,'normalization':report['normalization'],'certificate':report['certificate'],
                'samples':[{'n':n,'successful_allocations':m} for n,m in samples],
                'output_columns':['return_or_payload_sum','successful_allocations','live_nodes_after_entry','allocation_attempts'],
                'runs':runs})
    result = {'passed':True,'correspondences':len(samples)*len(rows)*2,'cases':rows,
        'compiler':subprocess.run(['cc','--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0]}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{result["correspondences"]} total list-call correspondences passed')


if __name__ == '__main__':
    main()
