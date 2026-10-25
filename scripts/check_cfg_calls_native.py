"""Original multi-function C oracles; helpers are never replaced in native code."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_cfg_calls import TypedCFGCalls
from build_cfg_call_cases import NARROW,ALIAS,OFFSET,CHAIN,LOOP,VOID,ARRAY
ROOT=Path(__file__).resolve().parents[1]


def main():
    specs=[('calls_heap',(ROOT/'examples/typed_cfg_calls.c').read_text(),{'n':[1,3]},[(n,) for n in range(1,4)]),
           ('calls_narrow',NARROW,{'n':[254,257]},[(n,) for n in range(254,258)]),
           ('calls_alias',ALIAS,{},[()]),('calls_offset',OFFSET,{},[()]),
           ('calls_chain',CHAIN,{'n':[-1,2]},[(n,) for n in range(-1,3)]),
           ('calls_loop',LOOP,{'n':[0,3]},[(n,) for n in range(4)]),
           ('calls_void',VOID,{'n':[0,1]},[(n,) for n in range(2)]),
           ('calls_array',ARRAY,{'n':[0,3]},[(n,) for n in range(4)])]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        # Compile each original translation unit separately: independent helper
        # names may repeat across test programs. Only allocator outcomes change.
        for name,code,bounds,inputs in specs:
            e=TypedCFGCalls(code,function=name,parameter_bounds=bounds,max_steps=256,max_paths=64)
            if e.report()['status']!='PROVED_DEFINED_TYPED_C_CFG_CALLS':raise AssertionError(e.report())
            for success in [True,False]:
                prefix='#include <stdlib.h>\n#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'
                if not success:prefix+='void *always_fail_malloc(size_t n){(void)n;return NULL;}\nvoid *always_fail_calloc(size_t n,size_t s){(void)n;(void)s;return NULL;}\n#define malloc always_fail_malloc\n#define calloc always_fail_calloc\n'
                source=path/(name+str(success)+'.c');source.write_text(prefix+code);so=source.with_suffix('.so')
                subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(so)],check=True,capture_output=True)
                native=ctypes.CDLL(str(so));fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=ctypes.c_int
                for values in inputs:
                    expected=e.evaluate_return(dict(zip(bounds,values)),success).as_long();actual=fn(*values)
                    if expected!=actual:raise AssertionError((name,values,success,expected,actual))
                print(f'{name} original multi-function C+UBSan allocator_{"success" if success else "failure"}: {len(inputs)}/{len(inputs)} matched',flush=True)

        faults=[
            ('callee_free_uaf','void release(int *p){free(p);} int entry(void){int *p=calloc(1,sizeof(int));if(!p){return 0;}release(p);return p[0];}','heap-use-after-free'),
            ('callee_discarded_overflow','int bad(int x){int temp=x+2147483647;return temp;} int entry(void){bad(1);return 0;}','signed integer overflow')]
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
        for name,code,diagnostic in faults:
            e=TypedCFGCalls(code,function='entry')
            if e.report()['status']!='UNKNOWN':raise AssertionError(e.report())
            source=path/(name+'.c');binary=path/name;source.write_text('#include <stdlib.h>\n'+code+'\nint main(void){return entry();}')
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
            outcome=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            if outcome.returncode==0 or diagnostic not in outcome.stderr:raise AssertionError((name,outcome.returncode,outcome.stderr[:1500]))
        print(f'Interprocedural intentional ASan+UBSan fault correspondences: {len(faults)}/{len(faults)} matched')


if __name__=='__main__':main()
