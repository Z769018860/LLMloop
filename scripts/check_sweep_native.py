"""Finite native C regression for dynamic-index pointwise sweep summaries."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.sweep_c import translate_sweep_c
from llmloop.sweep_memory import SweepMemory

CASES=[
'int f(int n,int m){int *p=calloc(n*m,sizeof(int));int i=0;int j=0;for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){p[i*m+j]=p[i*m+j]+i+j;}}return p[n*m-1];}',
'int f(int n,int m){int *p=calloc(n*m,sizeof(int));int *q=p+1;int i=0;for(i=0;i<n;i=i+1){p[i]=p[i]+i;}for(i=0;i<n-1;i=i+1){q[i]=q[i]+10;}return p[n-1];}',
'int f(int n,int m){int *p=calloc(n*m,sizeof(int));int *q=p;int i=0;int j=0;for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){q[i*m+j]=q[i*m+j]+1;}}free(q);return 0;}'
]


def main():
    count=0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'sweeps.c'
        source.write_text('#include <stdlib.h>\n'+'\n'.join(src.replace('int f(',f'int f{k}(') for k,src in enumerate(CASES)))
        subprocess.run(['cc','-shared','-fPIC','-O0',str(source),'-o',str(path/'sweeps.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'sweeps.so'))
        for k,src in enumerate(CASES):
            obj=translate_sweep_c(src,parameter_bounds={'n':[1,6],'m':[1,6]},signed_bits=32)
            engine=SweepMemory(obj)
            for n in range(1,7):
                for m in range(1,7):
                    report=engine.report({'n':n,'m':m})
                    if report['status']!='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY':raise AssertionError(report)
                    predicted=report['queries'][0]['value'] if report['queries'] else 0
                    fn=getattr(native,f'f{k}');fn.argtypes=[ctypes.c_int,ctypes.c_int];fn.restype=ctypes.c_int
                    actual=fn(n,m)
                    if predicted!=actual:raise AssertionError((k,n,m,predicted,actual))
                    count+=1
    print(f'Dynamic sweep / native C checks: {count}/{count} passed')


if __name__=='__main__':main()
