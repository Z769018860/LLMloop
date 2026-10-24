"""Independent native LP64/UBSan differential oracle for the exact integer lift."""
from pathlib import Path
import subprocess
import tempfile
import z3
from llmloop.integer_lift import IntegerLift
from llmloop.c_integers import UndefinedInteger


def main():
    engine=IntegerLift();cases=[]
    names=['signed char','unsigned char','short','unsigned short','int','unsigned int','long','unsigned long','long long','unsigned long long']
    for left in names:
        for right in names:
            for x,y in [(-7,3),(127,1),(0,2),(-1,-1)]:
                a,b=engine.abi.value(x,left),engine.abi.value(y,right)
                for op in ['+','-','*','/','%','&','|','^','<','==','<<','>>']:
                    try:engine.abi.binary(op,a,b)
                    except UndefinedInteger:continue
                    tree={'op':op,'args':[{'value':a.value,'type':left},{'value':b.value,'type':right}]}
                    engine.nodes=0;term=engine.lower(tree)
                    if not z3.is_true(z3.simplify(term.safe)):raise AssertionError(tree)
                    expression=f'((({left})({a.value if a.value>=0 else "("+str(a.value)+")"}{"ULL" if a.value>=0 else ""})) {op} (({right})({b.value if b.value>=0 else "("+str(b.value)+")"}{"ULL" if b.value>=0 else ""})))'
                    cases.append((expression,z3.simplify(term.value).as_long(),term.type))
    rank='_Generic((EXPR),char:1,signed char:1,unsigned char:1,short:2,unsigned short:2,int:3,unsigned int:3,long:4,unsigned long:4,long long:5,unsigned long long:5)'
    lines=['#include <stdio.h>','#include <limits.h>',
           '_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"LP64 required");','int main(void){']
    for expression,_,_ in cases:
        lines.append('printf("%llu,%zu,%d,%d\\n",(unsigned long long)('+expression+'),sizeof('+expression+'),((__typeof__('+expression+'))-1 < (__typeof__('+expression+'))0),'+rank.replace('EXPR',expression)+');')
    lines.append('return 0;}')
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'lift.c';source.write_text('\n'.join(lines))
        subprocess.run(['cc','-w','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(path/'lift')],check=True,capture_output=True)
        output=subprocess.run([str(path/'lift')],check=True,capture_output=True,text=True).stdout.splitlines()
        if len(output)!=len(cases):raise AssertionError('Native output length mismatch')
        for (expression,value,t),line in zip(cases,output):
            expected=(value%(1<<64),max(1,t.bits//8),int(t.signed),t.rank)
            actual=tuple(map(int,line.split(',')))
            if actual!=expected:raise AssertionError((expression,expected,actual))
    print(f'Exact typed integer lift / LP64+UBSan: {len(cases)}/{len(cases)} passed')


if __name__=='__main__':main()
