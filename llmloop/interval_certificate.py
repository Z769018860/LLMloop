"""Exact rational interval certificates for candidate range obligations only.

No source operation is evaluated/assumed defined here. Bounds are consequences
of conjunctive premises; unsupported arithmetic returns no certificate.
"""
from fractions import Fraction
import math
import z3


def prove_interval(premise,claim):
    constraints=[];pending=[premise]
    while pending:
        n=pending.pop()
        if z3.is_and(n):pending.extend(n.children())
        else:constraints.append(n)
    if len(constraints)>256:return None
    bounds={};variables={}
    def atom(n):return z3.is_const(n) and z3.is_int(n) and n.decl().kind()==z3.Z3_OP_UNINTERPRETED
    def interval(root):
        memo={};visits=0
        def get(n):
            nonlocal visits
            key=n.get_id()
            if key in memo:return memo[key]
            visits+=1
            if visits>512:raise ValueError('interval node budget')
            k=n.decl().kind();c=n.children();answer=None
            if z3.is_int_value(n):answer=(Fraction(n.as_long()),)*2
            elif z3.is_rational_value(n):answer=(Fraction(n.numerator_as_long(),n.denominator_as_long()),)*2
            elif atom(n):
                value=bounds.get(key);answer=value if value is not None and None not in value else None
            elif k==z3.Z3_OP_MOD and z3.is_int_value(c[1]) and c[1].as_long()>0:answer=(Fraction(0),Fraction(c[1].as_long()-1))
            elif k in (z3.Z3_OP_TO_REAL,z3.Z3_OP_TO_INT):
                a=get(c[0])
                if a:answer=tuple(Fraction(math.floor(v)) for v in a) if k==z3.Z3_OP_TO_INT else a
            elif k==z3.Z3_OP_ITE:
                a,b=get(c[1]),get(c[2])
                if a and b:answer=(min(a[0],b[0]),max(a[1],b[1]))
            elif k==z3.Z3_OP_UMINUS:
                a=get(c[0])
                if a:answer=(-a[1],-a[0])
            elif k in (z3.Z3_OP_ADD,z3.Z3_OP_MUL,z3.Z3_OP_SUB):
                parts=[get(v) for v in c]
                if all(v is not None for v in parts):
                    answer=parts[0]
                    for b in parts[1:]:
                        a=answer
                        if k==z3.Z3_OP_ADD:answer=(a[0]+b[0],a[1]+b[1])
                        elif k==z3.Z3_OP_SUB:answer=(a[0]-b[1],a[1]-b[0])
                        else:
                            products=[x*y for x in a for y in b];answer=(min(products),max(products))
            elif k in (z3.Z3_OP_DIV,z3.Z3_OP_IDIV):
                a,b=get(c[0]),get(c[1])
                if a and b and b[0]==b[1] and b[0]>0:
                    answer=(a[0]/b[0],a[1]/b[0])
                    if k==z3.Z3_OP_IDIV:answer=tuple(Fraction(math.floor(v)) for v in answer)
            elif k==z3.Z3_OP_POWER:
                a,b=get(c[0]),get(c[1])
                if a and b and b[0]==b[1] and b[0].denominator==1 and 0<=b[0]<=8:
                    power=int(b[0]);ends=[v**power for v in a]
                    answer=(Fraction(0) if power and power%2==0 and a[0]<=0<=a[1] else min(ends),max(ends))
            if answer and any(abs(v.numerator).bit_length()>4096 or v.denominator.bit_length()>4096 for v in answer):answer=None
            memo[key]=answer;return answer
        try:return get(root)
        except (ValueError,RecursionError):return None
    for _ in range(32):
        changed=False
        for n in constraints:
            k=n.decl().kind()
            if k not in (z3.Z3_OP_LE,z3.Z3_OP_LT,z3.Z3_OP_GE,z3.Z3_OP_GT,z3.Z3_OP_EQ) or len(n.children())!=2:continue
            a,b=n.children()
            if k in (z3.Z3_OP_GE,z3.Z3_OP_GT):a,b=b,a
            pairs=[(a,b,False),(b,a,True)]
            for target,other,lower in pairs:
                if not atom(target):continue
                value=interval(other)
                if not value:continue
                key=target.get_id();old=bounds.get(key,(None,None));lo,hi=old
                if k==z3.Z3_OP_EQ:
                    lo=max(lo,value[0]) if lo is not None else value[0];hi=min(hi,value[1]) if hi is not None else value[1]
                elif lower:
                    limit=math.floor(value[0])+1 if k in (z3.Z3_OP_LT,z3.Z3_OP_GT) else math.ceil(value[0]);lo=max(lo,limit) if lo is not None else Fraction(limit)
                else:
                    limit=math.ceil(value[1])-1 if k in (z3.Z3_OP_LT,z3.Z3_OP_GT) else math.floor(value[1]);hi=min(hi,limit) if hi is not None else Fraction(limit)
                if lo is not None and hi is not None and lo>hi:return None
                if (lo,hi)!=old:bounds[key]=(lo,hi);variables[key]=target;changed=True
        if not changed:break
    bounds={k:v for k,v in bounds.items() if None not in v}
    def valid(n):
        if z3.is_true(n):return True
        if z3.is_and(n):return all(valid(v) for v in n.children())
        k=n.decl().kind()
        if k not in (z3.Z3_OP_LE,z3.Z3_OP_LT,z3.Z3_OP_GE,z3.Z3_OP_GT,z3.Z3_OP_EQ):return False
        a,b=map(interval,n.children())
        if not a or not b:return False
        return {z3.Z3_OP_LE:lambda:a[1]<=b[0],z3.Z3_OP_LT:lambda:a[1]<b[0],z3.Z3_OP_GE:lambda:a[0]>=b[1],z3.Z3_OP_GT:lambda:a[0]>b[1],z3.Z3_OP_EQ:lambda:a[0]==a[1]==b[0]==b[1]}[k]()
    if not valid(claim):return None
    return {'method':'exact rational interval enclosure','bounds':{str(variables[k]):[str(a),str(b)] for k,(a,b) in bounds.items()}}
