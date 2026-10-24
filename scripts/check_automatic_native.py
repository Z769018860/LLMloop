"""Automatically generated and independently checked summaries versus native C."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_nested import TypedCNested
from llmloop.typed_memory import TypedCMemory

ROOT=Path(__file__).resolve().parents[1]
AFFINE='long auto_affine(int n){long x=7;for(int i=0;i<n;i++){x+=3;}return x;}'
POLY='long auto_square(int n){long x=0;for(int i=0;i<n;i++){x+=2*i+1;}return x;}'
SAT='int auto_saturate(int n,int limit){int x=0;for(int i=0;i<n;i++){if(x<limit){x++;}else{x=x;}}return x;}'
TOGGLE='int auto_toggle(int n){int x=1;for(int i=0;i<n;i++){x=-x;}return x;}'
TRANSIENT='long auto_transient(int n){long x=0;long y=0;for(int i=0;i<n;i++){y=x;x++;}return y;}'
PRIVATE='''long auto_private(int n,int m){long x=0;for(int i=0;i<n;i++){
    for(int j=0;j<m;j++){int *p=calloc(1,sizeof(int));p[0]=1;x+=p[0];free(p);}}return x;}'''
MALLOC='''int auto_initialized_heap(int n){int *p=malloc(2*sizeof(int));p[0]=7;
    for(int i=0;i<n;i++){p[0]++;}int result=p[0];free(p);return result;}'''


def main():
    samples=[-3,0,1,2,10,127,128,254,255,256,257,1000,1000000]
    rectangle=[(n,m) for n in range(9) for m in range(9)]+[(1000,1000)]
    cases=[
        ('auto_affine',AFFINE,TypedCNested,{'n':[-3,1000000000]},ctypes.c_long,[(n,) for n in samples]),
        ('auto_square',POLY,TypedCNested,{'n':[0,1000000]},ctypes.c_long,[(n,) for n in samples if n>=0]),
        ('auto_saturate',SAT,TypedCNested,{'n':[-3,1000000],'limit':[-10,1000]},ctypes.c_int,[(n,limit) for n in samples for limit in [-10,0,1,10,300]]),
        ('auto_toggle',TOGGLE,TypedCNested,{'n':[-3,1000000]},ctypes.c_int,[(n,) for n in samples]),
        ('auto_transient',TRANSIENT,TypedCNested,{'n':[-3,1000000]},ctypes.c_long,[(n,) for n in samples]),
        ('nested_typed',(ROOT/'examples/typed_nested_loop.c').read_text(),TypedCNested,{'n':[0,1000],'m':[0,1000]},ctypes.c_long,rectangle),
        ('typed_memory',(ROOT/'examples/typed_memory_loop.c').read_text(),TypedCMemory,{'n':[-3,1000000000]},ctypes.c_long,[(n,) for n in samples]),
        ('auto_private',PRIVATE,TypedCMemory,{'n':[0,1000],'m':[0,1000]},ctypes.c_long,rectangle),
        ('auto_initialized_heap',MALLOC,TypedCMemory,{'n':[-3,1000000000]},ctypes.c_int,[(n,) for n in samples])
    ]
    counts={}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'automatic.c';source.write_text('#include <stdlib.h>\n#include <limits.h>\n_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");\n'+'\n'.join(case[1] for case in cases))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'automatic.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'automatic.so'))
        for name,code,model,bounds,result_type,inputs in cases:
            engine=model(code,'auto',parameter_bounds=bounds);report=engine.report()
            if report['status'] not in ('PROVED_DEFINED_TYPED_C_NESTED','PROVED_DEFINED_TYPED_C_MEMORY') or not report['summary_synthesis']:raise AssertionError(report)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=result_type;counts[name]=0
            for values in inputs:
                expected=engine.report(dict(zip(bounds,values)))['evaluation']['value'];actual=fn(*values)
                if expected!=actual:raise AssertionError((name,values,expected,actual))
                counts[name]+=1
    for name,count in counts.items():print(f'{name} automatic checked summary / native C+UBSan: {count}/{count} passed')


if __name__=='__main__':main()
