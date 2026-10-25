"""Original recursive/mutually recursive functions versus bounded-closure proofs."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_cfg_calls import TypedCFGCalls
from build_recursion_cases import SUM,FACTORIAL,MUTUAL,FIB,VOID,STACK,ROOT_RECURSION,BYTE,FAULTS
ROOT=Path(__file__).resolve().parents[1]


def main():
    specs=[('heap',(ROOT/'examples/typed_recursive_calls.c').read_text(),'recursive_heap',3,4),
           ('sum',SUM,'entry',3,4),('factorial',FACTORIAL,'entry',3,4),('mutual',MUTUAL,'entry',3,4),
           ('branching',FIB,'entry',4,4),('void',VOID,'entry',3,4),('stack',STACK,'entry',3,4),
           ('root',ROOT_RECURSION,'rec_root',3,3),('byte',BYTE,'entry',3,4)]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,code,root,maximum,depth in specs:
            e=TypedCFGCalls(code,function=root,allow_recursion=True,max_call_depth=depth,max_steps=512,max_paths=64,parameter_bounds={'n':[0,maximum]})
            r=e.report()
            if r['status']!='PROVED_DEFINED_TYPED_C_CFG_CALLS' or not r['call_model']['all_frontiers_proved_unreachable']:raise AssertionError(r)
            for success in [True,False]:
                prefix='#include <stdlib.h>\n#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'
                if not success:prefix+='void *always_fail_calloc(size_t n,size_t s){(void)n;(void)s;return NULL;}\n#define calloc always_fail_calloc\n'
                source=path/(name+str(success)+'.c');source.write_text(prefix+code);so=source.with_suffix('.so')
                subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(so)],check=True,capture_output=True)
                native=ctypes.CDLL(str(so));fn=getattr(native,root);fn.argtypes=[ctypes.c_int];fn.restype=ctypes.c_int
                for n in range(maximum+1):
                    expected=e.evaluate_return({'n':n},success).as_long();actual=fn(n)
                    if expected!=actual:raise AssertionError((name,n,success,expected,actual))
                print(f'{name} original recursive C+UBSan allocator_{"success" if success else "failure"}: {maximum+1}/{maximum+1} matched',flush=True)
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
        for name,code,diagnostic in FAULTS:
            e=TypedCFGCalls(code,function='entry',allow_recursion=True,max_call_depth=4,max_steps=512,parameter_bounds={'n':[1,2]})
            if e.report()['status']!='UNKNOWN':raise AssertionError(e.report())
            source=path/(name+'.c');binary=path/name;source.write_text('#include <stdlib.h>\n'+code+'\nint main(void){return entry(1);}')
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
            outcome=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            if outcome.returncode==0 or diagnostic not in outcome.stderr:raise AssertionError((name,outcome.returncode,outcome.stderr[:1500]))
        print(f'Recursive intentional ASan+UBSan fault correspondences: {len(FAULTS)}/{len(FAULTS)} matched')


if __name__=='__main__':main()
