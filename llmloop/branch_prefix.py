"""Untrusted disjoint branch-prefix candidates; original typed proof is mandatory.

Nested/sequential Boolean counter guards are partitioned into exact integer
intervals, optionally over small residue classes. No sampled schedule is trusted.
"""
import math
import sympy as s
from pycparser import c_ast
from .smt_spath import SMTGraphError


def discover(builder,loop,env,mutable,k,clock,ancestors):
    index=loop.init.decls[0].name
    condition_nodes=[]
    class Branches(c_ast.NodeVisitor):
        def visit_If(self,n):condition_nodes.append(n.cond);self.generic_visit(n)
    Branches().visit(loop.stmt)
    if not condition_nodes:return None
    # Preserve the older simple threshold/saturation representations.
    if len(condition_nodes)==1:
        c=condition_nodes[0]
        if isinstance(c,c_ast.BinaryOp) and c.op in ('<','<=','>','>=') and isinstance(c.left,c_ast.ID):return None
    if len(condition_nodes)>6:raise SMTGraphError('Branch-prefix syntax budget is 6 conditions')
    period=1;branch_nodes=0;boolean_nodes=0
    def arithmetic(n,e):
        nonlocal period
        if isinstance(n,c_ast.BinaryOp) and n.op=='%':
            a=arithmetic(n.left,e);b=arithmetic(n.right,e)
            if not b.is_Integer or not 1<=b<=8:raise SMTGraphError('Branch residue modulus must be 1..8')
            period=math.lcm(period,int(b))
            if period>8:raise SMTGraphError('Branch residue period budget is 8')
            return s.Mod(a,b)
        return builder.arithmetic(n,e)
    def condition(n,e):
        nonlocal boolean_nodes
        boolean_nodes+=1
        if boolean_nodes>256:raise SMTGraphError('Branch Boolean extraction budget exceeded')
        if isinstance(n,c_ast.BinaryOp) and n.op in ('&&','||'):
            return (s.And if n.op=='&&' else s.Or)(condition(n.left,e),condition(n.right,e))
        if isinstance(n,c_ast.UnaryOp) and n.op=='!':return s.Not(condition(n.expr,e))
        if isinstance(n,c_ast.BinaryOp) and n.op in ('<','<=','>','>=','==','!='):
            a,b=arithmetic(n.left,e),arithmetic(n.right,e)
            return {'<':s.Lt,'<=':s.Le,'>':s.Gt,'>=':s.Ge,'==':s.Eq,'!=':s.Ne}[n.op](a,b)
        raise SMTGraphError('Branch-prefix needs Boolean integer comparisons')
    def alternatives(c,truth=True):
        if c is s.true:return [[]] if truth else []
        if c is s.false:return [] if truth else [[]]
        if c.func==s.Not:return alternatives(c.args[0],not truth)
        if c.func in (s.And,s.Or):
            args=list(c.args);left=args[0];right=c.func(*args[1:])
            def cap(rows):
                if len(rows)>32:raise SMTGraphError('Disjoint Boolean alternative budget is 32')
                return rows
            def product(a,b):
                if len(a)*len(b)>32:raise SMTGraphError('Disjoint Boolean product budget is 32')
                return [x+y for x in a for y in b]
            if c.func==s.And:
                return product(alternatives(left),alternatives(right)) if truth else cap(alternatives(left,False)+product(alternatives(left),alternatives(right,False)))
            return cap(alternatives(left)+product(alternatives(left,False),alternatives(right))) if truth else product(alternatives(left,False),alternatives(right,False))
        if not truth:c=s.Not(c)
        if c.func==s.Ne:return [[s.Lt(c.lhs,c.rhs)],[s.Gt(c.lhs,c.rhs)]]
        return [[c]]
    def execute(node,states):
        nonlocal branch_nodes
        branch_nodes+=1
        if branch_nodes>256:raise SMTGraphError('Branch-prefix extraction budget exceeded')
        if isinstance(node,c_ast.Compound):
            for child in node.block_items or []:states=execute(child,states)
            return states
        if isinstance(node,c_ast.If):
            out=[]
            for guards,e in states:
                c=condition(node.cond,e)
                for truth,arm in ((True,node.iftrue),(False,node.iffalse)):
                    for parts in alternatives(c,truth):out.extend(execute(arm,[(guards+parts,dict(e))]))
                if len(out)>32:raise SMTGraphError('Disjoint branch path budget is 32')
            return out
        return [(g,builder.lower(node,dict(e),set(ancestors)|{index})) for g,e in states]
    paths=execute(loop.stmt,[([],dict(env))]);state_symbols=set().union(*(env[name].free_symbols for name in mutable))
    result=dict(env);totals={name:s.Integer(0) for name in mutable};q=s.Dummy('residue_counter',integer=True,nonnegative=True)
    def prefix(expr,count):
        try:p=s.Poly(s.expand(expr),q)
        except s.PolynomialError as exc:raise SMTGraphError('Branch increments must be polynomial') from exc
        if p.degree()>3:raise SMTGraphError('Branch increment degree budget is 3')
        sums=[count,count*(count-1)/2,count*(count-1)*(2*count-1)/6,(count*(count-1)/2)**2]
        return sum(coef*sums[power[0]] for power,coef in p.terms())
    regions=0
    for guards,after in paths:
        deltas={name:builder.bounded(s.expand(after[name]-env[name])) for name in mutable}
        if any(v.free_symbols & state_symbols for v in deltas.values()):raise SMTGraphError('Branch-prefix requires state-independent additive deltas')
        for r in range(period):
            lo=s.Integer(0);hi=s.ceiling((k-r)/period);immutable=[];impossible=False
            for guard in guards:
                c=s.simplify(guard.subs(clock,period*q+r))
                if c is s.false:impossible=True;break
                if c is s.true:continue
                if not isinstance(c,s.core.relational.Relational):raise SMTGraphError('Residue branch did not reduce to a comparison')
                expr=s.expand(c.lhs-c.rhs)
                if expr.free_symbols & state_symbols:raise SMTGraphError('State-feedback branch requires supplied trajectory')
                if q not in expr.free_symbols:immutable.append(c);continue
                try:p=s.Poly(expr,q)
                except s.PolynomialError as exc:raise SMTGraphError('Branch guard must be affine in counter') from exc
                a=p.coeff_monomial(q);b=p.coeff_monomial(1)
                if p.degree()!=1 or not a.is_Integer or a==0:raise SMTGraphError('Branch guard needs constant nonzero counter coefficient')
                op=c.rel_op
                if a<0:a=-a;b=-b;op={'<':'>','<=':'>=','>':'<','>=':'<=','==':'==','!=':'!='}[op]
                cut=-b/a
                if op=='<':hi=s.Min(hi,s.ceiling(cut))
                elif op=='<=':hi=s.Min(hi,s.floor(cut)+1)
                elif op=='>':lo=s.Max(lo,s.floor(cut)+1)
                elif op=='>=':lo=s.Max(lo,s.ceiling(cut))
                elif op=='==':lo=s.Max(lo,s.ceiling(cut));hi=s.Min(hi,s.floor(cut)+1)
                else:raise SMTGraphError('Non-disjoint inequality branch')
            if impossible:continue
            active=s.And(hi>lo,*immutable);regions+=1
            if regions>128:raise SMTGraphError('Branch interval/residue budget is 128')
            for name,delta in deltas.items():
                polynomial=delta.subs(clock,period*q+r)
                value=s.factor(prefix(polynomial,hi)-prefix(polynomial,lo))
                if q not in polynomial.free_symbols and not immutable:
                    totals[name]+=polynomial*s.Max(0,hi-lo)
                else:totals[name]+=s.Piecewise((value,active),(0,True))
    for name in mutable:result[name]=builder.bounded(env[name]+totals[name])
    builder.evidence.append({'method':'disjoint Boolean branch interval/residue prefix candidate','paths':len(paths),'regions':regions,'period':period,'increment_degree_limit':3,'candidate_only':True,'original_branch_proof_required':True})
    return result
