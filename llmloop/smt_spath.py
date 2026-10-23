"""Sound SPath may-transition graph and conditional exact acceleration via Z3.

A satisfiable SPath edge is an existential *may* edge, NOT a guarantee of a
feasible arbitrary graph walk. Only an inductive invariant + guard partition +
functional successor certificate permits translation to a GraphAnalyzer.
Mathematical integers are the default. Optional fixed-width signed bit-vector mode models C integer wraparound, but does not use the affine accelerator.
"""
from __future__ import annotations
import ast
import json
from dataclasses import dataclass
from itertools import combinations
from typing import Any
import sympy as sp

try:
    import z3
except ImportError:
    z3 = None

from .expressions import parse, integer_value
from .graph import GraphAnalyzer, GraphError
from .graph_nested import GraphNestedAnalyzer


class SMTGraphError(ValueError):
    pass


def _solver():
    if z3 is None:
        raise SMTGraphError("z3-solver not installed; install llmloop[smt]")
    solver = z3.Solver()
    solver.set(timeout=10000)
    return solver


def _check(*clauses):
    solver = _solver()
    solver.add(*clauses)
    result = solver.check()
    if result == z3.unknown:
        return "unknown"
    return "sat" if result == z3.sat else "unsat"


def _z3_expr(text: Any, symbols: dict[str, Any], bit_width: int | None = None):
    """Parse a bounded Python-shaped integer/Boolean DSL; never use eval()."""
    if isinstance(text, bool):
        return z3.BoolVal(text)
    if type(text) is int:
        return z3.BitVecVal(text,bit_width) if bit_width else z3.IntVal(text)
    if not isinstance(text, str) or len(text)>1200:
        raise SMTGraphError("Expected a short textual expression")
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError as exc:
        raise SMTGraphError(str(exc)) from exc

    def rec(n):
        if isinstance(n, ast.Constant):
            if type(n.value) is bool: return z3.BoolVal(n.value)
            if type(n.value) is int: return z3.BitVecVal(n.value,bit_width) if bit_width else z3.IntVal(n.value)
        if isinstance(n, ast.Name) and n.id in symbols:
            return symbols[n.id]
        if isinstance(n, ast.UnaryOp):
            a=rec(n.operand)
            if isinstance(n.op, ast.Not): return z3.Not(a)
            if isinstance(n.op, ast.USub): return -a
            if isinstance(n.op, ast.UAdd): return a
        if isinstance(n, ast.BinOp):
            a,b=rec(n.left),rec(n.right)
            if isinstance(n.op, ast.Add): return a+b
            if isinstance(n.op, ast.Sub): return a-b
            if isinstance(n.op, ast.Mult): return a*b
            if isinstance(n.op,(ast.FloorDiv,ast.Mod)):
                if not isinstance(n.right,ast.Constant) or type(n.right.value) is not int or n.right.value==0:
                    raise SMTGraphError('Division/modulo requires a nonzero literal divisor')
                if isinstance(n.op,ast.Mod) and z3.is_bv(a): return z3.SRem(a,b)
                return a/b if isinstance(n.op,ast.FloorDiv) else a%b
        if isinstance(n, ast.BoolOp):
            args=[rec(x) for x in n.values]
            if isinstance(n.op, ast.And): return z3.And(*args)
            if isinstance(n.op, ast.Or): return z3.Or(*args)
        if isinstance(n, ast.Compare):
            terms=[rec(n.left)]+[rec(v) for v in n.comparators]
            claims=[]
            for i,op in enumerate(n.ops):
                a,b=terms[i],terms[i+1]
                if isinstance(op,ast.Eq):claim=a==b
                elif isinstance(op,ast.NotEq):claim=a!=b
                elif isinstance(op,ast.Lt):claim=a<b
                elif isinstance(op,ast.LtE):claim=a<=b
                elif isinstance(op,ast.Gt):claim=a>b
                elif isinstance(op,ast.GtE):claim=a>=b
                else:raise SMTGraphError("Unsupported comparator")
                claims.append(claim)
            return z3.And(*claims)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='ite' and not n.keywords and len(n.args)==3:
            condition,yes,no=(rec(x) for x in n.args)
            return z3.If(condition,yes,no)
        raise SMTGraphError("Unsupported expression node: "+type(n).__name__)
    try:
        return rec(node)
    except (z3.Z3Exception, TypeError) as exc:
        raise SMTGraphError("Ill-typed expression: "+str(exc)) from exc


def _tarjan(edges: dict[str, list[str]]) -> list[list[str]]:
    seq=0; idx={}; low={}; stack=[]; active=set(); components=[]
    def visit(v):
        nonlocal seq
        idx[v]=low[v]=seq;seq+=1;stack.append(v);active.add(v)
        for w in edges[v]:
            if w not in idx:
                visit(w);low[v]=min(low[v],low[w])
            elif w in active:low[v]=min(low[v],idx[w])
        if low[v]==idx[v]:
            component=[]
            while True:
                w=stack.pop();active.remove(w);component.append(w)
                if w==v:break
            components.append(sorted(component))
    for v in sorted(edges):
        if v not in idx: visit(v)
    return sorted(components,key=lambda c:c[0])


@dataclass
class _Path:
    name: str
    guard: Any
    updates: dict[str, Any]
    texts: dict[str, str]


class SMTPathGraph:
    def __init__(self, obj: dict[str, Any]):
        if z3 is None:
            raise SMTGraphError("z3-solver required; install llmloop[smt]")
        if obj.get("kind") != "smt_spgraph":
            raise SMTGraphError("Expected kind=smt_spgraph")
        self.obj=obj
        self.variables=tuple(obj.get("state",{}))
        self.parameters=tuple(obj.get("parameters",[]))
        self.control=obj.get("control_var")
        if not self.variables or len(set(self.variables+self.parameters))!=len(self.variables+self.parameters):
            raise SMTGraphError("State and parameter names must be unique")
        semantics=obj.get('integer_semantics','math')
        if semantics=='math' or semantics is None:
            self.bit_width=None
        elif isinstance(semantics,dict) and semantics.get('kind')=='c_signed' and type(semantics.get('bits')) is int and semantics['bits'] in (8,16,32,64):
            self.bit_width=semantics['bits']
        else:
            raise SMTGraphError("integer_semantics must be 'math' or {'kind':'c_signed','bits':8|16|32|64}")
        self.signed_min=-(1 << (self.bit_width-1)) if self.bit_width else None
        self.signed_max=(1 << (self.bit_width-1))-1 if self.bit_width else None
        self.x={v:(z3.BitVec("state_"+v,self.bit_width) if self.bit_width else z3.Int("state_"+v)) for v in self.variables}
        self.p={v:(z3.BitVec("param_"+v,self.bit_width) if self.bit_width else z3.Int("param_"+v)) for v in self.parameters}
        self.env={**self.p,**self.x}
        self.lower_bounds=obj.get("parameter_bounds",{})
        if set(self.lower_bounds)-set(self.parameters):
            raise SMTGraphError("Unexpected parameter bounds")
        bounds=[]
        for k,limits in self.lower_bounds.items():
            if not isinstance(limits,list) or len(limits)!=2 or any(x is not None and type(x)!=int for x in limits):
                raise SMTGraphError("Parameter bound must be [minimum,maximum] or null")
            if self.bit_width and any(x is not None and not self.signed_min<=x<=self.signed_max for x in limits):
                raise SMTGraphError('Parameter bounds exceed signed '+str(self.bit_width)+'-bit range for '+k)
            if limits[0] is not None:bounds.append(self.p[k]>=limits[0])
            if limits[1] is not None:bounds.append(self.p[k]<=limits[1])
        self.pre=z3.And(*bounds)
        if _check(self.pre)!='sat':
            raise SMTGraphError('Empty or undecidable input parameter domain')
        self.initial={v:_z3_expr(expr,self.env,self.bit_width) for v,expr in obj['state'].items()}
        try:
            zero=z3.BitVecVal(0,self.bit_width) if self.bit_width else z3.IntVal(0)
            for value in self.initial.values():zero+value
        except z3.Z3Exception as exc:
            raise SMTGraphError('Initial state must contain integers') from exc
        if any(z3.eq(self.x[v],symbol) for value in self.initial.values()
               for symbol in z3.z3util.get_vars(value) for v in self.variables):
            raise SMTGraphError("Initial state cannot refer to mutable state")
        self.loop_guard=_z3_expr(obj.get("loop_guard",True),self.env,self.bit_width)
        self.exit=obj.get('exit')
        self.paths={}
        source=obj.get('paths',[])
        if not 1<=len(source)<=48:raise SMTGraphError('Expected 1..48 SPaths')
        for entry in source:
            name=entry.get('id')
            if not isinstance(name,str) or not name.isidentifier() or name in self.paths:
                raise SMTGraphError('SPath ids must be unique identifiers')
            writes=entry.get('updates',{})
            if not isinstance(writes,dict) or set(writes)-set(self.variables):
                raise SMTGraphError('Unknown SPath update')
            texts={v:str(writes.get(v,v)) for v in self.variables}
            self.paths[name]=_Path(name,_z3_expr(entry.get('when',True),self.env,self.bit_width),
                         {v:_z3_expr(writes.get(v,v),self.env,self.bit_width) for v in self.variables},texts)
        self.certified=[]
        self._accelerated=None
        self._nested=None
        self._path_values=obj.get('control_values',{})
        self._check_types()

    def _check_types(self):
        try:
            z3.And(self.loop_guard)
            for path in self.paths.values():
                z3.And(path.guard)
                zero=z3.BitVecVal(0,self.bit_width) if self.bit_width else z3.IntVal(0)
                for value in path.updates.values():zero+value
        except z3.Z3Exception as exc:
            raise SMTGraphError('Non-Boolean guard or non-integer assignment: '+str(exc)) from exc

    def _at(self, term, mapping):
        return z3.substitute(term,*[(self.x[v],mapping[v]) for v in self.variables])

    def _updated(self, path, mapping=None):
        mapping=mapping or self.x
        return {v:self._at(path.updates[v],mapping) for v in self.variables}

    def _invariant(self,mapping=None):
        mapping=mapping or self.x
        if not self.certified:return z3.BoolVal(True)
        return z3.And(*[self._at(_z3_expr(pred,self.env,self.bit_width),mapping) for pred in self.certified])

    def _init_map(self):return self.initial

    def _partition(self,extra):
        active=z3.And(self.pre,extra,self.loop_guard)
        guards=[p.guard for p in self.paths.values()]
        uncovered=_check(active,z3.Not(z3.Or(*guards)))
        overlaps={}
        for a,b in combinations(self.paths.values(),2):
            result=_check(active,a.guard,b.guard)
            if result!='unsat':overlaps[a.name+' & '+b.name]=result
        return {'covered':uncovered=='unsat','coverage_check':uncovered,
                'disjoint':not overlaps,'overlaps':overlaps}

    def certify_invariants(self,predicates:list[str]):
        """A candidate is accepted only after initiation, coverage, consecution."""
        if not isinstance(predicates,list) or len(predicates)>30:
            raise SMTGraphError('At most 30 candidate invariants supported')
        outcomes=[]
        for expr in predicates:
            if not isinstance(expr,str) or len(expr)>1000:
                outcomes.append({'candidate':str(expr)[:60],'certified':False,'reason':'Invalid expression'});continue
            try:
                inv=_z3_expr(expr,self.env,self.bit_width)
                z3.And(inv)
                base=_check(self.pre,z3.Not(self._at(inv,self._init_map())))
                if base!='unsat':
                    outcomes.append({'candidate':expr,'certified':False,'stage':'base','result':base});continue
                coverage=self._partition(z3.And(self._invariant(),inv))
                if not coverage['covered']:
                    outcomes.append({'candidate':expr,'certified':False,'stage':'coverage','result':coverage['coverage_check']});continue
                checks={}
                for p in self.paths.values():
                    nxt=self._updated(p)
                    checks[p.name]=_check(self.pre,self._invariant(),inv,self.loop_guard,p.guard,
                                          z3.Not(self._at(inv,nxt)))
                if any(value!='unsat' for value in checks.values()):
                    outcomes.append({'candidate':expr,'certified':False,'stage':'step','checks':checks});continue
                self.certified.append(expr)
                outcomes.append({'candidate':expr,'certified':True,'method':'initiation + path coverage + consecution'})
            except (SMTGraphError,z3.Z3Exception,TypeError) as exc:
                outcomes.append({'candidate':expr,'certified':False,'reason':str(exc)})
        return outcomes

    def analyze(self):
        inv=self._invariant()
        edges={p:[] for p in self.paths}
        exit_paths=[]
        unknown=[]
        unknown_exit=[]
        for name,p in self.paths.items():
            after=self._updated(p)
            exit_result=_check(self.pre,inv,self.loop_guard,p.guard,
                               z3.Not(self._at(self.loop_guard,after)))
            if exit_result=='sat':exit_paths.append(name)
            elif exit_result=='unknown':unknown_exit.append(name)
            for dst,target in self.paths.items():
                check=_check(self.pre,inv,self.loop_guard,p.guard,
                             self._at(self.loop_guard,after),self._at(target.guard,after))
                if check=='sat':edges[name].append(dst)
                if check=='unknown':unknown.append([name,dst])
        partition=self._partition(inv)
        return {'kind':'smt_spgraph','spath_edges':edges,'spath_sccs':_tarjan(edges),
                'exit_spaths':exit_paths,'unknown_edges':unknown,'unknown_exits':unknown_exit,
                'path_partition':partition,'certified_invariants':list(self.certified),
                'meaning':'SAT edges are existential overapproximations, not an executable path schedule'}

    def try_accelerate(self):
        """Build proven phase-functional accelerated IR when source control is finite.

        No exact summary is emitted on ambiguous transitions or missing proof.
        """
        report=self.analyze()
        if self.bit_width:
            return {'status':'UNKNOWN','reason':'Fixed-width bit-vector analysis is enabled; exact affine acceleration requires a separate no-overflow proof and is intentionally disabled'}
        if not report['path_partition']['covered'] or not report['path_partition']['disjoint'] or report['unknown_edges'] or report['unknown_exits']:
            return {'status':'UNKNOWN','reason':'Path partition or SMT may-edge check is not certified'}
        if self.control not in self.variables or set(self._path_values)!=set(self.paths):
            return {'status':'UNKNOWN','reason':'No finite control-variable-to-SPath correspondence declared'}
        if len(set(self._path_values.values()))!=len(self.paths) or any(type(v)!=int for v in self._path_values.values()):
            return {'status':'UNKNOWN','reason':'Control values must be distinct literal integers'}
        invariant=self._invariant()
        for key,path in self.paths.items():
            region=self.x[self.control]==self._path_values[key]
            equivalence=z3.Xor(path.guard,region)
            if _check(self.pre,invariant,self.loop_guard,equivalence)!='unsat':
                return {'status':'UNKNOWN','reason':'SPath guard does not equal control-phase predicate: '+key}
        # Fixed initial phase for every allowed parameter valuation.
        init_candidates=[]
        for key,path in self.paths.items():
            if _check(self.pre,self._at(path.guard,self.initial))=='sat':init_candidates.append(key)
        if len(init_candidates)!=1:
            return {'status':'UNKNOWN','reason':'Initial phase depends on input or is uncovered'}
        first=init_candidates[0]
        if _check(self.pre,z3.Not(self._at(self.paths[first].guard,self.initial)))!='unsat':
            return {'status':'UNKNOWN','reason':'Initial phase not universally certified'}
        successors={}
        for key,path in self.paths.items():
            after=self._updated(path)
            prospective=[]
            for dst,target in self.paths.items():
                result=_check(self.pre,invariant,self.loop_guard,path.guard,
                              self._at(self.loop_guard,after),self._at(target.guard,after))
                if result=='unknown':return {'status':'UNKNOWN','reason':'SMT unknown successor'}
                if result=='sat':prospective.append(dst)
            if len(prospective)>1:
                return {'status':'UNKNOWN','reason':'Nonfunctional successor from '+key,'may_successors':prospective}
            # Paths with no in-loop successor represent final transitions.
            successors[key]=prospective[0] if prospective else key
            actual_control=after[self.control]
            # Even the final (exiting) step must preserve the concrete
            # control-state output, not only its abstract next phase.
            expected=z3.BitVecVal(self._path_values[successors[key]],self.bit_width) if self.bit_width else z3.IntVal(self._path_values[successors[key]])
            if _check(self.pre,invariant,self.loop_guard,path.guard,
                      actual_control!=expected)!='unsat':
                return {'status':'UNKNOWN','reason':'Concrete control update differs from predicted phase for '+key}
        # Only include phases actually reached from the initial phase.
        reachable=[];phase=first
        while phase not in reachable:
            reachable.append(phase);phase=successors[phase]
        to_phase={key:self._path_values[key] for key in reachable}
        source_state={self.control:self.obj['state'][self.control]}
        source_state.update({v:self.obj['state'][v] for v in self.variables if v!=self.control})
        converted=[]
        for key in reachable:
            path=self.paths[key]
            updates={v:expr for v,expr in path.texts.items() if v!=self.control}
            updates[self.control]=str(self._path_values[successors[key]])
            converted.append({'id':key,'guard':{self.control:to_phase[key]},'updates':updates})
        ir={'kind':'spgraph','name':self.obj.get('name','smt certified graph'),
            'parameters':list(self.parameters),'state':source_state,
            'control':{'var':self.control,'values':list(to_phase.values())},
            'paths':converted}
        if self.exit is not None:ir['exit']=self.exit
        try:
            accelerated=GraphAnalyzer(ir)
        except (GraphError,ValueError) as exc:
            return {'status':'UNKNOWN','reason':'Downstream closed form unsupported: '+str(exc)}
        self._accelerated=accelerated
        return {'status':'CERTIFIED_FUNCTIONAL_SCC',
                'method':'SMT guard equivalence + inductive invariants + unique successor + affine macro',
                'reachable_paths':reachable,'successors':{k:successors[k] for k in reachable},
                'accelerated_summary':accelerated.summary()}

    def verify_cycle_proposal(self,proposal:dict[str,Any]):
        """Check an LLM cycle for universal phase transitions and macro effect.

        A conditional cycle certificate is NOT a loop-bound or termination proof.
        """
        try:
            sequence=proposal.get('phase_sequence',[])
            effects=proposal.get('macro_map',{})
            if (not isinstance(sequence,list) or not 1<=len(sequence)<=32 or
                any(x not in self.paths for x in sequence) or set(effects)!=set(self.variables)):
                return {'certified':False,'reason':'Invalid phase sequence or macro map'}
            if not self._partition(self._invariant())['disjoint']:
                return {'certified':False,'reason':'Path predicates overlap'}
            first=self.paths[sequence[0]]
            assumptions=[self.pre,self._invariant(),first.guard,self.loop_guard]
            state=self.x
            for name in sequence:
                if _check(*assumptions)=='unsat':
                    return {'certified':False,'reason':'Phase sequence is unreachable'}
                here=self.paths[name]
                choice=_check(*assumptions,self._at(self.loop_guard,state),
                              z3.Not(self._at(here.guard,state)))
                if choice!='unsat':
                    return {'certified':False,'reason':'Not a universally forced phase: '+name,'solver':choice}
                # Cycle may only execute this step when guard holds.
                assumptions.append(self._at(self.loop_guard,state))
                state=self._updated(here,state)
            if _check(*assumptions)=='unsat':return {'certified':False,'reason':'No feasible complete cycle'}
            for v in self.variables:
                claimed=_z3_expr(effects[v],self.env,self.bit_width)
                mismatch=_check(*assumptions,state[v]!=claimed)
                if mismatch!='unsat':
                    return {'certified':False,'reason':'Incorrect macro update for '+v,'solver':mismatch}
            # Next period starts in the same path if loop continues.
            repeat=_check(*assumptions,self._at(self.loop_guard,state),
                          z3.Not(self._at(first.guard,state)))
            if repeat!='unsat':
                return {'certified':False,'reason':'Cycle phase not preserved','solver':repeat}
            return {'certified':True,'status':'CERTIFIED_CONDITIONAL_CYCLE',
                    'method':'SMT universal forced-step and macro equivalence',
                    'length':len(sequence),
                    'limitation':'No claim of overall loop termination or unlimited unrolling'}
        except (SMTGraphError,z3.Z3Exception,ValueError,TypeError) as exc:
            return {'certified':False,'reason':str(exc)}

    @staticmethod
    def _render_affine(expr):
        expr=sp.expand(sp.sympify(expr))
        if expr.is_Integer:return str(int(expr))
        if expr.is_Symbol:return str(expr)
        if expr.is_Add:
            return '('+' + '.join(SMTPathGraph._render_affine(term) if not term.could_extract_minus_sign()
                else '-'+SMTPathGraph._render_affine(-term) for term in expr.as_ordered_terms())+')'
        if expr.is_Mul:
            return '('+' * '.join(SMTPathGraph._render_affine(term) for term in expr.as_ordered_factors())+')'
        raise SMTGraphError('Cycle macro is not in the supported affine expression language')

    def synthesize_cycle_relations(self,max_cycle_length:int=8,max_candidates:int=128):
        """Enumerate bounded simple cycles in the may-SCC graph and synthesize exact affine macro maps.

        A candidate is only returned as certified if verify_cycle_proposal proves
        every branch choice, the macro identity, and the phase reset with Z3.
        """
        if type(max_cycle_length) is not int or not 1<=max_cycle_length<=12:
            raise SMTGraphError('max_cycle_length must be in [1,12]')
        if type(max_candidates) is not int or not 1<=max_candidates<=512:
            raise SMTGraphError('max_candidates must be in [1,512]')
        report=self.analyze()
        edges=report['spath_edges']
        cycles=[];seen=set()
        for component in report['spath_sccs']:
            members=set(component)
            for start in sorted(component):
                def walk(path):
                    if len(cycles)>=max_candidates:return
                    last=path[-1]
                    for nxt in sorted(edges.get(last,[])):
                        if nxt not in members:continue
                        if nxt==start:
                            cycle=tuple(path)
                            if len(cycle)<=max_cycle_length and cycle not in seen:
                                seen.add(cycle);cycles.append(list(cycle))
                            continue
                        if nxt in path or nxt<start or len(path)>=max_cycle_length:continue
                        walk(path+[nxt])
                walk([start])
                if len(cycles)>=max_candidates:break
            if len(cycles)>=max_candidates:break
        symbols={name:sp.Symbol(name,integer=True) for name in (*self.parameters,*self.variables)}
        outcomes=[]
        for sequence in cycles:
            try:
                state={name:symbols[name] for name in self.variables}
                for path_name in sequence:
                    path=self.paths[path_name]
                    updates={name:parse(path.texts[name],symbols) for name in self.variables}
                    state={name:sp.expand(updates[name].subs(state,simultaneous=True)) for name in self.variables}
                macro={}
                affine=True
                for name,expr in state.items():
                    polynomial=sp.Poly(sp.expand(expr),*symbols.values())
                    if polynomial.total_degree()>1:
                        affine=False;break
                    macro[name]=self._render_affine(expr)
                if not affine:
                    outcomes.append({'phase_sequence':sequence,'certified':False,
                                     'reason':'Macro relation is not affine; current synthesis backend only emits affine recurrences'})
                    continue
                proposal={'phase_sequence':sequence,'macro_map':macro}
                proof=self.verify_cycle_proposal(proposal)
                outcomes.append({'phase_sequence':sequence,'macro_map':macro,**proof})
            except (SMTGraphError,ValueError,TypeError,sp.PolynomialError) as exc:
                outcomes.append({'phase_sequence':sequence,'certified':False,'reason':str(exc)})
        certified=[item for item in outcomes if item.get('certified')]
        return {'status':'CYCLE_RELATIONS_SYNTHESIZED',
                'method':'bounded simple-cycle enumeration + affine symbolic composition + universal SMT certificate',
                'candidate_count':len(outcomes),'certified_count':len(certified),
                'certified_relations':certified,'candidates':outcomes,
                'complete':False,
                'limitation':'Search is bounded by cycle length/candidate count and only emits affine cycle maps; no termination or global closed-form claim'}

    def compose_nested(self,outer:dict[str,Any],inputs:dict[str,int]):
        """Reuse already proven functional phase transformer as nested loop.

        Requires unconditional SPaths, no inner exit guard. Guarded inner loops
        must not be replaced by arbitrary fixed counts.
        """
        if self.bit_width:
            raise SMTGraphError('Nested affine composition currently requires mathematical-integer semantics')
        if self.exit is not None or not z3.is_true(z3.simplify(self.loop_guard)):
            raise SMTGraphError('Nested fixed iteration requires unconditional inner-loop body')
        if self._accelerated is None:
            result=self.try_accelerate()
            if result['status']!='CERTIFIED_FUNCTIONAL_SCC':
                raise SMTGraphError('Unable to certify nested inner SCC: '+result['reason'])
        ir=dict(self._accelerated.summary())
        # Source-equivalent GraphAnalyzer IR is returned by graph IR construction
        graph_ir=self._graph_ir()
        nested=GraphNestedAnalyzer({'kind':'spgraph_nested','outer':outer,'body':graph_ir})
        self._validate_inputs(inputs)
        return {'certificate':'INDUCTIVE_SPATH_COMPOSITION',
                'outer_summary':nested.summary(),'evaluation':nested.evaluate(inputs)}

    def _graph_ir(self):
        if self._accelerated is None:
            raise SMTGraphError('Certified accelerated graph not available')
        graph=self._accelerated
        paths=[]
        for c in graph.control_values:
            p=graph.paths[c]
            # SymPy symbolic output is parsed by graph's safe AST parser.
            updates={v:str(sp.simplify((p.matrix * graph.data_syms.col_join(sp.Matrix([1])))[i]))
                     for i,v in enumerate(graph.data_vars)}
            updates[graph.control_var]=str(p.successor)
            paths.append({'guard':{graph.control_var:c},'updates':updates})
        return {'kind':'spgraph','parameters':list(graph.parameters),
                'state':graph.initial,'control':{'var':graph.control_var,
                'values':list(graph.control_values)},'paths':paths}

    def _validate_inputs(self,inputs):
        if set(inputs)!=set(self.parameters) or any(type(v)!=int for v in inputs.values()):
            raise SMTGraphError('Inputs must specify integer values for all parameters')
        for v,(lo,hi) in self.lower_bounds.items():
            if lo is not None and inputs[v]<lo or hi is not None and inputs[v]>hi:
                raise SMTGraphError('Input violates certified domain bound for '+v)

    def evaluate(self,inputs):
        self._validate_inputs(inputs)
        if self._accelerated is None:
            result=self.try_accelerate()
            if result['status']!='CERTIFIED_FUNCTIONAL_SCC':
                raise SMTGraphError(result['reason'])
        if self.exit:
            return self._accelerated.execute_until_exit(inputs)
        raise SMTGraphError('No exit guard: use compose_nested or after_steps')

    def _signed_value(self,value:int)->int:
        if not self.bit_width:return value
        modulus=1 << self.bit_width
        return value-modulus if value >= (1 << (self.bit_width-1)) else value

    def concrete(self,inputs:dict[str,int],max_steps:int=10000,steps:int|None=None):
        """Bounded literal execution oracle, separate from the matrix accelerator."""
        if self.bit_width and any(not self.signed_min<=value<=self.signed_max for value in inputs.values()):
            raise SMTGraphError('Input outside signed '+str(self.bit_width)+'-bit range')
        self._validate_inputs(inputs)
        numeral=lambda value: z3.BitVecVal(value,self.bit_width) if self.bit_width else z3.IntVal(value)
        assignments=[(self.p[k],numeral(value)) for k,value in inputs.items()]
        state={v:z3.simplify(z3.substitute(expr,*assignments))
               for v,expr in self.initial.items()}
        def value(term):
            repl=[(self.x[v],state[v]) for v in self.variables]
            return z3.simplify(z3.substitute(term,*repl,*assignments))
        if steps is None and z3.is_true(z3.simplify(self.loop_guard)):
            raise SMTGraphError('Concrete execution of nonterminating inner loop requires steps')
        for k in range(max_steps+1):
            active=value(self.loop_guard)
            if z3.is_false(active) or (steps is not None and k==steps):
                return {'trip_count':k,'final_state':{v:(self._signed_value(state[v].as_long()) if self.bit_width else state[v].as_long()) for v in self.variables}}
            if not z3.is_true(active):raise SMTGraphError('Concrete guard not ground')
            if k==max_steps:break
            choices=[p for p in self.paths.values() if z3.is_true(value(p.guard))]
            if len(choices)!=1:
                raise SMTGraphError('Concrete path partition violated: '+str(len(choices)))
            after={v:value(expr) for v,expr in choices[0].updates.items()}
            if not all((z3.is_bv_value(x) if self.bit_width else z3.is_int_value(x)) for x in after.values()):
                raise SMTGraphError('Concrete next state not an integer')
            state=after
        raise SMTGraphError('Concrete oracle step budget exceeded')
