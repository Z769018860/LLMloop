"""Pinned external reproduction and source-checking feature controls, never LLM fixtures."""
import argparse,ast,copy,hashlib,json,os,random,signal,subprocess,sys,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODES=['bounded','affine_candidates','flat_trajectory','full_trajectory','automatic']
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,obj):Path(path).write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
def controls():
 def c(name,source,forms,affine,value,n=[0,1000000]):
  return {'name':name,'source':source,'summaries':forms,'affine_summaries':affine,'bounds':{'n':n},'inputs':{'n':n[1]},'expected_value':value,'role':'unsafe_control' if value is None else 'defined_control'}
 return [
 c('linear','long f(int n){long x=0;for(int i=0;i<n;i++){x++;}return x;}',{'i':{'x':'i'}},{'i':{'x':'i'}},1000000),
 c('quadratic','long f(int n){long x=0;for(int i=0;i<n;i++){x+=2*i+1;}return x;}',{'i':{'x':'i*i'}},{'i':{'x':'i'}},1000000000000),
 c('unsigned_period','long f(int n){unsigned char x=0;for(int i=0;i<n;i++){x++;}return x;}',{'i':{'x':'i%256'}},{'i':{'x':'i'}},64),
 c('nested_product','long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<3;j++){x++;}}return x;}',{'i':{'x':'3*i'},'j':{'x':'entry("x")+j'}},{'i':{'x':'3*i'},'j':{'x':'entry("x")+j'}},3000000),
 c('nested_triangle','long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<2*i+1;j++){x++;}}return x;}',{'i':{'x':'i*i'},'j':{'x':'entry("x")+j'}},{'i':{'x':'i'},'j':{'x':'entry("x")+j'}},1000000000000),
 c('zero_domain','long f(int n){long x=0;for(int i=0;i<n;i++){x++;}return x;}',{'i':{'x':'i'}},{'i':{'x':'i'}},0,[-3,0]),
 c('canceled_overflow','long f(int n){int x=2147483647;for(int i=0;i<n;i++){x=(x+1)-1;}return x;}',{'i':{'x':'2147483647'}},{'i':{'x':'2147483647'}},None,[1,2]),
 c('division_by_zero','long f(int n){int x=0;for(int i=0;i<n;i++){x=n/(n-1);}return x;}',{'i':{'x':'0'}},{'i':{'x':'0'}},None,[1,2])]
def request(c,mode):
 q={'source':c['source'],'parameter_bounds':copy.deepcopy(c['bounds']),'inputs':c['inputs'],'abi':'LP64'}
 if mode=='bounded':q.update(frontend='typed_cfg_heap',max_steps=128)
 elif mode=='flat_trajectory':q.update(frontend='typed_recurrence',closed_forms=c['summaries']['i'])
 else:q.update(frontend='typed_nested',loop_summaries='auto' if mode=='automatic' else c['affine_summaries'] if mode=='affine_candidates' else c['summaries'])
 return q
def expected(c,mode):
 if c['role']=='unsafe_control':return False
 if mode=='bounded':return c['name']=='zero_domain'
 if mode=='affine_candidates':return c['name'] not in {'quadratic','unsigned_period','nested_triangle'}
 if mode=='flat_trajectory':return c['name'] not in {'nested_product','nested_triangle'}
 # Automatic extraction currently admits +,-,* and selected branches; division
 # is an unsafe refusal. The other six defined source shapes are admitted.
 return True

def freeze(tools,out):
 repos={'elba':('54c58fcd872481a5e72f8c4a31ed2ef242b6fbdd','bench_elba','*.smt2'),
        'loopscc':('09ef9351667a8ccd83d7a50907ca5ea90ec521a4','experiments/exp1/LoopSCC/input','*.py')}
 external=[]
 for tool,(commit,directory,glob) in repos.items():
  assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=tools/tool,text=True).strip()==commit
  for p in sorted((tools/tool/directory).glob(glob))[:12]:
   row={'tool':tool,'commit':commit,'path':str(p.relative_to(tools/tool)),'sha256':sha(p),'name':p.stem}
   if tool=='loopscc':
    raw=tools/tool/'experiments/exp1/raw_files'/p.name
    row.update(oracle_path=str(raw.relative_to(tools/tool)),oracle_sha256=sha(raw))
   external.append(row)
 corpus=[]
 for p in sorted((tools/'loopscc/experiments/exp1/LoopSCC/input').glob('*.py')):
  name=p.stem;family='leap' if name.startswith('leap') else 'speed' if name.startswith('speed') else 't_numbered' if name[0]=='t' and name[1:].isdigit() else 'bobble' if 'bobble' in name else name
  corpus.append({'name':name,'family':family,'split':'future_test' if family=='leap' else 'development','source_sha256':sha(p),'path':str(p.relative_to(tools/'loopscc'))})
 plan={'kind':'p0_partial_closure_protocol','prior_main':'30eada4b252377907baa0000e292b57c1e035ec9','seed':20261107,'repetitions':3,'worker_seconds':20,'external_seconds':15,'modes':MODES,
       'external_selection':'first twelve paths in lexicographic order per pinned input directory, fixed before execution; all outcomes retained; default ELBA config, not its multi-config portfolio',
       'public_corpus_partition':corpus,'partition_scope':'source/family-disjoint registration for future model experiments, no held-out LLM results or contamination audit claimed',
       'external_cases':external,'controls':controls(),'external_versions':{'loopscc':'public repository snapshot, not established equivalent to ICSE 2026 anonymous artifact','elba':'unaltered analysis sources; GCC13, Boost1.83, GMP6.3, Z3 4.13.0; forced standard deque include; differs from upstream CMake dependency pins','lift':'pinned 17bf85707be6677186f34dba25aca58130ac8abe, native Mono6.8 compatibility smoke, not author Docker environment or model experiment'},'remote_model_calls':0}
 out.parent.mkdir(parents=True,exist_ok=True);assert not out.exists();save(out,plan)

def run_loopscc(tools,c):
 sys.path.insert(0,str(tools/'loopscc'))
 source=tools/'loopscc'/c['path'];assert sha(source)==c['sha256']
 unit=ast.parse(source.read_text());prefix=[]
 for node in unit.body:
  if isinstance(node,(ast.Import,ast.ImportFrom,ast.Assign,ast.AnnAssign,ast.FunctionDef)):prefix.append(node)
 ns={};exec(compile(ast.Module(body=prefix,type_ignores=[]),str(source),'exec'),ns)
 timer=time.perf_counter();ns['summarizer'].summarize();build=time.perf_counter()-timer
 tests=ns.get('tests',[]);observations=[]
 chosen=tests[:3]
 if tests:
  chosen+= [[(symbol,value) for symbol,_ in tests[0]] for value in [0,1,3]]
 raw=tools/'loopscc'/c['oracle_path'];assert sha(raw)==c['oracle_sha256']
 oracle_ns={};exec(compile(ast.parse(raw.read_text()),str(raw),'exec'),oracle_ns)
 fn=oracle_ns.get('start');params=list(__import__('inspect').signature(fn).parameters) if fn else []
 for sample in chosen:
  init={v.symbols[0].name:int(value) for v,value in sample};point={'inputs':init}
  try:point['summary_output']={str(k):str(v) for k,v in ns['summarizer'].solve(sample)}
  except Exception as exc:point['summary_error']=type(exc).__name__+': '+str(exc)
  saved={};budget=[30000]
  def observer(frame,event,arg):
   if frame.f_code.co_filename==str(raw):
    budget[0]-=1
    if budget[0]<0:raise RuntimeError('direct source observational event cap')
    if event=='return' and frame.f_code.co_name=='start':saved.update(frame.f_locals)
   return observer
  try:
   args=[init[p[:-1] if p.endswith('0') else p] for p in params]
   sys.settrace(observer)
   try:fn(*args)
   finally:sys.settrace(None)
   point['direct_source_output']={k:saved[k] for k in init if k in saved}
   if 'summary_output' in point and set(init)<=set(saved):
    point['matched']=all(int(point['summary_output'][k])==saved[k] for k in init)
  except Exception as exc:point['oracle_incomplete']=type(exc).__name__+': '+str(exc)
  observations.append(point)
 return {'status':'SUMMARY_RETURNED','summary_seconds':build,'observations':observations,'point_checks':sum('matched'in x for x in observations),'point_matches':sum(x.get('matched') is True for x in observations),'point_mismatches':sum(x.get('matched') is False for x in observations),'scope':'mathematical INT source snapshot, finite point checks only; no typed C or universal correctness claim'}

def main():
 p=argparse.ArgumentParser();p.add_argument('--tools',type=Path,required=True);p.add_argument('--freeze',type=Path);p.add_argument('--plan',type=Path);p.add_argument('--output',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--result',type=Path);a=p.parse_args()
 if a.freeze:freeze(a.tools,a.freeze);return
 if a.worker:
  task=json.loads(a.worker.read_text());c=task['case']
  try:
   if task['kind']=='external':result=run_loopscc(a.tools,c)
   else:
    from llmloop.api import analyze_request
    timer=time.perf_counter();r=analyze_request(request(c,task['mode']));proved=r.get('c_overflow_verified') is True and r.get('termination_proved') is True and r.get('status') in {'PROVED_DEFINED_TYPED_C_NESTED','PROVED_DEFINED_TYPED_C_RECURRENCE','PROVED_DEFINED_TYPED_C_CFG_HEAP'}
    result={'status':r.get('status'),'proved':proved,'expected_proved':expected(c,task['mode']),'matched_expectation':proved==expected(c,task['mode']) and (not proved or r.get('evaluation',{}).get('value')==c['expected_value']),'analysis_seconds':time.perf_counter()-timer,'result':r}
  except Exception as exc:result={'status':'TOOL_ERROR','exception':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}
  save(a.result,result);return
 plan=json.loads(a.plan.read_text());out=a.output;out.mkdir(parents=True,exist_ok=True);assert set(p.name for p in out.iterdir())<={'attempts'};raw=out/'raw';raw.mkdir()
 tracked=subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines();assert not subprocess.check_output(['git','diff','HEAD'],cwd=ROOT,text=True)
 manifest={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'tree':subprocess.check_output(['git','rev-parse','HEAD^{tree}'],cwd=ROOT,text=True).strip(),'tracked_sha256':{s:sha(ROOT/s) for s in tracked}}
 save(out/'source_manifest.json',manifest);save(out/'protocol.json',plan)
 tasks=[];rng=random.Random(plan['seed'])
 for repeat in range(plan['repetitions']):
  block=[{'repeat':repeat,'kind':'external','case':c} for c in plan['external_cases']]
  block += [{'repeat':repeat,'kind':'control','case':c,'mode':m} for c in plan['controls'] for m in MODES]
  rng.shuffle(block);tasks+=block
 save(out/'schedule.json',tasks);rows=[]
 for index,task in enumerate(tasks):
  d=raw/f'{index:04d}';d.mkdir();req=d/'request.json';res=d/'result.json';save(req,task)
  if task['kind']=='external' and task['case']['tool']=='elba':
   c=task['case'];file=a.tools/'elba'/c['path'];assert sha(file)==c['sha256'];argv=[str(a.tools/'elba-local'),str(file)];cap=plan['external_seconds']
  else:argv=[sys.executable,str(Path(__file__).resolve()),'--tools',str(a.tools),'--worker',str(req.resolve()),'--result',str(res.resolve())];cap=plan['worker_seconds'] if task['kind']=='control' else plan['external_seconds']
  start=time.perf_counter();timeout=False
  env=dict(os.environ)
  if task['kind']=='external' and task['case']['tool']=='loopscc':env['PYTHONPATH']=str(a.tools/'loopscc-python')
  with (d/'stdout.txt').open('w') as stdout,(d/'stderr.txt').open('w') as stderr:
   proc=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,env=env,start_new_session=True)
   try:code=proc.wait(timeout=cap)
   except subprocess.TimeoutExpired:timeout=True;os.killpg(proc.pid,signal.SIGKILL);code=proc.wait()
  wall=time.perf_counter()-start;result={}
  if res.exists():result=json.loads(res.read_text())
  if task['kind']=='external' and task['case']['tool']=='elba':
   text=(d/'stdout.txt').read_text();result={'status':'HOST_TIMEOUT' if timeout else 'REPORTED_BOUND' if code==0 and 'Success! Found bounds:' in text else 'NO_REPORTED_BOUND','independently_certified':False};save(res,result)
  row={'index':index,'repeat':task['repeat'],'kind':task['kind'],'name':task['case']['name'],'tool':task['case'].get('tool','llmloop'),'mode':task.get('mode'),'wall_seconds':wall,'host_timeout':timeout,'exit_code':code,'status':'HOST_TIMEOUT' if timeout else result.get('status','PROCESS_ERROR'),'matched_expectation':result.get('matched_expectation'),'point_checks':result.get('point_checks',0),'point_matches':result.get('point_matches',0),'point_mismatches':result.get('point_mismatches',0),'argv':argv};save(d/'command.json',row);rows.append(row)
  with (out/'trials.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  if(index+1)%8==0:print(json.dumps({'completed':index+1,'planned':len(tasks),'control_mismatches':sum(r['kind']=='control' and r['matched_expectation'] is not True for r in rows)}),flush=True)
 unchanged=all(sha(ROOT/s)==h for s,h in manifest['tracked_sha256'].items())
 result={'captured_complete':len(rows)==len(tasks),'planned_runs':len(tasks),'recorded_runs':len(rows),'tracked_unchanged':unchanged,'control_mismatches':sum(r['kind']=='control' and r['matched_expectation'] is not True for r in rows),'external_outcomes_are_observations_not_predeclared_successes':True,'remote_model_calls':0,'external_trials':sum(r['kind']=='external' for r in rows),'rows':rows}
 result['passed']=result['captured_complete'] and unchanged and result['control_mismatches']==0
 save(out/'results.json',result);print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)
 if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
