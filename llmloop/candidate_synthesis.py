"""Untrusted automatic scalar/static-cell trajectory candidates.

Mathematical source extraction deliberately omits machine casts/intermediate
safety. Its output is NEVER a source certificate: the independent typed source
executor must prove the original program, including all discarded intermediates.
"""
import json
import sympy as s
from pycparser import c_ast,c_parser
from .memory_frontend import _lit
from .polynomial_recurrence import polynomial_orbit
from .smt_spath import SMTGraphError


def normalize_summaries(source,function,summaries):
    if summaries!='auto':return summaries
    try:unit=c_parser.CParser().parse(source)
    except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
    functions=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
    if len(functions)!=1:raise SMTGraphError('Expected one selected function for automatic summaries')
    result={}
    class Loops(c_ast.NodeVisitor):
        def visit_For(self,node):
            init=node.init
            if not isinstance(init,c_ast.DeclList) or len(init.decls)!=1 or not init.decls[0].name:raise SMTGraphError('Automatic summaries require declared counted indices')
            name=init.decls[0].name
            if name in result:raise SMTGraphError('Automatic loop indices must be unique')
            result[name]='auto';self.generic_visit(node)
    Loops().visit(functions[0].body)
    return result


def render(expr,entries):
    if expr in entries:return 'entry('+json.dumps(entries[expr])+')'
    if expr.is_Integer:return str(int(expr))
    if expr.is_Symbol:return str(expr)
    if expr.func==s.KroneckerDelta:
        return '(1 if '+render(expr.args[0],entries)+' == '+render(expr.args[1],entries)+' else 0)'
    if isinstance(expr,s.Piecewise):
        if expr.args[-1][1] is not s.true:raise SMTGraphError('Automatic Piecewise lacks a default')
        value=render(expr.args[-1][0],entries)
        for item,condition in reversed(expr.args[:-1]):value='('+render(item,entries)+' if '+condition_text(condition,entries)+' else '+value+')'
        return value
    numerator,denominator=s.fraction(s.together(expr))
    if denominator!=1:
        if denominator.is_Integer and denominator>0:return '('+render(s.expand(numerator),entries)+')//'+str(denominator)
        raise SMTGraphError('Automatic candidate has an unsupported denominator')
    if expr.is_Add:return '('+' + '.join(render(a,entries) for a in expr.args)+')'
    if expr.is_Mul:return '('+' * '.join(render(a,entries) for a in expr.args)+')'
    if expr.is_Pow:
        if expr.base==0:return '(1 if '+render(expr.exp,entries)+' == 0 else 0)'
        if expr.base==-1:return '(1 if ('+render(expr.exp,entries)+')%2 == 0 else -1)'
        if expr.exp.is_Integer and 0<=expr.exp<=8:return '('+render(expr.base,entries)+')**'+str(expr.exp)
        raise SMTGraphError('Automatic exponential/radical candidate cannot be encoded in the typed proof DSL')
    if expr.func in (s.Min,s.Max,s.Abs,s.Mod,s.floor,s.ceiling):return expr.func.__name__+'('+','.join(render(a,entries) for a in expr.args)+')'
    raise SMTGraphError('Unsupported automatic closed-form node: '+str(expr.func))


def condition_text(condition,entries):
    if condition is s.true:return 'True'
    if condition is s.false:return 'False'
    if isinstance(condition,s.core.relational.Relational):return '('+render(condition.lhs,entries)+' '+condition.rel_op+' '+render(condition.rhs,entries)+')'
    if condition.func in (s.And,s.Or):return '('+(' and ' if condition.func==s.And else ' or ').join(condition_text(a,entries) for a in condition.args)+')'
    if condition.func==s.Not:return '(not '+condition_text(condition.args[0],entries)+')'
    raise SMTGraphError('Unsupported automatic condition')


class Builder:
    def __init__(self,abi,parameters,live,nonnegative,aliases=None):
        self.abi=abi;self.parameters=parameters;self.live=live;self.nonnegative=nonnegative
        self.aliases=dict(aliases or {});self.nodes=0;self.evidence=[];self.expression_depth=0;self.expression_nodes=0

    def bounded(self,expr):
        # Check before any polynomial expansion, including coefficient-only
        # expressions and sequential repeated squaring.
        count=0
        for term in s.preorder_traversal(expr):
            count+=1
            if count>512:raise SMTGraphError('Automatic expression budget exceeded')
            if term.is_Integer and abs(int(term)).bit_length()>1024:raise SMTGraphError('Automatic constant budget exceeded')
        def size(term):
            if term.is_Number:return 0,1
            if term.is_Symbol:return 1,1
            if term.is_Pow and term.base in (0,-1) and term.exp.is_integer:return 0,1
            values=[size(arg) for arg in term.args]
            if term.is_Add:degree=max(d for d,_ in values);terms=sum(t for _,t in values)
            elif term.is_Mul:
                degree=sum(d for d,_ in values);terms=1
                for _,t in values:terms*=t
            elif term.is_Pow and term.exp.is_Integer and 0<=term.exp<=8:
                degree=values[0][0]*int(term.exp);terms=values[0][1]**int(term.exp)
            elif term.is_Pow:raise SMTGraphError('Automatic power budget exceeded before expansion')
            elif term.func in (s.Min,s.Max,s.Abs,s.Mod,s.floor,s.ceiling):
                # Opaque arithmetic functions do not distribute their argument
                # terms when an enclosing product is expanded. Arguments have
                # already been checked recursively; count the function as one
                # term, while retaining its conservative degree bound.
                degree=max((d for d,_ in values),default=0);terms=1
            else:degree=max((d for d,_ in values),default=0);terms=sum(t for _,t in values) or 1
            if degree>8 or terms>128:raise SMTGraphError('Automatic polynomial budget exceeded before expansion')
            return degree,terms
        size(expr)
        return expr

    def arithmetic(self,node,env):
        if self.expression_depth==0:self.expression_nodes=0
        self.expression_depth+=1;self.expression_nodes+=1
        try:
            if self.expression_depth>32 or self.expression_nodes>256:raise SMTGraphError('Automatic arithmetic AST budget exceeded')
            return self.bounded(self._arithmetic(node,env))
        finally:self.expression_depth-=1

    def _arithmetic(self,node,env):
        if isinstance(node,c_ast.ID) and node.name in env:return env[node.name]
        if isinstance(node,c_ast.Constant):return s.Integer(self.abi.literal(node.value).value)
        if isinstance(node,c_ast.Cast):return self.arithmetic(node.expr,env)
        if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-'):
            term=self.arithmetic(node.expr,env);return term if node.op=='+' else -term
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-','*'):
            a,b=self.arithmetic(node.left,env),self.arithmetic(node.right,env)
            return a+b if node.op=='+' else a-b if node.op=='-' else a*b
        if isinstance(node,c_ast.ArrayRef) or isinstance(node,c_ast.UnaryOp) and node.op=='*':return env[self.target(node,env)]
        raise SMTGraphError('Automatic extractor supports pure +,-,* arithmetic and static cells only')

    def address(self,node,env,depth=0):
        if depth>32:raise SMTGraphError('Automatic pointer depth budget exceeded')
        if isinstance(node,c_ast.ID) and node.name in self.aliases:return self.aliases[node.name]
        if isinstance(node,c_ast.UnaryOp) and node.op=='&' and isinstance(node.expr,c_ast.ArrayRef):
            cells,offset=self.address(node.expr.name,env);return cells,offset+self.arithmetic(node.expr.subscript,env)
        if isinstance(node,c_ast.BinaryOp) and node.op in ('+','-'):
            cells,offset=self.address(node.left,env,depth+1);delta=self.arithmetic(node.right,env)
            return cells,offset+delta if node.op=='+' else offset-delta
        raise SMTGraphError('Automatic cell inference requires a known array/alias')

    def target(self,node,env):
        if isinstance(node,c_ast.ID) and node.name in env:return node.name
        if isinstance(node,c_ast.ArrayRef):
            cells,offset=self.address(node.name,env);offset+=self.arithmetic(node.subscript,env)
        elif isinstance(node,c_ast.UnaryOp) and node.op=='*':cells,offset=self.address(node.expr,env)
        else:raise SMTGraphError('Unsupported automatic assignment target')
        offset=s.simplify(offset)
        if offset.is_Integer is not True or not 0<=offset<len(cells):raise SMTGraphError('Automatic inference needs statically resolved cell offsets')
        return cells[int(offset)]

    def local_object(self,node,env):
        if isinstance(node.type,c_ast.ArrayDecl):
            length=_lit(node.type.dim);items=node.init.exprs or [] if isinstance(node.init,c_ast.InitList) else []
        else:
            init=node.init
            if isinstance(init,c_ast.FuncCall) and isinstance(init.name,c_ast.ID) and init.name.name in ('malloc','calloc'):
                args=init.args.exprs if init.args else []
                if init.name.name=='calloc' and len(args)==2:length=_lit(args[0])
                elif init.name.name=='malloc' and len(args)==1:
                    arg=args[0];length=1 if isinstance(arg,c_ast.UnaryOp) and arg.op=='sizeof' else None
                    if isinstance(arg,c_ast.BinaryOp) and arg.op=='*':
                        length=_lit(arg.left) if isinstance(arg.right,c_ast.UnaryOp) and arg.right.op=='sizeof' else _lit(arg.right) if isinstance(arg.left,c_ast.UnaryOp) and arg.left.op=='sizeof' else None
                else:length=None
                items=[]
            else:
                self.aliases[node.name]=self.address(init,env);return
        if length is None or not 1<=length<=16 or len(env)+int(length)>64:raise SMTGraphError('Automatic private object limits exceeded')
        cells=['@'+node.name+'['+str(i)+']' for i in range(int(length))]
        self.aliases[node.name]=(cells,s.Integer(0))
        for i,key in enumerate(cells):env[key]=self.arithmetic(items[i],env) if i<len(items) else s.Integer(0)

    def lower(self,node,env,ancestors):
        if node is None or isinstance(node,c_ast.EmptyStatement):return env
        self.nodes+=1
        if self.nodes>4096:raise SMTGraphError('Automatic extractor statement budget exceeded')
        if isinstance(node,c_ast.Compound):
            visible=set(env);aliases=dict(self.aliases)
            try:
                for child in node.block_items or []:env=self.lower(child,env,ancestors)
                return {name:value for name,value in env.items() if name in visible}
            finally:self.aliases=aliases
        if isinstance(node,c_ast.Decl):
            if isinstance(node.type,(c_ast.ArrayDecl,c_ast.PtrDecl)):self.local_object(node,env)
            elif node.init is not None:env[node.name]=self.arithmetic(node.init,env)
            else:raise SMTGraphError('Automatic inference requires initialized locals')
            return env
        if isinstance(node,c_ast.Assignment):
            key=self.target(node.lvalue,env);value=self.arithmetic(node.rvalue,env)
            if node.op=='=':env[key]=value
            elif node.op in ('+=','-=','*='):
                old=env[key];env[key]=old+value if node.op=='+=' else old-value if node.op=='-=' else old*value
            else:raise SMTGraphError('Automatic assignment operator unsupported')
            env[key]=self.bounded(env[key])
            return env
        if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--'):
            key=self.target(node.expr,env);env[key]=self.bounded(env[key]+(1 if '++' in node.op else -1));return env
        if isinstance(node,c_ast.For):
            values,k=self.orbit(node,env,ancestors)
            bound=self.arithmetic(node.cond.right,env);count=s.Max(0,bound)
            return {name:s.simplify(self.bounded(value.subs(k,count))) for name,value in values.items()}
        if isinstance(node,c_ast.FuncCall) and isinstance(node.name,c_ast.ID) and node.name.name=='free':return env
        raise SMTGraphError('Automatic extractor does not infer arbitrary branch/control schedules')

    def saturation(self,body,env,mutable,k):
        nodes=body.block_items or [] if isinstance(body,c_ast.Compound) else [body]
        if len(nodes)!=1 or not isinstance(nodes[0],c_ast.If):return None
        branch=nodes[0];condition=branch.cond
        if not isinstance(condition,c_ast.BinaryOp) or condition.op not in ('<','<=','>','>='):return None
        try:key=self.target(condition.left,env)
        except SMTGraphError:return None
        if key not in mutable:return None
        bound=self.arithmetic(condition.right,env);x=env[key]
        if x in bound.free_symbols:return None
        yes=self.lower(branch.iftrue,dict(env),set());no=self.lower(branch.iffalse,dict(env),set())
        step=1 if condition.op in ('<','<=') else -1
        if any(s.simplify(yes[name]-env[name]-(step if name==key else 0))!=0 or s.simplify(no[name]-env[name])!=0 for name in mutable):return None
        if condition.op=='<=':bound+=1
        if condition.op=='>=':bound-=1
        result=dict(env)
        result[key]=s.Min(x+k,s.Max(x,bound)) if step==1 else s.Max(x-k,s.Min(x,bound))
        self.evidence.append({'method':'saturating unit-step candidate','counter':str(k)})
        return result

    def counted_phase(self,loop,env,mutable,k,clock,ancestors):
        """Untrusted additive candidates for one counter-threshold branch.

        Execute both full statement schedules mathematically, require every
        carried coordinate delta to be independent of mutable entry state, then
        sum its polynomial increments over the two exact counter intervals.
        The original typed-C proof independently checks the real branch guard.
        """
        nodes=loop.stmt.block_items or [] if isinstance(loop.stmt,c_ast.Compound) else [loop.stmt]
        positions=[i for i,node in enumerate(nodes) if isinstance(node,c_ast.If)]
        if len(positions)!=1:return None
        position=positions[0];branch=nodes[position];condition=branch.cond
        if not isinstance(condition,c_ast.BinaryOp) or condition.op not in ('<','<=','>','>='):return None
        index=loop.init.decls[0].name
        if not isinstance(condition.left,c_ast.ID) or condition.left.name!=index:return None
        threshold=self.arithmetic(condition.right,env)
        state_symbols=set().union(*(env[name].free_symbols for name in mutable))
        if threshold.free_symbols & (state_symbols|{clock}):
            raise SMTGraphError('Counter-threshold discovery needs an immutable threshold')
        if condition.op in ('<=','>'):threshold+=1
        cutoff=s.Max(0,threshold);split=s.Min(k,cutoff)
        schedules=[]
        for arm in (branch.iftrue,branch.iffalse):
            body=c_ast.Compound(nodes[:position]+([arm] if arm is not None else [])+nodes[position+1:])
            schedules.append(self.lower(body,dict(env),set(ancestors)|{index}))
        early,late=schedules if condition.op in ('<','<=') else reversed(schedules)
        antiderivatives={};q=s.Dummy('prefix_count',integer=True,nonnegative=True)
        def prefix(expression,count):
            expression=self.bounded(s.expand(expression))
            if expression.free_symbols & state_symbols:
                raise SMTGraphError('Counter-threshold discovery requires state-independent additive increments')
            if expression not in antiderivatives:
                try:polynomial=s.Poly(expression,clock)
                except s.PolynomialError as exc:raise SMTGraphError('Counter-threshold increments must be polynomial') from exc
                if polynomial.degree()>3:raise SMTGraphError('Counter-threshold increment degree budget is 3')
                sums=[q,q*(q-1)/2,q*(q-1)*(2*q-1)/6,(q*(q-1)/2)**2]
                total=sum(coefficient*sums[power[0]] for power,coefficient in polynomial.terms())
                if s.simplify(total.subs(q,0))!=0 or s.simplify(total.subs(q,q+1)-total-expression.subs(clock,q))!=0:
                    raise SMTGraphError('Counter-threshold prefix identities not proved')
                antiderivatives[expression]=total
            return antiderivatives[expression].subs(q,count)
        result=dict(env)
        for name in mutable:
            first=early[name]-env[name];second=late[name]-env[name]
            early_value=env[name]+prefix(first,k)
            late_value=env[name]+prefix(first,cutoff)+prefix(second,k)-prefix(second,cutoff)
            # Keep the interval choice outside nonlinear powers. This exact
            # representation lets source-path assumptions simplify each
            # polynomial successor before nonlinear SMT reasoning.
            result[name]=self.bounded(s.Piecewise((s.simplify(early_value),k<=cutoff),(s.simplify(late_value),True)))
        self.evidence.append({'method':'counter-threshold additive polynomial candidate',
            'counter':index,'split_count':str(split),'increment_degree_limit':3,
            'prefix_base_and_successor_identities':True,'distinct_increment_polynomials':len(antiderivatives),
            'candidate_only':True,'original_branch_proof_required':True})
        return result

    def multiple_counted_phases(self,loop,env,mutable,k,clock,ancestors):
        """Propose sums for independent additive threshold branches; never certify C."""
        from itertools import product
        nodes=loop.stmt.block_items or [] if isinstance(loop.stmt,c_ast.Compound) else [loop.stmt]
        positions=[i for i,node in enumerate(nodes) if isinstance(node,c_ast.If)]
        if not 2<=len(positions)<=3:return None
        index=loop.init.decls[0].name
        state_symbols=set().union(*(env[name].free_symbols for name in mutable))
        branches=[]
        for position in positions:
            node=nodes[position];cond=node.cond
            if not isinstance(cond,c_ast.BinaryOp) or cond.op not in ('<','<=','>','>=') or not isinstance(cond.left,c_ast.ID) or cond.left.name!=index:return None
            threshold=self.arithmetic(cond.right,env)
            if threshold.free_symbols & (state_symbols|{clock}):raise SMTGraphError('Counter-threshold discovery needs an immutable threshold')
            if cond.op in ('<=','>'):threshold+=1
            branches.append((node,s.Max(0,threshold),cond.op in ('<','<=')))
        schedules={}
        for choices in product((False,True),repeat=len(branches)):
            replacements=dict(zip(positions,choices));body=[]
            for pos,node in enumerate(nodes):
                if pos in replacements:
                    arm=node.iftrue if replacements[pos] else node.iffalse
                    if arm is not None:body.append(arm)
                else:body.append(node)
            schedules[choices]=self.lower(c_ast.Compound(body),dict(env),set(ancestors)|{index})
        zero=(False,)*len(branches);base=schedules[zero]
        deltas={}
        for name in mutable:
            base_delta=s.expand(base[name]-env[name])
            effects=[]
            for j in range(len(branches)):
                choice=tuple(i==j for i in range(len(branches)))
                effects.append(s.expand(schedules[choice][name]-base[name]))
            for choices,values in schedules.items():
                if s.simplify(values[name]-base[name]-sum((effects[j] for j,v in enumerate(choices) if v),s.Integer(0)))!=0:
                    raise SMTGraphError('Counter-threshold branches interact; independent additive synthesis refused')
            if any(expr.free_symbols & state_symbols for expr in [base_delta,*effects]):
                raise SMTGraphError('Counter-threshold discovery requires state-independent additive increments')
            deltas[name]=(base_delta,effects)
        q=s.Dummy('prefix_count',integer=True,nonnegative=True);cache={}
        def prefix(expr,count):
            expr=self.bounded(s.expand(expr))
            if expr not in cache:
                try:poly=s.Poly(expr,clock)
                except s.PolynomialError as exc:raise SMTGraphError('Counter-threshold increments must be polynomial') from exc
                if poly.degree()>3:raise SMTGraphError('Counter-threshold increment degree budget is 3')
                sums=[q,q*(q-1)/2,q*(q-1)*(2*q-1)/6,(q*(q-1)/2)**2]
                total=sum(coefficient*sums[power[0]] for power,coefficient in poly.terms())
                if s.simplify(total.subs(q,0))!=0 or s.simplify(total.subs(q,q+1)-total-expr.subs(clock,q))!=0:raise SMTGraphError('Counter-threshold prefix identities not proved')
                cache[expr]=total
            return cache[expr].subs(q,count)
        result=dict(env)
        for name,(base_delta,effects) in deltas.items():
            value=env[name]+prefix(base_delta,k)
            for effect,(_,cutoff,early) in zip(effects,branches):
                pre=prefix(effect,k)
                split=s.Piecewise((pre,k<=cutoff),(prefix(effect,cutoff),True))
                value+=split if early else pre-split
            result[name]=self.bounded(s.simplify(value))
        self.evidence.append({'method':'independent counter-threshold additive polynomial candidates','counter':index,
            'branches':len(branches),'schedules_checked':len(schedules),'prefix_base_and_successor_identities':True,
            'candidate_only':True,'original_branch_proof_required':True})
        return result

    def orbit(self,loop,entry,ancestors):
        index=loop.init.decls[0].name;k=s.Symbol(index,integer=True,nonnegative=True)
        frozen=set(self.parameters)|set(ancestors);mutable=[name for name in entry if name not in frozen]
        basis={name:s.Dummy('state',integer=True) for name in mutable}
        clock=s.Dummy('clock',integer=True,nonnegative=True)
        env={**entry,**basis,index:clock}
        saturated=self.saturation(loop.stmt,env,mutable,k)
        if saturated is not None:
            replacements={basis[name]:entry[name] for name in mutable}
            return {name:s.simplify(saturated[name].subs(replacements,simultaneous=True)) if name in mutable else value for name,value in entry.items()},k
        phased=self.counted_phase(loop,env,mutable,k,clock,ancestors)
        if phased is None:phased=self.multiple_counted_phases(loop,env,mutable,k,clock,ancestors)
        if phased is not None:
            replacements={basis[name]:entry[name] for name in mutable}
            return {name:s.simplify(phased[name].subs(replacements,simultaneous=True)) if name in mutable else value for name,value in entry.items()},k
        after=self.lower(loop.stmt,dict(env),set(ancestors)|{index})
        changed=[name for name in mutable if s.simplify(after[name]-basis[name])!=0]
        fixed={basis[name]:entry[name] for name in mutable if name not in changed}
        symbols=[basis[name] for name in changed]+[clock]
        updates={basis[name]:s.expand(after[name].subs(fixed,simultaneous=True)) for name in changed}
        updates[clock]=clock+1
        initial={basis[name]:entry[name] for name in changed};initial[clock]=s.Integer(0)
        result,monomials,lifted,certificate=polynomial_orbit(updates,initial,symbols,k,triangular_only=True)
        values=dict(entry)
        for i,name in enumerate(changed):
            unit=tuple(int(j==i) for j in range(len(symbols)))
            values[name]=s.simplify(result[monomials.index(unit)])
        self.evidence.append({'method':'finite exact polynomial lift','counter':index,'dimension':len(monomials),
                              'closure_identities':True,'power_certificate':certificate})
        return values,k


def synthesize(loop,state,parameters,live,abi,nonnegative,aliases=None):
    names={name:s.Symbol(name,integer=True,nonnegative=True) if name in nonnegative or not term.type.signed else s.Symbol(name,integer=True)
           for name,term in parameters.items()}
    for name,_,_ in live:names[name]=s.Symbol(name,integer=True,nonnegative=True)
    entries={s.Dummy('entry',integer=True):name for name in state}
    ghosts={name:symbol for symbol,name in entries.items()}
    builder=Builder(abi,parameters,live,nonnegative,aliases)
    values,k=builder.orbit(loop,{**names,**ghosts},{name for name,_,_ in live})
    formulas={}
    for name,term in state.items():
        value=values[name];t=term.type
        if t.name=='_Bool':value=s.Piecewise((0,s.Eq(value,0)),(1,True))
        elif not t.signed:value=s.Mod(value,1<<t.bits)
        elif t.rank<abi.types['int'].rank:value=s.Mod(value-t.minimum,1<<t.bits)+t.minimum
        formulas[name]=render(s.simplify(value),entries)
    return formulas,{'index':loop.init.decls[0].name,'candidates':formulas,'candidate_only':True,
                     'requires_separate_source_proof':True,'mathematical_derivations':builder.evidence,
                     'limitations':'candidate extraction approximates casts, intermediate safety and memory initialization/lifetimes; typed source proof is mandatory'}
