"""Re-check only the two historical certificates lost by prefix truncation.

Uses stored translated C and invariants. No benchmark download or LLM calls.
The harness follows the existing flat proof rule, with explicit typed havoc
helpers for CBMC 6.11; all original assertions and arithmetic checks remain.
"""
import argparse, collections, hashlib, json, signal, subprocess, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cbmc',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();a.cbmc=a.cbmc.resolve();out=a.output;out.mkdir(parents=True,exist_ok=False)
    import scripts.cert_recheck_flat_v100 as F
    F.PRE+='\n'+''.join(t+' '+name+'(void){'+t+' value; __CPROVER_havoc_object(&value); return value;}\n'for t,name in F.ND.items())
    trans={r['dir']+'/'+r['file']:r for r in json.loads((ROOT/'experiments/v099_fresh/translated.json').read_text())if r['stage'].startswith('in_')}
    kept={};seen=set();missing=[]
    for r in map(json.loads,(ROOT/'experiments/v099_fresh_hybrid/results.jsonl').read_text().splitlines()):
        if r['final']!='PROVED':continue
        v=json.dumps(r['invariant']);key=(r['program'],v[:600]);full=(r['program'],v)
        if key not in kept:kept[key]=v
        elif kept[key]!=v and full not in seen:missing.append(r)
        seen.add(full)
    assert len(missing)==2
    save(out/'protocol.json',{'base':'18d66724bfe94094afc5148ab2bac3dfaef3085d','selection':'all exact certificates excluded by 600-character prefix deduplication in fresh_hybrid','cbmc_version':subprocess.check_output([str(a.cbmc),'--version'],text=True).strip(),'binary_sha256':sha(a.cbmc),'flat_checker_sha256':sha(ROOT/'scripts/cert_recheck_flat_v100.py'),'driver_sha256':sha(Path(__file__)),'host_seconds':30,'scope':'two supplementary checks, not a rerun of the 586 historical records; same flat proof rule, own reimplementation on a separate engine'})
    rows=[]
    for i,r in enumerate(missing):
        d=out/f'{i:02d}';d.mkdir();source=trans[r['program']];code,n=F.build(source['source'],source['parameter_bounds'],r['invariant']);f=d/'harness.c';f.write_text(code);save(d/'request.json',{'program':r['program'],'source':source['source'],'bounds':source['parameter_bounds'],'invariant':r['invariant'],'abi':r['abi']})
        assert r['abi']=='LP64'
        argv=[str(a.cbmc),str(f.resolve()),'--64','--signed-overflow-check','--div-by-zero-check','--json-ui'];timed=False
        with (d/'stdout.json').open('w')as stdout,(d/'stderr.txt').open('w')as stderr:
            p=subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            try:code=p.wait(timeout=30)
            except subprocess.TimeoutExpired:timed=True;os.killpg(p.pid,signal.SIGKILL);code=p.wait()
        status='TIMEOUT'if timed else 'ERROR';failed=[]
        if not timed:
            try:
                blocks=json.loads((d/'stdout.json').read_text());props=[p for b in blocks for p in b.get('result',[])];failed=[{k:v for k,v in p.items()if k!='trace'}for p in props if p['status']=='FAILURE']
                if code==0 and any(b.get('cProverStatus')=='success'for b in blocks):status='VERIFIED'
                elif code==10 and failed:status='FAILED'
            except ValueError:pass
        row={'program':r['program'],'result':status,'exit_code':code,'failures':failed,'argv':argv,'invariant_sha256':hashlib.sha256(json.dumps(r['invariant']).encode()).hexdigest()};save(d/'result.json',row);rows.append(row);print(r['program'],status,flush=True)
    save(out/'results.json',{'supplemental_checks':len(rows),'historical_records_not_overwritten':True,'counts':dict(collections.Counter(r['result']for r in rows)),'rows':rows})
if __name__=='__main__':main()
