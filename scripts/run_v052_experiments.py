"""Local experiment-only continuation of v0.51; no proof-engine changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import time

import pycparser
import pytest
import sympy
import z3

from llmloop.clang_adapter import compiler_path


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('experiments/v052'))
    args = parser.parse_args()
    os.chdir(ROOT)
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    if any(p.name != 'attempts' for p in out.iterdir()):
        raise RuntimeError('Use an empty output directory; preserve earlier attempts')
    def git(*args):
        return subprocess.check_output(['git', *args], text=True).strip()
    paths = git('ls-files').splitlines()
    if git('diff', 'HEAD', '--', *[p for p in paths if not p.startswith('experiments/')]):
        raise RuntimeError('Commit experiment tooling before validation')
    source = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths if not p.startswith('experiments/')}
    prior = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths if p.startswith('experiments/')}
    manifest = {'tested_commit': git('rev-parse', 'HEAD'), 'tested_tree': git('rev-parse', 'HEAD^{tree}'),
                'source_sha256': source, 'historical_evidence_sha256': prior}
    (out/'source_manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    commands = {}
    def run(name, argv, timeout):
        start = time.perf_counter()
        with (out/(name+'.txt')).open('w') as log:
            try:
                code = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=timeout).returncode
            except subprocess.TimeoutExpired:
                code = 124
        commands[name] = {'argv': argv, 'exit_code': code, 'elapsed_seconds': time.perf_counter()-start, 'log': name+'.txt'}
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        print(name, json.dumps(commands[name]), flush=True)
        return (out/(name+'.txt')).read_text()
    # Timing comparison precedes pytest and other native runs: no parallel
    # experiment load, no retries, unchanged per-query proof budgets.
    for name, script, flags, timeout in [
        ('heap_scaling', 'check_heap_backend_scaling.py', [], 900),
        ('static_grid', 'check_static_contract_grid.py', [], 600),
        ('static_native', 'check_clang_static_arrays_native.py', [], 360),
        ('popcount', 'check_popcount_functional.py', [], 180),
        ('division', 'check_division_bv.py', ['--strategy', 'induction', '--compare-baseline', '--controls'], 360),
    ]:
        run(name, [sys.executable, 'scripts/'+script, *flags, '--output', str(out/(name+'.json'))], timeout)
    test_text = run('pytest', [sys.executable, '-m', 'pytest', '-q', '--forked'], 1800)
    def data(name):
        path = out/(name+'.json')
        return json.loads(path.read_text()) if path.exists() else {}
    heap, grid, static, popcount, division = (data(k) for k in ('heap_scaling', 'static_grid', 'static_native', 'popcount', 'division'))
    passed = re.findall(r'(\d+) passed', test_text)
    skipped = sum(int(v) for v in re.findall(r'(\d+) skipped', test_text))
    full = {'passed': int(passed[-1]) if passed else 0, 'skipped': skipped, 'expected': 2436}
    checks = {name: record['exit_code'] == 0 for name, record in commands.items()}
    checks.update({'full_pytest_count': full == {'passed': 2436, 'skipped': 0, 'expected': 2436},
        'heap_scaling_result': heap.get('passed') is True and heap.get('fresh_process_runs') == 108,
        'static_grid_result': grid.get('passed') is True and grid.get('case_count') == 384
            and grid.get('classifications') == {'proved': 144, 'insufficient_extent': 112, 'unsupported_interior': 128},
        'static_native_result': static.get('passed') is True and static.get('native_output_matches') == 1848,
        'source_unchanged': all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in source.items()),
        'historical_evidence_unchanged': all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in prior.items())})
    result = {'passed': all(checks.values()), 'checks': checks, 'full_pytest': full,
        'tested_commit': manifest['tested_commit'], 'tested_tree': manifest['tested_tree'],
        'commands': commands, 'source_paths': len(source), 'historical_evidence_paths': len(prior),
        'environment': {'python': platform.python_version(), 'platform': platform.platform(), 'z3': z3.get_version_string(),
            'pytest': pytest.__version__, 'sympy': sympy.__version__, 'pycparser': pycparser.__version__,
            'clang': subprocess.check_output([compiler_path(), '--version'], text=True).splitlines()[0],
            'gcc': subprocess.check_output(['gcc', '--version'], text=True).splitlines()[0]},
        'github_actions_used': False, 'ci_runs_used': 0, 'klee_used': False,
        'proof_engine_changed': False, 'query_budgets_increased': False, 'complete_c_support': False,
        'scope': 'Experiment-only continuation: exhaustive finite-capacity checks, constructed same-source heap backend '
                 'comparison, refreshed static native controls and two pinned upstream functional experiments. '
                 'This is not a full upstream matrix refresh or a LoopSCC on/off ablation.'}
    lines = ['# v0.52 experimental continuation (v0.51 proof engine)', '',
        f"Frozen source: `{manifest['tested_commit']}`; tree `{manifest['tested_tree']}`.", '',
        f"Full regression: **{full['passed']} passed, {skipped} skipped**. All experiment commands run locally, sequentially, with no retries or larger proof-query budgets. No Actions or KLEE.", '',
        '## Static entry-contract grid', '',
        f"The 384 constructed cases exhaust minima 1..8 × actual capacities 1..8 × `a`, `a+0`, `a+1` × inline/header-linked snapshot routes. Results: `{json.dumps(grid.get('classifications', {}), sort_keys=True)}`. Independent SMT replays: `{json.dumps(grid.get('query_replays', {}), sort_keys=True)}`.", '',
        'The body intentionally ignores its pointer, so entry definedness cannot rely on body reads. Interior slices remain UNKNOWN even when the remaining extent is sufficient. Their SAT base guards identify an unsupported analysis fragment, not source UB. Invalid static calls are never executed as positive native evidence.', '',
        f"The retained dual-compiler O0/O2 static matrix has {static.get('native_output_matches')} output matches, {static.get('model_matches')} model checks, {static.get('expected_body_arithmetic_traps')} arithmetic traps, and {static.get('expected_body_memory_failures')} memory failures. Sanitizer-silent invalid calls stay excluded from positive correspondence.", '',
        '## Finite heap versus owned-list induction', '',
        'Two unchanged, constructed existing list examples (sum and ordered stateful prefix fold) are analyzed from the same C source under `calls` and `list_calls`. Allocation failure remains enabled. This compares different backend contracts; it is **not** a LoopSCC on/off ablation.', '',
        'Each point has three fresh-process repetitions in one predetermined shuffled order. Default proof limits are unchanged; 60 seconds is the external process ceiling. Times include Clang ingestion/normalization. These descriptive measurements are not CPU-pinned, cross-machine results or a universal speedup claim.', '',
        '| Case | n | Finite heap | Median seconds | List induction | Median seconds |',
        '| --- | ---: | --- | ---: | --- | ---: |']
    for case in ('sum', 'stateful'):
        for n in heap.get('grid', []):
            a = [row for row in heap.get('aggregates', []) if row['case'] == case and row['n'] == n]
            if len(a) == 2:
                b, s = a
                label = lambda v: 'proved' if v['status'].startswith('PROVED_') else v['status']
                lines.append(f"| {case} | {n} | {label(b)} | {b['median_seconds']:.3f} | {label(s)} | {s['median_seconds']:.3f} |")
    lines += ['', f"Fresh process outcomes: `{json.dumps(heap.get('status_counts', {}), sort_keys=True)}`. Both summary proofs additionally cover the full declared interval n=0..1,000,000, with every allocation-failure prefix, and {heap.get('arithmetic_audits_replayed')} exact arithmetic audits replay independently.", '',
        f"GCC/Clang, O0/O2, original/normalized/composed programs match {heap.get('native_output_matches')} independent outputs and {heap.get('independent_model_matches')} model evaluations. Native instrumentation checks every payload and free identity, allocation attempts, successful allocation count and zero remaining live nodes. The Python formula is cross-checked by an independent short-list walk. Million-node cases include empty, early-failure, half-built and complete chains. An incorrect supplied fold is rejected, and an overflowing int fold is rejected with four required native UBSan failures.", '',
        '## Retained upstream functions and limits', '',
        'The pinned original compiler-rt popcount and unsigned-division scripts are rerun, retaining independent functional, source-safety and negative-control outcomes in `popcount.json` and `division.json`. Their direct timeouts remain separate from successful compositional/inductive strategies. This refresh does not rerun or claim completion of the whole upstream matrix.', '',
        'No proof-engine support is added. General VLA and interior slices, arbitrary ownership/heap shapes, wider C/LLVM semantics and arbitrary branch closed-form synthesis remain open. These constructed fixtures do not close representative-library evaluation. Clang and normalization remain trusted; native samples are supplementary evidence.', '',
        f"Source hashes: {len(source)} paths. Historical evidence hashes: {len(prior)} paths. Checks: `{json.dumps(checks, sort_keys=True)}`. Passed: **{result['passed']}**."]
    (out/'report.md').write_text('\n'.join(lines)+'\n')
    result['evidence_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file() and p.name != 'results.json'}
    (out/'results.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('commands', 'environment', 'evidence_sha256')}), flush=True)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
