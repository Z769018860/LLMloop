"""Complete-domain CFG proofs versus native C for success/failure allocator modes.

All deliberate fault controls execute in isolated ASan/UBSan subprocesses.
The allocator failure build changes only allocator results, not program logic.
"""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_cfg_heap import TypedCFGHeap
from build_cfg_heap_cases import STATE,GOTO,SWITCH,MALLOC,TRAVERSE,REUSE,REBIND,DO,FAULTS
ROOT=Path(__file__).resolve().parents[1]


def main():
    specs=[('cfg_heap',(ROOT/'examples/typed_cfg_heap.c').read_text(),{'n':[1,3],'select':[0,2]},[(n,k) for n in range(1,4) for k in range(3)]),
           ('cfg_state',STATE,{'n':[0,5]},[(n,) for n in range(6)]),
           ('cfg_goto',GOTO,{'n':[0,3]},[(n,) for n in range(4)]),
           ('cfg_switch',SWITCH,{'n':[0,3]},[(n,) for n in range(4)]),
           ('cfg_malloc',MALLOC,{'n':[1,3]},[(n,) for n in range(1,4)]),
           ('cfg_traverse',TRAVERSE,{'n':[1,3]},[(n,) for n in range(1,4)]),
           ('cfg_reuse',REUSE,{'n':[0,3]},[(n,) for n in range(4)]),
           ('cfg_rebind',REBIND,{},[()]),('cfg_do',DO,{'n':[0,4]},[(n,) for n in range(5)])]
    engines={name:TypedCFGHeap(code,parameter_bounds=bounds,max_paths=64) for name,code,bounds,_ in specs}
    for name,e in engines.items():
        if e.report()['status']!='PROVED_DEFINED_TYPED_C_CFG_HEAP':raise AssertionError((name,e.report()))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for mode in [True,False]:
            prefix='#include <stdlib.h>\n#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'
            if not mode:prefix+='void *always_fail_malloc(size_t n){(void)n;return NULL;}\nvoid *always_fail_calloc(size_t n,size_t s){(void)n;(void)s;return NULL;}\n#define malloc always_fail_malloc\n#define calloc always_fail_calloc\n'
            source=path/('success.c' if mode else 'failure.c');source.write_text(prefix+'\n'.join(row[1] for row in specs))
            so=source.with_suffix('.so')
            subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(so)],check=True,capture_output=True)
            native=ctypes.CDLL(str(so))
            for name,_,bounds,inputs in specs:
                fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=ctypes.c_int
                for values in inputs:
                    expected=engines[name].evaluate_return(dict(zip(bounds,values)),mode)
                    if not hasattr(expected,'as_long') or expected.as_long()!=fn(*values):raise AssertionError((name,values,mode,expected))
                print(f'{name} native C+UBSan allocator_{"success" if mode else "failure"}: {len(inputs)}/{len(inputs)} matched',flush=True)
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
        count=0
        for name,code,bounds,diagnostic in FAULTS:
            e=TypedCFGHeap(code,parameter_bounds=bounds)
            if e.report()['status']!='UNKNOWN':raise AssertionError(e.report())
            source=path/(name+'.c');binary=path/name
            source.write_text('#include <stdlib.h>\n'+code+'\nint main(void){return f(1);}')
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            if result.returncode==0 or diagnostic not in result.stderr:raise AssertionError((name,result.returncode,result.stderr[:1500]))
            count+=1
        print(f'CFG heap intentional ASan+UBSan rejection correspondences: {count}/{count} matched')


if __name__=='__main__':main()
