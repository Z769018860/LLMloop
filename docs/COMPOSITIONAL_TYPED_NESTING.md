# Compositional typed scalar nesting

The `typed_nested` frontend verifies nested and sequential canonical scalar C
for loops without unfolding their iteration counts. Every loop has a supplied
entry-relative state trajectory. Inner loop summaries are checked before they
are used as state transformers in an enclosing induction proof.

```sh
python -m llmloop.symbolic_cli examples/typed_nested_loop.c \
  --c-typed-nested --loop-summaries-file examples/typed_nested_summaries.json \
  --parameter-bounds '{"n":[0,1000],"m":[0,1000]}' \
  --inputs '{"n":5,"m":7}'
```

This example interleaves an outer long increment, an inner unsigned-char/long
loop, and another outer long update. It returns 85 for n=5,m=7. Both narrow
unsigned wrap and wide signed arithmetic are verified in the selected ABI.

## Entry-relative summaries

The API uses `frontend="typed_nested"` with `source`, `loop_summaries`, optional
`parameter_bounds`, `abi`, `char_signed`, `function`, `max_paths`, and `inputs`.
`loop_summaries` maps each loop's unique source index name to a formula for every
mutable scalar visible at that loop's entry. Input parameters and enclosing loop
indices are frozen in a loop body and do not require state-coordinate formulas.
Const scalar locals still require a coordinate describing their retained value.

```json
{
  "i": {"byte": "(i*m)%256", "total": "i*(m+3)"},
  "j": {
    "byte": "(entry(\"byte\")+j)%256",
    "total": "entry(\"total\")+j"
  }
}
```

`entry("total")` is the **actual value when that loop is entered**, including
all enclosing iterations and preceding source assignments. It is not the
function's initial value and is not an arbitrary unverified constant. It is
resolved to an independent mathematical ghost bound to the actual typed entry
expression. Formula names other than `entry` references denote original input
parameters and live source loop counters. Formula syntax is safely parsed with
AST validation and the closed-form parser; generated identifiers cannot be
introduced by writing them directly.

The current loop index starts at zero; a formula describes the state after that
many completed iterations of this invocation. Candidate checks only apply in
the loop's entry context and up to its actual exit count. A context can be
unreachable; its certificate does not assert that the loop executes. A loop
without carried scalar state uses an empty formula object and still checks its
body operations and termination.

## Compositional proof

For each loop-entry context the engine proves:

1. Entry values and the actual typed bound are defined.
2. The index is representable from zero through the exit test, and the typed
   comparison is equivalent to the inferred active-count range.
3. Every candidate coordinate is integral, type-representable, and equal to the
   actual entry value at zero.
4. Every executed source operation in one step is defined, and all branch paths
   preserve the candidate at the successor count and advance the index by one.

Nested loops encountered during that step are recursively verified under the
parent's active-count domain and the actual branch guard. Only after success is
the child replaced by its certified typed post-state. An unsafe or incorrect
child summary cannot be silently substituted into the parent proof.

The function executor then checks all source statements outside loops, complete
function-path coverage and the typed final return. This includes assignments
between sequential loops and after the final loop. Arithmetic uses the exact
ABI-aware integer lift from v0.15, preserving intermediate undefinedness,
promotions, narrowing, unsigned wrap and explicit implementation choices.

The report is `PROVED_DEFINED_TYPED_C_NESTED` only when every obligation succeeds.
It includes the input domain, selected ABI/policies, checked obligations, and
per-loop entry domains, counts, supplied formulas and nesting depth.
`c_overflow_verified=true` and `termination_proved=true` apply to the accepted
source and input domain. Failed obligations return `UNKNOWN` with a parameter
and live-counter witness when available. A rejected candidate's witness is not
itself an established reachable undefined source execution.

## Supported shape and limits

- Scalar integer parameters, initialized scalar locals and a final return.
- At most 16 for-loop definitions, with globally unique fresh declared indices;
  nesting depth is at most 16.
- Each loop initializes its index at zero, tests `index < bound` and advances by
  one. Bounds may read current input-parameter values and enclosing loop indices.
  Mutable carried-state bounds are rejected.
- Typed source assignments and if/else control flow may appear before, between,
  inside and after loops. Branch-local initialized scalar temporaries are
  checked and projected away at block exit.
- Each loop has at most 15 carried scalar coordinates; branch and statement
  budgets are retained from the typed executor. SMT obligations have a
  five-second timeout and unproved obligations return UNKNOWN.

Parameters may be assigned outside loops if their typed operations are defined;
formula parameter names continue to denote original function inputs. Parameters
and all live enclosing indices cannot be assigned in a loop body. Out-of-scope
indices, shadowing/reused declarations, arbitrary early exits, while/do loops,
calls, pointer/array memory and volatile/static/atomic storage remain unsupported.

This mode does not synthesize candidates generally. It composes certified
canonical scalar loops; it is not a general CFG, arbitrary heap, or unified
unbounded typed memory verifier.

## Symbol-hygiene correction

v0.15's single-loop verifier used a generated counter spelling that could collide
with a parameter named `counter_<index>`. That could restrict the count used in
the proof and incorrectly accept a candidate outside the accidentally restricted
counts. v0.16 uses independent fresh SMT symbols for both parameters and
counters, in both single-loop and nested modes.

A regression and experiment control use parameter `counter_i=0`, loop index i,
and an incorrect candidate that is right only for the first step. The corrected
verifier rejects it, while the correct candidate still proves and matches native
C results. The entire previous test and experiment set is rerun after the fix.

## Reproducible evidence

```sh
python -m pip install -e '.[test,smt]'
python scripts/build_nested_cases.py
python scripts/run_symbolic_experiments.py \
  --fixtures experiments/v016/cases.json --output experiments/v016
```

Added native C/UBSan experiments cover interleaved double nesting, outer-index-
dependent inner bounds, triple modular nesting, sequential loops and the symbol
namespace regression. Zero inner/outer counts and unsigned wrap boundaries are
included. The outer-dependent example proves a million-iteration outer domain
whose actual summed inner count reaches a trillion; native differential checks
use manageable finite samples instead of executing a trillion source steps.

The complete [v0.16 report](../experiments/v016/report.md) records positive,
incorrect-candidate and unsupported controls, source/fixture hashes, commands and
environment versions. Controlled native checks do not replace induction proofs
or representative real-world library benchmarking. LP64 native evidence remains
distinct from symbolic/unit ABI checks of ILP32/LLP64.
