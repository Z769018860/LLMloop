"""Shrink rarely-read run artefacts before they are archived or committed.

stdout/stderr above the threshold are gzipped in place; Ultimate's per-run working
directory (witnesses, dumps) is tarred and removed. Nothing is deleted without a
compressed replacement next to it.
"""
import gzip, json, shutil, sys, tarfile
from pathlib import Path

THRESHOLD = 32 * 1024


def pack(raw: Path):
    stats = {'dirs': 0, 'gz': 0, 'tar': 0, 'bytes_before': 0, 'bytes_after': 0}
    for d in sorted(p for p in raw.iterdir() if p.is_dir()):
        stats['dirs'] += 1
        for name in ('stdout.txt', 'stderr.txt'):
            f = d / name
            if f.exists() and f.stat().st_size > THRESHOLD:
                before = f.stat().st_size
                with f.open('rb') as src, gzip.open(d / (name + '.gz'), 'wb', compresslevel=6) as dst:
                    shutil.copyfileobj(src, dst)
                f.unlink(); stats['gz'] += 1
                stats['bytes_before'] += before; stats['bytes_after'] += (d / (name + '.gz')).stat().st_size
        work = d / 'work'
        if work.is_dir():
            size = sum(f.stat().st_size for f in work.rglob('*') if f.is_file())
            with tarfile.open(d / 'work.tar.gz', 'w:gz') as tf:
                tf.add(work, arcname='work')
            shutil.rmtree(work); stats['tar'] += 1
            stats['bytes_before'] += size; stats['bytes_after'] += (d / 'work.tar.gz').stat().st_size
    return stats


if __name__ == '__main__':
    for arg in sys.argv[1:]:
        raw = Path(arg)
        if not raw.exists():
            print(json.dumps({'raw': str(raw), 'skipped': 'missing'}))
            continue
        s = pack(raw); s['raw'] = str(raw)
        print(json.dumps(s))
