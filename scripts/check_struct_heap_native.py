"""Original linked/cyclic record C, allocator failures and native ABI layout."""
import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import z3
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_cfg_calls import TypedCFGCalls
from build_struct_heap_cases import ROOT,CYCLE,REWIRE,PAYLOAD,LAYOUT,NARROW,BOOL,FAULTS


def main():
    specs=[('list',(ROOT/'examples/typed_struct_list.c').read_text(),'struct_list',{'n':[0,3]},list(range(4)),True),
           ('cycle',CYCLE,'entry',{'n':[0,4]},list(range(5)),False),
           ('rewire',REWIRE,'entry',{'n':[0,4]},list(range(5)),False),
           ('payload',PAYLOAD,'entry',{'n':[0,3]},list(range(4)),False),
           ('layout',LAYOUT,'entry',{},[None],False),
           ('bool',BOOL,'entry',{'n':[-1,1]},[-1,0,1],False),
           ('narrow',NARROW,'entry',{'n':[255,257]},list(range(255,258)),False)]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,code,root,bounds,inputs,calls in specs:
            e=(TypedCFGCalls if calls else TypedCFGHeap)(code,function=root,parameter_bounds=bounds,max_steps=512,max_paths=64)
            assert e.report()['status'].startswith('PROVED_DEFINED_TYPED_C_CFG_'),e.report()
            for mode in ['success','all_fail','second_fail']:
                prefix='#include <stdlib.h>\n#include <limits.h>\n#include <stddef.h>\n_Static_assert(sizeof(void*)==8 && sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\nstatic int allocation_index;\nvoid reset_allocations(void){allocation_index=0;}\n'
                if mode!='success':
                    failure='1' if mode=='all_fail' else '(++allocation_index==2)'
                    prefix+=f'void *test_malloc(size_t n){{if({failure})return NULL;return malloc(n);}}\nvoid *test_calloc(size_t n,size_t s){{if({failure})return NULL;return calloc(n,s);}}\n#define malloc test_malloc\n#define calloc test_calloc\n'
                probe=''
                if name=='layout':probe='size_t probe_layout(int i){size_t v[]={sizeof(struct Layout),_Alignof(struct Layout),offsetof(struct Layout,c),offsetof(struct Layout,x),offsetof(struct Layout,p),offsetof(struct Layout,y)};return v[i];}'
                for opt in ['-O0','-O2']:
                    source=path/(name+mode+opt+'.c');source.write_text(prefix+code+probe);so=source.with_suffix('.so')
                    subprocess.run(['cc','-std=c11',opt,'-shared','-fPIC','-Wl,-Bsymbolic','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(so)],check=True,capture_output=True)
                    native=ctypes.CDLL(str(so));fn=getattr(native,root);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=ctypes.c_int
                    for n in inputs:
                        point={'n':n} if bounds else {};native.reset_allocations()
                        substitutions=[(term.value,z3.IntVal(point[key])) for key,term in e.parameters.items()]
                        substitutions.extend((choice,z3.BoolVal(mode=='success' or mode=='second_fail' and i!=1)) for i,choice in enumerate(e.choices))
                        expected=z3.simplify(z3.substitute(e.result.value,*substitutions)).as_long()
                        actual=fn(n) if bounds else fn()
                        assert actual==expected,(name,mode,opt,n,expected,actual)
                    print(f'{name} original record C UBSan {mode} {opt}: {len(inputs)}/{len(inputs)} matched',flush=True)
            if name=='layout':
                layout=e.report()['memory_model']['struct_layouts']['Layout'];expected=[layout['size'],layout['alignment']]+[m['offset'] for m in layout['members']]
                native.probe_layout.argtypes=[ctypes.c_int];native.probe_layout.restype=ctypes.c_size_t
                assert [native.probe_layout(i) for i in range(6)]==expected,expected
                print('Native LP64 sizeof/alignment/member-offset correspondences: 6/6 matched')
        env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
        for name,code,bounds,diagnostic in FAULTS:
            e=TypedCFGHeap(code,function='entry',parameter_bounds=bounds,max_steps=128)
            assert e.report()['status']=='UNKNOWN',e.report()
            source=path/(name+'.c');source.write_text('#include <stdlib.h>\n'+code+'\nint main(void){return entry(1);}')
            binary=path/name
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
            outcome=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            assert outcome.returncode!=0 and diagnostic in outcome.stderr,(name,outcome.stderr[:1800])
        print(f'Intentional struct ASan/UBSan fault correspondences: {len(FAULTS)}/{len(FAULTS)} matched')


if __name__=='__main__':main()
