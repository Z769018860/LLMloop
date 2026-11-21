"""Post-hoc existing polynomial profile on all nine default-unproved SAFE cases.
This selected follow-up is reported separately from the frozen 960-run study.
"""
import argparse, hashlib, json, os, random, signal, subprocess, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));D=ROOT/'experiments/v102'
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def main():
    p=argparse.ArgumentParser();p.add_argument('--worker',type=int);a=p.parse_args();out=D/'posthoc_poly'
    if a.worker is not None:
        import scripts.svcomp_translate as T
        from llmloop.houdini_loops import houdini_loops
        T.NOOVF=True;task=json.loads((out/'schedule.json').read_text())[a.worker];d=out/'raw'/f'{a.worker:03d}'
        src,bounds=T.translate(D/'corpus'/task['program']);status,inv,rounds,log=houdini_loops(src,bounds,abi='ILP32',integer_model='c',runs=60,seed=task['seed'],max_rounds=150,solver_timeout_ms=5000,poly=True)
        save(d/'result.json',{'status':status,'invariants':inv,'rounds':rounds,'log':log});return
    out.mkdir(exist_ok=False)
    names=sorted(r['program']for r in json.loads((D/'unproved_safe_cases.json').read_text()));assert len(names)==9
    plan={'selection':'all nine SAFE programs not proved by default Houdini in the completed study; posthoc, not blind holdout',
          'programs':names,'seeds':[1,2,3],'solver_timeout_ms':5000,'host_seconds':30,'max_rounds':150,'sample_runs':60,
          'change':'existing poly=True candidate profile only; verifier unchanged','remote_model_calls':0,
          'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()};save(out/'protocol.json',plan)
    tasks=[{'program':n,'seed':seed}for seed in plan['seeds']for n in names];random.Random(20261122).shuffle(tasks);save(out/'schedule.json',tasks)
    def trial(i,t):
        d=out/'raw'/f'{i:03d}';d.mkdir(parents=True);save(d/'request.json',t);argv=[sys.executable,str(Path(__file__).resolve()),'--worker',str(i)];start=time.perf_counter();timed=False
        with (d/'stdout.txt').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
            proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            try:code=proc.wait(timeout=30)
            except subprocess.TimeoutExpired:timed=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        result=json.loads((d/'result.json').read_text())if(d/'result.json').exists()else{}
        row={**t,'index':i,'status':'HOST_TIMEOUT'if timed else result.get('status','PROCESS_ERROR'),'exit_code':code,'argv':argv,'wall_seconds':time.perf_counter()-start};save(d/'command.json',row);return row
    rows=[]
    with ThreadPoolExecutor(2)as pool:
        for f in as_completed([pool.submit(trial,i,t)for i,t in enumerate(tasks)]):
            rows.append(f.result());print(len(rows),'/',len(tasks),flush=True)
    save(out/'results.json',{'captured':len(rows),'planned':len(tasks),'rows':sorted(rows,key=lambda r:r['index']), 'newly_proved_programs':sorted({r['program']for r in rows if r['status']=='PROVED'}),'remote_model_calls':0})
if __name__=='__main__':main()
