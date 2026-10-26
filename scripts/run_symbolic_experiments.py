"""Reproduce unit regressions, all native oracles, and guarded proof controls.

Writes honest structured evidence; never treats UNKNOWN as certification.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import platform
import pycparser
import re
import subprocess
import sys
import sympy
import z3
from llmloop.api import analyze_request

ROOT = Path(__file__).resolve().parents[1]


def command(args, timeout=300):
    try:
        result = subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=timeout)
        return {'command':args,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
    except subprocess.TimeoutExpired as exc:
        def decode(value):return value.decode(errors='replace') if isinstance(value,bytes) else value or ''
        return {'command':args,'exit_code':None,'timeout':True,'stdout':decode(exc.stdout),'stderr':decode(exc.stderr)}


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT/'experiments/v029')
    parser.add_argument('--fixtures',type=Path,default=ROOT/'experiments/v029/cases.json')
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=True)
    version=command(['git','rev-parse','HEAD'])
    manifest={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
              for pattern in ['llmloop/*.py','tests/*.py','scripts/*.py','pyproject.toml','examples/guarded*','examples/typed_unbounded_loop.c','examples/typed_nested*','examples/typed_memory*','examples/typed_coupled*','examples/typed_counter*','examples/typed_cfg*','examples/typed_recursive*','examples/typed_pointer*','examples/typed_struct*','examples/clang_project/*','examples/clang_proof_project/*','examples/clang_memory_project/*']
              for path in sorted(ROOT.glob(pattern)) if path.is_file()}
    evidence={'schema_version':1,'generated_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'source_base_commit':version['stdout'].strip(),'source_sha256':manifest,
              'environment':{'python':platform.python_version(),'platform':platform.platform(),
                             'sympy':sympy.__version__,'z3':z3.get_version_string(),'pycparser':pycparser.__version__,
                             'compiler':command(['cc','--version'])['stdout'].splitlines()[0]},
              'protocol':{'proof_domain':'each certificate reported input/count domain and integer semantics; typed candidates checked through actual exit',
                          'native_samples':'fixed boundary grids/million-iteration cases plus controlled sanitizer-failure correspondences; not proof of arbitrary C',
                          'scope':'restricted research prototype; no claim that UNKNOWN cases are supported',
                          'performance_claims':False,'suite_timeouts_seconds':{'pytest':1200,'native':300,'api_case':60},'solver_timeouts_ms':{'typed_obligations':5000,'legacy_graph_queries':10000,'finite_control_residue_subqueries':5000,'residue_cases_maximum':8},'pytest_isolation':'fresh forked process per test; original assertions and query budgets unchanged','api_case_isolation':'fresh interpreter/SMT context per request; timeout never becomes a proof','clang_memory_native_isolation':'fresh interpreter per example; each original/normalized scenario checked with ASan/UBSan and live-object accounting; LeakSanitizer disabled because /proc task scanning is unavailable'},'suites':[],'guarded_cases':[]}
    suite_commands=[('pytest',[sys.executable,'-m','pytest','--forked','-q'])]
    suite_commands += [(path.stem,[sys.executable,str(path.relative_to(ROOT))])
                       for path in sorted((ROOT/'scripts').glob('check_*native.py'))]
    for name,argv in suite_commands:
        print('Running '+name,flush=True)
        result=command(argv,timeout=1200 if name=='pytest' else 300)
        checks=[{'passed':int(a),'total':int(b)} for a,b in re.findall(r'(\d+)/(\d+)',result['stdout'])]
        passed=result['exit_code']==0 and all(c['passed']==c['total'] for c in checks)
        if name!='pytest' and not checks:passed=False
        evidence['suites'].append({'name':name,**result,'passed':passed,'checks':checks})
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
        # Preserve a checkpoint even if a subsequent suite is interrupted.
        (args.output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    fixtures=json.loads(args.fixtures.read_text())
    evidence['fixtures_sha256']=hashlib.sha256(args.fixtures.read_bytes()).hexdigest()
    for fixture in fixtures:
        try:
            isolated=subprocess.run([sys.executable,str(ROOT/'scripts/analyze_experiment_case.py')],input=json.dumps(fixture['request']),cwd=ROOT,text=True,capture_output=True,timeout=60)
            report=json.loads(isolated.stdout) if isolated.returncode==0 else {'status':'UNKNOWN','reason':'isolated case process failed: '+isolated.stderr[-2000:]}
        except subprocess.TimeoutExpired:report={'status':'UNKNOWN','reason':'isolated experiment case timed out','analysis_limit':'experiment_case_timeout'}
        except ValueError:report={'status':'UNKNOWN','reason':'invalid isolated experiment report'}
        matched=report['status']==fixture['expected_status']
        evidence['guarded_cases'].append({'name':fixture['name'],'expected_status':fixture['expected_status'],
            'actual_status':report['status'],'matched':matched,'frontend_only':fixture['request'].get('frontend')=='clang','clang_proof':fixture['request'].get('frontend')=='clang_proof',
            **{k:report[k] for k in ['failed_obligation','counterexample','evaluation','reason','analysis_limit','c_overflow_verified'] if k in report},
            'proved_obligations':len(report.get('certificate',{}).get('obligations',report.get('proved_obligations',[]))),
            'synthesized_candidates':len(report.get('summary_synthesis',[]))})
        print(fixture['name']+': '+('PASS' if matched else 'FAIL'),flush=True)
    native=[c for suite in evidence['suites'] if suite['name']!='pytest' for c in suite['checks']]
    pytest_counts=re.findall(r'(\d+) passed',evidence['suites'][0]['stdout'])
    summary={'unit_tests_passed':int(pytest_counts[-1]) if pytest_counts else None,'suites_passed':sum(suite['passed'] for suite in evidence['suites']),
             'suites_total':len(evidence['suites']),
             'native_passed':sum(c['passed'] for c in native),'native_total':sum(c['total'] for c in native),
             'guarded_expectations_matched':sum(case['matched'] for case in evidence['guarded_cases']),
             'guarded_cases_total':len(fixtures),'clang_frontend_cases':sum(case['frontend_only'] for case in evidence['guarded_cases']),'clang_frontend_ready':sum(case['actual_status']=='CLANG_FRONTEND_READY' for case in evidence['guarded_cases']),'clang_proof_cases':sum(case['clang_proof'] for case in evidence['guarded_cases']),'clang_proof_certified':sum(case['actual_status'].startswith('PROVED_DEFINED_CLANG_') for case in evidence['guarded_cases']),'owned_list_certified':sum(case['actual_status']=='PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY' for case in evidence['guarded_cases'])}
    evidence['summary']=summary
    evidence['passed']=all(suite['passed'] for suite in evidence['suites']) and all(case['matched'] for case in evidence['guarded_cases'])
    (args.output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    rows=['| Suite | Result | Native comparisons |','| --- | --- | --- |']
    for suite in evidence['suites']:
        comparisons=', '.join(f"{c['passed']}/{c['total']}" for c in suite['checks']) or '—'
        rows.append(f"| {suite['name']} | {'PASS' if suite['passed'] else 'FAIL'} | {comparisons} |")
    project_version=re.search(r'version = "([^"]+)"',(ROOT/'pyproject.toml').read_text()).group(1)
    lines=['# v'+project_version+' reproducible experiment results','',
           'Generated: '+evidence['generated_at'],'',
           'Base commit: `'+evidence['source_base_commit']+'`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.',
           '',f"Unit regressions: {summary['unit_tests_passed']} passed.",'',*rows,'',f"Native comparisons: {summary['native_passed']}/{summary['native_total']}.",
           f"Analysis/frontend/control expectations: {summary['guarded_expectations_matched']}/{summary['guarded_cases_total']}.",'',
           '| Case | Expected | Actual |','| --- | --- | --- |']
    for case in evidence['guarded_cases']:
        lines.append(f"| {case['name']} | {case['expected_status']} | {case['actual_status']} |")
    lines += ['', '## Interpretation','',
              'Unit tests run in fresh forked processes and each API fixture runs in a fresh interpreter/SMT context. Assertions and per-query solver budgets are unchanged; the aggregate pytest budget is 1200 seconds for the larger isolated suite. A timeout is UNKNOWN and never a proof. This protocol does not claim sequence-independent solver performance in a long-lived service.',
              'CLANG_FRONTEND_READY is compiler AST/layout/LLVM ingestion, never a safety/termination certificate. Clang acceptance cases are counted separately in results.json; compiling deliberate UB does not prove it safe. The scalar Clang AST proof bridge uses explicit trusted normalization and existing typed proof kernels; general LLVM instruction semantics and KLEE execution remain unsupported.',
              'Native checks are finite differential tests; the memory-rejection sanitizer suite counts expected fault correspondences separately in its log, not certified safe executions. Mathematical recurrence and typed scalar-loop claims come from checked induction obligations within their reported domains, not from the sample count.',
              'Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain, typed intermediate/return overflow, overwritten division by zero, index wrap, and unsupported expressions. UNKNOWN controls are never counted as supported functionality.',
              'These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.',
              'Compiler-typed finite memory and bounded direct/recursive calls now normalize into existing checked kernels. A separate exact owned-list constructor/consumer recognizer proves escaping lists without heap-instance unfolding, including every partial allocation-failure prefix. Its shape rules and standard allocator axioms are trusted; typed counter and reverse payload-fold proofs are retained. It does not prove arbitrary heap shapes or physical capacity.',
              'Automatic branch discovery handles admitted Boolean counter intervals/residues and finite control-state lassos with polynomial accumulators. Candidate exploration is never proof: original typed base, ranges, executed intermediates, coverage and every successor must pass. Finite-control successors may split into at most eight exhaustive integer residues, each with a 5000 ms SMT budget.',
              'The new original/normalized/model native checks use ASan/UBSan, forced allocation-failure budgets and explicit live-object counts. LeakSanitizer is disabled because this environment cannot perform its /proc task scan. Intentional sanitizer faults are separate rejection correspondences, not safe executions.',
              'General shared/cyclic escaping heap summaries, external pointers, realloc, indirect/lazy/multiple calls, arbitrary CFG termination, and arbitrary coupled/branching closed-form discovery remain incomplete. No KLEE integration or execution is included.','',
              f'Reproduce: `python scripts/run_symbolic_experiments.py --fixtures {args.fixtures} --output {args.output}` after `python -m pip install -e ".[test,smt]"`.']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary),flush=True)
    return 0 if evidence['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
