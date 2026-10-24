"""Native C/UBSan checks for compositional typed nested-loop certificates."""
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_nested import TypedCNested
from llmloop.typed_recurrence import TypedCRecurrence

ROOT=Path(__file__).resolve().parents[1]
RECT=(ROOT/'examples/typed_nested_loop.c').read_text()
RECT_FORMS=json.loads((ROOT/'examples/typed_nested_summaries.json').read_text())
ODD='''long odd_sum(int n){long x=0;for(int i=0;i<n;i++){
    for(int j=0;j<2*i+1;j++){x++;}}return x;}'''
CUBE='''int cube_wrap(int n,int m,int p){unsigned char x=0;
    for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<p;k++){x++;}}}return x;}'''
SEQ='''long sequence(int n,int m){long x=0;for(int i=0;i<n;i++){x++;}
    x=2*x+3;for(int j=0;j<m;j++){x+=2;}return x;}'''
NAMESPACE='''int namespace_guard(int n,int counter_i){int x=0;
    for(int i=0;i<n;i++){x++;}return x;}'''


def main():
    cases=[
        ('nested_typed',RECT,RECT_FORMS,{'n':[0,1000],'m':[0,1000]},ctypes.c_long,
         [(n,m) for n in range(9) for m in range(9)]+[(1000,1000)]),
        ('odd_sum',ODD,{'i':{'x':'i*i'},'j':{'x':'entry("x")+j'}},{'n':[0,1000000]},ctypes.c_long,
         [(n,) for n in range(31)]+[(1000,)]),
        ('cube_wrap',CUBE,{'i':{'x':'i*m*p%256'},'j':{'x':'(entry("x")+j*p)%256'},'k':{'x':'(entry("x")+k)%256'}},
         {'n':[0,100],'m':[0,100],'p':[0,100]},ctypes.c_int,
         [(n,m,p) for n in range(9) for m in range(9) for p in [0,1,3]]+[(100,100,100)]),
        ('sequence',SEQ,{'i':{'x':'entry("x")+i'},'j':{'x':'entry("x")+2*j'}},
         {'n':[0,1000000],'m':[0,1000000]},ctypes.c_long,
         [(n,m) for n in range(9) for m in range(9)]+[(1000000,10)])
    ]
    counts={}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'nested.c';source.write_text('\n'.join(case[1] for case in cases)+'\n'+NAMESPACE)
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'nested.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'nested.so'))
        for name,code,summaries,bounds,return_type,inputs in cases:
            engine=TypedCNested(code,summaries,parameter_bounds=bounds)
            report=engine.report()
            if report['status']!='PROVED_DEFINED_TYPED_C_NESTED':raise AssertionError(report)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int]*len(bounds);fn.restype=return_type;counts[name]=0
            for values in inputs:
                expected=engine.report(dict(zip(bounds,values)))['evaluation']['value'];actual=fn(*values)
                if expected!=actual:raise AssertionError((name,values,expected,actual))
                counts[name]+=1
        bad=TypedCRecurrence(NAMESPACE,{'x':'0 if i==0 else 1'},parameter_bounds={'n':[2,3],'counter_i':[0,0]}).report()
        if bad['status']!='UNKNOWN':raise AssertionError('Internal symbol collision masked a wrong candidate')
        engine=TypedCRecurrence(NAMESPACE,{'x':'i'},parameter_bounds={'n':[0,100],'counter_i':[0,0]})
        if engine.report()['status']!='PROVED_DEFINED_TYPED_C_RECURRENCE':raise AssertionError(engine.report())
        fn=native.namespace_guard;fn.argtypes=[ctypes.c_int,ctypes.c_int];fn.restype=ctypes.c_int;counts['namespace_guard']=0
        for n in range(101):
            expected=engine.report({'n':n,'counter_i':0})['evaluation']['value']
            if fn(n,0)!=expected:raise AssertionError(n)
            counts['namespace_guard']+=1
    for name,count in counts.items():print(f'{name} typed nested / native C+UBSan: {count}/{count} passed')


if __name__=='__main__':main()
