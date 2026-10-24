"""Independent native/UBSan checks for typed SMT integer results on LP64."""
from pathlib import Path
import subprocess
import tempfile
from llmloop.symbolic_integers import SymbolicIntegers
from llmloop.c_integers import IntegerABI


def main():
    abi=IntegerABI();cases=[]
    operations=['+','-','*','/','%','&','|','^','<','<=','>','>=','==','!=','<<','>>']
    for left,right,a,b in [('int','unsigned int',-7,3),('short','unsigned char',7,2),('long','unsigned int',-4,1)]:
        for op in operations:
            obj={'kind':'c_integer_symbolic','variables':{'a':{'type':left,'bounds':[a,a]},'b':{'type':right,'bounds':[b,b]}},
                 'expression':{'op':op,'args':[{'var':'a'},{'var':'b'}]}}
            report=SymbolicIntegers(obj).report({'a':a,'b':b})
            if report['status']=='POSSIBLE_UNDEFINED_INTEGER_OPERATION':continue
            if report['status']!='PROVED_DEFINED_INTEGER_EXPRESSION':raise AssertionError(report)
            expression=f'((({left})({a}LL)) {op} (({right})({b}LL)))'
            cases.append((expression,report))
    rank='_Generic((EXPR),char:1,signed char:1,unsigned char:1,short:2,unsigned short:2,int:3,unsigned int:3,long:4,unsigned long:4,long long:5,unsigned long long:5)'
    lines=['#include <stdio.h>','#include <limits.h>',
           '_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");','int main(void){']
    for expression,_ in cases:
        lines.append('printf("%llu,%zu,%d,%d\\n",(unsigned long long)('+expression+'),sizeof('+expression+'),((__typeof__('+expression+'))-1 < (__typeof__('+expression+'))0),'+rank.replace('EXPR',expression)+');')
    lines.append('return 0;}')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'symbolic.c';source.write_text('\n'.join(lines))
        subprocess.run(['cc','-w','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'symbolic')],check=True,capture_output=True)
        native=subprocess.run([str(path/'symbolic')],check=True,capture_output=True,text=True).stdout.splitlines()
        if len(native)!=len(cases):raise AssertionError('Native output mismatch')
        for (expression,report),line in zip(cases,native):
            t=abi.types[report['type']]
            expected=(report['evaluation']['value']%(1<<64),t.bits//8,int(t.signed),t.rank)
            actual=tuple(int(x) for x in line.split(','))
            if expected!=actual:raise AssertionError((expression,expected,actual))
    print(f'Typed SMT / native LP64+UBSan checks: {len(cases)}/{len(cases)} passed')


if __name__=='__main__':main()
