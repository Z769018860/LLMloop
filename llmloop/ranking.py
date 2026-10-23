"""Universal linear-ranking certificates over mathematical integer SPaths."""
from __future__ import annotations
from itertools import combinations
from .smt_spath import SMTGraphError, _z3_expr, _solver, z3


def verify_ranking(graph, expression: str) -> dict:
    """Prove a natural-valued ranking decreasing by at least one each step.

    Completeness and disjointness of defined transitions are prerequisites;
    the proof is relative only to the parameter domain and certified invariants.
    """
    if graph.bit_width:raise SMTGraphError('Linear ranking requires mathematical integer semantics')
    term = _z3_expr(expression,graph.env)
    if not z3.is_int(term):raise SMTGraphError('Ranking expression must be integer-valued')
    # Limit this certificate to affine forms (including immutable parameters).
    import ast
    tree=ast.parse(expression,mode='eval')
    def affine(n):
        if isinstance(n,ast.Constant):return type(n.value) is int
        if isinstance(n,ast.Name):return n.id in graph.env
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):return affine(n.operand)
        if isinstance(n,ast.BinOp) and isinstance(n.op,(ast.Add,ast.Sub)):return affine(n.left) and affine(n.right)
        if isinstance(n,ast.BinOp) and isinstance(n.op,ast.Mult):
            def constant(x):return isinstance(x,ast.Constant) and type(x.value) is int or isinstance(x,ast.UnaryOp) and isinstance(x.op,(ast.UAdd,ast.USub)) and constant(x.operand)
            return constant(n.left) and affine(n.right) or constant(n.right) and affine(n.left)
        return False
    if not affine(tree.body):raise SMTGraphError('Ranking candidate must be affine')
    context=z3.And(graph.pre,graph._invariant(),graph.loop_guard)
    obligations={'nonnegative':z3.And(context,term<0),
                 'defined_partition':z3.And(context,z3.Not(z3.PbEq([(p.guard,1) for p in graph.paths.values()],1)))}
    obligations.update({'decrease_'+name:z3.And(context,p.guard,graph._at(term,graph._updated(p))>term-1)
                        for name,p in graph.paths.items()})
    results={}
    for name,violation in obligations.items():
        solver=_solver();solver.add(violation);check=solver.check()
        results[name]='unsat' if check==z3.unsat else 'sat' if check==z3.sat else 'unknown'
    certified=all(value=='unsat' for value in results.values())
    return {'status':'CERTIFIED_TERMINATION' if certified else 'UNKNOWN',
            'expression':expression,'obligations':results,
            'certified_invariants':list(graph.certified),
            'meaning':'Natural-valued ranking decreases on every defined transition; not an exact trip count',
            'step_bound':'max(0, ranking(initial)) + 1' if certified else None}


def synthesize_ranking(graph,max_candidates: int = 64) -> dict:
    """Try a finite affine template bank; failure is not nontermination."""
    if type(max_candidates) is not int or not 1<=max_candidates<=256:
        raise SMTGraphError('max_candidates must be in [1,256]')
    variables=list(graph.variables);names=variables+list(graph.parameters)
    candidates=[]
    for v in variables:candidates.extend([v,'-('+v+')'])
    for a,b in combinations(names,2):
        if a not in graph.variables and b not in graph.variables:continue
        candidates.extend([a+' - '+b,b+' - '+a,a+' + '+b,'-('+a+' + '+b+')'])
    reports=[]
    for candidate in candidates[:max_candidates]:
        report=verify_ranking(graph,candidate);reports.append(report)
        if report['status']=='CERTIFIED_TERMINATION':
            return {'status':'CERTIFIED_TERMINATION','certificate':report,'attempted':len(reports),
                    'search_complete':False}
    return {'status':'UNKNOWN','attempted':len(reports),'search_complete':False,
            'reason':'No ranking in the attempted affine template bank; nontermination is not established',
            'candidates':reports}
