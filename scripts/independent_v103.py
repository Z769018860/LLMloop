"""Frozen external-origin signed-overflow benchmark with independent labels.
NIST int64 max-source controls plus all TACLeBench C main candidates.
No result-dependent selection and no model calls. Unknown labels remain unknown.
"""
import argparse,collections,hashlib,json,os,random,re,subprocess,sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from scripts.resource_capture import capture
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def freeze(external,out):
    out.mkdir(parents=True,exist_ok=False);cases=[];jt=external/'juliet';tb=external/'tacle-bench';prefix='CWE190_Integer_Overflow__int64_t_max_'
    prior=[]
    for p in (ROOT/'experiments').rglob('*'):
        if p.is_file()and p.suffix in ['.json','.jsonl']and'v103'not in p.parts:
            if prefix.encode()in p.read_bytes():prior.append(str(p.relative_to(ROOT)))
    assert not prior, 'Selected NIST family already appears in stored experiment records'
    for p in sorted((jt/'testcases/CWE190_Integer_Overflow').glob('s*/*.c')):
        m=re.fullmatch(prefix+r'(add|multiply|postinc|preinc|square)_(\d\d)\.c',p.name)
        if not m or int(m[2])>22:continue
        for kind,truth in [('bad',False),('good',True)]:
            cases.append({'corpus':'nist-int64','path':str(p.relative_to(jt)),'name':p.stem+'_'+kind,'entry':p.stem+'_'+kind,'upstream_label_nooverflow':truth,'abi':'LP64','source_sha256':sha(p),'sources':[str(p.relative_to(jt)),'testcasesupport/io.c'],'source_hashes':{str(p.relative_to(jt)):sha(p),'testcasesupport/io.c':sha(jt/'testcasesupport/io.c')},'family':m[1],'variant':m[2]})
    assert len(cases)==190
    for p in sorted((tb/'bench').rglob('*.c')):
        if not re.search(r'\bint\s+main\s*\(',p.read_text(errors='replace')):continue
        sources=sorted(p.parent.glob('*.c'));cases.append({'corpus':'tacle','path':str(p.relative_to(tb)),'name':str(p.relative_to(tb)),'entry':'main','upstream_label_nooverflow':None,'abi':'LP64','source_sha256':sha(p),'sources':[str(x.relative_to(tb))for x in sources],'source_hashes':{str(x.relative_to(tb)):sha(x)for x in sources},'family':p.relative_to(tb/'bench').parts[0]})
    assert len(cases)==257
    deps={}
    for name,repo,folder in [('nist',jt,jt/'testcasesupport'),('tacle',tb,tb/'bench')]:
        for p in sorted(folder.rglob('*.h')):deps[name+':'+str(p.relative_to(repo))]=sha(p)
    (out/'environment/fake').mkdir(parents=True)
    for n in ['config.h','prelude.h']:(out/'environment/fake'/n).write_text('/* Empty compatibility header: external benchmark needs no gnulib macros. */\n')
    files=[Path(__file__),ROOT/'scripts/resource_capture.py',ROOT/'scripts/auto_transcribe.py',*sorted((ROOT/'llmloop').glob('*.py'))]
    plan={'cases':cases,'nist_pin':subprocess.check_output(['git','rev-parse','HEAD'],cwd=jt,text=True).strip(),'tacle_pin':subprocess.check_output(['git','rev-parse','HEAD'],cwd=tb,text=True).strip(),'prior_nist_exact_family_record_hits':prior,'header_sha256':deps,
       'selection':'all NIST C int64_t_max operations add/multiply/preinc/postinc/square with single-file flow variants <=22, both public good/bad entry points (190); all 67 TACLe C source files matching an int main definition candidate; frozen before reference or system outcomes',
       'independence':'new external source paths and integer-width/source family absent from earlier recorded runs; Juliet int32/control-flow templates were used historically, so this is NOT fully template-family-disjoint; TACLe origin is new; no post-selection tuning',
       'property':'signed arithmetic overflow in original user C, LP64. NIST good/bad labels are upstream expectations, independently checked against original sources with CBMC; TACLe has no provided overflow labels, so only definite CBMC outcomes establish reference labels. No-trap native runs never establish SAFE.',
       'tools':['reference_cbmc','llmloop'],'host_seconds':60,'memory_bytes':512*1024**2,'workers':1,'cbmc_unwind':16,'seed':20261122,'remote_model_calls':0,
       'cbmc_configuration':'original source+original support io.c for NIST, original sibling C units for TACLe; actual public entry; --64 --no-standard-checks --signed-overflow-check --unwind16 --unwinding-assertions --json-ui; unrolling failure alone UNKNOWN',
       'llmloop_configuration':'unchanged production automatic transcriber, existing default then polynomial Houdini; scalar-only safety proofs; declared memory abstractions kept conditional and excluded from unconditional TRUE; per-query5s/sample60/round150/seed1; actual parse and unsupported errors retained',
       'empty_compatibility_headers':'only two empty gnulib compatibility headers, no benchmark function or macro stubs',
       'frozen_source_sha256':{str(p.relative_to(ROOT)):sha(p)for p in files},'reference_binary_sha256':sha(external/'native/usr/bin/cbmc')}
    save(out/'protocol.json',plan);tasks=[{'case':c,'tool':t}for c in cases for t in plan['tools']];random.Random(plan['seed']).shuffle(tasks);save(out/'schedule.json',tasks)
def worker(external,out,index):
    task=json.load(open(out/'schedule.json'))[index];c=task['case'];d=out/'raw'/f'{index:04d}';repo=external/('juliet'if c['corpus']=='nist-int64'else'tacle-bench');p=repo/c['path']
    import scripts.auto_transcribe as A
    from llmloop.houdini_loops import houdini_loops
    includes=[str(p.parent)]+([str(repo/'testcasesupport')]if c['corpus']=='nist-int64'else[])
    try:orig,source,bounds,notes,info=A.transcribe(str(p),c['entry'],includes)
    except Exception as e:save(d/'result.json',{'status':'UNSUPPORTED','reason':type(e).__name__+': '+str(e)});return
    save(d/'translation.json',{'original_function':orig,'source':source,'bounds':bounds,'notes':list(notes),'extra':str(info.extra),'nondet':str(info.nondet)})
    conditional=any('assum'in str(n).lower()or'memory abstract'in str(n).lower()or'loaded pointer'in str(n).lower() for n in notes)
    phases=[]
    for poly in [False,True]:
        try:status,inv,rounds,log=houdini_loops(source,bounds,abi='LP64',integer_model='c',runs=60,max_rounds=150,solver_timeout_ms=5000,seed=1,poly=poly)
        except Exception as e:status='ERROR:'+type(e).__name__+':'+str(e);inv=[];rounds=0;log=[]
        phases.append({'poly':poly,'status':status,'invariant':inv,'rounds':rounds,'log':log});save(d/'phases.json',phases)
        if status=='PROVED':save(d/'result.json',{'status':'CONDITIONAL_TRUE'if conditional else'TRUE','phases':phases,'notes':list(notes)});return
    save(d/'result.json',{'status':'UNKNOWN','phases':phases,'notes':list(notes)})
def trial(external,out,plan,i,t):
    d=out/'raw'/f'{i:04d}'
    if(d/'outcome.json').exists():return json.load(open(d/'outcome.json'))
    d.mkdir(parents=True,exist_ok=True);c=t['case'];repo=external/('juliet'if c['corpus']=='nist-int64'else'tacle-bench');p=repo/c['path'];assert all(sha(repo/n)==h for n,h in c['source_hashes'].items());save(d/'request.json',t);env=os.environ.copy();env['LLMLOOP_CU']=str(out/'environment')
    if t['tool']=='reference_cbmc':
        argv=[str(external/'native/usr/bin/cbmc'),*[str(repo/n)for n in c['sources']],'--function',c['entry'],'--64','--no-standard-checks','--signed-overflow-check','--unwind','16','--unwinding-assertions','--json-ui','-I',str(p.parent)]
        if c['corpus']=='nist-int64':argv+=['-I',str(repo/'testcasesupport')]
    else:argv=[sys.executable,'-u',str(Path(__file__).resolve()),'worker','--external',str(external),'--output',str(out),'--index',str(i)]
    res=capture(argv,d,cwd=d,env=env,wall_seconds=plan['host_seconds'],memory_bytes=plan['memory_bytes']);status=res['stop_reason']or'ERROR'
    if not res['stop_reason']:
        if t['tool']=='reference_cbmc':
            try:
                bs=json.loads((d/'stdout.txt').read_text());props=[p for b in bs for p in b.get('result',[])];failed=[p for p in props if p['status']=='FAILURE'];save(d/'properties.json',[{k:v for k,v in p.items()if k!='trace'}for p in props])
                if res['exit_code']==10 and any(p.get('sourceLocation',{}).get('propertyClass')=='overflow'for p in failed):status='FALSE'
                elif res['exit_code']==0 and any(b.get('cProverStatus')=='success'for b in bs):status='TRUE'
                elif res['exit_code']in [0,10]:status='UNKNOWN'
                else:status='PROCESS_ERROR'
            except ValueError:status='MALFORMED_OUTPUT'
        elif(d/'result.json').exists():status=json.load(open(d/'result.json'))['status']
    row={'index':i,'corpus':c['corpus'],'program':c['name'],'tool':t['tool'],'upstream_label_nooverflow':c['upstream_label_nooverflow'],'status':status,**res};save(d/'outcome.json',row);return row
def run(external,out,shard=None,shards=None):
    plan=json.load(open(out/'protocol.json'));assert all(sha(ROOT/p)==h for p,h in plan['frozen_source_sha256'].items());tasks=json.load(open(out/'schedule.json'));assert len(tasks)==514
    selected=[(i,t)for i,t in enumerate(tasks)if shards is None or i%shards==shard];rows=[]
    with ThreadPoolExecutor(plan['workers'])as pool:
        for f in as_completed([pool.submit(trial,external,out,plan,i,t)for i,t in selected]):
            rows.append(f.result())
            if len(rows)%10==0:print(json.dumps({'captured':len(rows),'planned':len(selected),'counts':dict(collections.Counter(r['corpus']+':'+r['tool']+':'+r['status']for r in rows))}),flush=True)
    unchanged=all(sha(ROOT/p)==h for p,h in plan['frozen_source_sha256'].items())
    payload={'complete_capture':len(rows)==len(selected),'source_unchanged':unchanged,'counts':dict(collections.Counter(r['corpus']+':'+r['tool']+':'+r['status']for r in rows)),'rows':sorted(rows,key=lambda r:r['index']),'remote_model_calls':0,
             'shard':shard,'shards':shards,'planned':len(selected),'protocol_sha256':sha(out/'protocol.json'),'schedule_sha256':sha(out/'schedule.json')}
    if shards is None:save(out/'results.json',payload)
    else:(out/'shards').mkdir(exist_ok=True);save(out/'shards'/f'shard_{shard:02d}.json',payload)
    assert unchanged
def merge(out):
    plan=json.load(open(out/'protocol.json'));tasks=json.load(open(out/'schedule.json'))
    files=sorted((out/'shards').glob('shard_*.json'));assert files,'no shard results'
    by_index={};per_shard={}
    for f in files:
        d=json.load(open(f));assert d['protocol_sha256']==sha(out/'protocol.json')and d['schedule_sha256']==sha(out/'schedule.json')
        assert d['complete_capture'],f'incomplete shard {f}'
        per_shard[f.name]={'rows':len(d['rows']),'counts':d['counts']}
        for r in d['rows']:
            assert r['index']not in by_index,f'duplicate index {r["index"]}'
            by_index[r['index']]=r
    assert len(by_index)==len(tasks)==514,f'{len(by_index)} of {len(tasks)}'
    rows=[by_index[i]for i in range(len(tasks))]
    save(out/'results.json',{'complete_capture':True,'source_unchanged':all(sha(ROOT/p)==h for p,h in plan['frozen_source_sha256'].items()),'counts':dict(collections.Counter(r['corpus']+':'+r['tool']+':'+r['status']for r in rows)),'rows':rows,'remote_model_calls':0,'merged_from_shards':per_shard,'schedule_sha256':sha(out/'schedule.json')})
    print(json.dumps({'merged':len(rows),'shards':len(files),'counts':dict(collections.Counter(r['corpus']+':'+r['tool']+':'+r['status']for r in rows))},indent=1))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','worker','merge']);p.add_argument('--external',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--index',type=int);p.add_argument('--shard',type=int);p.add_argument('--shards',type=int);a=p.parse_args();a.output=a.output.resolve()
    if a.action=='freeze':a.external=a.external.resolve();freeze(a.external,a.output)
    elif a.action=='worker':a.external=a.external.resolve();worker(a.external,a.output,a.index)
    elif a.action=='merge':merge(a.output)
    else:
        a.external=a.external.resolve();assert (a.shard is None)==(a.shards is None);run(a.external,a.output,a.shard,a.shards)
