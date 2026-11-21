"""Independent bit-precise audit of every frozen synthetic ORIGINAL input.

An unwinding failure alone is UNKNOWN, never an overflow. Limited BMC is not
an estimate of CBMC's best configuration or general comparative performance.
"""
import argparse, hashlib, json, os, random, signal, subprocess, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def classify(blocks,code):
    if code not in (0,10):return 'PROCESS_ERROR',[]
    props=[p for b in blocks for p in b.get('result',[])]
    failures=[p for p in props if p.get('status')=='FAILURE']
    if any(p.get('sourceLocation',{}).get('propertyClass')=='overflow' for p in failures):return 'OVERFLOW',props
    if code==0 and any(b.get('cProverStatus')=='success'for b in blocks) and all(p.get('status')=='SUCCESS'for p in props):return 'SAFE',props
    return 'UNKNOWN',props

def main():
    p=argparse.ArgumentParser();p.add_argument('--cbmc',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--resume',action='store_true');a=p.parse_args();a.cbmc=a.cbmc.resolve();a.corpus=a.corpus.resolve();out=a.output.resolve()
    labels=json.loads((a.corpus/'labels.json').read_text());driver=sha(Path(__file__))
    if not a.resume:
        out.mkdir(parents=True,exist_ok=False)
        plan={'cases':[{'name':k,'label':v['label'],'sha256':v['source_sha256']}for k,v in sorted(labels.items())],
              'binary_sha256':sha(a.cbmc),'version':subprocess.check_output([str(a.cbmc),'--version'],text=True).strip(),'driver_sha256':driver,
              'unwind':64,'host_seconds':10,'parallel_workers':2,'seed':20261122,'pilot':'synth_0001 inspected to validate JSON property classification after corpus freeze',
              'scope':'original-source independent oracle audit with bounded model checking; not SOTA timing or complete BMC portfolio','remote_model_calls':0}
        save(out/'protocol.json',plan)
        tasks=list(plan['cases']);random.Random(plan['seed']).shuffle(tasks);save(out/'schedule.json',tasks)
    plan=json.loads((out/'protocol.json').read_text());assert plan['driver_sha256']==driver and plan['binary_sha256']==sha(a.cbmc)
    tasks=json.loads((out/'schedule.json').read_text())
    def trial(i,c):
        src=a.corpus/c['name'];assert sha(src)==c['sha256'];d=out/'raw'/f'{i:03d}'
        if (d/'command.json').exists():return json.loads((d/'command.json').read_text())
        d.mkdir(parents=True,exist_ok=True);save(d/'request.json',c)
        argv=[str(a.cbmc),str(src),'--32','--no-standard-checks','--signed-overflow-check','--unwind',str(plan['unwind']),'--unwinding-assertions','--json-ui']
        start=time.perf_counter();timed=False
        with (d/'stdout.json').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
            proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            try:code=proc.wait(timeout=plan['host_seconds'])
            except subprocess.TimeoutExpired:timed=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
        status='HOST_TIMEOUT' if timed else 'MALFORMED_OUTPUT';props=[]
        if not timed:
            try:status,props=classify(json.loads((d/'stdout.json').read_text()),code)
            except (ValueError,TypeError):pass
        row={'index':i,'program':c['name'],'label':c['label'],'status':status,'contradiction':status in ['SAFE','OVERFLOW']and status!=c['label'],
             'exit_code':code,'wall_seconds':time.perf_counter()-start,'argv':argv,
             'properties':[{k:v for k,v in p.items()if k!='trace'}for p in props]}
        save(d/'command.json',row);return row
    rows=[]
    with ThreadPoolExecutor(plan['parallel_workers'])as pool:
        for f in as_completed([pool.submit(trial,i,c)for i,c in enumerate(tasks)]):
            rows.append(f.result())
            if len(rows)%20==0:print(json.dumps({'captured':len(rows),'planned':len(tasks)}),flush=True)
    from collections import Counter
    save(out/'results.json',{'captured':len(rows),'complete_capture':len(rows)==len(tasks),'contradictions':[r for r in rows if r['contradiction']],
         'counts':dict(Counter(r['label']+':'+r['status']for r in rows)), 'rows':sorted(rows,key=lambda r:r['index'])})
if __name__=='__main__':main()
