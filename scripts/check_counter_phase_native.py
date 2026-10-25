"""Additive threshold summaries versus original LP64 C with UBSan."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_nested import TypedCNested
from llmloop.typed_memory import TypedCMemory
from build_counter_phase_cases import LINEAR,MISSING_ELSE,CELLS,MULTI,CUBIC,RAW_CUBIC,NESTED,STEPS
ROOT=Path(__file__).resolve().parents[1]


def main():
    samples=[(n,t) for n in [-3,0,1,2,3,7,31,1000] for t in [-1000,-1,0,1,2,3,7,1000]]
    bounds={'n':[-3,1000],'t':[-1000,1000]}
    cases=[('phase_linear',LINEAR,TypedCNested,ctypes.c_long,bounds,samples),
           ('phase_optional',MISSING_ELSE,TypedCNested,ctypes.c_long,bounds,samples),
           ('phase_cells',CELLS,TypedCMemory,ctypes.c_int,bounds,samples),
           ('phase_multi',MULTI,TypedCNested,ctypes.c_long,bounds,samples),
           ('phase_cubic',CUBIC,TypedCNested,ctypes.c_long,bounds,samples),
           ('phase_raw_cubic',RAW_CUBIC.replace('phase_cubic','phase_raw_cubic'),TypedCNested,ctypes.c_long,bounds,samples),
           ('phase_steps',STEPS,TypedCNested,ctypes.c_long,{'n':[-3,1000000000],'t':[-1000000000,1000000000]},samples+[(1000000,1),(1000000,999999),(1000000,1000000)]),
           ('counter_phases',(ROOT/'examples/typed_counter_phases.c').read_text(),TypedCNested,ctypes.c_long,{'n':[-3,1000],'threshold':[-1000,1000]},samples),
           ('phase_nested',NESTED,TypedCNested,ctypes.c_long,{'n':[-3,1000000]},[(n,) for n in [-3,0,1,2,3,7,31,1000000]])]
    for suffix,op in [('le','<='),('gt','>'),('ge','>=')]:
        cases.append(('phase_'+suffix,LINEAR.replace('phase_linear','phase_'+suffix).replace('i<t','i'+op+'t'),TypedCNested,ctypes.c_long,bounds,samples))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'phases.c'
        source.write_text('#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'+'\n'.join(row[1] for row in cases))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'phases.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'phases.so'))
        for name,code,model,result_type,domain,inputs in cases:
            engine=model(code,'auto',parameter_bounds=domain);r=engine.report()
            if r['status'] not in ('PROVED_DEFINED_TYPED_C_NESTED','PROVED_DEFINED_TYPED_C_MEMORY'):raise AssertionError(r)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(domain);fn.restype=result_type
            for values in inputs:
                expected=engine.report(dict(zip(domain,values)))['evaluation']['value'];actual=fn(*values)
                if expected!=actual:raise AssertionError((name,values,expected,actual))
            print(f'{name} counter phases / native C+UBSan: {len(inputs)}/{len(inputs)} passed',flush=True)


if __name__=='__main__':main()
