# v061 P0 evidence and reproduction

This directory contains complete capture of a finite, preregistered 192-run
study and separately identified supplements. `passed` means the capture and
declared controlled expectations passed; it is not an external-tool success
rate and does not close all paper P0 requirements. Read `p0_ledger.json` and
`report.md` before using any numbers.

## Revisions and environment

| Tool | Source | Revision |
| --- | --- | --- |
| ELBA | https://github.com/freqhorn/elba | 54c58fcd872481a5e72f8c4a31ed2ef242b6fbdd |
| LoopSCC public snapshot | https://github.com/hahaleyile/LoopSCC | 09ef9351667a8ccd83d7a50907ca5ea90ec521a4 |
| LIFT artifact | https://github.com/prouzan/LIFT_Artifact | 17bf85707be6677186f34dba25aca58130ac8abe |

The public LoopSCC snapshot is not established as the ICSE 2026 artifact.
Neither ELBA's dependency compatibility build nor LIFT's native Mono setup is
the authors' exact environment. No general cross-tool speedup is claimed.

Clone these repositories into sibling directories `elba`, `loopscc`, `lift`
under an external tools directory, and checkout the exact commits above.
Original source paths and SHA256 are in the frozen protocols. Sources and
external binaries are not redistributed here; redistribution permission and
license compatibility for a combined benchmark release remain unresolved.

ELBA was built with GCC13.3, Boost1.83, GMP6.3, Z3 4.13.0. Ubuntu dependency
packages were downloaded and extracted privately, without a system install.
Set `P0_TOOLS` to the absolute tools directory. Install z3-solver4.13.0.0 into
`$P0_TOOLS/elba-python` and place Boost/GMP headers/libraries under `native`.
From the ELBA repository:

```sh
g++ -std=c++14 -O1 -include deque \
  -Iinclude -I"$P0_TOOLS/native/usr/include" \
  -I"$P0_TOOLS/native/usr/include/x86_64-linux-gnu" \
  -I"$P0_TOOLS/elba-python/z3/include" \
  tools/elba/BoundSolver.cpp \
  -L"$P0_TOOLS/elba-python/z3/lib" \
  -L"$P0_TOOLS/native/usr/lib/x86_64-linux-gnu" \
  -Wl,-rpath,"$P0_TOOLS/elba-python/z3/lib" \
  -Wl,-rpath,"$P0_TOOLS/native/usr/lib/x86_64-linux-gnu" \
  -lz3 -lgmpxx -lgmp -o "$P0_TOOLS/elba-local"
```

For LoopSCC, install SymPy1.12.1 and z3-solver4.13.0.0 into
`$P0_TOOLS/loopscc-python`. For LIFT, install antlr4-python3-runtime4.9.2,
pyyaml, openai and requests into `$P0_TOOLS/lift-python`. The last two packages
are imported by upstream code; this supplied-bound smoke makes zero model
calls. The private Mono6.8 runtime also needs System.Core, System.Xml,
System.Runtime.Serialization, System.Xml.Linq and System.Data assemblies and
their package dependencies. Use the extracted Mono configuration mapping
System.Native, and the upstream bundled Z3 4.8.9, Boogie and learner binaries.
The exact wrapper and all failed dependency attempts are archived.

## Commands

Run the main study at source commit `5b883aa361b7ffb1208e920eeb4ecb7e59035183`
(tree `44f2bb99df8d0ccbff04c87a98e66bc08c2513dc`) in a clean checkout. This is
important: the original runner freezes *all* tracked file hashes. Later report
changes intentionally are not part of that original tree. The corresponding
GitHub source checkpoint is `22e8a7c83c6cb47aff54f415ff4f4988b53d4c7a` with
the identical tree. Use a fresh output directory:

```sh
python3 scripts/p0_experiments.py --tools "$P0_TOOLS" \
  --plan experiments/protocols/v061_p0.json --output experiments/v061
```

The later supplements were frozen at local source commits
`dfaafc9dcf31ab5c6d7ef9c77fe7548b449b98d4` (projection and LIFT adapter) and
`c7eb1691dc597ccdf04befe5a604d50009cbeeb6` (unchanged upstream scripts).
Their script hashes, upstream revisions and schedules are in the evidence. The combined supplemental source is published at `c9eee04120577f14e14d5eebff1566f97f47e3ac`, tree `c63ad31cbd851a4f88b29b0de0c2b2fec45518cf`, identical to the local native-supplement checkpoint.
These supplements remain reproducible from the final code tree:

```sh
python3 scripts/p0_projection.py --tools "$P0_TOOLS" \
  --output experiments/v061/projection
python3 scripts/p0_native_loopscc.py --tools "$P0_TOOLS" \
  --output experiments/v061/native_loopscc
```

Use a copy with the original main raw directory extracted for the projection's
post-hoc audit. Give new output paths or remove only your own prior generated
outputs. Do not overwrite published evidence to rerun it.

With Mono's private wrapper on PATH and the LIFT isolated Python dependencies
on PYTHONPATH, run `scripts/p0_lift_smoke.py --root "$P0_TOOLS/lift/LIFT"
--workspace /absolute/fresh/workspace` three times in fresh processes, each
with a 60-second host deadline. The adapter preserves logical checks and
disables only upstream global process-name cleanup. Host timeout handling
must own and terminate only its child process group. LIFT's original output
reader can label a missing-assembly crash as a verification timeout; diagnose
such runs from complete stdout/stderr before interpreting that label.

```sh
python3 -m pytest -q tests/test_p0_protocol.py tests/test_p0_projection.py
```

## Archive

`raw_evidence.tar.gz` contains original requests, per-run commands, stdout,
stderr, results, schedules, the finite point observations and all dependency
attempts. `raw_manifest.json` provides each member's SHA256 and archive SHA256.
Archive extraction requires no third-party binaries. Executable outputs and
generated third-party LIFT BPL files are excluded. The repository carries the
original drivers and frozen plans separately.
