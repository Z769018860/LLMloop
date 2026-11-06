"""Restricted CHC count certificates, with explicit failed-admission denominators.

Admit exactly one relation, one entry rule and one constant-delta transition.
No external statement or reported bound is trusted as an accepted certificate.
"""
import argparse, ast, hashlib, itertools, json, re, subprocess
from pathlib import Path
import z3
ROOT=Path(__file__).resolve().parents[1]
def save(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n')
def sexprs(text):
    tokens=re.findall(r'\(|\)|[^\s()]+',re.sub(r';[^\n]*','',text));stack=[];out=[]
    for token in tokens:
        if token=='(':
            row=[]
            if stack:stack[-1].append(row)
            stack.append(row)
        elif token==')':
            if not stack:raise ValueError('unbalanced source')
            row=stack.pop()
            if not stack:out.append(row)
        elif stack:stack[-1].append(token)
        else:raise ValueError('unparenthesized source token')
    if stack:raise ValueError('unbalanced source')
    return out
def conjuncts(e):
    return sum((conjuncts(x)for x in e[1:]),[])if isinstance(e,list)and e and e[0]=='and'else[e]
def smt(e,env):
    if isinstance(e,str):
        if e=='true':return z3.BoolVal(True)
        if e=='false':return z3.BoolVal(False)
        if re.fullmatch(r'-?\d+',e):return z3.IntVal(int(e))
        if e in env:return env[e]
        raise ValueError('unknown source symbol '+e)
    op,*args=e;v=[smt(x,env)for x in args]
    if op=='+':return sum(v,z3.IntVal(0))
    if op=='-':return -v[0]if len(v)==1 else v[0]-sum(v[1:],z3.IntVal(0))
    if op=='*'and len(v)==2:return v[0]*v[1]
    if op=='and':return z3.And(*v)
    if op=='or':return z3.Or(*v)
    if op=='not'and len(v)==1:return z3.Not(v[0])
    if op in ['=','<','<=','>','>=']and len(v)==2:return {'=':lambda:v[0]==v[1],'<':lambda:v[0]<v[1],'<=':lambda:v[0]<=v[1],'>':lambda:v[0]>v[1],'>=':lambda:v[0]>=v[1]}[op]()
    raise ValueError('unsupported source operator '+op)
def admit(text):
    forms=sexprs(text);rels=[f for f in forms if f[0]=='declare-rel']
    if len(rels)!=1:raise ValueError('requires exactly one relation')
    if len(rels[0])!=3 or not rels[0][2]or any(s!='Int'for s in rels[0][2]):raise ValueError('relation must have integer argument sorts')
    declarations={f[1]:f[2]for f in forms if f[0]=='declare-var'and len(f)==3}
    rel=rels[0][1];rules=[f[1]for f in forms if f[0]=='rule'];entry=[];steps=[]
    for rule in rules:
        pre,head=(rule[1],rule[2])if rule[0]=='=>'else('true',rule)
        if not isinstance(head,list)or head[0]!=rel:raise ValueError('non-relation rule head')
        inv=[e for e in conjuncts(pre)if isinstance(e,list)and e and e[0]==rel]
        (steps if inv else entry).append((pre,head,inv))
    if len(entry)!=1 or len(steps)!=1:raise ValueError('requires one entry and one transition')
    pre,head,inv=steps[0]
    if len(inv)!=1:raise ValueError('multiple body relations')
    current=inv[0][1:];next_args=head[1:];initial=entry[0][1][1:]
    if len(current)!=len(rels[0][2]):raise ValueError('declared relation arity mismatch')
    if len(current)!=len(set(current))or not all(isinstance(x,str)and x.isidentifier()for x in current):raise ValueError('non-unique state slots')
    if len(initial)!=len(current)or len(initial)!=len(set(initial))or not all(isinstance(x,str)and x.isidentifier()for x in initial):raise ValueError('unsupported entry slots')
    if any(declarations.get(v)!='Int'for v in [*current,*initial,*next_args]):raise ValueError('state variables require declared Int sorts')
    if len(next_args)!=len(current):raise ValueError('state arity mismatch')
    env={v:z3.Int('v'+str(i))for i,v in enumerate(current)};parts=[p for p in conjuncts(pre)if p!=inv[0]];used=[];delta=[]
    for old,new in zip(current,next_args):
        if old==new:delta.append(0);continue
        eq=[p for p in parts if isinstance(p,list)and len(p)==3 and p[0]=='='and(p[1]==new or p[2]==new)]
        if len(eq)!=1:raise ValueError('missing/ambiguous next-state definition')
        p=eq[0];rhs=p[2]if p[1]==new else p[1]
        diff=z3.simplify(smt(rhs,env)-env[old])
        if not z3.is_int_value(diff):raise ValueError('non-constant state delta')
        delta.append(diff.as_long());used.append(p)
    guard=z3.And(*[smt(p,env)for p in parts if p not in used]);entry_env={v:env[c]for v,c in zip(initial,current)}
    return {'variables':list(env.values()),'delta':delta,'guard':guard,'entry':smt(entry[0][0],entry_env),'arity':len(current)}
def reported_expr(text,env):
    text=re.sub(r'(?<![<>=!])=(?!=)','==',text).replace('&&',' and ').replace('||',' or ')
    node=ast.parse(text.strip(),mode='eval').body
    def visit(n):
        if isinstance(n,ast.Constant)and type(n.value)is int:return z3.IntVal(n.value)
        if isinstance(n,ast.Name):
            if n.id=='true':return z3.BoolVal(True)
            if n.id=='false':return z3.BoolVal(False)
            if n.id in env:return env[n.id]
            raise ValueError('unbound report symbol')
        if isinstance(n,ast.UnaryOp)and isinstance(n.op,(ast.USub,ast.UAdd,ast.Not)):
            a=visit(n.operand);return -a if isinstance(n.op,ast.USub)else z3.Not(a)if isinstance(n.op,ast.Not)else a
        if isinstance(n,ast.BinOp)and isinstance(n.op,(ast.Add,ast.Sub,ast.Mult)):
            a,b=visit(n.left),visit(n.right);return a+b if isinstance(n.op,ast.Add)else a-b if isinstance(n.op,ast.Sub)else a*b
        if isinstance(n,ast.BoolOp):return (z3.And if isinstance(n.op,ast.And)else z3.Or)(*[visit(v)for v in n.values])
        if isinstance(n,ast.Compare)and len(n.ops)==1:
            a,b=visit(n.left),visit(n.comparators[0]);op=n.ops[0]
            for typ,fn in [(ast.Eq,lambda:a==b),(ast.NotEq,lambda:a!=b),(ast.Lt,lambda:a<b),(ast.LtE,lambda:a<=b),(ast.Gt,lambda:a>b),(ast.GtE,lambda:a>=b)]:
                if isinstance(op,typ):return fn()
        raise ValueError('unsupported report syntax')
    return visit(node)
def branches(text,variables):
    if 'Success! Found bounds:'not in text:raise ValueError('no reported bound')
    env={'_FH_'+str(i):v for i,v in enumerate(variables)};gh=z3.Int('reported_trip_count');env['_gh_0']=gh;rows=[]
    for line in text.split('Success! Found bounds:',1)[1].strip().splitlines():
        if not line.strip():continue
        if line.count('-->')!=1:raise ValueError('non-branch report output')
        left,right=line.split('-->');cond=reported_expr(left,env);eq=reported_expr(right,env)
        if not z3.is_eq(eq)or len(eq.children())!=2:raise ValueError('bound is not one equality')
        diff=eq.arg(0)-eq.arg(1);rem=z3.simplify(z3.substitute(diff,(gh,z3.IntVal(0))))
        coef=z3.simplify(z3.substitute(diff,(gh,z3.IntVal(1)))-rem)
        if not z3.is_int_value(coef)or coef.as_long()==0:raise ValueError('nonlinear/absent trip-count coefficient')
        c=coef.as_long();n=z3.simplify((-rem)/c if c>0 else rem/(-c))
        # No hidden state-dependent coefficient or nonlinear count term.
        identity=z3.simplify(diff-(coef*gh+rem))
        if not z3.is_int_value(identity)or identity.as_long()!=0:raise ValueError('non-affine count equation')
        rows.append((cond,n,z3.substitute(eq,(gh,n))))
    if not rows:raise ValueError('empty bound branches')
    return rows
def query(domain,claim):
    solver=z3.Solver();solver.set(timeout=5000);solver.add(domain,z3.Not(claim));r=solver.check()
    return {'status':str(r),'counterexample':str(solver.model())if r==z3.sat else None,'smt2':solver.to_smt2()}
def certify(program,rows,shift=0):
    variables=program['variables'];domain=z3.And(program['entry'],*[z3.And(v>=-16,v<=16)for v in variables]);k=z3.Int('completed_steps')
    s=z3.Solver();s.set(timeout=5000);s.add(domain)
    if s.check()!=z3.sat:raise ValueError('empty/undecidable declared entry domain')
    checks=[{'obligation':'reported branches cover declared entry domain',**query(domain,z3.Or(*[r[0]for r in rows]))}]
    for index,(condition,count,equation)in enumerate(rows):
        n=count+shift;state=[(v,v+d*k)for v,d in zip(variables,program['delta'])];guard=z3.substitute(program['guard'],*state)
        exit_guard=z3.substitute(program['guard'],*[(v,v+d*n)for v,d in zip(variables,program['delta'])])
        claims={'integer count equation':equation,'nonnegative count':n>=0,'all prior guards active':z3.Implies(z3.And(k>=0,k<n),guard),'first exit guard false':z3.Not(exit_guard)}
        for name,claim in claims.items():checks.append({'branch':index,'obligation':name,**query(z3.And(domain,condition),claim)})
    return {'certified':all(c['status']=='unsat'for c in checks),'checks':checks,'domain':'each entry relation slot in [-16,16] intersect original entry rule','structural_induction':'one admitted simultaneous constant-delta transition gives state(k)=entry+delta*k'}
def cexpr(e):
    e=z3.simplify(e)
    if z3.is_int_value(e):
        n=e.as_long()
        if not -(2**63-1)<=n<=2**63-1:raise ValueError('C literal outside signed long')
        return '('+str(n)+'L)'
    if z3.is_true(e):return '1'
    if z3.is_false(e):return '0'
    if z3.is_const(e)and e.decl().name().startswith('v'):return e.decl().name()
    ops={z3.Z3_OP_ADD:'+',z3.Z3_OP_SUB:'-',z3.Z3_OP_MUL:'*',z3.Z3_OP_IDIV:'/',z3.Z3_OP_MOD:'%',z3.Z3_OP_EQ:'==',z3.Z3_OP_LE:'<=',z3.Z3_OP_LT:'<',z3.Z3_OP_GE:'>=',z3.Z3_OP_GT:'>',z3.Z3_OP_AND:'&&',z3.Z3_OP_OR:'||'}
    op=e.decl().kind()
    if op==z3.Z3_OP_UMINUS:return '(-'+cexpr(e.arg(0))+')'
    if op==z3.Z3_OP_NOT:return '(!'+cexpr(e.arg(0))+')'
    if op in ops:return '('+ops[op].join(cexpr(c)for c in e.children())+')'
    raise ValueError('unsupported C projection expression')
def projection(program,rows,d):
    from llmloop.api import analyze_request
    vars=program['variables'];bound='0L'
    for cond,n,eq in reversed(rows):bound='('+cexpr(cond)+'?'+cexpr(n)+':'+bound+')'
    source='long f('+','.join('long '+v.decl().name()for v in vars)+'){long x=0;for(long i=0;i<'+bound+';i++){x++;}return x;}'
    request={'source':source,'frontend':'typed_recurrence','closed_forms':{'x':'i'},'parameter_bounds':{str(v):[-16,16]for v in vars},'abi':'LP64'}
    result=analyze_request(request);save(d/'typed.json',{'request':request,'result':result})
    preservation={'status':'not_checked'}
    if result.get('c_overflow_verified')is True:
        # Compare the verifier's actual C iteration expression with the CHC
        # integer candidate, so C truncation cannot silently replace SMT div.
        declarations={str(v):v for v in vars}
        for token in re.findall(r'typed_loop_v\d+!\d+',result['domain_smt2']):
            key=re.fullmatch(r'typed_loop_(v\d+)!\d+',token).group(1)
            declarations[token]=next(v for v in vars if str(v)==key)
        selected=z3.IntVal(0)
        for cond,n,eq in reversed(rows):selected=z3.If(cond,n,selected)
        equality=z3.parse_smt2_string('(assert (= '+result['iterations_smt2']+' '+selected.sexpr()+'))',decls=declarations)[0]
        domain=z3.And(program['entry'],*[z3.And(v>=-16,v<=16)for v in vars])
        preservation=query(domain,equality)
    observations=[];skipped=[]
    if len(vars)>4:return {'typed_status':result['status'],'count_preservation':preservation,'native_scope':'arity cap exceeded','observations':[]}
    for values in itertools.product([-2,0,2],repeat=len(vars)):
        repl=[(v,z3.IntVal(x))for v,x in zip(vars,values)]
        if not z3.is_true(z3.simplify(z3.substitute(program['entry'],*repl))):continue
        chosen=[n for cond,n,eq in rows if z3.is_true(z3.simplify(z3.substitute(cond,*repl)))]
        if not chosen:continue
        n=z3.simplify(z3.substitute(chosen[0],*repl)).as_long()
        if n>10000:skipped.append({'inputs':values,'reason':'direct iteration cap','count':n});continue
        state=list(values);count=0
        while z3.is_true(z3.simplify(z3.substitute(program['guard'],*[(v,z3.IntVal(x))for v,x in zip(vars,state)]))):
            state=[x+delta for x,delta in zip(state,program['delta'])];count+=1
            if count>10000:raise ValueError('direct transition cap disagrees with certified count')
        observations.append({'inputs':values,'reference_iterations':count,'reported_iterations':n})
    native=[]
    if observations:
        harness=source+'\n#include <stdio.h>\nint main(void){' + ''.join('printf("%ld\\n",f('+','.join(str(x)+'L'for x in r['inputs'])+'));'for r in observations)+'return 0;}\n'
        c=d/'projection.c';c.write_text(harness)
        for cc in ['gcc','clang']:
            for opt in ['-O0','-O2']:
                binary=d/(cc+opt[1:]);cmd=[cc,'-std=c11',opt,str(c),'-o',str(binary)];built=subprocess.run(cmd,text=True,capture_output=True,timeout=30)
                (d/(binary.name+'.build.txt')).write_text(built.stdout+built.stderr)
                if built.returncode:raise ValueError('projection compile failed')
                ran=subprocess.run([str(binary)],text=True,capture_output=True,timeout=15);(d/(binary.name+'.stdout.txt')).write_text(ran.stdout);binary.unlink()
                actual=[int(x)for x in ran.stdout.splitlines()]
                native.append({'compiler':cc,'optimization':opt,'observations':len(actual),'matches':sum(x==r['reference_iterations']for x,r in zip(actual,observations)),'passed':ran.returncode==0 and actual==[r['reference_iterations']for r in observations]})
    return {'typed_status':result['status'],'typed_defined':result.get('c_overflow_verified')is True,'count_preservation':preservation,'direct_points':observations,'skipped_points':skipped,'native':native}
def main():
    p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--external',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
    frozen={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),*sorted((ROOT/'llmloop').glob('*.py'))]}
    save(out/'source.json',{'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sha256':frozen})
    protocol=json.loads((ROOT/'experiments/protocols/v062_external.json').read_text());cases=[c for c in protocol['cases']if c['tool']=='elba'];schedule=json.loads((a.external/'schedule.json').read_text());results=[]
    for i,c in enumerate(cases):
        d=out/f'{i:03d}';d.mkdir();row={'path':c['path'],'source_sha256':c['sha256']}
        try:
            source=a.tools/'elba'/c['path'];assert hashlib.sha256(source.read_bytes()).hexdigest()==c['sha256'];program=admit(source.read_text());row['admission']='CONSTANT_DELTA_CHC'
            index=next(j for j,t in enumerate(schedule)if t['repeat']==0 and t['case']['tool']=='elba'and t['case']['path']==c['path'])
            stdout=a.external/'raw'/f'{index:04d}'/'stdout.txt';text=stdout.read_text();row['external_trial_index']=index
            bs=branches(text,program['variables']);proof=certify(program,bs);save(d/'certificate.json',proof);row['math_certified']=proof['certified']
            if proof['certified']:
                row['negative_bound_checks']={str(k):certify(program,bs,k)['certified']for k in [-1,1]}
                row['projection']=projection(program,bs,d)
        except Exception as exc:row.update(status='UNSUPPORTED_OR_NOT_CERTIFIED',reason=type(exc).__name__+': '+str(exc))
        save(d/'result.json',row);results.append(row)
    unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in frozen.items())
    save(out/'results.json',{'captured_all_cases':len(results)==75,'source_unchanged':unchanged,'cases':75,'rows':results,'remote_model_calls':0,'scope':'restricted mathematical CHC exact-count certificates plus explicitly adapted C counters; not original public typed C or full-state equivalence'})
    assert unchanged
if __name__=='__main__':main()
