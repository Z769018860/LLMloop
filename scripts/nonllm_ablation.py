"""Same mathematical IR/full-state goal: bounded, invariant-only and SCC modes."""
import argparse, hashlib, json, os, random, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODES=['bounded','invariant_range','invariant_relational','scc_range','scc_no_invariants']
WEIGHTS=[[1],[2],[1,2],[2,1],[1,2,3],[3,1,-1],[0,2,0,2],[-1,1,-1,1]]
def save(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def graph(weights,maximum):
    q=len(weights)
    return {'kind':'smt_spgraph','name':'period_'+str(q)+'_'+str(weights),'parameters':['n'],'parameter_bounds':{'n':[0,maximum]},'state':{'p':0,'i':0,'x':0},
            'control_var':'p','control_values':{'phase'+str(r):r for r in range(q)},'loop_guard':'i<n','exit':{'var':'i','op':'<','bound':'n'},
            'paths':[{'id':'phase'+str(r),'when':'p=='+str(r),'updates':{'p':str((r+1)%q),'i':'i+1','x':'x+('+str(w)+')'}}for r,w in enumerate(weights)]}
def relation(weights,index='i'):
    q=len(weights);return '('+' or '.join('(p=='+str(r)+' and '+index+'%'+str(q)+'=='+str(r)+' and x=='+str(sum(weights))+'*('+index+'//'+str(q)+')+('+str(sum(weights[:r]))+'))'for r in range(q))+')'
def check(domain,claim):
    import z3
    s=z3.Solver();s.set(timeout=5000);s.add(domain,z3.Not(claim));r=s.check()
    return {'status':str(r),'counterexample':str(s.model())if r==z3.sat else None}
def analyze(case,mode):
    import z3,sympy as sym
    from llmloop.smt_spath import SMTPathGraph,_z3_expr
    from llmloop.expressions import parse
    weights=case['weights'];q=len(weights);g=SMTPathGraph(case['graph']);post=_z3_expr('i==n and '+relation(weights,'n'),g.env,None)
    result={'mode':mode,'scope':'mathematical INT IR; universal exact final i,p,x over n domain; no C claim','certified':False}
    if mode=='bounded':
        state=dict(g.initial);active=z3.BoolVal(True);exits=[];bad=[]
        for k in range(129):
            guard=z3.simplify(g._at(g.loop_guard,state));ex=z3.And(active,z3.Not(guard));exits.append(ex);bad.append(z3.Implies(ex,g._at(post,state)))
            if k==128:break
            enabled=[p for p in g.paths.values()if z3.is_true(z3.simplify(g._at(p.guard,state)))]
            if len(enabled)!=1:return dict(result,reason='non-unique original symbolic step')
            active=z3.And(active,guard);state={v:z3.simplify(e)for v,e in g._updated(enabled[0],state).items()}
        proofs={'all_inputs_exit_in_budget':check(g.pre,z3.Or(*exits)),'postcondition':check(g.pre,z3.And(*bad))}
        return dict(result,certified=all(p['status']=='unsat'for p in proofs.values()),proofs=proofs,expanded_steps=128)
    invariant='p>=0 and p<'+str(q)+' and i>=0 and i<=n'
    if mode=='invariant_relational':invariant+=' and '+relation(weights)
    certificates=[] if mode=='scc_no_invariants'else g.certify_invariants([invariant]);result['invariants']=certificates
    if mode.startswith('invariant_'):
        if not certificates or not all(c['certified']for c in certificates):return result
        inv=g._invariant();ranking=[]
        for path in g.paths.values():
            after=g._updated(path);ranking.append(check(z3.And(g.pre,inv,g.loop_guard,path.guard),z3.And(g.p['n']-g.x['i']>0,g.p['n']-after['i']==g.p['n']-g.x['i']-1)))
        proof=check(z3.And(g.pre,inv,z3.Not(g.loop_guard)),post)
        return dict(result,certified=proof['status']=='unsat'and all(r['status']=='unsat'for r in ranking),postcondition=proof,ranking=ranking,acceleration_called=False)
    accelerated=g.try_accelerate();result['acceleration']=accelerated
    if accelerated['status']!='CERTIFIED_FUNCTIONAL_SCC':return result
    summary=accelerated['accelerated_summary'];cycles=sym.Symbol('_cycles',integer=True);algebra=[]
    if summary['macro_period']!=q:return dict(result,reason='unexpected cycle period')
    for r in range(q):
        state=summary['residues'][str(r)]
        algebra.append(state['phase']==r and sym.simplify(parse(state['i'],{'_cycles':cycles})-(q*cycles+r))==0 and sym.simplify(parse(state['x'],{'_cycles':cycles})-(sum(weights)*cycles+sum(weights[:r])))==0)
    points=[]
    for n in sorted({0,1,2,3,case['maximum']}):
        if n>case['maximum']:continue
        got=g.evaluate({'n':n});expected={'i':n,'p':n%q,'x':sum(weights)*(n//q)+sum(weights[:n%q])}
        points.append({'n':n,'result':got,'matched':got['trip_count']==n and got['final_state']==expected})
    result.update(certified=all(algebra)and all(p['matched']for p in points),universal_residue_equalities=algebra,point_checks=points)
    return result
def freeze(out):
    cases=[{'name':'weights'+str(i)+'_max'+str(maximum),'weights':w,'maximum':maximum,'graph':graph(w,maximum)}for i,w in enumerate(WEIGHTS)for maximum in [32,1000000]]
    plan={'kind':'nonllm_same_IR_full_state_mechanism_controls','cases':cases,'modes':MODES,'repetitions':5,'seed':20261111,'worker_seconds':20,
          'semantics':'unbounded mathematical integers, original simultaneous transitions; not typed-C, memory access count or external LoopSCC reproduction',
          'goal':'defined admitted transition system terminates and universal final i,p,x equal specified postcondition for n in declared domain',
          'invariant_policy':'range invariants identical for invariant_range and scc_range; invariant_relational supplies an additional exact relational invariant, explicitly separating a stronger candidate language',
          'expected':'bounded succeeds on 8 domains up to32, fails 8 million domains; invariant_range and scc_no_invariants fail all16; invariant_relational and scc_range prove all16',
          'timing':'fresh sequential processes after concurrent external jobs finish; startup, generation/construction, checking and evaluation included; no LLM latency',
          'pilot':'one existing two-phase example was inspected during setup; no result-based case selection',
          'driver_sha256':sha(Path(__file__)),'remote_model_calls':0}
    assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);save(out,plan)
def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--result',type=Path);a=p.parse_args()
    if a.freeze:freeze(a.freeze);return
    if a.worker:
        req=json.loads(a.worker.read_text());start=time.perf_counter()
        try:r=analyze(req['case'],req['mode']);r['analysis_seconds']=time.perf_counter()-start
        except Exception as e:r={'certified':False,'error':type(e).__name__+': '+str(e)}
        save(a.result,r);return
    plan=json.loads(a.plan.read_text());assert sha(Path(__file__))==plan['driver_sha256'];out=a.output;out.mkdir(parents=True,exist_ok=False);save(out/'protocol.json',plan)
    frozen={str(p.relative_to(ROOT)):sha(p)for p in [Path(__file__),*sorted((ROOT/'llmloop').glob('*.py'))]};save(out/'source.json',{'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'hashes':frozen})
    rng=random.Random(plan['seed']);tasks=[]
    for repeat in range(5):
        block=[{'repeat':repeat,'case':c,'mode':m}for c in plan['cases']for m in MODES];rng.shuffle(block);tasks+=block
    save(out/'schedule.json',tasks);rows=[]
    for i,task in enumerate(tasks):
        d=out/'raw'/f'{i:04d}';d.mkdir(parents=True);save(d/'request.json',task);argv=[sys.executable,str(Path(__file__).resolve()),'--worker',str((d/'request.json').resolve()),'--result',str((d/'result.json').resolve())]
        timeout=False;start=time.perf_counter()
        with (d/'stdout.txt').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
            proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,cwd=ROOT,start_new_session=True)
            try:code=proc.wait(timeout=20)
            except subprocess.TimeoutExpired:timeout=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        result=json.loads((d/'result.json').read_text())if(d/'result.json').exists()else{}
        expected=task['mode']in ['invariant_relational','scc_range']or task['mode']=='bounded'and task['case']['maximum']==32
        row={'index':i,'repeat':task['repeat'],'name':task['case']['name'],'mode':task['mode'],'wall_seconds':time.perf_counter()-start,'analysis_seconds':result.get('analysis_seconds'),
             'exit_code':code,'host_timeout':timeout,'certified':result.get('certified',False),'expected':expected,'matched':not timeout and code==0 and not result.get('error')and result.get('certified')==expected,'error':result.get('error'),'argv':argv}
        save(d/'command.json',row);rows.append(row)
        with (out/'trials.jsonl').open('a')as log:log.write(json.dumps(row)+'\n')
        if len(rows)%20==0:print(json.dumps({'captured':len(rows),'planned':len(tasks),'mismatches':sum(not x['matched']for x in rows)}),flush=True)
    unchanged=all(sha(ROOT/p)==h for p,h in frozen.items());save(out/'results.json',{'passed':len(rows)==400 and all(r['matched']for r in rows)and unchanged,'rows':rows,'source_unchanged':unchanged,'remote_model_calls':0})
if __name__=='__main__':main()
