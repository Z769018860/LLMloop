"""Exhaustive integer-residue splitting for difficult successor obligations.

For every integer x there are unique integers q,r with x=p*q+r, 0<=r<p.
Every substituted implication must be independently UNSAT. No sampling or
assumed branch schedule is used; unsuccessful splitting falls back to the caller.
"""
import math
import z3
from .proof_normalization import normalize_polynomial_floors


def prove_residues(premise,claim,witness,timeout=5000):
    period=1;pending=[premise,claim];seen=set();small=[]
    while pending:
        n=pending.pop();key=n.get_id()
        if key in seen:continue
        seen.add(key)
        if len(seen)>4096:return None
        if n.decl().kind() in (z3.Z3_OP_MOD,z3.Z3_OP_IDIV) and z3.is_int_value(n.arg(1)):
            divisor=n.arg(1).as_long()
            if 1<divisor<=8:period=math.lcm(period,divisor);small.append(n.arg(0))
        pending.extend(n.children())
    if not 1<period<=8:return None
    def contains(root,target):
        todo=[root];visited=set()
        while todo:
            n=todo.pop()
            if n.eq(target):return True
            if n.get_id() in visited:continue
            visited.add(n.get_id());todo.extend(n.children())
        return False
    for name,counter in reversed(list(witness.items())):
        if not z3.is_const(counter) or not z3.is_int(counter) or counter.decl().kind()!=z3.Z3_OP_UNINTERPRETED:continue
        if not any(contains(n,counter) for n in small):continue
        quotient=z3.FreshInt('residue_quotient');cases=[]
        for residue in range(period):
            substitution=(counter,period*quotient+residue)
            p=z3.simplify(z3.substitute(premise,substitution),som=True,pull_cheap_ite=True)
            c=z3.simplify(z3.substitute(claim,substitution),som=True,pull_cheap_ite=True)
            p=z3.simplify(normalize_polynomial_floors(p),som=True,pull_cheap_ite=True)
            c=z3.simplify(normalize_polynomial_floors(c),som=True,pull_cheap_ite=True)
            solver=z3.Solver();solver.set(timeout=timeout);solver.add(p,z3.Not(c))
            if solver.check()!=z3.unsat:return None
            cases.append({'residue':residue,'proved':True})
        return {'method':'exhaustive integer residue substitution','counter':name,'period':period,'subquery_timeout_ms':timeout,'cases':cases}
    return None
