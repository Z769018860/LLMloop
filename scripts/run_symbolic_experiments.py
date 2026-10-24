"""Reproduce unit regressions, all native oracles, and guarded proof controls.

Writes honest structured evidence; never treats UNKNOWN as certification.
"""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import platform
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
    parser.add_argument('--output',type=Path,default=ROOT/'experiments/v014')
    args=parser.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=True)
    version=command(['git','rev-parse','HEAD'])
    manifest={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
              for pattern in ['llmloop/*.py','tests/*.py','scripts/*.py','pyproject.toml','examples/guarded*']
              for path in sorted(ROOT.glob(pattern)) if path.is_file()}
    evidence={'schema_version':1,'generated_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'source_base_commit':version['stdout'].strip(),'source_sha256':manifest,
              'environment':{'python':platform.python_version(),'platform':platform.platform(),
                             'sympy':sympy.__version__,'z3':z3.get_version_string(),
                             'compiler':command(['cc','--version'])['stdout'].splitlines()[0]},
              'protocol':{'proof_domain':'all nonnegative counts in each declared mathematical integer domain',
                          'native_samples':'fixed boundary grids and million-iteration cases; not a proof of arbitrary C',
                          'scope':'restricted research prototype; no claim that UNKNOWN cases are supported',
                          'performance_claims':False},'suites':[],'guarded_cases':[]}
    suite_commands=[('pytest',[sys.executable,'-m','pytest','-q'])]
    suite_commands += [(path.stem,[sys.executable,str(path.relative_to(ROOT))])
                       for path in sorted((ROOT/'scripts').glob('check_*native.py'))]
    for name,argv in suite_commands:
        print('Running '+name,flush=True)
        result=command(argv)
        checks=[{'passed':int(a),'total':int(b)} for a,b in re.findall(r'(\d+)/(\d+)',result['stdout'])]
        passed=result['exit_code']==0 and all(c['passed']==c['total'] for c in checks)
        if name!='pytest' and not checks:passed=False
        evidence['suites'].append({'name':name,**result,'passed':passed,'checks':checks})
        print(name+': '+('PASS' if passed else 'FAIL'),flush=True)
        # Preserve a checkpoint even if a subsequent suite is interrupted.
        (args.output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    fixtures=json.loads((ROOT/'experiments/v014/cases.json').read_text())
    for fixture in fixtures:
        report=analyze_request(fixture['request'])
        matched=report['status']==fixture['expected_status']
        evidence['guarded_cases'].append({'name':fixture['name'],'expected_status':fixture['expected_status'],
            'actual_status':report['status'],'matched':matched,
            **{k:report[k] for k in ['failed_obligation','counterexample','evaluation','reason'] if k in report},
            'proved_obligations':len(report.get('certificate',{}).get('obligations',report.get('proved_obligations',[])))})
        print(fixture['name']+': '+('PASS' if matched else 'FAIL'),flush=True)
    native=[c for suite in evidence['suites'] if suite['name']!='pytest' for c in suite['checks']]
    summary={'suites_passed':sum(suite['passed'] for suite in evidence['suites']),
             'suites_total':len(evidence['suites']),
             'native_passed':sum(c['passed'] for c in native),'native_total':sum(c['total'] for c in native),
             'guarded_expectations_matched':sum(case['matched'] for case in evidence['guarded_cases']),
             'guarded_cases_total':len(fixtures)}
    evidence['summary']=summary
    evidence['passed']=all(suite['passed'] for suite in evidence['suites']) and all(case['matched'] for case in evidence['guarded_cases'])
    (args.output/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    rows=['| Suite | Result | Native comparisons |','| --- | --- | --- |']
    for suite in evidence['suites']:
        comparisons=', '.join(f"{c['passed']}/{c['total']}" for c in suite['checks']) or '—'
        rows.append(f"| {suite['name']} | {'PASS' if suite['passed'] else 'FAIL'} | {comparisons} |")
    lines=['# v0.14 reproducible experiment results','',
           'Generated: '+evidence['generated_at'],'',
           'Base commit: `'+evidence['source_base_commit']+'`. Exact source SHA-256 manifest, commands, versions, logs and counterexamples are in `results.json`.',
           '',*rows,'',f"Native comparisons: {summary['native_passed']}/{summary['native_total']}.",
           f"Guarded proof/control expectations: {summary['guarded_expectations_matched']}/{summary['guarded_cases_total']}.",'',
           '| Case | Expected | Actual |','| --- | --- | --- |']
    for case in evidence['guarded_cases']:
        lines.append(f"| {case['name']} | {case['expected_status']} | {case['actual_status']} |")
    lines += ['', '## Interpretation','',
              'Native checks are finite differential tests. Universal mathematical recurrence claims come from checked induction obligations, not from the sample count.',
              'Negative controls include incorrect base/successor formulas, a failure near iteration one million, ambiguous/missing branches, an empty domain and unsupported expressions. UNKNOWN controls are never counted as supported functionality.',
              'These are controlled examples, not a representative real-world library benchmark. No performance advantage or universal C coverage is claimed.',
              'General escaping heaps, unbounded heterogeneous C integer/memory verification, and automatic discovery of arbitrary closed forms remain incomplete.','',
              'Reproduce: `python scripts/run_symbolic_experiments.py --output experiments/v014` after `python -m pip install -e ".[test,smt]"`.']
    (args.output/'report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(summary),flush=True)
    return 0 if evidence['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
