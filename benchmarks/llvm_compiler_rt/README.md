# Pinned LLVM compiler-rt integer pilot

The 20 files listed in [manifest.json](manifest.json) are byte-for-byte copies
from LLVM **18.1.8**, commit
[`3b5b5c1ec4a3095ab096dd780e84d7ab81f3d7ff`](https://github.com/llvm/llvm-project/tree/3b5b5c1ec4a3095ab096dd780e84d7ab81f3d7ff/compiler-rt/lib/builtins).
The manifest records immutable URLs, upstream Git blob identities, SHA-256 and
byte counts. Original headers and the real `int_util.c` abort utility are kept;
there is no replacement compatibility header or stubbed abort implementation.
The complete upstream [license](LICENSE.TXT) and source notices are retained.
This README and the manifest are LLMloop metadata, not upstream files.

Thirteen public builtins form 15 declared input-domain cases. Leading/trailing
zero counts split nonzero signed inputs into positive and negative intervals,
preserving the upstream nonzero precondition. Absolute value/negation return
cases exclude `INT_MIN`, while separate native controls check the intended
abort at `INT_MIN`. Unsigned division excludes a zero divisor. Unsupported
union storage, external abort calls and compiler builtins are retained in the
coverage denominator; native success never upgrades an `UNKNOWN` proof.

From a repository checkout, with Clang, GCC, test and SMT dependencies installed:

```sh
python scripts/check_llvm_builtins.py --compare-baseline \
  --output experiments/v037/upstream.json
```

The run is offline. `--compare-baseline` needs the previous commit `95fb055`
available in local Git history; it executes the prior integer-lift kernel in
isolated child processes and keeps the original 5-second SMT query timeout.
Omit that option to run the pilot from a source archive without Git history.

Clang ingests original translation units and headers through a generated
compilation database. Every successful source safety proof is paired with a
separate typed bit-vector evaluator and an independent reference circuit;
unknown functional queries remain unknown. GCC `-O0`/`-O2` with UBSan compiles
original/normalized source and a runtime-input harness as separate translation
units, without LTO. Only the exported function symbol is renamed by a recorded
preprocessor flag to prevent host runtime symbol interposition. Boundary and
seeded random inputs are compared against Python integer references. The
original upstream abort utility is linked to native executables.

Controls distinguish a defined but incorrect popcount mask (safety passes,
functional/native reference fails), an undefined signed-shift mutation, and
intended library aborts. Full commands, values, model samples, SMT queries,
coverage gaps and before/after evidence are in the [experiment report](../../experiments/v037/report.md).

This is a small integer-runtime pilot, **not a representative survey of C
libraries**, general memory, external contracts, floating point or LLVM
instruction semantics. The production source kernels keep their stated scope.
