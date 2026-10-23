# Sequential C CFG extraction and automatic invariant templates

This extension adds two bounded steps to the Z3 pipeline.

## 1. C CFG to SPath

The --c-cfg frontend parses one scalar-int function with initialized local
integers, one while loop, and a scalar return. Its body may contain nested
if/else blocks and multiple sequential conditionals. Symbolic execution
rewrites each later branch condition through earlier assignments, so for:

~~~c
if (x < 5) x = x + 2; else x = x - 3;
if (x >= 4) y = y + 2; else y = y + 1;
~~~

the second condition uses the post-first-branch value (x+2 >= 4 or
x-3 >= 4), not the stale loop-head x. Each complete path becomes an SPath
guard plus loop-head-to-loop-head updates. The path count is capped at 48 by
default; unsupported statements and path explosion fail closed.

## 2. Automatic invariant templates

The --synthesize-invariants option mines candidate intervals from integer
thresholds and constant branch deltas, one-sided bounds for monotone
accumulators, and pairwise affine equalities preserved by every path. Every
candidate is checked by Z3 for initiation, path coverage and consecution.
For examples/smt_nonfunctional.json, the generator proposes
x >= 0 and x <= 6 and the solver must prove it before graph refinement.

This is incomplete template synthesis, not a complete abstract interpreter.
Failure to discover an invariant is not a counterexample to its existence.
Only certified candidates are returned as invariants.

## Run

~~~bash
python -m pip install -e '.[test,smt]'
llmloop-smt examples/smt_sequential_cfg.c --c-cfg --parameter-bounds '{"n":[0,100]}' --synthesize-invariants
llmloop-smt examples/smt_nonfunctional.json --synthesize-invariants
pytest -q
~~~

The model uses mathematical unbounded integers. Signed C overflow, pointer
and heap aliasing, calls, nested loops, and arbitrary CFG control flow remain
unsupported. This is an SPath extractor for a single loop, not a full C
compiler or a complete LoopSCC reimplementation.
