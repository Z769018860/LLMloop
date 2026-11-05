"""Execute each pinned upstream input script unchanged, including its adapters."""
import argparse, hashlib, json, os, random, signal, subprocess, sys, time
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    plan=json.loads((root/'experiments/protocols/v061_p0.json').read_text())
    cases=[c for c in plan['external_cases'] if c['tool']=='loopscc']
    out=a.output;out.mkdir(parents=True,exist_ok=False)
    frozen={'kind':'unaltered_upstream_script_replay','cases':cases,'repetitions':3,'worker_seconds':15,'seed':20261108,
            'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            'acceptance':'capture all scheduled outcomes and unchanged sources; process completion is not correctness',
            'scope':'supplement to initial direct-API observations; retain author variable-coordinate adapters and complete author test loops; no C or universal proof claim'}
    (out/'protocol.json').write_text(json.dumps(frozen,indent=2)+'\n')
    rng=random.Random(frozen['seed']);tasks=[]
    for repeat in range(3):
        block=[dict(c,repeat=repeat) for c in cases];rng.shuffle(block);tasks+=block
    (out/'schedule.json').write_text(json.dumps(tasks,indent=2)+'\n');rows=[]
    for i,c in enumerate(tasks):
        file=a.tools/'loopscc'/c['path'];assert hashlib.sha256(file.read_bytes()).hexdigest()==c['sha256']
        assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.tools/'loopscc',text=True).strip()==c['commit']
        d=out/f'{i:03d}';d.mkdir();argv=[sys.executable,'-u',str(file.resolve())];env=dict(os.environ,PYTHONPATH=str((a.tools/'loopscc-python').resolve())+':'+str((a.tools/'loopscc').resolve()))
        start=time.perf_counter();timeout=False
        with (d/'stdout.txt').open('w') as stdout,(d/'stderr.txt').open('w') as stderr:
            proc=subprocess.Popen(argv,cwd=a.tools/'loopscc',stdout=stdout,stderr=stderr,env=env,start_new_session=True)
            try:code=proc.wait(timeout=15)
            except subprocess.TimeoutExpired:timeout=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        text=(d/'stdout.txt').read_text()
        placeholder=file.read_text().strip()=='# cannot process'
        status='HOST_TIMEOUT' if timeout else 'UPSTREAM_PLACEHOLDER' if placeholder else 'PROCESS_ERROR' if code else 'COMPLETED_SCRIPT'
        row={'name':c['name'],'repeat':c['repeat'],'argv':argv,'exit_code':code,'wall_seconds':time.perf_counter()-start,
             'status':status,'printed_lines':len(text.splitlines()),'printed_none':sum('None' in l for l in text.splitlines()),
             'source_unchanged':hashlib.sha256(file.read_bytes()).hexdigest()==c['sha256'],'independently_certified':False}
        (d/'command.json').write_text(json.dumps(row,indent=2)+'\n');rows.append(row)
        print(json.dumps({'completed':len(rows),'planned':len(tasks)}),flush=True)
    passed=len(rows)==36 and all(r['source_unchanged'] for r in rows)
    (out/'results.json').write_text(json.dumps({'passed_capture':passed,'rows':rows,'remote_model_calls':0},indent=2)+'\n')
    assert passed

if __name__=='__main__':main()
