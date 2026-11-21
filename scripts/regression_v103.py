"""Run the repository's full regression suite and record an auditable summary.

pytest's own exit code and the literal FAILED/ERROR lines are preserved; the job is
allowed to finish so the failure list itself becomes evidence.
"""
import json, os, re, subprocess, sys
from pathlib import Path

OUT = Path('experiments/v103/regression')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    log = OUT / 'pytest.log'
    with log.open('w') as f:
        p = subprocess.run([sys.executable, '-m', 'pytest', '-q', '--forked', '-p', 'no:cacheprovider'],
                           stdout=f, stderr=subprocess.STDOUT)
    text = log.read_text(errors='replace')
    tail = [l for l in text.splitlines() if re.search(r'\d+ (passed|failed|error)', l)]
    failed = [l for l in text.splitlines() if l.startswith(('FAILED ', 'ERROR '))]
    skipped = [l for l in text.splitlines() if ' SKIPPED ' in l]
    summary = {'returncode': p.returncode, 'summary_line': tail[-1] if tail else None,
               'failed_or_error_lines': failed, 'skipped_lines': skipped,
               'python': sys.version, 'cwd': os.getcwd(),
               'command': 'pytest -q --forked -p no:cacheprovider'}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    print(json.dumps({k: summary[k] for k in ('returncode', 'summary_line')}, indent=1))
    print('\n'.join(failed[:40]))


if __name__ == '__main__':
    main()
