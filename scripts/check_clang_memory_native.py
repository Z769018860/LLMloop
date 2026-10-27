"""Reproduce original C / normalized C / proved model correspondences.

Allocator wrappers independently exercise success and each allocation-failure
position. Finite native points supplement the symbolic proof; they do not prove
compiler equivalence or unbounded heap-shape safety.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.typed_cfg_calls import TypedCFGCalls
from llmloop.typed_memory import TypedCMemory


ROOT = Path(__file__).resolve().parents[1]
ARRAY = 'int entry(int n){int a[2]={1,2};int *p=a;for(int i=0;i<n;i++){p[0]+=2;}return a[0]+a[1];}'
FILLER = 'int entry(void){int a[4]={[2]=7};return a[0]+a[1]+a[2]+a[3];}'
ALIAS = 'int *move(int *p){p[0]+=1;return p+1;}int entry(void){int a[3]={3,5,7};int *q=move(a);q[0]=11;return a[0]+a[1]+a[2];}'


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    clang = compiler_path()
    specs = [
        ('million_array', ARRAY, 'memory', {'n':[0,1000000]}, [{'n':n} for n in (0,1,7,1000000)], [0]),
        ('semantic_filler', FILLER, 'calls', {}, [{}], [0]),
        ('helper_alias', ALIAS, 'calls', {}, [{}], [0]),
        ('linked_heap', (ROOT/'examples/clang_heap_calls.c').read_text(), 'calls', {'n':[0,100]}, [{'n':n} for n in (0,1,7,100)], [0,1,2]),
    ]
    prefix = '''#include <stdlib.h>
#include <stdio.h>
static int fixture_calls,fixture_fail;
static void *fixture_calloc(size_t n,size_t s){
    fixture_calls++;
    if(fixture_calls==fixture_fail){return NULL;}
    return calloc(n,s);
}
#define calloc fixture_calloc
'''
    rows = []
    with tempfile.TemporaryDirectory(prefix='clang-memory-native-') as temp:
        path = Path(temp)
        for name, source, backend, bounds, points, failures in specs:
            request = {'source':source, 'function':'entry', 'frontend':'clang_proof', 'clang':{'executable':clang},
                       'proof':{'backend':backend, 'parameter_bounds':bounds}}
            if backend=='calls':
                request['proof']['max_steps']=256
            report = analyze_request(request)
            if not report['status'].startswith('PROVED_DEFINED_CLANG_'):
                raise AssertionError(report)
            normalized = report['normalization']['source']
            if backend=='memory':
                engine = TypedCMemory(normalized,'auto',function='entry',parameter_bounds=bounds)
            else:
                engine = TypedCFGCalls(normalized,function='entry',parameter_bounds=bounds,max_steps=256)
            samples = [(point, fail) for fail in failures for point in points]
            expected = []
            for point, fail in samples:
                if backend=='memory':
                    value = engine.report(point)['evaluation']['value']
                else:
                    term = engine.evaluate_return(point)
                    replacements = [(choice,z3.BoolVal(not fail or index+1!=fail)) for index,choice in enumerate(engine.choices)]
                    term = z3.simplify(z3.substitute(term,*replacements)) if replacements else z3.simplify(term)
                    if not z3.is_int_value(term):
                        raise AssertionError(('unresolved model outcome',name,point,fail,term))
                    value = term.as_long()
                expected.append(value)
            harness = '\n#undef calloc\nint main(void){' + ''.join(
                'fixture_calls=0;fixture_fail='+str(fail)+';printf("%lld\\n",(long long)entry('+','.join(str(point[key]) for key in bounds)+'));'
                for point,fail in samples) + 'return 0;}\n'
            runs=[]
            for opt in ('-O0','-O2'):
                values={}
                for tag,code in [('original',source),('normalized',normalized)]:
                    c_file=path/(name+tag+'.c');executable=path/(name+tag+opt)
                    c_file.write_text(prefix+code+harness)
                    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(c_file),'-o',str(executable)],check=True,capture_output=True,timeout=60)
                    output=subprocess.run([str(executable)],check=True,capture_output=True,text=True,timeout=60)
                    if output.stderr:
                        raise AssertionError(output.stderr)
                    values[tag]=[int(value) for value in output.stdout.splitlines()]
                if values['original']!=values['normalized'] or values['original']!=expected:
                    raise AssertionError((name,opt,values,expected))
                runs.append({'optimization':opt,'original':values['original'],'normalized':values['normalized'],'model':expected})
                print(f'{name} {opt}: {len(samples)} original/normalized/model correspondences passed',flush=True)
            rows.append({'name':name,'source':source,'source_sha256':digest(source),'backend':backend,'bounds':bounds,
                         'samples':[{'inputs':point,'fail_at_allocation':fail} for point,fail in samples],
                         'status':report['status'],'normalization':report['normalization'],
                         'runs':runs,'certificate':report.get('certificate',report.get('loop_certificates'))})
    result={'compiler':subprocess.run(['cc','--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0],
            'clang':subprocess.run([clang,'--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0],
            'correspondences':sum(len(row['samples'])*len(row['runs']) for row in rows),'cases':rows,'passed':True}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{result["correspondences"]} total original/normalized/model correspondences passed')


if __name__=='__main__':
    main()
