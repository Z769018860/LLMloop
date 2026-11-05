"""Complete disjoint full-suite partitions, per-test forks, one fixed deadline."""
import argparse,collections,json,os,re,signal,subprocess,sys,time
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-tests',type=int,required=True);a=p.parse_args();out=a.output;out.mkdir()
 start=time.monotonic();deadline=start+1795
 collect=subprocess.run([sys.executable,'-m','pytest','--collect-only','-q'],capture_output=True,text=True,timeout=60)
 (out/'collection.txt').write_text(collect.stdout+collect.stderr);assert collect.returncode==0
 ids=[x for x in collect.stdout.splitlines() if x.startswith('tests/')];assert len(ids)==len(set(ids))==a.expected_tests
 perfile=collections.defaultdict(list)
 for item in ids:perfile[item.split('::')[0]].append(item)
 groups=[[],[]];sizes=[0,0]
 # Whole files are assigned once. No item is excluded for status or duration.
 for name in sorted(perfile,key=lambda name:(-len(perfile[name]),name)):
  k=min(range(2),key=lambda i:sizes[i]);groups[k].append(name);sizes[k]+=len(perfile[name])
 group_ids=[{node for f in group for node in perfile[f]} for group in groups]
 assert not group_ids[0]&group_ids[1] and group_ids[0]|group_ids[1]==set(ids)
 manifest={'full_deadline_seconds':1800,'effective_worker_deadline_seconds':1795,'workers':2,'per_test_forked':True,'expected_items':a.expected_tests,'group_files':groups,'group_items':[sorted(x) for x in group_ids],'disjoint_and_complete':True}
 (out/'partition_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 processes=[];logs=[];argvs=[]
 for k,group in enumerate(groups):
  events=(out/('worker'+str(k)+'.jsonl')).resolve();env={**os.environ,'LLMLOOP_TEST_REPORT_LOG':str(events),'PYTHONPATH':str(Path(__file__).resolve().parent)+os.pathsep+os.environ.get('PYTHONPATH','')}
  argv=[sys.executable,'-m','pytest','-q','--forked','-p','regression_trace',*sorted(group)];argvs.append(argv)
  log=(out/('worker'+str(k)+'.txt')).open('w');logs.append(log)
  processes.append(subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True))
 codes=[]
 try:
  for process in processes:
   try:codes.append(process.wait(timeout=max(0.01,deadline-time.monotonic())))
   except subprocess.TimeoutExpired:raise TimeoutError('Fixed full-suite deadline exceeded')
 except BaseException:
  for process in processes:
   if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
  raise
 finally:
  for log in logs:log.close()
 all_events=[];group_checks=[]
 for k in range(2):
  events=[json.loads(line) for line in (out/('worker'+str(k)+'.jsonl')).read_text().splitlines()];all_events+=events
  calls=[e for e in events if e['phase']=='call'];actual=[e['nodeid'] for e in calls]
  group_checks.append(len(actual)==len(set(actual)) and set(actual)==group_ids[k] and all(e['outcome']=='passed' for e in events))
 counts=collections.Counter(e['outcome'] for e in all_events if e['phase']=='call');errors=[e for e in all_events if e['outcome']!='passed']
 passed=codes==[0,0] and all(group_checks) and counts['passed']==a.expected_tests and not errors
 summary={'passed':passed,'exit_codes':codes,'group_complete':group_checks,'call_outcomes':dict(counts),'nonpassing_reports':errors,'commands':argvs,'elapsed_seconds':time.monotonic()-start,'per_query_budgets_increased':False,'all_items_covered_exactly_once':all(group_checks)}
 (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 print(json.dumps(summary),flush=True)
 print(str(counts['passed'])+' passed'+('' if passed else ', '+str(len(errors))+' failed')+' (two disjoint full-suite partitions)',flush=True)
 if not passed:raise SystemExit(1)

if __name__=='__main__':main()
