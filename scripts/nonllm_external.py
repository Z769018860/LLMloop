"""Full pinned-directory replay; standalone observations, no common success rate."""
import argparse, concurrent.futures, hashlib, json, os, random, signal, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PINS={'elba':'54c58fcd872481a5e72f8c4a31ed2ef242b6fbdd','loopscc':'09ef9351667a8ccd83d7a50907ca5ea90ec521a4'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def freeze(tools,out):
    cases=[]
    for name,folder,pattern in [('elba','bench_elba','*.smt2'),('loopscc','experiments/exp1/LoopSCC/input','*.py')]:
        assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=tools/name,text=True).strip()==PINS[name]
        for p in sorted((tools/name/folder).glob(pattern)):
            cases.append({'tool':name,'path':str(p.relative_to(tools/name)),'sha256':sha(p),'placeholder':p.read_text().strip()=='# cannot process'})
    assert len([c for c in cases if c['tool']=='elba'])==75 and len(cases)==110
    plan={'kind':'full_pinned_directory_nonllm_replay','prior_main':'d3c5cc76829a1117c390f6c657f42c6775b65bc3',
          'pins':PINS,'cases':cases,'repetitions':3,'seed':20261109,'worker_seconds':15,'parallel_workers':3,
          'elba':'default configuration only; compatibility build as v061, not author portfolio',
          'loopscc':'execute original script unchanged including author test loop and coordinate adapters',
          'timing_scope':'concurrent throughput observations; no paired comparative timing or speedup inference',
          'remote_model_calls':0,'execution_driver_sha256':sha(Path(__file__)),
          'acceptance':'all 330 scheduled outcomes captured, immutable inputs/driver; no success expectation on external tools'}
    assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);save(out,plan)
def trial(index,task,tools,out,plan):
    c=task['case'];file=tools/c['tool']/c['path'];assert sha(file)==c['sha256']
    d=out/'raw'/f'{index:04d}';d.mkdir(parents=True);save(d/'request.json',task)
    env=dict(os.environ)
    if c['tool']=='elba':argv=[str(tools/'elba-local'),str(file)]
    else:
        argv=[sys.executable,'-u',str(file)]
        env['PYTHONPATH']=str(tools/'loopscc-python')+':'+str(tools/'loopscc')
    start=time.perf_counter();timeout=False
    with (d/'stdout.txt').open('w') as stdout,(d/'stderr.txt').open('w') as stderr:
        p=subprocess.Popen(argv,stdout=stdout,stderr=stderr,env=env,cwd=tools/c['tool'],start_new_session=True)
        try:code=p.wait(timeout=plan['worker_seconds'])
        except subprocess.TimeoutExpired:timeout=True;os.killpg(p.pid,signal.SIGKILL);code=p.wait()
    text=(d/'stdout.txt').read_text()
    if timeout:status='HOST_TIMEOUT'
    elif code:status='PROCESS_ERROR'
    elif c['placeholder']:status='UPSTREAM_PLACEHOLDER'
    elif c['tool']=='elba':status='REPORTED_BOUND' if 'Success! Found bounds:' in text else 'NO_REPORTED_BOUND'
    elif not text.strip():status='EMPTY_SCRIPT'
    elif 'None' in text:status='COMPLETED_WITH_NONE'
    else:status='COMPLETED_SCRIPT'
    result={'index':index,'repeat':task['repeat'],'tool':c['tool'],'path':c['path'],'argv':argv,
            'wall_seconds':time.perf_counter()-start,'exit_code':code,'status':status,'host_timeout':timeout,
            'source_unchanged':sha(file)==c['sha256'],'printed_lines':len(text.splitlines()),
            'printed_none':sum('None' in l for l in text.splitlines()),'independently_certified':False}
    save(d/'command.json',result);return result
def main():
    p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--freeze',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    a.tools=a.tools.resolve()
    if a.freeze:freeze(a.tools,a.freeze);return
    plan=json.loads(a.plan.read_text());assert sha(Path(__file__))==plan['execution_driver_sha256']
    for name,pin in plan['pins'].items():assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.tools/name,text=True).strip()==pin
    out=a.output;out.mkdir(parents=True,exist_ok=False);save(out/'protocol.json',plan)
    save(out/'source.json',{'local_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),'driver_sha256':sha(Path(__file__)),'elba_binary_sha256':sha(a.tools/'elba-local')})
    rng=random.Random(plan['seed']);tasks=[]
    for repeat in range(plan['repetitions']):
        block=[{'repeat':repeat,'case':c}for c in plan['cases']];rng.shuffle(block);tasks+=block
    save(out/'schedule.json',tasks);rows=[];start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(plan['parallel_workers'])as pool:
        jobs=[pool.submit(trial,i,t,a.tools,out,plan)for i,t in enumerate(tasks)]
        for f in concurrent.futures.as_completed(jobs):
            row=f.result();rows.append(row)
            with (out/'trials.jsonl').open('a')as log:log.write(json.dumps(row)+'\n')
            if len(rows)%10==0:print(json.dumps({'captured':len(rows),'planned':len(tasks)}),flush=True)
    passed=len(rows)==330 and all(r['source_unchanged']for r in rows) and sha(Path(__file__))==plan['execution_driver_sha256']
    save(out/'results.json',{'passed_capture':passed,'remote_model_calls':0,'runs':len(rows),'elapsed_seconds':time.perf_counter()-start,'rows':sorted(rows,key=lambda r:r['index'])})
    assert passed
if __name__=='__main__':main()
