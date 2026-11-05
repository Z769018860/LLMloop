"""Paired local source checks of supplied (not real-LLM) trajectory proposals."""
import argparse,copy,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
ROOT=Path(__file__).resolve().parents[1]
WRAP='long f(int n){unsigned char x=0;long y=0;for(int i=0;i<n;i++){x++;y++;}return y+x;}'
SAT='long f(int n){unsigned char x=0;for(int i=0;i<n;i++){if(x<255)x++;}return x;}'
NEST='long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}'
TRI='long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<2*i+1;j++){x++;}}return x;}'
OVER='long f(int n){int x=2147483647;for(int i=0;i<n;i++){x=(x+1)-1;}return x;}'
OBS='long f(int n){int x=2147483647;for(int i=0;i<n;i++){x=x+1;}return x;}'
DIV='long f(int n){int x=0;for(int i=0;i<n;i++){x=n/(n-1);}return x;}'


def fixtures():
 def case(name,source,summaries,bounds,inputs,value,status='PROVED_DEFINED_TYPED_C_RECURRENCE',backend='typed_recurrence',fallback=None,abi='LP64',native_inputs=None,oracle=None):
  q={'source':source,'frontend':'typed_summary_portfolio','summary_backend':backend,'proposals':[{'id':str(i),'summary':s} for i,s in enumerate(summaries)],'parameter_bounds':bounds,'inputs':inputs,'abi':abi}
  if fallback is not None:q['fallback']={'max_steps':fallback}
  return dict(name=name,request=q,expected_status=status,expected_value=value,native_inputs=native_inputs or [],oracle=oracle)
 good={'x':'i%256','y':'i'};bad={'x':'0','y':'i'}
 rows=[case('modular_'+abi,WRAP,[bad,good],{'n':[0,1000000000]},{'n':1000000000},1000000000,abi=abi,native_inputs=[(0,),(1,),(3,),(257,)] if abi=='LP64' else [],oracle=lambda n:n+n%256) for abi in ['LP64','ILP32','LLP64']]
 rows += [case('saturation',SAT,[{'x':'i'},{'x':'Min(i,255)'}],{'n':[0,1000000]},{'n':1000000},255,native_inputs=[(0,),(1,),(255,),(300,)],oracle=lambda n:min(n,255)),
  case('negative_zero',WRAP,[good],{'n':[-5,0]},{'n':-3},0,native_inputs=[(-5,),(-1,),(0,)],oracle=lambda n:0),
  case('nested_product',NEST,[{'i':{'x':'i*m'},'j':{'x':'entry("x")+j'}}],{'n':[0,1000],'m':[0,1000]},{'n':1000,'m':1000},1000000,status='PROVED_DEFINED_TYPED_C_NESTED',backend='typed_nested',native_inputs=[(0,0),(0,3),(3,0),(3,5)],oracle=lambda n,m:n*m),
  case('nonrectangular',TRI,[{'i':{'x':'i*i'},'j':{'x':'entry("x")+j'}}],{'n':[0,1000000]},{'n':1000000},1000000000000,status='PROVED_DEFINED_TYPED_C_NESTED',backend='typed_nested',native_inputs=[(0,),(1,),(3,),(15,)],oracle=lambda n:n*n),
  case('explicit_small_fallback',WRAP,[bad],{'n':[0,3]},{'n':3},6,status='PROVED_DEFINED_TYPED_C_CFG_HEAP',fallback=128,native_inputs=[(0,),(1,),(2,),(3,)],oracle=lambda n:2*n),
  case('large_fallback_frontier',WRAP,[bad],{'n':[0,1000000000]},{'n':1000000000},None,status='UNKNOWN',fallback=16),
  case('late_wrong_candidate',WRAP,[{'x':'i%256','y':'i if i<1000000 else 0'}],{'n':[0,1000000000]},{'n':1000000},None,status='UNKNOWN'),
  case('intermediate_overflow',OVER,[{'x':'2147483647'}],{'n':[1,2]},{'n':1},None,status='UNKNOWN',fallback=128),
  case('observable_overflow',OBS,[{'x':'2147483647'}],{'n':[1,2]},{'n':1},None,status='UNKNOWN',fallback=128),
  case('executed_zero_divisor',DIV,[{'x':'0'}],{'n':[1,2]},{'n':1},None,status='UNKNOWN',fallback=128)]
 return rows


def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--result',type=Path);a=p.parse_args()
 if a.worker:
  start=time.perf_counter();r=analyze_request(json.loads(a.worker.read_text()));a.result.write_text(json.dumps({'result':r,'analysis_seconds':time.perf_counter()-start},indent=2)+'\n');return
 if a.output is None:p.error('--output required')
 out=a.output;out.parent.mkdir(parents=True,exist_ok=True);raw=out.parent/(out.stem+'_raw');raw.mkdir(exist_ok=False)
 rows=[];commands=[];native_matches=traps=coverage_traps=coverage_misses=0
 def command(argv,log,timeout=120):
  start=time.perf_counter();r=subprocess.run(argv,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
  record={'argv':argv,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr,'wall_seconds':time.perf_counter()-start};commands.append(record);log.write_text(json.dumps(record,indent=2)+'\n');return r,record
 for c in fixtures():
  directory=raw/c['name'];directory.mkdir();q=c['request'];results={}
  for mode in ['portfolio','bounded_cfg']:
   request=copy.deepcopy(q)
   if mode=='bounded_cfg':
    request={k:v for k,v in request.items() if k not in {'frontend','summary_backend','proposals','fallback'}};request.update(frontend='typed_cfg_heap',max_steps=128)
   context_keys={'source','function','parameter_bounds','abi','char_signed','max_paths','inputs'}
   assert {k:v for k,v in request.items() if k in context_keys}=={k:v for k,v in q.items() if k in context_keys}
   req=directory/(mode+'_request.json');res=directory/(mode+'_result.json');req.write_text(json.dumps(request,indent=2)+'\n')
   r,cmd=command([sys.executable,str(Path(__file__).resolve()),'--worker',str(req.resolve()),'--result',str(res.resolve())],directory/(mode+'_command.json'))
   assert r.returncode==0,(c['name'],mode,cmd)
   result=json.loads(res.read_text());results[mode]=result
  actual=results['portfolio']['result'];assert actual['status']==c['expected_status'],(c['name'],actual)
  if c['expected_value'] is not None:assert actual['evaluation']['value']==c['expected_value'],(c['name'],actual)
  if c['expected_status']=='UNKNOWN':assert not actual.get('c_overflow_verified') and not actual.get('termination_proved')
  observations=[]
  if c['native_inputs'] or c['name'] in ['intermediate_overflow','observable_overflow','executed_zero_divisor']:
   inputs=c['native_inputs'] or [(1,)];args=len(inputs[0]);source=directory/'source.c';harness=directory/'harness.c';source.write_text(q['source'])
   calls=''.join('printf("%lld\\n",(long long)f('+','.join(map(str,values))+'));' for values in inputs)
   harness.write_text('#include <stdio.h>\nlong f('+','.join(['int']*args)+');int main(void){'+calls+'return 0;}\n')
   for compiler_name,compiler in [('gcc','gcc'),('clang',compiler_path())]:
    for opt in ['-O0','-O2']:
     tag=compiler_name+opt;obj=directory/(tag+'.o');exe=directory/tag
     flags=['-std=c11',opt,'-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-fno-builtin']
     for index,argv in enumerate([[compiler,*flags,'-c',str(source.resolve()),'-o',str(obj.resolve())],[compiler,*flags,str(harness.resolve()),str(obj.resolve()),'-o',str(exe.resolve())]]):
      comp,_=command(argv,directory/(tag+'-compile'+str(index)+'.json'));assert comp.returncode==0,comp.stderr
     run,record=command([str(exe.resolve())],directory/(tag+'-run.json'))
     if c['native_inputs']:
      expected=[str(c['oracle'](*values)) for values in inputs];assert run.returncode==0 and not run.stderr and run.stdout.splitlines()==expected,(c['name'],record,expected);native_matches+=len(expected)
     elif c['name']=='intermediate_overflow':
      if run.returncode==-4:coverage_traps+=1
      else:assert run.returncode==0,(c['name'],record);coverage_misses+=1
     else:assert run.returncode==-4,(c['name'],record);traps+=1
     observations.append(record)
  rows.append({'name':c['name'],'source_sha256':hashlib.sha256(q['source'].encode()).hexdigest(),'expected_status':c['expected_status'],'expected_value':c['expected_value'],'native_inputs':c['native_inputs'],'native_observations':observations,'results':results})
  print(c['name'],actual['status'],results['bounded_cfg']['result']['status'],flush=True)
 summary={'passed':True,'analysis_configurations':len(rows),'unique_source_programs':len({r['source_sha256'] for r in rows}),'certified_summary_configurations':sum(r['results']['portfolio']['result']['summary_portfolio']['certified_summary'] for r in rows),'bounded_fallback_proved_configurations':sum(r['results']['portfolio']['result']['status']=='PROVED_DEFINED_TYPED_C_CFG_HEAP' for r in rows),'unknown_configurations':sum(r['results']['portfolio']['result']['status']=='UNKNOWN' for r in rows),'native_output_matches':native_matches,'expected_ubsan_traps':traps,'canceled_overflow_sanitizer_traps':coverage_traps,'canceled_overflow_sanitizer_misses':coverage_misses,'sanitizer_coverage_observations':coverage_traps+coverage_misses,'remote_model_calls':0,'real_llm_gain_measured':False,'speedup_claimed':False,'comparators':['supplied_untrusted_portfolio','original_bounded_cfg_128_steps'],'semantic_context_identical_between_modes':True,'timing_scope':'fresh-worker wall time includes interpreter startup; analysis_seconds excludes startup, includes verification. No provider/network time: proposals are supplied fixtures.','rows':rows,'commands':commands}
 assert (summary['analysis_configurations'],summary['unique_source_programs'],summary['certified_summary_configurations'],summary['bounded_fallback_proved_configurations'],summary['unknown_configurations'],native_matches,traps)==(13,7,7,1,5,92,8),summary
 assert coverage_traps+coverage_misses==4
 out.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k not in ['rows','commands']}),flush=True)

if __name__=='__main__':main()
