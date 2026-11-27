"""Download the v1.03 run artifacts and lay them out for local overlay.

Usage: python fetch_v103_artifacts.py <run-id> <dest-dir>
Reads a GitHub token from H:/Temp/.gc.txt (git credential store) if present,
otherwise from GITHUB_TOKEN. Artifacts named <study>-shard-*/tacle-*/v103-regression
are extracted into <dest>/<study>/ preserving their uploaded relative paths.
"""
import io, json, os, subprocess, sys, tempfile, urllib.request, zipfile
from pathlib import Path

TOKEN = os.environ.get('GITHUB_TOKEN')
if not TOKEN:
    gc = Path('H:/Temp/.gc.txt')
    if gc.exists():
        for line in gc.read_text().splitlines():
            if line.startswith('password='):
                TOKEN = line.split('=', 1)[1].strip()
REPO = 'Z769018860/LLMloop'
STUDY = {'full165-shard': 'full165', 'independent-shard': 'independent',
         'tacle-reference256': 'tacle_reference256', 'v103-regression': 'regression'}


def api(url):
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {TOKEN}',
                                               'Accept': 'application/vnd.github+json'})
    return urllib.request.urlopen(req, timeout=120)


def main():
    run, dest = sys.argv[1], Path(sys.argv[2])
    arts = json.load(api(f'https://api.github.com/repos/{REPO}/actions/runs/{run}/artifacts?per_page=100'))['artifacts']
    kept = 0
    for a in arts:
        name = a['name']
        study = next((v for k, v in STUDY.items() if name.startswith(k)), None)
        if not study or study == 'regression' and 'v103-regression' not in name:
            continue
        if name == 'v103-merged':
            continue
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp:
            path = tmp.name
        subprocess.run(['curl', '-sL', '-H', f'Authorization: Bearer {TOKEN}', a['archive_download_url'], '-o', path], check=True)
        data = Path(path).read_bytes(); os.unlink(path)
        target = dest / study
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            z.extractall(target)
        kept += 1
        print(f'{name:32s} -> {study}  ({len(data)/1024:.0f} KiB)')
    print('artifacts laid out:', kept)


if __name__ == '__main__':
    main()
