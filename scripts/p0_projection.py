"""Narrow ELBA count projection and transparent post-hoc oracle eligibility audit.

Not a general CHC importer. This validates only the registered ABC_ex01 schema.
"""
import argparse, ast, hashlib, json, os, re, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'long f(int a,int b){long x=0;for(int i=0;i<b-a;i++){x++;}return x;}'

def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False)+'\n')

def entry_eligibility(raw_source, inputs):
    """Evaluate simple unmodified raw-function prologues, never override them."""
    tree = ast.parse(raw_source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'start')
    env = {}
    for p in fn.args.args:
        key = p.arg[:-1] if p.arg.endswith('0') else p.arg
        if key not in inputs:
            return {'eligible': False, 'reason': 'missing parameter '+key}
        env[p.arg] = inputs[key]
    def val(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.Name):
            return env[node.id]
        raise ValueError('unrecognized prologue expression')
    found = False
    try:
        for stmt in fn.body:
            if isinstance(stmt, ast.While):
                found = True
                break
            if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                raise ValueError('unrecognized prologue statement')
            env[stmt.targets[0].id] = val(stmt.value)
    except (ValueError, KeyError) as exc:
        return {'eligible': False, 'reason': str(exc)}
    if not found:
        return {'eligible': False, 'reason': 'no loop boundary'}
    differences = {k: {'requested':v, 'raw_loop_entry':env.get(k)} for k,v in inputs.items() if env.get(k) != v}
    return {'eligible': not differences, 'entry_differences': differences}

def parse_abc(text):
    compact = re.sub(r'\s+', '', text.split('Success! Found bounds:', 1)[1])
    required = ['((_FH_1+(-1*_FH_2))>=1)-->(_gh_0=(_FH_1+(-1*_FH_2)))',
                '((_FH_1+(-1*_FH_2))<1)-->(_gh_0=0)']
    if compact != ''.join(required):
        raise ValueError('ELBA output outside the registered two-branch ABC schema')
    return {'relation_arguments': ['a','b','i'], 'bound': 'If(b-i >= 1, b-i, 0)',
            'entry_binding': 'i=a', 'entry_bound': 'max(b-a,0)'}

def obligations(offset=0):
    import z3
    a,b,k = z3.Ints('projection_a projection_b projection_k')
    n = z3.If(b-a >= 1,b-a,0)+offset
    conditions = {'nonnegative':n>=0, 'entry':a+0==a,
                  'active_guard':z3.Implies(z3.And(k>=0,k<n),a+k<b),
                  'exact_successor':z3.Implies(z3.And(k>=0,k<n),(a+k)+1==a+(k+1)),
                  'exit_guard':a+n>=b}
    rows=[]
    for name, claim in conditions.items():
        s=z3.Solver();s.set(timeout=5000);s.add(z3.Not(claim));status=s.check()
        rows.append({'name':name,'solver_status':str(status),
                     'counterexample':str(s.model()) if status==z3.sat else None})
    return rows

def audit(tools, study):
    audited=[]
    for folder in sorted((study/'raw').iterdir()):
        task=json.loads((folder/'request.json').read_text())
        if task['kind']!='external' or task['case']['tool']!='loopscc':continue
        result=json.loads((folder/'result.json').read_text()) if (folder/'result.json').exists() else {}
        raw=(tools/'loopscc'/task['case']['oracle_path']).read_text()
        for i,point in enumerate(result.get('observations',[])):
            eligibility=entry_eligibility(raw,point['inputs'])
            audited.append({'run':folder.name,'name':task['case']['name'],'point':i,
                            'raw_matched':point.get('matched'),**eligibility})
    return {'kind':'post_hoc_adapter_boundary_audit','selection':'all captured LoopSCC observations; raw files unchanged',
            'rows':audited,'raw_checks':sum(r['raw_matched'] is not None for r in audited),
            'raw_mismatches':sum(r['raw_matched'] is False for r in audited),
            'eligible_checks':sum(r['eligible'] and r['raw_matched'] is not None for r in audited),
            'eligible_matches':sum(r['eligible'] and r['raw_matched'] is True for r in audited),
            'eligible_mismatches':sum(r['eligible'] and r['raw_matched'] is False for r in audited),
            'ineligible_points':sum(not r['eligible'] for r in audited),
            'missing_comparison':sum(r['eligible'] and r['raw_matched'] is None for r in audited)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    tools=args.tools;out=args.output;out.mkdir(parents=True,exist_ok=False)
    plan=json.loads((ROOT/'experiments/protocols/v061_projection.json').read_text())
    save(out/'protocol.json',plan)
    save(out/'source.json',{'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                          'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    registered=json.loads((ROOT/'experiments/protocols/v061_p0.json').read_text())
    case=next(c for c in registered['external_cases'] if c['tool']=='elba' and c['name']=='ABC_ex01')
    assert hashlib.sha256((tools/'elba'/case['path']).read_bytes()).hexdigest()==case['sha256']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=tools/'elba',text=True).strip()==case['commit']
    start=time.perf_counter()
    proc=subprocess.run([str(tools/'elba-local'),str(tools/'elba/bench_elba/ABC_ex01.smt2')],text=True,capture_output=True,timeout=15)
    (out/'elba.stdout.txt').write_text(proc.stdout);(out/'elba.stderr.txt').write_text(proc.stderr)
    parsed=parse_abc(proc.stdout);assert proc.returncode==0
    proof=obligations();negative={str(i):obligations(i) for i in [-1,1]}
    from llmloop.api import analyze_request
    query={'source':SOURCE,'parameter_bounds':{'a':[-1000,1000],'b':[-1000,1000]},'inputs':{'a':-8,'b':8},'abi':'LP64','frontend':'typed_recurrence','closed_forms':{'x':'i'}}
    result=analyze_request(query);save(out/'typed_request.json',query);save(out/'typed_result.json',result)
    bad=dict(query,closed_forms={'x':'i+1'});bad_result=analyze_request(bad);save(out/'typed_negative.json',{'request':bad,'result':bad_result})
    harness=SOURCE+'\n#include <stdio.h>\nint main(void){for(int a=-8;a<=8;a++)for(int b=-8;b<=8;b++)printf("%d %d %ld\\n",a,b,f(a,b));return 0;}\n'
    cfile=out/'projection.c';cfile.write_text(harness);native=[]
    for compiler in ['gcc','clang']:
        for opt in ['-O0','-O2']:
            name=compiler+opt[1:];binary=out/name
            command=[compiler,'-std=c11',opt,str(cfile),'-o',str(binary)]
            built=subprocess.run(command,text=True,capture_output=True,timeout=30)
            (out/(name+'.build.txt')).write_text(built.stdout+built.stderr);assert built.returncode==0
            ran=subprocess.run([str(binary)],text=True,capture_output=True,timeout=10)
            (out/(name+'.stdout.txt')).write_text(ran.stdout);assert ran.returncode==0
            rows=[tuple(map(int,s.split())) for s in ran.stdout.splitlines()]
            native.append({'compiler':compiler,'optimization':opt,'command':command,'version':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
                           'observations':len(rows),'matches':sum(v==max(b-a,0) for a,b,v in rows)})
            binary.unlink()
    boundary=audit(tools,ROOT/'experiments/v061');save(out/'oracle_boundary_audit.json',boundary)
    accepted=(all(x['solver_status']=='unsat' for x in proof) and all(any(x['solver_status']=='sat' for x in v) for v in negative.values())
              and result.get('c_overflow_verified') is True and result.get('evaluation',{}).get('value')==16
              and bad_result.get('status')=='UNKNOWN' and sum(x['matches'] for x in native)==1156)
    save(out/'results.json',{'passed':accepted,'schema':parsed,'integer_obligations':proof,'wrong_bound_controls':negative,
         'native':native,'native_observations':sum(x['observations'] for x in native),'native_matches':sum(x['matches'] for x in native),
         'typed_certificate':result.get('status'),'wrong_typed_candidate':bad_result.get('status'),'wall_seconds':time.perf_counter()-start,
         'remote_model_calls':0,'scope':'one adapted ABC count projection, not unchanged public typed C, general CHC import, full-state comparison or baseline speedup'})
    assert accepted

if __name__=='__main__':main()
