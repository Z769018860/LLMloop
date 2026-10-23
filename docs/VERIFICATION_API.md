# Whole-graph verification and integration API (0.7)

## Bounded execution verification

```bash
llmloop-smt examples/smt_nonfunctional.json --verify-steps 12 --assertion 'x >= 0'
llmloop-smt examples/c_memory_sequential_loops.c --c-memory --bounded-function --parameter-bounds '{"n":[0,3]}' --max-unroll 8 --verify-steps 1
```

`verify_bounded(graph, steps, assertion)` starts at the IR initial state and
composes all enabled transitions, including moves between SCCs. Parameters
remain symbolic over their declared domain. The verifier does not assume
candidate or even certified invariants: it checks reachability directly.
Assertions are checked at each loop head, including the initial and exit
states. They are not statements inserted inside a C loop body.

| Status | Meaning |
| --- | --- |
| `ALL_EXECUTIONS_TERMINATE_WITHIN_BOUND` | All IR executions terminate by the bound, and the supplied assertion holds at all visited heads. |
| `ASSERTION_VIOLATED` | A reachable loop-head state violates the assertion. |
| `UNDEFINED_OR_AMBIGUOUS_TRANSITION` | Reachable missing/overlapping SPaths, or a modeled signed-overflow obligation fails. |
| `BOUND_EXHAUSTED` | At least one execution remains active; no termination or unbounded safety claim. |
| `UNKNOWN` | Solver did not decide a query. |

SAT results include parameter values, a state trace and the executed SPath IDs.
The trace is a witness in the IR, not an independent native-C replay. The
verifier allows 0..256 steps and per-query timeouts of 1..60000 ms. A host
accepting untrusted inputs must additionally limit total process time/memory.

For bounded whole-function memory IR, one transition represents the entire
statically unrolled function. Intermediate C states are embedded in its path
conditions, not exposed as BMC assertion locations. The memory frontend uses
mathematical integers; it does not prove absence of C signed overflow.

## Unbounded termination through affine rankings

```bash
llmloop-smt examples/smt_nonfunctional.json --ranking 'n - i'
llmloop-smt examples/smt_nonfunctional.json --synthesize-ranking
```

`verify_ranking(graph, expression)` checks an affine integer expression R under
the parameter domain and previously **certified** inductive invariants:

1. R is nonnegative whenever the loop guard holds.
2. Exactly one defined SPath is enabled at each such state.
3. Every enabled transition decreases R by at least one.

All counterexample formulas must be UNSAT. `CERTIFIED_TERMINATION` then proves
termination even for nonfunctional SPath SCCs. `max(0,R(initial))+1` is a safe
step bound, not an exact trip count. Bit-vector graphs are rejected. The
synthesizer tries a bounded template bank of variables, negations, sums and
differences. Failure remains UNKNOWN, never a nontermination proof. This does
not synthesize general piecewise closed forms or lexicographic rankings.

## JSON-compatible Python API

```python
from llmloop.api import analyze_request

report = analyze_request({
    "source": "int f(int n){int i=0;while(i<n){i++;}return i;}",
    "parameter_bounds": {"n": [0, 3]},
    "max_unroll": 3,
    "verify_steps": 1,
    "assertion": "i == 0 or i == n"
})
```

Supply exactly one of `source` (bounded C memory frontend) or `ir` (SPath JSON).
C source defaults to whole-function mode; `whole_function: false` instead uses
one-outer-while mode. Other fields: `function`, `parameter_bounds`, `max_unroll`,
`max_paths`, `invariants`, `verify_steps`, `assertion`, `ranking`,
`synthesize_ranking`. Unknown fields and invalid limits produce a structured
UNKNOWN response. Responses carry `schema_version: 1`. `ANALYZED` means the
analysis ran, not that the program is safe; inspect the nested proof statuses.

This in-process adapter performs no network/model calls and starts no server.
A web/editor host can pass decoded JSON and display the returned JSON. The
host remains responsible for transport, authentication and process isolation.

## Memory semantic corrections

Memory stores now distinguish `=`, `+=`, `-=`, and `*=` using the old aliased
cell value. Other store operators fail explicitly. Logical `&&`/`||` condition
safety guards respect C short circuit evaluation: invalid accesses on a
skipped RHS do not exclude defined executions. `calloc` sizes must use
`sizeof(int)` (optionally multiplied by a positive integer), and excess array
initializers are rejected.


## Reproduce validation locally

```bash
python -m pip install -e '.[test,smt]'
python -m pytest -q
python scripts/check_memory_native.py
```

The native oracle requires a POSIX C compiler `cc` and compares three memory
programs over `n=0..4` (15 executions): aliased compound stores, skipped null
pointer accesses, and sequential/nested array loops. Constant `ite` selections
are folded during translation to prevent unnecessary expression growth.
No GitHub Actions run is required for these checks.
