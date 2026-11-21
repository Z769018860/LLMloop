"""Resource accounting and owned child process-group shutdown."""
import json,sys
from pathlib import Path
from scripts.resource_capture import capture


def test_success_retains_output_and_wait4_cpu(tmp_path):
    r=capture([sys.executable,'-c','print("captured")'],tmp_path,wall_seconds=2)
    assert r['exit_code']==0 and r['stop_reason']is None
    assert (tmp_path/'stdout.txt').read_text().strip()=='captured'
    assert r['cpu_user_seconds']>=0 and r['wall_seconds']>0
    assert json.loads((tmp_path/'command.json').read_text())['argv']==r['argv']


def test_deadline_kills_owned_group_and_retains_partial_output(tmp_path):
    r=capture([sys.executable,'-u','-c','import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]); print(p.pid,flush=True); time.sleep(30)'],tmp_path,wall_seconds=.4)
    assert r['stop_reason']=='HOST_TIMEOUT' and r['exit_code']<0
    assert (tmp_path/'stdout.txt').read_text().strip().isdigit()
    assert r['wall_seconds']<3


def test_memory_budget_is_distinct_from_solver_failure(tmp_path):
    r=capture([sys.executable,'-c','import time;x=bytearray(50_000_000);time.sleep(10)'],tmp_path,wall_seconds=2,memory_bytes=1_000_000)
    assert r['stop_reason']=='MEMORY_LIMIT' and r['exit_code']<0
    assert r['sampled_peak_group_rss_bytes']>r['memory_limit_bytes']
