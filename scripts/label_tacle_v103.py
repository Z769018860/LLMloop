"""Independent label refinement on ALL frozen TACLe inputs, unwind256.
No input selection by either system's outcome; unknowns remain in the corpus.
"""
import argparse,collections,hashlib,json,os,random,sys
from pathlib import Path
from scripts.resource_capture import capture
ROOT=Path(__file__).resolve().parents[1]
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def main():
    p=argparse.ArgumentParser();p.add_argument('--external',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();ext=a.external.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    origin=json.load(open(ROOT/'experiments/v103/independent/protocol.json'));cases=[c for c in origin['cases']if c['corpus']=='tacle'];assert len(cases)==67;random.Random(20261122).shuffle(cases)
    plan={'scope':'all 67 frozen TACLe entries; supplementary reference labeling after first-stage setup, not a candidate-generator change or a new test-set selection','selection':'all frozen TACLe source paths, no removal','unwind':256,'host_seconds':60,'memory_bytes':512*1024**2,'reference':'CBMC6.11.0,64bit,signed-overflow,unwinding-assertions','driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'cases':cases}
    out.mkdir(parents=True,exist_ok=True)
    if (out/'protocol.json').exists():  # resume after an interrupted run: the frozen protocol may not drift
        existing={k:v for k,v in json.load(open(out/'protocol.json')).items()if k!='protocol_amendment'}
        assert existing==plan,'existing protocol differs from the frozen one'
    else:save(out/'protocol.json',plan)
    rows=[]
    for i,c in enumerate(cases):
        d=out/'raw'/f'{i:03d}';d.mkdir(parents=True);save(d/'request.json',c);repo=ext/'tacle-bench';src=repo/c['path'];argv=[str(ext/'native/usr/bin/cbmc'),*[str(repo/n)for n in c['sources']],'--function','main','--64','--no-standard-checks','--signed-overflow-check','--unwind','256','--unwinding-assertions','--json-ui','-I',str(src.parent)]
        res=capture(argv,d,cwd=d,env=os.environ.copy(),wall_seconds=60,memory_bytes=512*1024**2);status=res['stop_reason']or'ERROR'
        if not res['stop_reason']:
            try:
                bs=json.load(open(d/'stdout.txt'));props=[p for b in bs for p in b.get('result',[])];failed=[p for p in props if p['status']=='FAILURE'];save(d/'properties.json',[{k:v for k,v in p.items()if k!='trace'}for p in props])
                if res['exit_code']==10 and any(p.get('sourceLocation',{}).get('propertyClass')=='overflow'for p in failed):status='FALSE'
                elif res['exit_code']==0 and any(b.get('cProverStatus')=='success'for b in bs):status='TRUE'
                elif res['exit_code']in [0,10]:status='UNKNOWN'
                else:status='PROCESS_ERROR'
            except ValueError:status='MALFORMED_OUTPUT'
        row={'program':c['name'],'status':status,**res};rows.append(row);save(d/'outcome.json',row)
        print(json.dumps({'captured':len(rows),'planned':67,'counts':dict(collections.Counter(r['status']for r in rows))}),flush=True)
    save(out/'results.json',{'complete_capture':len(rows)==67,'rows':rows,'counts':dict(collections.Counter(r['status']for r in rows))})
if __name__=='__main__':main()
