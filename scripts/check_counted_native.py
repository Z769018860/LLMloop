"""Native regression oracle for unbounded counted C summaries (finite samples)."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.counted_c import translate_counted_memory_c
from llmloop.unbounded_memory import UnboundedMemory

CASES=[
    'int f(int n,int m){int a[2]={1,7};int *p=&a[0];int *q=p;int i=0;int j=0;for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){*p=*q+1;}*q=*q*2;a[1]=a[1]+a[0];}return a[1];}',
    'int f(int n,int m){int a[1]={0};int i=0;int j=0;for(i=0;i<n;i=i+1){a[0]=a[0]+3;for(j=0;j<m;j=j+1){a[0]=a[0]+i+j;}a[0]=a[0]+5;}return a[0];}',
    'int f(int n,int m){int *p=calloc(1,sizeof(int));int i=0;int j=0;for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){p[0]=p[0]+2;}p[0]=p[0]+1;}return p[0];}'
]


def main():
    count=0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);unit=path/'counted.c'
        unit.write_text('#include <stdlib.h>\n'+'\n'.join(src.replace('int f(',f'int f{k}(') for k,src in enumerate(CASES)))
        subprocess.run(['cc','-O0','-shared','-fPIC',str(unit),'-o',str(path/'counted.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'counted.so'))
        for k,source in enumerate(CASES):
            summary=UnboundedMemory(translate_counted_memory_c(source,parameter_mins={'n':0,'m':0}))
            fn=getattr(native,f'f{k}');fn.argtypes=[ctypes.c_int,ctypes.c_int];fn.restype=ctypes.c_int
            for n in range(6):
                for m in range(6):
                    predicted=summary.report({'n':n,'m':m})['return_value'];actual=fn(n,m)
                    if predicted!=actual:raise AssertionError((k,n,m,predicted,actual))
                    count+=1
    print(f'Counted nested memory / native C checks: {count}/{count} passed')


if __name__=='__main__':main()
