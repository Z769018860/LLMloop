#!/usr/bin/env bash
# Commit the evidence, then prove it arrived.
#
# The v1.05 run that produced the post-cutoff numbers ended 21/21 green and recorded nothing:
# `git push` was rejected three times (GH001: Large files detected, a single CBMC log of 361 MB) and
# the step's exit status was the exit status of the retry loop, which is 0. "The step went green" and
# "the bytes are on the remote" are two different facts and only one of them was being checked.
#
# So: retries stay, but the last thing this script does is look at the remote. `git push` returns
# non-zero when it fails, `pushed` records that it did not, and the script exits 1. A caller cannot
# mistake a rejection for a success.
#
# usage: push_evidence.sh <branch> <path-to-commit> <commit message>
set -uo pipefail

branch="${1:?branch}"
path="${2:?path}"
message="${3:-evidence}"

git config user.name >/dev/null 2>&1 || git config user.name 'github-actions[bot]'
git config user.email >/dev/null 2>&1 || \
  git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

git add -A -- "$path"
if git diff --cached --quiet -- "$path"; then
  echo "nothing to commit under $path"
  exit 0
fi
git commit -q -m "$message"

pushed=0
for attempt in 1 2 3; do
  # Push first, pull only after a rejection. Pulling first fails on a branch the remote does not
  # have yet ("couldn't find remote ref"), which turned the very first push of a new study into a
  # guaranteed failure -- and a guaranteed failure that, in the old idiom, was still exit 0.
  if git push origin "HEAD:refs/heads/$branch"; then
    pushed=1
    break
  fi
  echo "push attempt $attempt rejected; rebasing and retrying" >&2
  git pull --rebase --quiet --autostash origin "$branch" || true
  sleep 5
done

if [ "$pushed" != 1 ]; then
  echo "push failed three times; nothing was recorded" >&2
  echo "the usual cause is a file GitHub will not accept (GH001: over 100 MB); run" >&2
  echo "  python -u scripts/trim_logs.py $path" >&2
  echo "and retry" >&2
  exit 1
fi
echo "pushed $(git rev-parse --short HEAD) to $branch"
