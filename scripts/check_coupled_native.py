"""Source-verified coupled candidates against native LP64 C with UBSan."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_nested import TypedCNested
from llmloop.typed_memory import TypedCMemory
from build_coupled_cases import SWAP,ACCUM,CELLS,POLY,NESTED,cycle
ROOT=Path(__file__).resolve().parents[1]


def main():
    cases=[('coupled_swap',SWAP,TypedCNested,ctypes.c_int),
           ('coupled_rotate',(ROOT/'examples/typed_coupled_rotation.c').read_text(),TypedCNested,ctypes.c_long),
           ('coupled_accum',ACCUM,TypedCNested,ctypes.c_long),
           ('coupled_poly',POLY,TypedCNested,ctypes.c_long),
           ('coupled_cells',CELLS,TypedCMemory,ctypes.c_int),
           ('coupled_nested',NESTED,TypedCNested,ctypes.c_long)]
    cases.extend(('coupled_cycle'+str(p),cycle(p),TypedCNested,ctypes.c_int) for p in [3,5,8])
    samples=[-3,0,*range(1,25),127,128,255,256,999999,1000000]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'coupled.c'
        source.write_text('#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'+'\n'.join(row[1] for row in cases))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'coupled.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'coupled.so'))
        for name,code,model,result_type in cases:
            engine=model(code,'auto',parameter_bounds={'n':[-3,1000000]});r=engine.report()
            if r['status'] not in ('PROVED_DEFINED_TYPED_C_NESTED','PROVED_DEFINED_TYPED_C_MEMORY'):raise AssertionError(r)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int];fn.restype=result_type
            for n in samples:
                expected=engine.report({'n':n})['evaluation']['value'];actual=fn(n)
                if expected!=actual:raise AssertionError((name,n,expected,actual))
            print(f'{name} cyclic candidates / native C+UBSan: {len(samples)}/{len(samples)} passed',flush=True)


if __name__=='__main__':main()
