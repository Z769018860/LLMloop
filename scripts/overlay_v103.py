"""Overlay downloaded shard artefacts onto the study directories.

Artifacts keep their upload-relative paths (`raw/`, `shards/`); this copies every
per-unit directory and every shard result into experiments/v103/<study>/ without
overwriting anything already present.
"""
import json, shutil, sys
from pathlib import Path


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1 else 'incoming')
    dst = Path(sys.argv[2] if len(sys.argv) > 2 else 'experiments/v103')
    moved = {'units': 0, 'shards': 0, 'studies': {}}
    for part in sorted(p for p in src.rglob('*') if p.is_dir() and p.name in ('raw', 'shards')):
        study = part.parent.name
        target_dir = dst / study / part.name
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(part.iterdir()):
            if f.is_dir():
                if not (target_dir / f.name).exists():
                    shutil.copytree(f, target_dir / f.name, dirs_exist_ok=True)
                    moved['units'] += 1
                    moved['studies'][study] = moved['studies'].get(study, 0) + 1
            elif not (target_dir / f.name).exists():
                shutil.copy2(f, target_dir / f.name)
                moved['shards'] += 1
    print(json.dumps(moved, indent=1))


if __name__ == '__main__':
    main()
