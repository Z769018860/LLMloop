"""Overlay downloaded shard artefacts onto the study directories.

Layout expected under <incoming>:
  full165/raw, full165/shards            <- one directory per shard artifact download
  independent/raw, independent/shards
  tacle_reference256/...                 <- artifact root is the study directory itself
  regression/...                         <- pytest log and summary

Nothing that already exists is overwritten; the merge step re-reads the frozen
schedule, so a unit can only appear once.
"""
import json, shutil, sys
from pathlib import Path

STUDIES = ('full165', 'independent', 'tacle_reference256')


def copy_children(src: Path, dst: Path, counters, key):
    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted(src.iterdir()):
        if (dst / f.name).exists():
            continue
        if f.is_dir():
            shutil.copytree(f, dst / f.name, dirs_exist_ok=True)
        else:
            shutil.copy2(f, dst / f.name)
        n += 1
    counters[key] = counters.get(key, 0) + n
    return n


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'incoming')
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else 'experiments/v103')
    counters = {}
    for study in STUDIES:
        for sub in ('raw', 'shards'):
            p = src / study / sub
            if p.is_dir():
                copy_children(p, dst / study / sub, counters, f'{study}/{sub}')
        for extra in ('protocol.json', 'results.json', 'summary.json', 'summary.md'):
            f = src / study / extra
            if f.is_file() and not (dst / study / extra).exists():
                shutil.copy2(f, dst / study / extra)
                counters[f'{study}/{extra}'] = counters.get(f'{study}/{extra}', 0) + 1
    if (src / 'regression').is_dir():
        copy_children(src / 'regression', dst / 'regression', counters, 'regression')
    print(json.dumps(counters, indent=1))


if __name__ == '__main__':
    main()
