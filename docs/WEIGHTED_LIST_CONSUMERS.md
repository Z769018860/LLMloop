# Checked scalar arguments and weighted list consumers (v0.44)

The `list_calls` backend now binds pure integer expressions to scalar parameters
following a consumer's unique owned head. It preserves C parameter conversions,
checks every eager actual independently of chain length or formal use, and
retains the consumer's complete additive step and scalar return expression.
This extends one checked ownership pipeline; it is not general call contracts,
stateful consumers, arbitrary aliases or graph analysis.

```sh
python -m llmloop.symbolic_cli examples/clang_list_weighted_consumer.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100,"loop_summaries":{"__list_scan":{"__list_call_total":"((delta+260)%256)*(__list_scan*(2*__list_length-__list_scan-1)//2)+__list_scan*(delta-1)"}}}' \
  --parameter-bounds '{"n":[0,1000000],"delta":[0,2]}' \
  --inputs '{"n":1000000,"delta":2}'
```

The result is `PROVED_DEFINED_CLANG_LIST_CALLS`, value **29806**, with no live
nodes after return. This selected outcome has 100 successful allocations and
then one allocation failure. The proof covers every prefix outcome in the
declared domain. No heap-capacity guarantee or all-allocations-succeed assumption
is introduced.

## Parameter and ownership binding

A consumer has one literal same-record pointer parameter followed by at most
sixteen named integer parameters. The first actual must be the caller's unique
owned head. Every scalar actual must be a pure expression of immutable entry
parameters and integer constants: arithmetic, integer casts, comparisons,
logical operators and conditionals. Memory/pointer observations, nested calls,
assignments, increments, comma and other effects are rejected, even if placed
in an unevaluated branch. Pure arguments have no observable ordering conflict.

Each actual, including unused formals, is proved defined in the full entry
domain before using a composed witness. A zero-length list or first-allocation
failure never erases division by zero, signed overflow or an invalid shift in
an actual. Failure returns `UNKNOWN` with a consumer argument source diagnostic;
it does not continue to trajectory discovery. Separate source hashes, the
converted typed value and the argument proofs appear in
`certificate.composition.argument_checks`. The exact scalar bindings appear in
`consumer_scalar_argument_bindings`.

Formal assignment conversions remain explicit casts in the witness. Narrowing,
signedness, `_Bool`, ABI-dependent `long` widths and ordinary-char signedness
therefore retain the existing typed semantics. The implementation choice for
out-of-range signed conversion is two's-complement modular conversion. A
strictly wider containing target range needs no modular reduction in the list-fold
integer profile; this representation change retains the original safety predicate.
Other backends keep the original v0.43 conversion function unchanged.
Arithmetic sign-bit right shifts and zero/all-ones bit masks additionally use
exact word identities in the typed-source word profile. Generic IntegerLift
retains its original arbitrary-integer semantics; the word profile is selected
only by source kernels with checked parameter, trajectory and operation ranges. All original shift bounds
and eager operand safety predicates remain. This makes the original signed-abs
idiom a linear integer expression rather than an avoidable mixed-theory query;
INT_MIN and reachable abort frontiers remain independently rejected.
It cannot repair earlier undefined arithmetic or remove a narrowing conversion.
List fold candidates use the same Euclidean remainder expression as typed C
conversions for positive integral `Mod`. This exact normalization avoids forcing
weighted induction to rediscover the floor/remainder identity under products.
Other proof kernels retain their existing default translation. Negative divisors
and nonintegral dividends retain their exact floor rule.

Helper locals and scalar formal placeholders are renamed before simultaneous
substitution. This avoids capture by caller variables, the owned head, another
formal or generated proof locals. Record member/tag names are never substituted.
One call's expanded consumer body is limited to 100000 source characters; the
existing overall source and eight-stage heap budgets remain unchanged.

## Typed additive step and return

The checked fold still has zero-initialized accumulator, `while(head)`, next
load, one `accumulator += expression`, `free(head)`, and saved-tail advance.
The step expression may read only the current initialized payload and immutable
scalar inputs. It may read the payload multiple times and use guarded operators.
It cannot read another node, the accumulator, pointer identities, freed objects,
globals or effectful calls. The final expression may read the accumulator and
immutable scalar inputs, with no pointer/memory access or effects.

The exact original expression tree is retained. Only current payload reads are
replaced with the typed load from the already checked stored-payload trajectory;
operators, all conversions and lazy guards remain. Thus a multiplication that
overflows before widening or a division by zero in an empty-chain return cannot
inherit shape success. The callee return conversion precedes caller casts and
the caller's return conversion. The same fold expression rule also applies to
the direct `list` backend.

Construction, maps and reversal keep their existing shape/initialization proofs.
Traversal uses the actual final orientation. `TypedCNested` independently checks
the source step, supplied or discovered trajectory, overflow, termination and
return for every modeled failure-prefix length. Weighted formulas are candidates,
not assumptions: a formula that uses an unconverted weight is refuted. Automatic
discovery still supports its previous restricted arithmetic fragment; admission
of a pure expression does not guarantee discovery or a proof within resource
limits. Unsupported synthesis or solver UNKNOWN remains unsuccessful.

`certificate.fold_expression_contract` records the actual step/return and
preservation conditions. It does not replace the typed fold proof.

## Reproduce and limits

```sh
python -m pytest -q --forked tests/test_list_consumer_arguments.py
python scripts/check_list_consumers_native.py --output /tmp/consumers.json
python scripts/run_v044_experiments.py
```

Native checks compare original C, Clang-normalized C and the composed witness
against independent typed arithmetic expectations at GCC `-O0` and `-O2` with
UBSan. They count allocation attempts/successes, verify each payload and exact
free identity/order, and require all owned nodes freed. Inputs include empty,
failed-prefix and million-node outcomes; the LP64 large-long-weight case uses
an explicit maximum of 1000 to avoid accumulator overflow. Negative controls
run original/normalized C only, because a rejected argument/step does not justify
a composed witness. Native tests are supplementary finite evidence, not the
universal source proof. Three x86 ABIs and char signedness are checked separately.

Builder arguments retain their identity-only contract. Consumers cannot mutate
payloads/links, keep aliases, allocate, call other helpers, recurse, change the
fixed traversal, or carry arbitrary state-dependent accumulator recurrences.
General builder contracts, aliases/ownership composition, external-call contracts,
graphs, arbitrary branch closed forms, broader independent library families and
complete C/LLVM semantics remain open. Clang normalization, source composition
and typed interpretation remain trusted components; no proof-assistant compiler
equivalence theorem is claimed. KLEE is not integrated.

See [v0.44 evidence](../experiments/v044/report.md),
[ownership composition](INTERPROCEDURAL_LIST_HEAP.md) and
[remaining requirements](C_COVERAGE.md).
