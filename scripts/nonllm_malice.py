"""MALICE's pinned QCP backend on existing annotations; never model generation."""
import argparse, concurrent.futures, hashlib, json, os, random, signal, subprocess, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PIN='4675d37c4f66531a29e0ccd2a746f357ae8dfd7a'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n')
def freeze(repo,out):
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==PIN
    files=sorted((repo/'dataset').rglob('*.c'));cases=[]
    for f in files:
        if '/*@'in f.read_text(errors='replace'):cases.append({'path':str(f.relative_to(repo)),'sha256':sha(f)})
    assert len(files)==557 and len(cases)==321
    support={str(f.relative_to(repo)):sha(f)for f in sorted((repo/'dataset').rglob('*'))if f.is_file()and f.suffix in {'.h','.strategies'}}
    plan={'kind':'malice_qcp_existing_annotation_replay','upstream_pin':PIN,'all_c_files':557,'annotated_c_inputs':321,'cases':cases,'support_hashes':support,
          'repetitions':3,'seed':20261110,'worker_seconds':15,'parallel_workers':3,'driver_sha256':sha(Path(__file__)),'binary_sha256':sha(repo/'bin/symexec'),
          'remote_model_calls':0,'selection':'all dataset C paths containing annotation opener /*@, before backend execution; original headers/strategies retained',
          'scope':'reference annotation/backend integration only, not MALICE generation/refinement accuracy or a common exact-state task',
          'pilot':'count_target source and a false-postcondition mutation were checked while preparing dependency setup',
          'negative_control':'three false-postcondition mutations of count_target in fresh processes; original source never overwritten'}
    assert not out.exists();out.parent.mkdir(parents=True,exist_ok=True);save(out,plan)
def trial(index,task,repo,out,plan):
    source=repo/task['case']['path'];assert sha(source)==task['case']['sha256']
    d=out/'raw'/f'{index:04d}';d.mkdir(parents=True);save(d/'request.json',task)
    argv=[str(repo/'bin/symexec'),'--input-file='+str(source),'--full-auto','--no-exec-info','--basic-assertion']
    timeout=False;start=time.perf_counter()
    with (d/'stdout.txt').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
        proc=subprocess.Popen(argv,cwd=source.parent,stdout=stdout,stderr=stderr,start_new_session=True)
        try:code=proc.wait(timeout=plan['worker_seconds'])
        except subprocess.TimeoutExpired:timeout=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
    text=(d/'stdout.txt').read_text();verified=code==0 and 'Successfully finished full automation check'in text
    row={'index':index,'repeat':task['repeat'],'path':task['case']['path'],'argv':argv,'wall_seconds':time.perf_counter()-start,
         'exit_code':code,'status':'HOST_TIMEOUT'if timeout else 'BACKEND_VERIFIED_ANNOTATIONS'if verified else 'BACKEND_NOT_VERIFIED',
         'source_unchanged':sha(source)==task['case']['sha256'],'model_generated':False}
    save(d/'command.json',row);return row
def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--freeze',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);a=p.parse_args();a.repo=a.repo.resolve()
    if a.freeze:freeze(a.repo,a.freeze);return
    plan=json.loads(a.plan.read_text());assert sha(Path(__file__))==plan['driver_sha256'] and sha(a.repo/'bin/symexec')==plan['binary_sha256']
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.repo,text=True).strip()==PIN
    out=a.output;out.mkdir(parents=True,exist_ok=False);save(out/'protocol.json',plan)
    save(out/'source.json',{'local_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'driver_sha256':sha(Path(__file__))})
    tasks=[];rng=random.Random(plan['seed'])
    for repeat in range(3):
        block=[{'repeat':repeat,'case':c}for c in plan['cases']];rng.shuffle(block);tasks+=block
    save(out/'schedule.json',tasks);rows=[];start=time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(3)as pool:
        for f in concurrent.futures.as_completed([pool.submit(trial,i,t,a.repo,out,plan)for i,t in enumerate(tasks)]):
            r=f.result();rows.append(r)
            with (out/'trials.jsonl').open('a')as log:log.write(json.dumps(r)+'\n')
            if len(rows)%30==0:print(json.dumps({'captured':len(rows),'planned':len(tasks)}),flush=True)
    negative=[];origin=a.repo/'dataset/simple_array/count_target.c';before=sha(origin)
    for repeat in range(3):
        mutant=origin.parent/('.p0_false_post_'+str(repeat)+'.c')
        try:
            text=origin.read_text();assert 'Ensure UIntArray::full_shape(a, n)'in text
            mutant.write_text(text.replace('Ensure UIntArray::full_shape(a, n)','Ensure 0 == 1 && UIntArray::full_shape(a, n)'))
            command=[str(a.repo/'bin/symexec'),'--input-file='+str(mutant),'--full-auto','--no-exec-info','--basic-assertion']
            r=subprocess.run(command,cwd=origin.parent,text=True,capture_output=True,timeout=15)
            (out/f'negative-{repeat}.stdout.txt').write_text(r.stdout);(out/f'negative-{repeat}.stderr.txt').write_text(r.stderr)
            negative.append({'repeat':repeat,'exit_code':r.returncode,'false_post_refused':r.returncode!=0 and 'Successfully finished full automation check'not in r.stdout})
        finally:mutant.unlink(missing_ok=True)
    unchanged=all(sha(a.repo/k)==h for k,h in plan['support_hashes'].items())
    passed=len(rows)==963 and all(r['source_unchanged']for r in rows) and unchanged and sha(origin)==before and all(r['false_post_refused']for r in negative)
    save(out/'results.json',{'passed_capture_and_negative_controls':passed,'runs':len(rows),'remote_model_calls':0,'elapsed_seconds':time.perf_counter()-start,'rows':sorted(rows,key=lambda r:r['index']),'negative_controls':negative,'support_unchanged':unchanged})
    assert passed
if __name__=='__main__':main()
