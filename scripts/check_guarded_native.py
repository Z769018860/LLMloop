"""Compare nonperiodic branching closed forms to native C under UBSan."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
import sympy as s
from llmloop.periodic_c import analyze_guarded_c

CASES = [
    ('saturation', (Path(__file__).resolve().parents[1]/'examples/guarded_saturation.c').read_text(),
     {'x':'Min(i,limit)'}, {'limit':[0,None]}),
    ('slope', '''int slope(int steps,int limit) {int x=0; int clock=0;
        for(int i=0;i<steps;i=i+1) {
            if(clock<limit) {x=x+1; clock=clock+1;}
            else {x=x+2; clock=clock+1;}
        } return x;}''', {'x':'i if i < limit else 2*i-limit','clock':'i'}, {'limit':[0,None]}),
    ('countdown', '''int countdown(int steps,int limit) {int x=limit;
        for(int i=0;i<steps;i=i+1) {
            if(x>0) {x=x-1;} else {x=x;}
        } return x;}''', {'x':'Max(limit-i,0)'}, {'limit':[0,None]}),
    ('normalize', '''int normalize(int steps,int a) {int x=a;
        for(int i=0;i<steps;i=i+1) {
            if(x<0) {x=-x;} else {x=x;}
        } return x;}''', {'x':'a if i == 0 else Abs(a)'}, {})
]


def main():
    counts = {}
    with tempfile.TemporaryDirectory() as tmp:
        source, library = Path(tmp)/'guarded.c', Path(tmp)/'guarded.so'
        source.write_text('\n'.join(case[1] for case in CASES))
        subprocess.run(['cc','-std=c11','-O0','-shared','-fPIC','-fsanitize=undefined',
                        '-fno-sanitize-recover=undefined',str(source),'-o',str(library)],check=True)
        native = ctypes.CDLL(str(library))
        for name, code, forms, bounds in CASES:
            report = analyze_guarded_c(code,forms,parameter_bounds=bounds)
            if report['status'] != 'CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM':raise AssertionError(report)
            fn = getattr(native,name);fn.argtypes = [ctypes.c_int,ctypes.c_int];fn.restype = ctypes.c_int
            param = 'a' if name == 'normalize' else 'limit'
            steps, symbol = s.symbols('steps '+param,integer=True)
            formula = s.sympify(report['return_expr'],locals={'steps':steps,param:symbol})
            counts[name] = 0
            for count in list(range(-3,31))+[1000000]:
                for value in range(-10,11) if param == 'a' else range(11):
                    predicted = int(formula.subs({steps:count,symbol:value}))
                    actual = fn(count,value)
                    if predicted != actual:raise AssertionError((name,count,value,predicted,actual))
                    counts[name] += 1
    for name,count in counts.items():print(f'{name} guarded C/UBSan: {count}/{count} passed')


if __name__ == '__main__':main()
