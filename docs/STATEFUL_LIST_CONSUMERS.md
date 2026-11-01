# Typed scalar-state list consumers (v0.46)

The `list` and `list_calls` contracts now admit one to eight initialized integer
states and one to sixteen source-ordered scalar assignments per consumed node.
Updates may read current initialized payload, immutable scalar parameters and
current scalar states. Later assignments see earlier assignments from the same
node. This extends the existing single owned prepend-chain contract; arbitrary
heap/call contracts and complete C support remain open.

```sh
python -m llmloop.symbolic_cli examples/clang_list_stateful_consumer.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100}' \
  --parameter-bounds '{"n":[0,1000000],"delta":[-3,3]}' \
  --inputs '{"n":1000000,"delta":2}'
```

This double prefix sum returns **338452**, with no live nodes. It represents 100
successful allocations followed by failure. Every possible allocation prefix
is covered. Reversal changes prefix histories and is tracked in the proof.

## Source and ownership contract

The consumer has one to eight initialized scalar declarations, `while(head)`,
and a scalar return. Each iteration saves next, executes one to sixteen scalar
assignments, frees exactly the current head, then advances to saved next. The
fixed complete traversal and decreasing rank still exclude early exits, hidden
calls, allocation, aliases, retained pointers and arbitrary memory updates.

Initializers are pure expressions of entry parameters and previously initialized
states. Forward/self reads, uninitialized states, pointer/memory observations,
increments, calls, globals and effects are refused. Every initializer is checked,
including unused states and empty/first-allocation-failure outcomes. Updates may
use `=`, arithmetic/bitwise compound assignments and pure conditional expressions;
they may write only declared states. Ordinary statement-level branches remain
outside this source pattern. Admission does not guarantee automatic discovery.

State types may differ. Initialization, every intermediate arithmetic operation,
each assignment conversion, and callee/caller return conversions are retained.
For example, a byte-state store precedes any following state read. Even an
overwritten or zero-masked undefined operation must fail source definedness.
The final return is also checked when no node was consumed.

The existing typed trajectory kernel proves all state coordinates, bases,
inclusive type ranges, actual source steps, guarded definedness, complete exits,
termination and final return. Polynomial/periodic discovery produces candidates;
supplied candidates must pass the same obligations. The scalar fold domain still
overapproximates all failure-prefix lengths. Arbitrary exponential, nonlinear or
branching state recurrences may remain `UNKNOWN`.

## Scoped proof representations and audits

All list folds, including the original zero-initialized additive fold, use a
scoped typed profile in which assignment to the
same C integer type preserves an already represented typed value and its entire
safety guard. Parameter and candidate ranges and every source arithmetic guard
are checked independently; unsafe intermediate arithmetic is never repaired.
Generic arbitrary-integer conversion and the other proof kernels are unchanged.
Universal representability lemmas cover integer types, char choices and three
ABIs, including negative signed-minimum controls.

Existing exact rational interval enclosures may certify the actual source
arithmetic safety predicates for these stateful folds. They prove inequalities
from conjunctive parameter/counter bounds; they do not assume operations defined.
All original guard predicates remain present. Unsupported enclosures fall back
to the normal SMT proof.

Successor equalities may use a budgeted exact integer-valued polynomial audit.
Only integer atoms are admitted. For a rational polynomial with denominator D,
the checker verifies integer coefficients of every shift `P(x+D)-P(x)` and all
residue tuples modulo D. This is a finite universal integrality certificate,
including negative integer inputs. It can remove only certified integral floors;
other integer operations remain distinct opaque atoms. The resulting polynomial
differences must be exactly zero. It does not infer C safety from algebra.

The audit caps degree at eight, atoms at eight, denominator at 64, residue tuples
at 4096 and equalities at sixteen. Claims, atom bindings, complete residue tables,
shift identities and zero differences are exported. Replay parses the original
SMT-LIB query and recomputes the certificate. Missing/tampered coverage or claims
are rejected. This uses the trusted exact arithmetic checker rather than claiming
a single root SMT UNSAT query or a proof-assistant theorem.

Remaining successor obligations may use a complete counter-residue partition
chosen before solving, with modulus at most twelve. Every residue and coverage
must be proved. Query deadlines stay at 5000 ms; there is no timeout retry or
input-domain reduction. These are finitely many symbolic induction cases, not
enumeration of represented nodes or loop iterations.

## Reproduce and evidence limits

```sh
python -m pytest -q --forked tests/test_list_stateful_consumers.py tests/test_integer_polynomial_audit.py
python scripts/check_list_stateful_native.py --output /tmp/stateful.json
python scripts/run_v046_experiments.py
```

Native controls compare original C, Clang-normalized C and composed C at GCC
`-O0`/`-O2` with UBSan against independent recurrence oracles. They also check each
payload and free identity/order, allocation attempts, empty/million-node outcomes
and live footprint. Arithmetic certificates are replayed separately. Native
observations supplement universal source obligations; they do not replace them.

Some discarded/overwritten or zero-masked undefined computations can be removed
before sanitizer instrumentation. Such zero-exit observations are recorded as
sanitizer frontiers, never as defined executions or positive correspondences.
The source checker must still reject every negative source on its actual
definedness obligation. Observable overflow/division/negation controls remain
mandatory sanitizer failures. Rejected programs have no composed witness.

One former accumulator-read structural rejection is superseded by a checked
positive in an explicit two-node domain. Million-node parity feedback and coupled
prefix histories are separate positive cases; general exponential discovery is
not claimed. Multiple owners, arbitrary graph updates, recursive heap induction,
external contracts, wider C/LLVM semantics and broader libraries remain open.
The experiment driver can select a source-worker process wall ceiling explicitly;
the default remains 60 seconds, while this release selects 120 seconds and an
1800-second full-pytest process ceiling. These process limits are separate from
unchanged SMT query and total functional proof budgets. The first unsuccessful
frozen validation is retained in the final attempt record; no merge follows a
partial pass or a timeout. No KLEE. See [coverage](C_COVERAGE.md) and
[v0.46 results](../experiments/v046/report.md).
