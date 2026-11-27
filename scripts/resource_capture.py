"""Capture a command's process-group resources and own its lifetime."""
import json, os, signal, subprocess, time
from pathlib import Path
import psutil

def capture(argv, directory, *, cwd=None, env=None, wall_seconds=600, memory_bytes=2*1024**3):
    d=Path(directory);d.mkdir(parents=True,exist_ok=True);start=time.monotonic();reason=None;peak=0;samples=0;errors=[]
    with (d/'stdout.txt').open('w')as stdout,(d/'stderr.txt').open('w')as stderr,(d/'resources.jsonl').open('w')as resources:
        p=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stdout,stderr=stderr,start_new_session=True)
        while True:
            pid,status,usage=os.wait4(p.pid,os.WNOHANG)
            if pid:break
            elapsed=time.monotonic()-start
            try:
                parent=psutil.Process(p.pid);group=[parent]+parent.children(recursive=True);rss=0;cpu=0
                for child in group:
                    try:rss+=child.memory_info().rss;ct=child.cpu_times();cpu+=ct.user+ct.system
                    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
                peak=max(peak,rss);samples+=1;resources.write(json.dumps({'wall_seconds':elapsed,'group_rss_bytes':rss,'live_group_cpu_seconds':cpu,'processes':len(group)})+'\n')
                if rss>memory_bytes and reason is None:reason='MEMORY_LIMIT'
            except (psutil.NoSuchProcess,psutil.AccessDenied)as e:errors.append(type(e).__name__)
            if elapsed>=wall_seconds and reason is None:reason='HOST_TIMEOUT'
            if reason:
                try:os.killpg(p.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            time.sleep(.1)
        p.returncode=os.waitstatus_to_exitcode(status)
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    result={'argv':argv,'cwd':str(cwd)if cwd else None,'exit_code':p.returncode,'stop_reason':reason,'wall_seconds':time.monotonic()-start,'cpu_user_seconds':usage.ru_utime,'cpu_system_seconds':usage.ru_stime,'wait4_maxrss_kib':usage.ru_maxrss,'sampled_peak_group_rss_bytes':peak,'wall_limit_seconds':wall_seconds,'memory_limit_bytes':memory_bytes,'sampling_interval_seconds':.1,'resource_samples':samples,'monitor_errors':dict(__import__('collections').Counter(errors))}
    (d/'command.json').write_text(json.dumps(result,indent=2)+'\n');return result
