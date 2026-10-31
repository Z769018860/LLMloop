# Source-bound unsigned division functional induction

The explicit scalar BV functional strategy `unsigned_division` now proves the
original compiler-rt 32-bit unsigned divider's output over the original full
nonzero-divisor domain. Source definedness and complete exit remain a separate
prerequisite. Recognition only identifies candidate source regions; it does not
assign a division specification from a function name or an algorithm signature.
Every accepted expression comes from the actual normalized C AST.

API example (inside a Clang proof request):

```json
{
  "backend":"bv_calls",
  "max_steps":512,
  "parameter_bounds":{"a":[0,4294967295],"b":[1,4294967295]},
  "functional":{"kind":"unsigned_division","timeout_ms":30000}
}
```

The raw `typed_bv_cfg` / `typed_bv_calls` API also accepts `functional`. The
strategy is optional; existing backends and direct functional queries are
unchanged. Unsupported graphs or unproved lemmas give functional `UNKNOWN`
without discarding an independently successful source-safety certificate.

## Actual source binding

The current admitted graph has two unsigned-32 inputs, optionally one direct
wrapper return, a constant-width declaration, a counter initializer, two guarded
fast returns, counter initialization, remainder/packed-word/carry initialization,
a countdown for-loop, and a final update/return. The loop has the original five
state-update statements and one body-local temporary. State identifiers may be
renamed. Width, counter, remainder and carry slots must be unsigned-32; the mask
expression is evaluated with its actual declared C type.

An identity wrapper's actual argument conversions are checked against the ordered
original inputs. Pure scalar prefix helpers are interpreted from their real
initialized declarations and final return, with actual parameter/return
conversions, the primary ABI's ordinary-char signedness (including
`-funsigned-char`), eager arguments, all declaration safety predicates, a bounded
acyclic call graph and no globals or observable effects. A helper name, Clang
attribute or unused argument never supplies an assumed count value. Clang's
existing checked builtin lowering remains a trusted frontend component.

For the actual prefix, queries establish:

- The actual width is 32 and every evaluated prefix operation is defined.
- The actual zero-return path has numerator below divisor and returns zero.
- The actual unit-divisor path has divisor one and returns the original numerator.
- The remaining path starts with a counter K in 1..31, remainder below divisor
  and below 2^31. A high divisor additionally establishes K=1 and remainder
  at least 2^30.
- Actual source initialization packs the original numerator into its high
  remainder and unprocessed low bits, with zero initial carry.

No leading-zero-count theorem is assumed. Other initializers can succeed when
they independently establish these properties. Equivalent or compensating final
expressions can also succeed because their actual typed values are checked.

## Induction state and preservation

Let A be the original unsigned numerator and D the nonzero divisor. At a loop
head, S is the remaining counter; T is the unprocessed input tail; P is the stored
partial quotient; C is the delayed carry; R is the remainder. Unsigned word
representatives are interpreted as nonnegative integers.

The checked packing and arithmetic invariant is:

```
n_word = T * 2^(32-S) + P
Q = 2*P + C
A = (D*Q + R)*2^S + T
0 <= T < 2^S
0 <= P < 2^(31-S)
0 <= C <= 1
0 <= R < D and R < 2^31
D >= 2^31 implies S=1 and R >= 2^30
```

For each of all 31 possible positive S values, the real source body is evaluated
in a symbolic state satisfying the invariant bounds. These are universal state
queries, not sampled program inputs or executions of a fixed original input.
The queries check all executed intermediate safety predicates, including values
later overwritten or discarded. The actual loop condition and decrement must
match the countdown rank, including exit at zero.

The actual mask/carry/subtraction is compared with an independent unsigned
comparison and conditional subtraction. Queries establish the new remainder
bound and exact widened conservation, not merely modular equality:

```
expanded = 2*R + next_input_bit
expanded = R_next + D*C_next
P_next = Q
Q_next = 2*Q + C_next
```

The actual packed-word update, carry bit, tail decomposition and their range
bounds are checked in QF_BV. After any nonfinal step, they establish the same
invariant for S-1. The high-divisor phase can only occur at the last step;
otherwise D is below 2^31. These facts justify both the source sign-mask idiom
and the absence of unnoticed word-representation wrap in the integer decoding.

The arithmetic conservation identity is independently normalized as an exact
integer polynomial. With H=2^(S-1), B the next bit and U the remaining tail:

```
(D*(2*Q+F) + (2*R+B-D*F))*H + U
= (D*Q+R)*(2*H) + B*H + U
```

The certificate exports both expressions and requires their normalized difference
to be exactly zero. All numeric powers and counter cases are recorded.

At the final step, the actual post-loop update and return must equal Q_next.
Counter zero gives tail zero, so A=D*Q+R with 0<=R<D. A separate QF_NIA query
checks the general integer theorem that this Euclidean decomposition uniquely
determines Q=A/D. This specifies unsigned division of the original word values.

## Budgets, evidence and trust

For the original wrapper, 40 solver queries (39 QF_BV and one QF_NIA) and one
exact polynomial audit form the functional certificate. The functional strategy
has **one explicit total deadline, at most 30000 ms, including preparation and
certificate finalization**, and a **5000 ms maximum per query**. Each query gets
the smaller of its cap and the remaining total time; there are no retries or
timeout resets. Primary source analysis has its separate existing budget.

The unchanged direct whole-output QF_BV baseline keeps its 5000 ms solver timeout.
The source, typed execution, reference and domain hashes must agree between
strategies. The new proof uses a different, explicitly declared total budget;
it is not presented as a same-five-second speed comparison.

SAT or UNKNOWN in an intermediate lemma stops composition with functional
UNKNOWN. A failed induction hypothesis may arise for a correct implementation;
it is never exposed as an original-program counterexample. Actual wrong-result
controls are separately refuted with an independently checked whole-output query
at a validated input and native execution. Missing source safety, an incomplete
exit, zero in the declared divisor interval, unsupported state graphs, invalid
options and exhausted budgets cannot yield a functional proof.

Run all original-source checks and controls with:

```sh
python scripts/check_division_bv.py --strategy induction --compare-baseline --controls --output /tmp/division.json
```

The script checks 20 immutable vendor files, uses real Clang compilation-database
input, replays source and functional queries with their recorded logics, rebuilds
the polynomial audit, checks complete counter coverage, and retains the direct
baseline even if it times out. Original/normalized GCC -O0/-O2 outputs, model
values, unsafe-shift UBSan controls and a defined wrong-quotient refutation remain
part of the experiment. The standalone [example](../examples/clang_division_induction.c)
uses the simpler valid domain n in [0,2^32-1], d in [2,2^31-1]; it is not the
original upstream translation unit.

`PROVED_FUNCTIONAL_DIVISION_INDUCTION` requires the complete source binding,
initialization, all counter cases, rank, packing/range interpretations,
arithmetic audit and Euclidean uniqueness. There is no single whole-program SMT
query that replaces that composition. Typed expression/CFG/call execution,
Clang normalization, unsigned-word decoding and the induction composition rule
remain trusted and tested components. Query replay does not independently
verify the source interpreter or prove compiler equivalence in a proof assistant.

This closes the selected unsigned-32 quotient proof. It does not implement an
arbitrary functional-contract language, unrestricted division families, general
heap/alias/ownership contracts, arbitrary branch closed-form discovery or complete
C/LLVM semantics. No KLEE is used. See [v0.43 evidence](../experiments/v043/report.md).
