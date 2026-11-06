"""Provided-bound quality controls on the official LIFT smoke source."""
import argparse,json,os,random,signal,subprocess,sys,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def save(p,j):p.write_text(json.dumps(j,indent=2)+'\n')
def worker(tools,d,bound):
    root=tools/'lift/LIFT';sys.path[:0]=[str(root/'code/Guess_Check'),str(root/'code'),str(root)]
    from Check_loop_bound_newiter import BoogieVerifier,extract_variables_from_bpl
    from K_Transform import K_Transformer
    class Scoped(BoogieVerifier):
        def _kill_related_processes(self):pass
    source=root/'experiment/benchmarks-Instrumented/for_bounded_loop1_false-unreach-call_true-termination-simplified/for_bounded_loop1_false-unreach-call_true-termination-simplified.bpl'
    work=d/'work';work.mkdir();k=K_Transformer(str(work),str(source),'i')
    v=Scoped(k.fileName,str(source),learner='dt_penalty',varlist=extract_variables_from_bpl(str(source)),project_dir=str(root));v.ensure_varlist_contains('i');v.timeout=20
    v.GenerateConcreteBplFile([('i',bound)]);k.GenerateConcreteBplFile(1,withinv=True)
    ret,inv,cex=v.run_verification(k.K_fileName);save(d/'result.json',{'backend_result':ret,'bound':bound,'remote_model_calls':0});return ret
def main():
    p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--output',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--bound');a=p.parse_args();a.tools=a.tools.resolve()
    if a.worker:worker(a.tools,a.worker,a.bound);return
    plan=json.loads((ROOT/'experiments/protocols/v062_lift.json').read_text());assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.tools/'lift',text=True).strip()==plan['upstream_pin']
    out=a.output;out.mkdir(parents=True,exist_ok=False);save(out/'protocol.json',plan);rows=[];tasks=[];rng=random.Random(plan['seed'])
    for repeat in range(3):
        block=[dict(c,repeat=repeat)for c in plan['cases']];rng.shuffle(block);tasks+=block
    save(out/'schedule.json',tasks);save(out/'source.json',{'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    env=dict(os.environ,PATH=str(a.tools/'bin')+':'+os.environ['PATH'],PYTHONPATH=str(a.tools/'lift-python')+':'+str(a.tools/'loopscc-python'))
    for index,task in enumerate(tasks):
        d=out/'raw'/f'{index:03d}';d.mkdir(parents=True);save(d/'request.json',task);argv=[sys.executable,str(Path(__file__).resolve()),'--tools',str(a.tools),'--worker',str(d.resolve()),'--bound',task['bound']]
        start=time.perf_counter();timeout=False
        with (d/'stdout.txt').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
            proc=subprocess.Popen(argv,cwd=a.tools/'lift/LIFT',env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            try:code=proc.wait(timeout=60)
            except subprocess.TimeoutExpired:timeout=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        result=json.loads((d/'result.json').read_text())if(d/'result.json').exists()else{}
        text=(d/'stdout.txt').read_text();verified=code==0 and result.get('backend_result')==1 and 'finished with 1 verified, 0 errors'in text
        row={'index':index,**task,'argv':argv,'wall_seconds':time.perf_counter()-start,'exit_code':code,'host_timeout':timeout,'backend_result':result.get('backend_result'),'verified':verified,
             'matched':not timeout and code==0 and verified==task['expected_verified']};save(d/'command.json',row);rows.append(row)
    save(out/'results.json',{'captured':len(rows),'passed_expected_controls':len(rows)==12 and all(r['matched']for r in rows),'rows':rows,'remote_model_calls':0})
if __name__=='__main__':main()
