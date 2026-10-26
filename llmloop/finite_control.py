"""Untrusted finite control-orbit proposals for state-dependent branch schedules.

Concrete mathematical exploration only proposes a lasso. Independent typed-C
base, source-path, range and successor obligations prove it for the full domain.
"""
import sympy as s
from pycparser import c_ast
from .smt_spath import SMTGraphError


def discover(builder,loop,env,mutable,k,clock,ancestors):
    pending=[(loop.stmt,0)];node_count=0
    while pending:
        node,depth=pending.pop();node_count+=1
        if node_count>8192 or depth>64:raise SMTGraphError('Finite control AST budget exceeded')
        pending.extend((child,depth+1) for _,child in node.children())
    branches=[];assignments=[]
    class Scan(c_ast.NodeVisitor):
        def visit_If(self,n):branches.append(n.cond);self.generic_visit(n)
        def visit_Assignment(self,n):assignments.append(n);self.generic_visit(n)
        def visit_UnaryOp(self,n):
            if n.op in ('++','p++','--','p--'):assignments.append(n)
            self.generic_visit(n)
    Scan().visit(loop.stmt)
    def reads(node):
        result=set()
        class IDs(c_ast.NodeVisitor):
            def visit_ID(self,n):result.add(n.name)
        IDs().visit(node);return result
    controls=set().union(*(reads(c) for c in branches)) & set(mutable) if branches else set()
    if not controls:return None
    for _ in range(16):
        old=set(controls)
        for node in assignments:
            lhs=node.lvalue if isinstance(node,c_ast.Assignment) else node.expr
            if isinstance(lhs,c_ast.ID) and lhs.name in controls:
                controls.update(reads(node.rvalue) if isinstance(node,c_ast.Assignment) else {lhs.name})
        if controls==old:break
    if not controls<=set(mutable):raise SMTGraphError('Finite control orbit needs parameter/counter-independent control transitions')
    constants=getattr(builder,'initial_constants',{})
    if not controls<=set(constants):raise SMTGraphError('Finite control orbit requires concrete integer control entries')
    accumulating=[v for v in mutable if v not in controls]
    basis_symbols=set().union(*(env[v].free_symbols for v in mutable))
    sequence=[];deltas=[];seen={};control=tuple(sorted(controls));current={v:s.Integer(constants[v]) for v in controls}
    def arithmetic(n,e):
        if isinstance(n,c_ast.BinaryOp) and n.op=='%':
            b=builder.arithmetic(n.right,e)
            if not b.is_Integer or b==0:raise SMTGraphError('Finite control modulus must be a nonzero constant')
            return s.Mod(arithmetic(n.left,e),b)
        return builder.arithmetic(n,e)
    def condition(n,e):
        if isinstance(n,c_ast.BinaryOp) and n.op in ('&&','||'):
            return (s.And if n.op=='&&' else s.Or)(condition(n.left,e),condition(n.right,e))
        if isinstance(n,c_ast.UnaryOp) and n.op=='!':return s.Not(condition(n.expr,e))
        if isinstance(n,c_ast.BinaryOp) and n.op in ('<','<=','>','>=','==','!='):
            a,b=arithmetic(n.left,e),arithmetic(n.right,e)
            return {'<':s.Lt,'<=':s.Le,'>':s.Gt,'>=':s.Ge,'==':s.Eq,'!=':s.Ne}[n.op](a,b)
        return s.Ne(arithmetic(n,e),0)
    def execute(node,e):
        if isinstance(node,c_ast.Compound):
            for child in node.block_items or []:e=execute(child,e)
            return e
        if isinstance(node,c_ast.If):
            guard=s.simplify(condition(node.cond,e))
            if guard is s.true:return execute(node.iftrue,e)
            if guard is s.false:return execute(node.iffalse,e)
            raise SMTGraphError('Finite control branch guard was not concrete')
        return builder.lower(node,e,set(ancestors)|{loop.init.decls[0].name})
    for step in range(33):
        key=tuple(current[v] for v in control)
        if key in seen:
            transient=seen[key];period=step-transient;break
        if step==32:raise SMTGraphError('Finite control orbit exploration budget is 32 states')
        if not all(v.is_Integer and abs(int(v)).bit_length()<=128 for v in key):raise SMTGraphError('Finite control orbit not concrete/bounded')
        seen[key]=step;sequence.append(dict(current))
        before={**env,**current};after=execute(loop.stmt,dict(before))
        row={v:builder.bounded(s.expand(after[v]-env[v])) for v in accumulating}
        if any(x.free_symbols & basis_symbols for x in row.values()):raise SMTGraphError('Finite control accumulators must have state-independent additive deltas')
        deltas.append(row);current={v:s.simplify(after[v]) for v in control}
    if period>8 or transient>8:raise SMTGraphError('Finite control summary period/transient budget is 8')
    result=dict(env)
    for v in control:
        cases=[(sequence[j][v],s.Eq(k,j)) for j in range(transient)]
        cases.extend((sequence[transient+r][v],s.Eq(s.Mod(k-transient,period),r)) for r in range(period-1))
        result[v]=s.Piecewise(*cases,(sequence[transient+period-1][v],True))
    q=s.Dummy('orbit_period_counter',integer=True,nonnegative=True)
    def prefix(expr,count):
        try:p=s.Poly(s.expand(expr),q)
        except s.PolynomialError as exc:raise SMTGraphError('Finite control increments must be polynomial') from exc
        if p.degree()>3:raise SMTGraphError('Finite control increment degree budget is 3')
        sums=[count,count*(count-1)/2,count*(count-1)*(2*count-1)/6,(count*(count-1)/2)**2]
        return sum(coef*sums[power[0]] for power,coef in p.terms())
    for v in accumulating:
        value=env[v]
        for j in range(transient):value+=s.Piecewise((deltas[j][v].subs(clock,j),k>j),(0,True))
        elapsed=s.Max(0,k-transient);blocks=s.floor(elapsed/period);residue=s.Mod(elapsed,period)
        block=sum(deltas[transient+r][v].subs(clock,transient+r+period*q) for r in range(period))
        value+=s.expand(prefix(block,blocks))
        tails=[];tail=s.Integer(0)
        for r in range(period-1):
            tails.append((tail,s.Eq(residue,r)))
            tail+=deltas[transient+r][v].subs(clock,transient+r+period*blocks)
        value+=s.Piecewise(*tails,(s.expand(tail),True)) if tails else 0
        result[v]=builder.bounded(value)
    builder.evidence.append({'method':'finite state-dependent control orbit with polynomial accumulator prefixes','transient':transient,'period':period,'explored_states':len(sequence),'control_coordinates':list(control),'candidate_only':True,'original_branch_proof_required':True})
    return result
