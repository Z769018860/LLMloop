"""Original pointer-table C under UBSan and isolated expected ASan faults."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import z3
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_cfg_calls import TypedCFGCalls
from build_pointer_cell_cases import ROOT,TABLE,STORE,TRIPLE,COPY,CALLOC,SET,SELECT,OFFSET,FAULTS


def main():
    specs=[('load',TABLE,'entry',{'i':[0,2]},[(i,) for i in range(3)],False),
           ('store',STORE,'entry',{'i':[0,1]},[(i,) for i in range(2)],False),
           ('triple',TRIPLE,'entry',{},[()],False),('copy',COPY,'entry',{'i':[0,1]},[(i,) for i in range(2)],False),
           ('calloc',CALLOC,'entry',{'n':[1,3]},[(i,) for i in range(1,4)],False),
           ('select',SELECT,'entry',{'i':[0,2]},[(i,) for i in range(3)],True),
           ('offset',OFFSET,'entry',{'i':[0,1]},[(i,) for i in range(2)],False),
           ('set',SET,'entry',{},[()],True),
           ('escape',(ROOT/'examples/typed_pointer_cells.c').read_text(),'pointer_cells',{'n':[1,3]},[(i,) for i in range(1,4)],True)]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,code,root,bounds,inputs,calls in specs:
            e=(TypedCFGCalls if calls else TypedCFGHeap)(code,function=root,parameter_bounds=bounds,max_steps=512,max_paths=64)
            assert e.report()['status'].startswith('PROVED_DEFINED_TYPED_C_CFG_'),e.report()
            modes=['success','all_fail']+(['second_fail'] if name=='escape' else [])
            for mode in modes:
                prefix='#include <stdlib.h>\n#include <limits.h>\n_Static_assert(sizeof(void*)==8 && sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'
                if mode!='success':
                    prefix+='static int allocation_number;\n'
                    failure='1' if mode=='all_fail' else '(++allocation_number==2)'
                    prefix+=f'void *test_malloc(size_t n){{if({failure})return NULL;return malloc(n);}}\nvoid *test_calloc(size_t n,size_t s){{if({failure})return NULL;return calloc(n,s);}}\n#define malloc test_malloc\n#define calloc test_calloc\n'
                for opt in ['-O0','-O2']:
                    source=path/(name+mode+opt+'.c');source.write_text(prefix+code);so=source.with_suffix('.so')
                    subprocess.run(['cc','-std=c11',opt,'-shared','-fPIC','-Wl,-Bsymbolic','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(so)],check=True,capture_output=True)
                    native=ctypes.CDLL(str(so));fn=getattr(native,root);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=ctypes.c_int
                    # The partial-failure allocator counter must reset for every invocation.
                    # Build a fresh process below for that mode, since its counter is private.
                    for values in inputs:
                        point=dict(zip(bounds,values))
                        if mode=='second_fail':
                            substitutions=[(term.value,z3.IntVal(point[key])) for key,term in e.parameters.items()]
                            assert len(e.choices)==2
                            substitutions.extend((choice,z3.BoolVal(i!=1)) for i,choice in enumerate(e.choices))
                            expected=z3.simplify(z3.substitute(e.result.value,*substitutions)).as_long()
                            binary=source.with_suffix('.run')
                            main=source.read_text()+f'\n#include <stdio.h>\nint main(void){{printf("%d",{root}({values[0]}));return 0;}}'
                            run_source=source.with_suffix('.run.c');run_source.write_text(main)
                            subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',str(run_source),'-o',str(binary)],check=True,capture_output=True)
                            actual=int(subprocess.run([str(binary)],check=True,capture_output=True,text=True).stdout)
                        else:expected=e.evaluate_return(point,mode=='success').as_long();actual=fn(*values)
                        assert actual==expected,(name,mode,opt,values,expected,actual)
                    print(f'{name} original C UBSan {mode} {opt}: {len(inputs)}/{len(inputs)} matched',flush=True)
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
        for name,code,bounds,diagnostic in FAULTS:
            e=TypedCFGHeap(code,function='entry',parameter_bounds=bounds,max_steps=256)
            assert e.report()['status']=='UNKNOWN',e.report()
            value=bounds['i'][0];source=path/(name+'.c');source.write_text('#include <stdlib.h>\n'+code+f'\nint main(void){{return entry({value});}}');binary=path/name
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
            outcome=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            assert outcome.returncode!=0 and diagnostic in outcome.stderr,(name,outcome.stderr[:1500])
        print(f'Intentional pointer-cell ASan/UBSan fault correspondences: {len(FAULTS)}/{len(FAULTS)} matched')


if __name__=='__main__':main()
