"""Full frozen 165-input, original-source, equal-cap comparison.
All outcomes retained. No model calls; proof-only comparison is primary.
"""
import argparse,collections,hashlib,json,os,random,re,subprocess,sys,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import yaml
from scripts.resource_capture import capture
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def freeze(external,out):
    sv=external/'svbench';ult=external/'ultimate-v0.3.2/UAutomizer-linux';cbmc=external/'native/usr/bin/cbmc';cases=[]
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=sv,text=True).strip()=='2e1723fde6aa65a250dcb677efa45edaa4b6b631'
    import scripts.svcomp_translate as T
    T.NOOVF=True;T.GHOST=True
    for r in json.loads((ROOT/'experiments/v099_fresh/translated.json').read_text()):
        rel=Path(r['dir'])/r['file'];p=sv/'c'/rel;yp=p.with_suffix('.yml');y=yaml.safe_load(yp.read_text());prop=[x for x in y['properties']if x['property_file'].endswith('/no-overflow.prp')];expected=prop[0].get('expected_verdict')if prop else None
        if r['stage'].startswith('in_'):
            code,bounds=T.translate(p);assert code==r['source']and bounds==r['parameter_bounds']
        cases.append({'name':str(rel),'source_sha256':sha(p),'yaml_sha256':sha(yp),'abi':y['options']['data_model'],'expected_nooverflow':expected,'old_expected_unreach':r['expected_unreach'],'historical_stage':r['stage']})
    assert len(cases)==165
    out.mkdir(parents=True,exist_ok=False);(out/'no-overflow.prp').write_text('CHECK( init(main()), LTL(G ! overflow) )\n')
    files=[Path(__file__),ROOT/'scripts/resource_capture.py',ROOT/'scripts/ultimate_adapter_v103.py',ROOT/'scripts/svcomp_translate.py',*sorted((ROOT/'llmloop').glob('*.py'))]
    configs={str(p.relative_to(ult)):sha(p)for p in sorted((ult/'config').rglob('*'))if p.is_file()}
    plan={'base_commit':'18d66724bfe94094afc5148ab2bac3dfaef3085d','cases':cases,'tools':['ultimate','cbmc','llmloop'],'host_seconds':600,'memory_bytes':2*1024**3,'workers':4,'seed':20261122,
       'scope':'all 165 original input paths; proof-only comparison primary; equal 600 s process-group wall cap and 2 GiB sampled group RSS cap; no LLM or reconstructed model latency',
       'labels':'read no-overflow.prp from original YAML, not translator expected_unreach; 102 upstream true,63 unlabelled; labels subject to independent corroboration',
       'svbench_pin':'2e1723fde6aa65a250dcb677efa45edaa4b6b631','ultimate_release':'v0.3.2','ultimate_archive_sha256':sha(external/'ultimate-v0.3.2.zip'),'ultimate_wrapper_sha256':sha(ult/'Ultimate.py'),'ultimate_config_sha256':configs,
       'ultimate_adapter':'unmodified release imported with JVM Xmx1G and ActiveProcessorCount=1; default/bitvector author portfolio retained; internal timeout600 and overall host600 includes startup/portfolio',
       'cbmc_version':subprocess.check_output([str(cbmc),'--version'],text=True).strip(),'cbmc_binary_sha256':sha(cbmc),'cbmc_configuration':'--no-standard-checks --signed-overflow-check --unwind 64 --unwinding-assertions, actual ABI; incomplete unrolling is UNKNOWN',
       'llmloop_configuration':'current translator NOOVF/GHOST; deterministic default then existing polynomial profile only if default not proved; 60 samples,150 rounds,5s per query,seed1; unsupported inputs retained',
       'timing':'concurrent throughput observations, not cross-tool speedup; wait4 CPU, sampled group RSS, stdout/stderr, actual commands retained','pilot_disclosure':'GCD3 original inspected and Ultimate setup piloted before freeze; all165 selected before outcomes; no case removal',
       'frozen_source_sha256':{str(p.relative_to(ROOT)):sha(p)for p in files},'remote_model_calls':0}
    save(out/'protocol.json',plan);tasks=[{'case':c,'tool':t}for c in cases for t in plan['tools']];random.Random(plan['seed']).shuffle(tasks);save(out/'schedule.json',tasks)
    save(out/'environment.json',{'python':sys.version,'platform':__import__('platform').platform(),'java':subprocess.run(['java','-version'],capture_output=True,text=True).stderr,'cpu_count':os.cpu_count(),'z3':__import__('z3').get_version_string(),'pycparser':__import__('pycparser').__version__,'sympy':__import__('sympy').__version__})
def worker(external,out,index):
    task=json.loads((out/'schedule.json').read_text())[index];c=task['case'];d=out/'raw'/f'{index:04d}';p=external/'svbench/c'/c['name']
    import scripts.svcomp_translate as T
    from llmloop.houdini_loops import houdini_loops
    T.NOOVF=True;T.GHOST=True
    try:source,bounds=T.translate(p)
    except Exception as e:save(d/'result.json',{'status':'UNSUPPORTED','reason':str(e)});return
    save(d/'translation.json',{'source':source,'bounds':bounds,'abi':c['abi']});phases=[]
    for poly in [False,True]:
        try:status,inv,rounds,log=houdini_loops(source,bounds,abi=c['abi'],integer_model='c',runs=60,max_rounds=150,solver_timeout_ms=5000,seed=1,poly=poly)
        except Exception as e:status='ERROR:'+type(e).__name__+':'+str(e);inv=[];rounds=0;log=[]
        phases.append({'poly':poly,'status':status,'invariant':inv,'rounds':rounds,'log':log});save(d/'phases.json',phases)
        if status=='PROVED':save(d/'result.json',{'status':'TRUE','phases':phases});return
    save(d/'result.json',{'status':'UNKNOWN','phases':phases})
def run(external,out):
    plan=json.loads((out/'protocol.json').read_text());assert all(sha(ROOT/p)==v for p,v in plan['frozen_source_sha256'].items())
    ult=external/'ultimate-v0.3.2/UAutomizer-linux';cbmc=external/'native/usr/bin/cbmc';tasks=json.loads((out/'schedule.json').read_text())
    def trial(i,t):
        d=out/'raw'/f'{i:04d}'
        if(d/'outcome.json').exists():return json.loads((d/'outcome.json').read_text())
        d.mkdir(parents=True,exist_ok=True);c=t['case'];p=external/'svbench/c'/c['name'];assert sha(p)==c['source_sha256'];save(d/'request.json',t);work=d/'work';work.mkdir(exist_ok=True);env=os.environ.copy()
        if t['tool']=='ultimate':
            env['V103_ULTIMATE']=str(ult);argv=[sys.executable,'-u',str(ROOT/'scripts/ultimate_adapter_v103.py'),'--spec',str(out/'no-overflow.prp'),'--file',str(p),'--architecture','32bit'if c['abi']=='ILP32'else'64bit','--full-output','--witness-dir',str(work),'--core.toolchain.timeout.in.seconds','600']
        elif t['tool']=='cbmc':argv=[str(cbmc),str(p),'--32'if c['abi']=='ILP32'else'--64','--no-standard-checks','--signed-overflow-check','--unwind','64','--unwinding-assertions','--json-ui']
        else:argv=[sys.executable,'-u',str(Path(__file__).resolve()),'worker','--external',str(external),'--output',str(out),'--index',str(i)]
        res=capture(argv,d,cwd=work,env=env,wall_seconds=plan['host_seconds'],memory_bytes=plan['memory_bytes']);status=res['stop_reason']or'ERROR'
        if not res['stop_reason']:
            if t['tool']=='ultimate':
                m=re.search(r'Result:\s*\n\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)',(d/'stdout.txt').read_text(errors='replace'));status=m.group(1)if m else'NO_RESULT'
            elif t['tool']=='cbmc':
                try:
                    blocks=json.loads((d/'stdout.txt').read_text());props=[p for b in blocks for p in b.get('result',[])];failed=[p for p in props if p['status']=='FAILURE'];save(d/'properties.json',[{k:v for k,v in p.items()if k!='trace'}for p in props])
                    if res['exit_code']==10 and any(p.get('sourceLocation',{}).get('propertyClass')=='overflow'for p in failed):status='FALSE'
                    elif res['exit_code']==0 and any(b.get('cProverStatus')=='success'for b in blocks):status='TRUE'
                    else:status='UNKNOWN'
                except ValueError:status='MALFORMED_OUTPUT'
            elif(d/'result.json').exists():status=json.loads((d/'result.json').read_text())['status']
        result={'index':i,'program':c['name'],'tool':t['tool'],'expected_nooverflow':c['expected_nooverflow'],'status':status,'upstream_label_conflict':c['expected_nooverflow']is True and status=='FALSE',**res};save(d/'outcome.json',result);return result
    rows=[]
    with ThreadPoolExecutor(plan['workers'])as pool:
        for f in as_completed([pool.submit(trial,i,t)for i,t in enumerate(tasks)]):
            rows.append(f.result())
            if len(rows)%10==0:print(json.dumps({'captured':len(rows),'planned':len(tasks),'counts':dict(collections.Counter(r['tool']+':'+r['status']for r in rows))}),flush=True)
    unchanged=all(sha(ROOT/p)==v for p,v in plan['frozen_source_sha256'].items());save(out/'results.json',{'complete_capture':len(rows)==495,'source_unchanged':unchanged,'rows':sorted(rows,key=lambda r:r['index']),'counts':dict(collections.Counter(r['tool']+':'+r['status']for r in rows)),'remote_model_calls':0});assert unchanged
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['freeze','run','worker']);p.add_argument('--external',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--index',type=int);a=p.parse_args();a.external=a.external.resolve();a.output=a.output.resolve()
    if a.action=='freeze':freeze(a.external,a.output)
    elif a.action=='worker':worker(a.external,a.output,a.index)
    else:run(a.external,a.output)
