"""Frozen, resumable synthetic control study; original inputs remain the denominator.

No model calls. A closed explicit-state graph is the label oracle; native
sanitizers replay the oracle's positive witnesses on original and translated C.
Native replay is not a universal equivalence proof or an external-tool ranking.
"""
import argparse, collections, hashlib, json, os, random, signal, subprocess, sys, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, v): p.write_text(json.dumps(v, indent=2) + '\n')
def hashes():
    files = [Path(__file__), ROOT/'scripts/synth_bench_v102.py', ROOT/'scripts/svcomp_translate.py', *sorted((ROOT/'llmloop').glob('*.py'))]
    return {str(p.relative_to(ROOT)): sha(p) for p in files}

def freeze(corpus, out):
    labels = json.loads((corpus/'labels.json').read_text())
    assert len(labels) == 160
    for name, item in labels.items(): assert sha(corpus/name) == item['source_sha256']
    out.mkdir(parents=True, exist_ok=False)
    source = {'base_commit': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(), 'hashes':hashes()}
    save(out/'source.json', source)
    plan = {'cases': [{'name':n, 'label':v['label'], 'sha256':v['source_sha256']} for n,v in sorted(labels.items())],
            'modes':['trivial','houdini'], 'seeds':[1,2,3], 'schedule_seed':20261122,
            'host_seconds':30, 'solver_timeout_ms':5000, 'sample_runs':60, 'max_rounds':150,
            'scope':'synthetic signed-int32 controls; one generator family; not external holdout or SOTA comparison',
            'acceptance':'capture every outcome; no unsafe source certified; all original+translated overflow witnesses replay',
            'native':'GCC14 and Clang19, O0/O2; original and translated source; sanitizer checks, not sampled SAFE proofs',
            'remote_model_calls':0, 'labels_sha256':sha(corpus/'labels.json')}
    save(out/'protocol.json',plan)
    tasks = [{'case':c,'mode':m,'seed':seed} for seed in plan['seeds'] for c in plan['cases'] for m in plan['modes']]
    random.Random(plan['schedule_seed']).shuffle(tasks); save(out/'schedule.json',tasks)

def worker(corpus, task, target, plan):
    import scripts.svcomp_translate as T
    T.NOOVF = True  # property selection: source assertions are outside no-overflow
    from llmloop.api import analyze_request
    from llmloop.houdini_loops import houdini_loops, _prepare
    started=time.perf_counter()
    try:
        source,bounds=T.translate(corpus/task['case']['name'])
        save(target/'translation.json',{'source':source,'bounds':bounds})
    except Exception as e:
        save(target/'result.json',{'status':'REJECTED','reason':str(e),'seconds':time.perf_counter()-started}); return
    try:
        if task['mode']=='trivial':
            _,_,loops = _prepare(source)
            request={'source':source,'frontend':'typed_invariant_loops','range_invariants':{'invariants':[['True']]*len(loops)},'parameter_bounds':bounds,'abi':'ILP32','integer_model':'c','solver_timeout_ms':plan['solver_timeout_ms']}
            r=analyze_request(request); save(target/'verification.json',r)
            status='PROVED' if r['status'].startswith('PROVED') else r['status']; inv=[['True']]*len(loops)
        else:
            status,inv,rounds,log=houdini_loops(source,bounds,abi='ILP32',integer_model='c',runs=plan['sample_runs'],seed=task['seed'],max_rounds=plan['max_rounds'],solver_timeout_ms=plan['solver_timeout_ms'])
            save(target/'verification.json',{'status':status,'invariants':inv,'rounds':rounds,'log':log})
        save(target/'result.json',{'status':status.split(':')[0],'detail':status,'invariants':inv if status=='PROVED' else None,'seconds':time.perf_counter()-started})
    except Exception as e: save(target/'result.json',{'status':'ERROR','reason':type(e).__name__+': '+str(e),'seconds':time.perf_counter()-started})

def trial(i, task, corpus, out, plan):
    d=out/'raw'/f'{i:04d}'; d.mkdir(parents=True,exist_ok=True)
    if (d/'command.json').exists(): return json.loads((d/'command.json').read_text())
    save(d/'request.json',task)
    argv=[sys.executable,str(Path(__file__).resolve()),'worker','--corpus',str(corpus),'--output',str(out),'--index',str(i)]
    start=time.perf_counter(); timed=False
    with (d/'stdout.txt').open('w') as stdout,(d/'stderr.txt').open('w') as stderr:
        proc=subprocess.Popen(argv,stdout=stdout,stderr=stderr,cwd=ROOT,start_new_session=True)
        try:code=proc.wait(timeout=plan['host_seconds'])
        except subprocess.TimeoutExpired:timed=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
    result=json.loads((d/'result.json').read_text()) if (d/'result.json').exists() else {}
    row={'index':i,'program':task['case']['name'],'label':task['case']['label'],'mode':task['mode'],'seed':task['seed'],
         'status':'HOST_TIMEOUT' if timed else result.get('status','PROCESS_ERROR'), 'exit_code':code, 'wall_seconds':time.perf_counter()-start,'argv':argv}
    save(d/'command.json',row); return row

def run(corpus,out,jobs):
    plan=json.loads((out/'protocol.json').read_text());source=json.loads((out/'source.json').read_text());assert hashes()==source['hashes']
    assert sha(corpus/'labels.json')==plan['labels_sha256']
    for c in plan['cases']:assert sha(corpus/c['name'])==c['sha256']
    tasks=json.loads((out/'schedule.json').read_text());rows=[]
    with ThreadPoolExecutor(jobs) as pool:
        pending=[pool.submit(trial,i,t,corpus,out,plan) for i,t in enumerate(tasks)]
        for f in as_completed(pending):
            rows.append(f.result())
            if len(rows)%40==0: print(json.dumps({'captured':len(rows),'planned':len(tasks)}),flush=True)
    assert hashes()==source['hashes']
    bad=[r for r in rows if r['label']=='OVERFLOW' and r['status']=='PROVED']
    summary={'captured':len(rows),'planned':len(tasks),'complete_capture':len(rows)==len(tasks),'unsafe_certified':bad,'source_unchanged':True,'remote_model_calls':0,
             'counts':dict(collections.Counter(f"{r['mode']}:{r['label']}:{r['status']}" for r in rows)), 'rows':sorted(rows,key=lambda r:r['index'])}
    save(out/'results.json',summary);print(json.dumps({k:v for k,v in summary.items() if k!='rows'}),flush=True)

def native(corpus,out):
    import scripts.svcomp_translate as T
    T.NOOVF = True
    labels=json.loads((corpus/'labels.json').read_text());base=out/'native';base.mkdir(exist_ok=False);rows=[]
    versions={cc:subprocess.check_output([cc,'--version'],text=True).splitlines()[0] for cc in ['gcc','clang']};save(base/'versions.json',versions)
    for name,item in labels.items():
        if item['label']!='OVERFLOW':continue
        d=base/name.removesuffix('.c');d.mkdir();w=item['evidence']['witness'];original=(corpus/name).read_text()
        try:trans,bounds=T.translate(corpus/name)
        except Exception as e:trans=None;save(d/'translation_rejected.json',{'reason':str(e)})
        for kind,src,stream,call in [('original',original.replace('int main()', 'int benchmark_main()'),list(w['inputs'].values())+w['choices'],'benchmark_main()'),
                                     ('translated',trans,w['choices'],'f('+','.join(str(w['inputs'][v]) for v in (bounds if trans else []))+')')]:
            if src is None:continue
            harness='#include <stdlib.h>\nstatic int seq[]={'+','.join(map(str,stream))+'};\nstatic unsigned pos;\nint __VERIFIER_nondet_int(void){if(pos>=sizeof(seq)/sizeof(seq[0]))exit(90);return seq[pos++];}\n'
            file=d/(kind+'.c');file.write_text(harness+src+'\nint main(void){return '+call+';}\n')
            for cc in ['gcc','clang']:
                for opt in ['-O0','-O2']:
                    tag=kind+'_'+cc+opt[1:];exe=d/tag
                    flags=['-fsanitize=signed-integer-overflow']+(['-fno-sanitize-recover=all'] if cc=='gcc' else ['-fsanitize-trap=all'])
                    argv=[cc,'-std=c11',opt,*flags,str(file),'-o',str(exe)]
                    built=subprocess.run(argv,capture_output=True,text=True,timeout=30);(d/(tag+'.build.txt')).write_text(built.stdout+built.stderr)
                    row={'program':name,'kind':kind,'compiler':cc,'optimization':opt,'build_argv':argv,'build_code':built.returncode}
                    if built.returncode==0:
                        try:
                            r=subprocess.run([str(exe.resolve())],capture_output=True,text=True,timeout=10)
                            (d/(tag+'.stdout.txt')).write_text(r.stdout);(d/(tag+'.stderr.txt')).write_text(r.stderr)
                            row.update(exit_code=r.returncode,replayed=(r.returncode==1 and 'runtime error:' in r.stderr and 'overflow' in r.stderr) if cc=='gcc' else r.returncode==-signal.SIGILL)
                        except subprocess.TimeoutExpired:row.update(replayed=False,timeout=True)
                        exe.unlink()
                    else:row['replayed']=False
                    rows.append(row)
        print(name, sum(r['replayed'] for r in rows if r['program']==name),flush=True)
    save(base/'results.json',{'rows':rows,'runs':len(rows),'all_replayed':bool(rows) and all(r['replayed'] for r in rows), 'scope':'positive witness differential replay only; safe labels rely on exhaustive graph oracle'})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','worker','native']);p.add_argument('--corpus',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--jobs',type=int,default=2);p.add_argument('--index',type=int);a=p.parse_args();a.corpus=a.corpus.resolve();a.output=a.output.resolve()
    if a.action=='freeze':freeze(a.corpus,a.output)
    elif a.action=='run':run(a.corpus,a.output,a.jobs)
    elif a.action=='native':native(a.corpus,a.output)
    else:
        plan=json.loads((a.output/'protocol.json').read_text());task=json.loads((a.output/'schedule.json').read_text())[a.index]
        worker(a.corpus,task,a.output/'raw'/f'{a.index:04d}',plan)
