"""Package raw outcomes deterministically; no third-party binaries or sources."""
import gzip, hashlib, io, json, tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'experiments/v102'
DIRECTORIES=['study/raw','study/native','cbmc/raw','attempt_wrong_property','late_attempt_outputs','initial_parser_attempt','regression_older_parser_attempt','regression_modern','legacy_witness']

def main():
    files=sorted({p for name in DIRECTORIES for p in (D/name).rglob('*') if p.is_file()})
    allowed={'.json','.jsonl','.txt','.c','.s'}
    assert all(p.suffix in allowed for p in files), 'unexpected/binary raw member'
    members=[];out=D/'raw_evidence.tar.gz'
    with out.open('wb')as raw,gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0)as gz,tarfile.open(fileobj=gz,mode='w|')as tar:
        for p in files:
            data=p.read_bytes();name=str(p.relative_to(D));info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.mtime=0
            tar.addfile(info,io.BytesIO(data));members.append({'path':name,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    manifest={'archive':'raw_evidence.tar.gz','archive_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'members':members,'count':len(members)}
    (D/'raw_manifest.json').write_text(json.dumps(manifest,indent=1)+'\n');print({'members':len(files),'compressed_bytes':out.stat().st_size})
if __name__=='__main__':main()
