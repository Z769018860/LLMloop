"""Native positive memory/ABI differential checks under UBSan."""
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_memory import TypedCMemory

ROOT=Path(__file__).resolve().parents[1]
ARRAY=(ROOT/'examples/typed_memory_loop.c').read_text()
FORMS=json.loads((ROOT/'examples/typed_memory_summaries.json').read_text())
PRIVATE='''long private_heap(int n){long x=0;for(int i=0;i<n;i++){
    unsigned char *p=calloc(2,sizeof(unsigned char));unsigned char *q=p;
    p[0]=1;q[1]=255;q[1]++;x=x+p[0]+p[1];free(q);}return x;}'''
MALLOC='''int initialized_heap(int n){int *p=malloc(2*sizeof(int));int *q=p;p[0]=7;
    for(int i=0;i<n;i++){q[0]++;}int result=p[0];free(q);return result;}'''
DYNAMIC='''int dynamic_cells(int n){unsigned char a[2]={0,0};unsigned char *p=a;
    for(int i=0;i<n;i++){p[i%2]++;}return a[0]+a[1];}'''
NESTED='''int nested_cells(int n,int m){unsigned char a[1]={0};unsigned char *p=a;
    for(int i=0;i<n;i++){for(int j=0;j<m;j++){(*p)++;}}return a[0];}'''
SIGNED='''int signed_cells(int n){signed char a[1]={-128};signed char *p=a;
    for(int i=0;i<n;i++){(*p)++;}return a[0];}'''
MIXED='''long mixed_cells(int n){long a[1]={0};unsigned char b[1]={255};
    for(int i=0;i<n;i++){a[0]++;b[0]++;}return a[0]+b[0];}'''


NESTED_PRIVATE='''long nested_private_heap(int n,int m){long x=0;for(int i=0;i<n;i++){
    for(int j=0;j<m;j++){unsigned char *p=calloc(1,sizeof(unsigned char));p[0]=1;x+=p[0];free(p);}}return x;}'''


def main():
    samples=[-3,0,1,2,10,127,128,254,255,256,257,512,1000,1000000]
    bound={'n':[-3,1000000000]}
    cases=[
        ('typed_memory',ARRAY,FORMS,bound,ctypes.c_long,[(n,) for n in samples]),
        ('private_heap',PRIVATE,{'i':{'x':'i'}},bound,ctypes.c_long,[(n,) for n in samples]),
        ('initialized_heap',MALLOC,{'i':{'p[0]':'7+i','p[1]':'entry("p[1]")'}},bound,ctypes.c_int,[(n,) for n in samples]),
        ('dynamic_cells',DYNAMIC,{'i':{'a[0]':'((i+1)//2)%256','a[1]':'(i//2)%256'}},bound,ctypes.c_int,[(n,) for n in samples]),
        ('signed_cells',SIGNED,{'i':{'a[0]':'i%256-128'}},bound,ctypes.c_int,[(n,) for n in samples]),
        ('mixed_cells',MIXED,{'i':{'a[0]':'i','b[0]':'(255+i)%256'}},bound,ctypes.c_long,[(n,) for n in samples]),
        ('nested_private_heap',NESTED_PRIVATE,{'i':{'x':'i*m'},'j':{'x':'entry("x")+j'}},
         {'n':[0,1000],'m':[0,1000]},ctypes.c_long,[(n,m) for n in range(5) for m in range(5)]+[(100,100)]),
        ('nested_cells',NESTED,{'i':{'a[0]':'i*m%256'},'j':{'a[0]':'(entry("a[0]")+j)%256'}},
         {'n':[0,1000],'m':[0,1000]},ctypes.c_int,[(n,m) for n in range(9) for m in range(9)]+[(1000,1000)])
    ]
    counts={}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'memory.c';source.write_text('#include <stdlib.h>\n'+'\n'.join(c[1] for c in cases))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'memory.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'memory.so'))
        for name,code,forms,bounds,return_type,inputs in cases:
            engine=TypedCMemory(code,forms,parameter_bounds=bounds)
            report=engine.report()
            if report['status']!='PROVED_DEFINED_TYPED_C_MEMORY':raise AssertionError(report)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=return_type;counts[name]=0
            for values in inputs:
                expected=engine.report(dict(zip(bounds,values)))['evaluation']['value'];actual=fn(*values)
                if expected!=actual:raise AssertionError((name,values,expected,actual))
                counts[name]+=1
    for name,count in counts.items():print(f'{name} typed memory / native C+UBSan: {count}/{count} passed')


if __name__=='__main__':main()
