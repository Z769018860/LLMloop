"""Unroll-free typed loop certificates versus native scalar C/UBSan."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_recurrence import TypedCRecurrence

CASES=[
    ('typed_loop',(Path(__file__).resolve().parents[1]/'examples/typed_unbounded_loop.c').read_text(),
     {'byte':'(250+i)%256','total':'i'},ctypes.c_long),
    ('signed_narrow','''int signed_narrow(int n){signed char x=-128;
        for(int i=0;i<n;i++){x++;}return x;}''',{'x':'i%256-128'},ctypes.c_int),
    ('boolean_toggle','''int boolean_toggle(int n){_Bool flag=0;
        for(int i=0;i<n;i++){flag=!flag;}return flag;}''',{'flag':'i%2'},ctypes.c_int),
    ('saturating_byte','''int saturating_byte(int n){unsigned char x=0;
        for(int i=0;i<n;i++){if(x<255){x++;}else{x=x;}}return x;}''',{'x':'Min(i,255)'},ctypes.c_int)
]


def main():
    counts={}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'loops.c';source.write_text('\n'.join(case[1] for case in CASES))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'loops.so')],check=True,capture_output=True)
        native=ctypes.CDLL(str(path/'loops.so'))
        for name,code,forms,result_type in CASES:
            engine=TypedCRecurrence(code,forms,parameter_bounds={'n':[-3,1000000000]})
            report=engine.report()
            if report['status']!='PROVED_DEFINED_TYPED_C_RECURRENCE':raise AssertionError(report)
            fn=getattr(native,name);fn.argtypes=[ctypes.c_int];fn.restype=result_type;counts[name]=0
            for n in [-3]+list(range(41))+[127,128,254,255,256,257,511,512,1000000]:
                predicted=engine.report({'n':n})['evaluation']['value'];actual=fn(n)
                if predicted!=actual:raise AssertionError((name,n,predicted,actual))
                counts[name]+=1
    for name,count in counts.items():print(f'{name} typed recurrence / native C+UBSan: {count}/{count} passed')


if __name__=='__main__':main()
