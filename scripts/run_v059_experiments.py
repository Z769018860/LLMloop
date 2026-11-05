"""Frozen validation of typed proposal certification and paper-facing evidence."""
import argparse,hashlib,json,os,platform,re,subprocess,sys,time
from pathlib import Path
import pycparser,pytest,sympy,z3
from llmloop.clang_adapter import compiler_path
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=3210

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('experiments/v059'));a=p.parse_args();os.chdir(ROOT);out=a.output;out.mkdir(parents=True,exist_ok=True)
 assert all(p.name=='attempts' for p in out.iterdir()),'Retain previous attempts; start with an empty evidence directory'
 def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
 files=git('ls-files').splitlines();source={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files if not p.startswith('experiments/')};prior={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in files if p.startswith('experiments/')}
 assert not git('diff','HEAD','--',*source),'Freeze source before validating'
 manifest={'tested_commit':git('rev-parse','HEAD'),'tested_tree':git('rev-parse','HEAD^{tree}'),'source_sha256':source,'historical_evidence_sha256':prior};(out/'source_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');commands={}
 def run(name,argv,timeout):
  start=time.perf_counter()
  with (out/(name+'.txt')).open('w') as log:
   try:code=subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
   except subprocess.TimeoutExpired:code=124
  commands[name]={'argv':argv,'exit_code':code,'elapsed_seconds':time.perf_counter()-start,'log':name+'.txt'};(out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');print(name,json.dumps(commands[name]),flush=True)
  return (out/(name+'.txt')).read_text()
 text=run('pytest',[sys.executable,'-m','pytest','-q','--forked'],1800)
 def count(word):
  x=re.findall(r'(\d+) '+word,text);return int(x[-1]) if x else 0
 full={'passed':count('passed'),'failed':count('failed'),'skipped':count('skipped'),'expected':EXPECTED}
 run('portfolio',[sys.executable,'scripts/check_summary_portfolio.py','--output',str(out/'portfolio.json')],600)
 for name in ['typed_recurrence','typed_nested']:run(name,[sys.executable,'scripts/check_'+name+'_native.py'],600)
 demo=run('demo',[sys.executable,'-c','import json;from pathlib import Path;from llmloop.api import analyze_request;print(json.dumps(analyze_request(json.loads(Path("examples/typed_summary_portfolio.json").read_text()))))'],120)
 (out/'demo.json').write_text(demo)
 try:matrix=json.loads((out/'portfolio.json').read_text())
 except (FileNotFoundError,json.JSONDecodeError):matrix={}
 try:d=json.loads(demo)
 except json.JSONDecodeError:d={}
 expected={'analysis_configurations':13,'unique_source_programs':7,'certified_summary_configurations':7,'bounded_fallback_proved_configurations':1,'unknown_configurations':5,'native_output_matches':92,'expected_ubsan_traps':8,'sanitizer_coverage_observations':4,'remote_model_calls':0,'real_llm_gain_measured':False,'speedup_claimed':False}
 checks={k:v['exit_code']==0 for k,v in commands.items()};checks.update(full_count=full=={'passed':EXPECTED,'failed':0,'skipped':0,'expected':EXPECTED},portfolio_result=matrix.get('passed') is True and all(matrix.get(k)==v for k,v in expected.items()),coverage_retained=matrix.get('canceled_overflow_sanitizer_traps',-10)+matrix.get('canceled_overflow_sanitizer_misses',-10)==4,demo=d.get('status')=='PROVED_DEFINED_TYPED_C_RECURRENCE' and d.get('evaluation',{}).get('value')==1000000000 and d.get('summary_portfolio',{}).get('selected_id')=='modular-trajectory',source_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in source.items()),historical_evidence_unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in prior.items()))
 result={'passed':all(checks.values()),'checks':checks,'full_pytest':full,'new_tests':49,'existing_cases_deleted':0,'tested_commit':manifest['tested_commit'],'tested_tree':manifest['tested_tree'],'source_paths':len(source),'historical_evidence_paths':len(prior),'commands':commands,'portfolio_metrics':{k:matrix.get(k) for k in expected},'sanitizer_coverage':{k:matrix.get(k) for k in ['canceled_overflow_sanitizer_traps','canceled_overflow_sanitizer_misses']},'github_actions_used':False,'klee_used':False,'per_query_budgets_increased':False,'real_llm_gain_measured':False,'external_baselines_measured':False,'complete_c_support':False,'environment':{'python':platform.python_version(),'platform':platform.platform(),'pytest':pytest.__version__,'sympy':sympy.__version__,'z3':z3.get_version_string(),'pycparser':pycparser.__version__,'clang':subprocess.check_output([compiler_path(),'--version'],text=True).splitlines()[0],'gcc':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]}}
 report=f'''# v0.59 Source-checked trajectory portfolio

Frozen source `{manifest['tested_commit']}`, tree `{manifest['tested_tree']}`.
Full regression: **{full['passed']} passed, {full['failed']} failed, {full['skipped']} skipped**.
49 new tests, no deleted cases. All execution is local; Actions and KLEE are not used.

The coordinator validates every proposal envelope before any proof, then checks
at most eight supplied trajectories with fresh original-source typed recurrence
or nested-loop verifiers on deep copies of the identical source/domain/ABI.
Only an exact backend success status with definedness and termination flags
selects a result. It retains failed candidates and unattempted suffixes. Failed
candidates do not prove source undefinedness. Optional 1..512-step bounded CFG
fallback must prove complete exit and is never labeled an accelerated summary.
The first-certified order is explicit, not cost-optimal. No remote model is
called. Per-query (5000 ms) and existing engine budgets are unchanged; up to
eight independent proofs plus one fallback can take longer than one query.

Paired local evidence: **13 configurations over 7 distinct source programs**;
**7 certified trajectory configurations**, **1 proved bounded fallback**, and
**5 UNKNOWN controls**. The original bounded CFG baseline always uses 128 steps;
source, domain and ABI match each paired configuration. Fresh workers record
startup-inclusive wall times and analysis-only times separately. This controlled
fixture replay does not measure real LLM gain, external-tool superiority or a
general speedup. Neither configuration counts nor native samples are a count
of independently held-out programs. Typed nested/recurrence native suites are
also rerun; the selected feature does not change the sizeof/memory kernels.

GCC/Clang O0/O2 original separate objects have **92 positive output matches** on
small native inputs. Universal and very large-count evaluations come from source
certificates, not native billion/trillion-iteration executions. Observable
signed overflow and zero-divisor controls require **8 UBSan traps**. The canceled
intermediate-overflow source remains UNKNOWN in both modes but has
**{matrix.get('canceled_overflow_sanitizer_traps')} traps and
{matrix.get('canceled_overflow_sanitizer_misses')} non-diagnosed executions** in
four sanitizer observations. These executions are undefined source and are not
positive matches. The initial failed assumption that every such execution must
trap is retained. Sanitizer silence never certifies source correctness.

All {len(source)} tracked source paths and {len(prior)} historical evidence paths
are hash checked. Full commands, requests/results, source forms, times and
prevalidation attempts are retained. Compiled objects/executables are disposable
intermediates; raw source/command/result evidence is archived. The earlier v0.58
3,161-test / 6,384-match report is a separate grammar/memory validation baseline,
not a speedup or representative program-coverage result.

Still missing for the planned paper: real typed-trajectory model runs with
model/prompt/response provenance, held-out benchmarks, explicit LoopSCC/ELBA/
MALICE/LIFT comparisons on compatible tasks, repeated end-to-end timings and
pre-registered ablations. General C/LLVM/heap coverage remains open and is not a
precondition for a paper with an explicit restricted source contract.

Checks: `{json.dumps(checks,sort_keys=True)}`. Passed: **{result['passed']}**.
'''
 (out/'report.md').write_text(report);result['evidence_sha256']={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in {'.json','.txt','.c','.py','.md'} and p!=out/'results.json'};(out/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ['commands','environment','evidence_sha256']}),flush=True)
 if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
