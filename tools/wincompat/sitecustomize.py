"""POSIX process primitives for the frozen harness, on Windows.

`scripts/resource_capture.py` is inside every arm's `frozen_source_sha256`, and the paper's central
claim is that the verifier was not edited between arms. It is also the only file that reaches for
`os.wait4`, `os.killpg` and `signal.SIGKILL` -- none of which exist on Windows. Editing it would
move a hash and make "unmodified" false, so the three names are supplied from outside instead: this
module is imported by the interpreter before the runner starts (`PYTHONPATH=tools/wincompat`), and
the frozen file keeps its bytes.

What this changes, and what it cannot. The shim reimplements the *interface*: wait4 polls the
Popen that created the pid, killpg walks the process tree through psutil, SIGKILL becomes SIGTERM.
Three consequences are real and are not hidden:

  * `wait4` reports `(0, 0)` until the child has exited, then the pid once, then `(0, 0)` again --
    POSIX would reap, so a caller that waits twice on the same pid sees a difference. `capture`
    waits in a loop until the pid comes back, which is the case this is built for.
  * `ru_utime`/`ru_stime` are read from psutil while the exited process' handle is still open. When
    Windows has already torn the process down they come back 0.0, and `command.json` then says
    `cpu_user_seconds: 0.0` for a run that did use CPU. `wall_seconds`, `sampled_peak_group_rss_bytes`
    and `resource_samples` come from the sampler and are unaffected.
  * the exit status is re-encoded as `(code & 0xFF) << 8` so that `os.waitstatus_to_exitcode`
    decodes it back to the same integer a POSIX wait would have produced.

None of this touches a proof: `capture` brackets a subprocess and records what it cost. The
verdicts come from `llmloop`, which is untouched.
"""
import os
import signal
import subprocess
import sys

if sys.platform == 'win32' and not hasattr(os, 'wait4'):
    import psutil

    _live = {}
    _init = subprocess.Popen.__init__

    def _tracked_init(self, *args, **kwargs):
        _init(self, *args, **kwargs)
        try:
            _live[self.pid] = self
        except Exception:                                   # pragma: no cover - defensive
            pass

    subprocess.Popen.__init__ = _tracked_init

    class _Usage:
        __slots__ = ('ru_utime', 'ru_stime', 'ru_maxrss')

        def __init__(self, u=0.0, s=0.0, r=0):
            self.ru_utime, self.ru_stime, self.ru_maxrss = u, s, r

    def wait4(pid, options=0):
        p = _live.get(pid)
        if p is None:                                       # not ours: report "not exited"
            return (0, 0, _Usage())
        rc = p.poll()
        if rc is None:
            return (0, 0, _Usage())
        user = system = 0.0
        rss_kib = 0
        try:
            proc = psutil.Process(pid)
            times = proc.cpu_times()
            user, system = times.user, times.system
            rss_kib = proc.memory_info().rss // 1024
        except Exception:
            pass
        _live.pop(pid, None)
        status = ((rc & 0xFF) << 8) if rc >= 0 else 1
        return (pid, status, _Usage(user, system, rss_kib))

    def killpg(pgid, sig):
        procs = []
        try:
            procs = psutil.Process(pgid).children(recursive=True)
        except Exception:
            pass
        for q in procs:
            try:
                q.kill()
            except Exception:
                pass
        try:
            psutil.Process(pgid).kill()
        except Exception:
            raise ProcessLookupError(pgid)

    os.wait4 = wait4
    os.killpg = killpg
    os.WNOHANG = 1                       # only ever passed through; the shim never blocks
    if not hasattr(signal, 'SIGKILL'):
        signal.SIGKILL = signal.SIGTERM
