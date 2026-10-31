# Pure bit-vector scalar CFG certificates

The explicit `typed_bv_cfg` and `typed_bv_calls` API frontends execute admitted
scalar integer C control flow. Clang proof configurations select `bv_cfg` or
`bv_calls`. Existing integer-lift/heap backends remain available and unchanged;
there is no automatic fallback or silent budget increase.

This backend reuses the existing CFG compiler and, in calls mode, hygienic direct
call expansion. It supports scalar branches, for/while/do loops, break/continue,
labels/goto, flat switches with fallthrough, early returns, parameter/return
conversions, lazy/nested calls and opt-in bounded recursive closure. Every path
must return within an explicitly selected step budget. It is bounded execution,
not an unbounded loop summary, closed-form synthesizer or LLVM interpreter.

## Integer and execution obligations

The pure expression kernel shares the project's concrete ABI/type/literal rules,
promotions and usual conversions. Signed overflow predicates use exact arithmetic
at twice the operand width and require equality to the sign-extended result.
Negating the signed minimum, zero division and signed minimum/-1 division or
remainder retain their undefinedness guards. Shift counts are checked in their
original promoted type before conversion to the left operand width; negative or
out-of-width counts cannot be hidden by truncation. Signed left shifts additionally
check nonnegative input and representable result. Unsigned arithmetic wraps;
signed casts and right shifts retain the explicit two's-complement/arithmetic
ABI choices. Conditional and logical operators guard only evaluated operands.

Parameter bounds are validated ordered representable intervals and encoded with
signed or unsigned BV comparisons, including `_Bool` and ABI-specific widths.
The expression kernel uses no BV2Int, integer arithmetic sorts, quantifiers or
uninterpreted applications in proof queries. Every solver input passes the strict
QF_BV guard before a `SolverFor('QF_BV')` query.

Each executed operation is checked under its incoming path condition. A proved
store may then carry a true safety flag: its original safety predicate has
already been discharged on that path. No paths are merged using unproved safety
assumptions. Leaving lexical scopes removes locals; unsupported shadowing and
uninitialized locals are refused. Goto cannot make skipped declarations become
initialized values. Duplicate converted switch cases are refused.

Reachability UNKNOWN stops analysis. Reachable external/depth markers and step
frontiers remain explicit analysis limits, not source-UB diagnoses. A successful
certificate requires all reachable paths to return and a final full-domain return
coverage query to be UNSAT. Concrete return evaluation is available only after
success and checks the certified input domain.

## Limits and replay

The existing per-path limits remain: 1..512 CFG steps, 1..64 paths, 1..8 call depth
in calls mode, with existing call expansion and syntax limits. All scalar queries
have a 5000 ms timeout, at most 4096 queries and 16 MiB of saved SMT-LIB per
analysis. These are **per-query** time limits, not a total 5-second source-analysis
claim. Exact reachability caching retains the AST with each cache key; it does
not conflate distinct guards or treat UNKNOWN as UNSAT.

`certificate.queries` records labels, logic, timeout, result, elapsed time and
SMT-LIB. Safety/coverage queries require UNSAT; feasible reachability queries
legitimately return SAT. Replaying these queries validates their SMT answers,
while the source executor, CFG compiler, call expansion and Clang structural
normalizers remain trusted and tested components. This is not a machine-checked
compiler-equivalence theorem or an independently checked source proof trace.

Example:

```json
{
  "frontend": "clang_proof",
  "source": "int entry(int n){int i=0;while(i<n)i++;return i;}",
  "function": "entry",
  "proof": {"backend":"bv_cfg","max_steps":128,"parameter_bounds":{"n":[0,8]}}
}
```

Pointers, arrays, globals, static/volatile/atomic storage, records and external
memory effects are not modeled by this scalar kernel. The existing finite-memory
and list backends retain their separate contracts. A successful scalar certificate's
memory-safety flag applies only to its admitted scalar fragment (including trusted
normalization of already supported integer union views), not general heaps.

## Original unsigned division

Run:

```sh
python scripts/check_division_bv.py --compare-baseline --controls --output /tmp/division.json
```

The experiment ingests the untouched pinned compiler-rt `udivsi3.c` and real
headers through a compilation database, verifies all 20 vendor files, then invokes
the Clang `bv_calls` API once in a fresh worker. The full domain is
`a in [0,2^32-1]`, `b in [1,2^32-1]`. It exports the actual certified return term,
replays all safety/reachability/coverage queries, compares 64 concrete model
outputs and 1024 original/normalized GCC -O0/-O2 outputs with independent Python
integer division on deterministic boundary/random inputs.

The 128-step mode still refuses incomplete exits. At the same explicit 512-step
limit and same 5000 ms per-query timeout, both the legacy integer-lift backend and
new BV backend analyze the same normalized source; their actual statuses and
timings are recorded. A legacy timeout is measured, not required for success.

Definedness/complete exit are separate from quotient correctness. A fresh output
query compares the certified original return with unsigned SMT division at a
5000 ms solver timeout. UNKNOWN is retained without asserting a universal
functional theorem. A shift-count mutation must be rejected with a source witness
and fail native UBSan at both optimization levels. A wrong-quotient mutation must
still pass universal source safety and be functionally/native-refuted at an
explicitly validated nonzero-divisor input. Zero-divisor compiler-rt behavior is
outside the functional specification; it is not labeled source UB merely because
mathematical division is undefined there.

The division pilot does not close general heap/alias/ownership composition,
unbounded termination, arbitrary branch recurrence discovery, all builtin
families or complete C/LLVM semantics. No KLEE is used. See
[v0.42 evidence](../experiments/v042/report.md).

The optional [source-bound division induction strategy](SOURCE_BOUND_DIVISION_INDUCTION.md) now closes the original unsigned-32 quotient proof with checked actual-source invariants and a separately declared total functional budget. The direct 5000 ms query and source-safety budgets remain unchanged.
