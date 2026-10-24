"""Differential reference checks for typed C integer expressions on LP64 cc.

Only kernel-defined expressions are executed; UB is separately unit-tested.
The native compiler determines value, result width, signedness and integer rank.
"""
from pathlib import Path
import subprocess
import tempfile
from llmloop.c_integers import IntegerABI,UndefinedInteger


def main():
    abi=IntegerABI();cases=[]
    names=['signed char','unsigned char','short','unsigned short','int','unsigned int','long','unsigned long','long long','unsigned long long']
    for left in names:
        for right in names:
            for x,y in [(-7,3),(127,1),(0,2),(-1,-1)]:
                a,b=abi.value(x,left),abi.value(y,right)
                for op in ['+','-','*','/','%','&','|','^','<','==','<<','>>']:
                    try:expected=abi.binary(op,a,b)
                    except UndefinedInteger:continue
                    expr=f'((({left})({a.value}LL)) {op} (({right})({b.value}LL)))'
                    cases.append((expr,expected))
    rank='_Generic((EXPR),char:1,signed char:1,unsigned char:1,short:2,unsigned short:2,int:3,unsigned int:3,long:4,unsigned long:4,long long:5,unsigned long long:5)'
    lines=['#include <stdio.h>','#include <limits.h>',
           '_Static_assert(sizeof(long)==8 && sizeof(int)==4 && CHAR_BIT==8,"requires LP64");','int main(void){']
    for expr,_ in cases:
        lines.append('printf("%llu,%zu,%d,%d\\n",(unsigned long long)('+expr+'),sizeof('+expr+'),((__typeof__('+expr+'))-1 < (__typeof__('+expr+'))0),'+rank.replace('EXPR',expr)+');')
    lines+=['return 0;}']
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);(path/'integer.c').write_text('\n'.join(lines))
        subprocess.run(['cc','-w','-std=c11','-O0',str(path/'integer.c'),'-o',str(path/'integer')],check=True,capture_output=True)
        output=subprocess.run([str(path/'integer')],check=True,capture_output=True,text=True).stdout.splitlines()
        if len(output)!=len(cases):raise AssertionError('Native output length mismatch')
        for (expr,value),line in zip(cases,output):
            actual=tuple(int(x) for x in line.split(','))
            expected=(value.value%(1<<64),value.type.bits//8,int(value.type.signed),value.type.rank)
            if actual!=expected:raise AssertionError((expr,actual,expected))
    print(f'Typed integer / native LP64 checks: {len(cases)}/{len(cases)} passed')


if __name__=='__main__':main()
