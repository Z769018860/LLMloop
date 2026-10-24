"""Native C regression for typed source, private allocation folds and scans."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_c import TypedCFunction
from llmloop.private_allocations import PrivateAllocations
from llmloop.scan_c import translate_scan_c
from llmloop.linear_scan import LinearScan

TYPED=[
('int f(unsigned char x,int y){unsigned char z=x;z=z+1;if(y<0){return z;}return z+y;}',ctypes.c_int),
('unsigned long f(unsigned char x,int y){return sizeof(long)+(unsigned long)(x+y);}',ctypes.c_ulong),
('int f(unsigned char x,int y){int s=0;for(int i=0;i<x;i=i+1){s=s+i;}if(y<0){return s;}return s+y;}',ctypes.c_int),
('int f(unsigned char x,int y){signed char z=(signed char)x;z++;return z+(y/2);}',ctypes.c_int)
]
PRIVATE=[
'int f(int n,int m){int x=0;int i=0;for(i=0;i<n;i=i+1){int *p=calloc(2,sizeof(int));int *q=p;p[0]=i+m;q[1]=p[0]+1;x=x+q[1];free(q);}return x;}',
'int f(int n,int m){int x=0;int i=0;int j=0;for(i=0;i<n;i=i+1){int *p=calloc(1,sizeof(int));p[0]=i;for(j=0;j<m;j=j+1){int *q=calloc(1,sizeof(int));q[0]=p[0]+j;x=x+q[0];free(q);}free(p);}return x;}'
]
SCANS=[
'int f(int n){int *p=calloc(n,sizeof(int));int i=0;p[0]=1;for(i=1;i<n;i=i+1){p[i]=p[i-1]+2;}return p[n-1];}',
'int f(int n){int *p=calloc(n,sizeof(int));int i=0;p[0]=0;p[1]=1;for(i=2;i<n;i=i+1){p[i]=p[i-1]+p[i-2];}return p[n-1];}',
'int f(int n){int *p=calloc(n,sizeof(int));int *q=p;int i=0;p[0]=0;for(i=1;i<n;i=i+1){q[i]=p[i-1]+i;}return q[n-1];}'
]


def main():
    counts={'typed_source':0,'private_allocation':0,'cross_cell_scan':0}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        sources=[src.replace(' f(',f' typed{k}(') for k,(src,_) in enumerate(TYPED)]
        sources +=[src.replace(' f(',f' private{k}(') for k,src in enumerate(PRIVATE)]
        sources +=[src.replace(' f(',f' scan{k}(') for k,src in enumerate(SCANS)]
        unit=path/'remaining.c';unit.write_text('#include <stdlib.h>\n'+'\n'.join(sources))
        subprocess.run(['cc','-shared','-fPIC','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(unit),'-o',str(path/'remaining.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'remaining.so'))
        for k,(source,result_type) in enumerate(TYPED):
            domain=[0,5] if k==2 else [0,255]
            samples=range(6) if k==2 else [0,1,127,128,254,255]
            engine=TypedCFunction(source,parameter_bounds={'x':domain,'y':[-3,3]},max_unroll=5)
            fn=getattr(native,f'typed{k}');fn.argtypes=[ctypes.c_ubyte,ctypes.c_int];fn.restype=result_type
            for x in samples:
                for y in range(-3,4):
                    report=engine.report({'x':x,'y':y})
                    if report['status']!='PROVED_DEFINED_TYPED_C_FUNCTION':raise AssertionError(report)
                    predicted=report['evaluation']['value'];actual=fn(x,y)
                    if predicted!=actual:raise AssertionError(('typed',k,x,y,predicted,actual))
                    counts['typed_source']+=1
        for k,source in enumerate(PRIVATE):
            engine=PrivateAllocations(source,parameter_mins={'n':0,'m':0})
            fn=getattr(native,f'private{k}');fn.argtypes=[ctypes.c_int,ctypes.c_int];fn.restype=ctypes.c_int
            for n in range(6):
                for m in range(6):
                    predicted=engine.report({'n':n,'m':m})['return_value'];actual=fn(n,m)
                    if predicted!=actual:raise AssertionError(('private',k,n,m,predicted,actual))
                    counts['private_allocation']+=1
        for k,source in enumerate(SCANS):
            engine=LinearScan(translate_scan_c(source,parameter_bounds={'n':[2,20]},signed_bits=None if k==1 else 32))
            fn=getattr(native,f'scan{k}');fn.argtypes=[ctypes.c_int];fn.restype=ctypes.c_int
            for n in range(2,21):
                report=engine.report({'n':n})
                if report['status']!='CERTIFIED_UNBOUNDED_LINEAR_MEMORY_SCAN':raise AssertionError(report)
                predicted=report['queries'][0]['value'];actual=fn(n)
                if predicted!=actual:raise AssertionError(('scan',k,n,predicted,actual))
                counts['cross_cell_scan']+=1
    for name,count in counts.items():print(f'{name} / native C: {count}/{count} passed')


if __name__=='__main__':main()
