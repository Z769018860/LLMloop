#!/usr/bin/env bash
# Prepare the pinned external inputs required by the v1.03 frozen protocols.
# Every artefact is checked against the hash recorded in the frozen protocol before any run starts.
# Usage: ci_setup_v103.sh <external-dir> [svbench|juliet|tacle|tools|all]
set -euo pipefail
EXT="${1:?usage: ci_setup_v103.sh <external-dir> [component]}"
WHAT="${2:-all}"
mkdir -p "$EXT/native" "$EXT/logs"
PIN_SVBENCH=2e1723fde6aa65a250dcb677efa45edaa4b6b631
PIN_JULIET=f88433e3443648a17671398797a04ea1f8e1a274
PIN_TACLE=c6a0d73e47bbd2bc86e34637156fb26dd4d5cf08
ULT_SHA=1787c24c6e57f1519e4a0b0c8b893042e082f3da08ed82c36a7f562b27869d40
CBMC_SHA=a62af25d27425610608221d79c202f993efe1d5a85cece186119bec196382995
SVBENCH_URL=https://github.com/sosy-lab/sv-benchmarks.git
JULIET_URL=https://github.com/arichardson/juliet-test-suite-c.git
TACLE_URL=https://github.com/tacle/tacle-bench.git
ULT_URL=https://github.com/ultimate-pa/ultimate/releases/download/v0.3.2/UltimateAutomizer-linux.zip
CBMC_URL=https://github.com/diffblue/cbmc/releases/download/cbmc-6.11.0/ubuntu-24.04-cbmc-6.11.0-Linux.deb

sparse_at_pin () { # url dir pin paths...
  local url="$1" dir="$2" pin="$3"; shift 3
  if [ -f "$dir/.git/HEAD" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null || true)" = "$pin" ]; then
    echo "[skip] $dir already at $pin"; return 0
  fi
  rm -rf "$dir"; mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote add origin "$url"
  git -C "$dir" config core.sparseCheckout true
  : > "$dir/.git/info/sparse-checkout"
  for pat in "$@"; do printf '%s\n' "$pat" >> "$dir/.git/info/sparse-checkout"; done
  git -C "$dir" fetch -q --depth 1 --filter=blob:none origin "$pin"
  git -C "$dir" checkout -q FETCH_HEAD
  local got; got="$(git -C "$dir" rev-parse HEAD)"
  [ "$got" = "$pin" ] || { echo "FATAL: $dir at $got, expected $pin" >&2; exit 1; }
  echo "[ok] $dir @ $pin"
}

if [ "$WHAT" = all ] || [ "$WHAT" = svbench ]; then
  sparse_at_pin "$SVBENCH_URL" "$EXT/svbench" "$PIN_SVBENCH" 'c/termination-15/*' 'c/termination-restricted-15/*'
fi

# Certificates of the older no-overflow studies are re-checked against the same pin but need
# the directories those studies drew from; a separate checkout keeps the frozen studies' input
# set byte-identical to what they ran with.
if [ "$WHAT" = all ] || [ "$WHAT" = certbench ]; then
  sparse_at_pin "$SVBENCH_URL" "$EXT/svbench-cert" "$PIN_SVBENCH" \
    'c/termination-crafted/*' 'c/termination-crafted-lit/*' 'c/termination-restricted-15/*' 'c/bitvector/*'
fi

# CBMC alone, for certificate re-checks that need no Ultimate.
if [ "$WHAT" = all ] || [ "$WHAT" = cbmc ]; then
  if [ ! -x "$EXT/native/usr/bin/cbmc" ]; then
    [ -f "$EXT/cbmc.deb" ] || curl -fsSL --retry 3 -o "$EXT/cbmc.deb" "$CBMC_URL"
    dpkg-deb -x "$EXT/cbmc.deb" "$EXT/native"
    chmod +x "$EXT/native/usr/bin/cbmc"
  fi
  got="$(sha256sum "$EXT/native/usr/bin/cbmc" | cut -d' ' -f1)"
  [ "$got" = "$CBMC_SHA" ] || { echo "FATAL: cbmc binary sha256 $got != $CBMC_SHA" >&2; exit 1; }
  echo "[ok] cbmc $("$EXT/native/usr/bin/cbmc" --version)"
fi

if [ "$WHAT" = all ] || [ "$WHAT" = loopbench ]; then
  # v1.04 held-out study: the ten standard loop suites, none of which an earlier protocol used
  sparse_at_pin "$SVBENCH_URL" "$EXT/svbench-loop" "$PIN_SVBENCH" 'c/loop-*/*'
fi

if [ "$WHAT" = all ] || [ "$WHAT" = juliet ]; then
  sparse_at_pin "$JULIET_URL" "$EXT/juliet" "$PIN_JULIET" 'testcases/CWE190_Integer_Overflow/*' 'testcasesupport/*'
fi

if [ "$WHAT" = all ] || [ "$WHAT" = tacle ]; then
  sparse_at_pin "$TACLE_URL" "$EXT/tacle-bench" "$PIN_TACLE" 'bench/*'
fi

if [ "$WHAT" = all ] || [ "$WHAT" = tools ]; then
  if [ ! -f "$EXT/ultimate-v0.3.2.zip" ]; then
    curl -fsSL --retry 3 -o "$EXT/ultimate-v0.3.2.zip" "$ULT_URL"
  fi
  echo "$ULT_SHA  $EXT/ultimate-v0.3.2.zip" | sha256sum -c - >/dev/null
  if [ ! -f "$EXT/ultimate-v0.3.2/UAutomizer-linux/Ultimate.py" ]; then
    rm -rf "$EXT/ultimate-v0.3.2"; mkdir -p "$EXT/ultimate-v0.3.2"
    unzip -q -o "$EXT/ultimate-v0.3.2.zip" -d "$EXT/ultimate-v0.3.2"
    if [ -f "$EXT/ultimate-v0.3.2/Ultimate.py" ]; then
      mkdir -p "$EXT/ultimate-v0.3.2/UAutomizer-linux_tmp"
      mv "$EXT/ultimate-v0.3.2"/* "$EXT/ultimate-v0.3.2/UAutomizer-linux_tmp"/ 2>/dev/null || true
      mv "$EXT/ultimate-v0.3.2/UAutomizer-linux_tmp" "$EXT/ultimate-v0.3.2/UAutomizer-linux"
    fi
    chmod +x "$EXT/ultimate-v0.3.2/UAutomizer-linux/Ultimate.py" || true
  fi
  [ -f "$EXT/ultimate-v0.3.2/UAutomizer-linux/Ultimate.py" ] || { echo "FATAL: Ultimate layout unexpected" >&2; exit 1; }
  echo "[ok] Ultimate v0.3.2 archive sha256 $ULT_SHA"

  if [ ! -x "$EXT/native/usr/bin/cbmc" ]; then
    [ -f "$EXT/cbmc.deb" ] || curl -fsSL --retry 3 -o "$EXT/cbmc.deb" "$CBMC_URL"
    dpkg-deb -x "$EXT/cbmc.deb" "$EXT/native"
    chmod +x "$EXT/native/usr/bin/cbmc"
  fi
  got="$(sha256sum "$EXT/native/usr/bin/cbmc" | cut -d' ' -f1)"
  [ "$got" = "$CBMC_SHA" ] || { echo "FATAL: cbmc binary sha256 $got != $CBMC_SHA" >&2; exit 1; }
  echo "[ok] cbmc $("$EXT/native/usr/bin/cbmc" --version)"
fi

echo "[done] $WHAT"
