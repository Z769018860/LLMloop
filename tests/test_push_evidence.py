"""The one property a "record the evidence" step must have: it fails when the evidence did not arrive.

v1.05's first attempt at recording the post-cutoff results went green 21/21 and pushed nothing:
`git push` was rejected three times (GH001, a 361 MB log) and the step's status was the status of
the retry loop, which is 0. The failure was invisible in the run list and invisible in the working
tree; it was found by noticing that a `git pull` after the run changed nothing.

These tests drive the replacement against real repositories, including one whose receive hook
rejects every push, which is what GH001 looks like from the client.
"""
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/push_evidence.sh'


def git(cwd, *args, check=True):
    return subprocess.run(['git', *args], cwd=cwd, capture_output=True, text=True, check=check)


def repo_pair(tmp_path):
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', '-b', 'main', str(remote)], check=True,
                   capture_output=True)
    work = tmp_path / 'work'
    work.mkdir()
    git(work, 'init', '-b', 'main')
    git(work, 'config', 'user.email', 'test@example.com')
    git(work, 'config', 'user.name', 'test')
    git(work, 'remote', 'add', 'origin', str(remote))
    (work / 'evidence.txt').write_text('one\n')
    git(work, 'add', 'evidence.txt')
    git(work, 'commit', '-q', '-m', 'first')
    return remote, work


def run(work, branch='main'):
    return subprocess.run(['bash', str(SCRIPT), branch, 'evidence.txt', 'record evidence [skip ci]'],
                          cwd=work, capture_output=True, text=True)


def test_the_evidence_really_reaches_the_remote(tmp_path):
    remote, work = repo_pair(tmp_path)
    (work / 'evidence.txt').write_text('two\n')
    r = run(work)
    assert r.returncode == 0, r.stderr
    log = git(remote, 'log', '--oneline', 'main').stdout
    assert 'record evidence' in log
    assert git(work, 'status', '--short').stdout.strip() == ''


def test_a_rejected_push_exits_non_zero_and_says_why(tmp_path):
    remote, work = repo_pair(tmp_path)
    hook = remote / 'hooks' / 'pre-receive'
    hook.write_text('#!/bin/sh\necho "GH001: Large files detected" >&2\nexit 1\n')
    hook.chmod(0o755)
    (work / 'evidence.txt').write_text('two\n')
    r = run(work)
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert 'nothing was recorded' in r.stderr
    assert 'trim_logs' in r.stderr


def test_nothing_to_commit_is_a_success_and_a_no_op(tmp_path):
    remote, work = repo_pair(tmp_path)
    r = run(work)
    assert r.returncode == 0, r.stderr
    assert 'nothing to commit' in r.stdout


def test_a_new_branch_on_an_empty_remote_is_not_a_failure(tmp_path):
    """The first push of a study creates the branch; pulling before pushing cannot work there."""
    remote, work = repo_pair(tmp_path)
    (work / 'evidence.txt').write_text('two\n')
    r = run(work, branch='research/v105')
    assert r.returncode == 0, r.stderr
    assert 'research/v105' in git(remote, 'branch', '-a').stdout
