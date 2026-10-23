"""Independent finite native-C regression oracle; requires a C compiler.

Run after installation: python scripts/check_memory_native.py
This comparison is regression evidence, not a universal equivalence proof.
"""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.memory_frontend import translate_memory_c
from llmloop.smt_spath import SMTPathGraph

CASES = [
    'int f(int n){int a[2]={4,9};int *p=&a[1];int *q=p;int i=0;int x=0;while(i<n){*q+=3;*p-=1;*q*=2;x=*q;i++;}return x;}',
    'int f(int n){int *p=0;int i=0;int x=0;while(i<n){if(1 || p[3]){x+=2;}if(0 && p[3]){x+=100;}i++;}return x;}',
    'int f(int n){int a[3]={1,2,3};int i=0;int j=0;int x=0;while(i<n){for(j=0;j<3;j++){a[j]+=i+1;}i++;}for(j=0;j<3;j++){x+=a[j];}return x;}'
]


def main():
    count=0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        (path/'cases.c').write_text('\n'.join(source.replace('int f(',f'int f{k}(')
                                              for k,source in enumerate(CASES)),encoding='utf-8')
        subprocess.run(['cc','-shared','-fPIC','-O0',str(path/'cases.c'),'-o',str(path/'cases.so')],check=True)
        native=ctypes.CDLL(str(path/'cases.so'))
        for k,source in enumerate(CASES):
            graph=SMTPathGraph(translate_memory_c(source,whole_function=True,max_unroll=4,
                                                 parameter_bounds={'n':[0,4]}))
            function=getattr(native,f'f{k}')
            function.argtypes=[ctypes.c_int];function.restype=ctypes.c_int
            for n in range(5):
                actual=function(n)
                predicted=graph.concrete({'n':n})['final_state']['x']
                if actual!=predicted:raise AssertionError((k,n,actual,predicted))
                count+=1
    print(f'Native C differential checks: {count}/{count} passed')


if __name__=='__main__':main()
