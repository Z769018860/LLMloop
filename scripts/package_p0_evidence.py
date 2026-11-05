"""Verify and compact completed v061 observations without discarding raw evidence."""
import argparse, gzip, hashlib, io, json, shutil, subprocess, tarfile
from pathlib import Path

def read(p):return json.loads(p.read_text())
def save(p,j):p.write_text(json.dumps(j,indent=2,ensure_ascii=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--backup',type=Path,required=True);a=p.parse_args();out=a.directory
    root=Path(__file__).resolve().parents[1]
    assert not (out/'raw_evidence.tar.gz').exists() and not a.backup.exists()
    main=read(out/'results.json');native=read(out/'native_loopscc/results.json');lift=read(out/'lift/results.json');projection=read(out/'projection/results.json')
    assert main['passed'] and main['recorded_runs']==192 and main['control_mismatches']==0 and main['tracked_unchanged']
    assert native['passed_capture'] and len(native['rows'])==36
    assert lift['captured']==3 and lift['verified']==3 and projection['passed']
    assert projection['native_observations']==projection['native_matches']==1156
    test_log=(out/'attempts/v061-tests.txt').read_text();assert '9 passed' in test_log and 'failed' not in test_log
    previous=subprocess.check_output(['git','rev-parse','30eada4b252377907baa0000e292b57c1e035ec9:llmloop'],cwd=root,text=True).strip()
    current=subprocess.check_output(['git','rev-parse','HEAD:llmloop'],cwd=root,text=True).strip();assert previous==current
    save(out/'acceptance.json',{'passed_capture_and_controls':True,'all_p0_complete':False,'main_runs':192,'control_trials':120,'external_initial_trials':72,
         'unaltered_loopscc_supplement_trials':36,'lift_known_bound_trials':3,'native_output_observations':1156,
         'new_integrity_tests_passed':9,'new_full_suite_claimed':False,'remote_model_calls':0,'unchanged_analyzer_tree':current,
         'external_success_not_assumed':True,'raw_adapter_disagreements_preserved':True})
    shutil.copytree(out,a.backup)
    excluded={'README.md','report.md','p0_ledger.json','novelty_audit.md'}
    members=[p for p in sorted(out.rglob('*')) if p.is_file() and p.name not in excluded and 'work' not in p.relative_to(out).parts]
    assert all(p.suffix in {'.json','.jsonl','.txt','.c','.sh'} for p in members)
    manifest=[{'path':str(p.relative_to(out)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in members]
    archive=out/'raw_evidence.tar.gz'
    with archive.open('wb') as f:
        with gzip.GzipFile(filename='',mode='wb',fileobj=f,mtime=0) as gz:
            with tarfile.open(fileobj=gz,mode='w') as tar:
                for p in members:
                    data=p.read_bytes();info=tarfile.TarInfo(str(p.relative_to(out)));info.size=len(data);info.mtime=0;info.mode=0o644
                    tar.addfile(info,io.BytesIO(data))
    with tarfile.open(archive,'r:gz') as tar:
        assert len(tar.getmembers())==len(manifest)
        for item in manifest:
            assert hashlib.sha256(tar.extractfile(item['path']).read()).hexdigest()==item['sha256']
    save(out/'raw_manifest.json',{'archive':archive.name,'archive_sha256':sha(archive),'members':manifest,'third_party_sources_and_binaries_redistributed':False})
    for directory in ['raw','attempts']:shutil.rmtree(out/directory)
    keep={'projection':{'results.json','oracle_boundary_audit.json','protocol.json','source.json'},
          'lift':{'results.json','source.json'},'native_loopscc':{'results.json','protocol.json','schedule.json'}}
    for directory,names in keep.items():
        for p in (out/directory).iterdir():
            if p.name not in names:
                if p.is_dir():shutil.rmtree(p)
                else:p.unlink()
    print(json.dumps({'verified_archive_members':len(members),'archive_bytes':archive.stat().st_size,'archive_sha256':sha(archive),'all_p0_complete':False}))

if __name__=='__main__':main()
