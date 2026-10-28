# Eager scalar expressions in owned-list map calls (v0.36)

The `list_calls` backend accepts pure integer expressions for a borrowed map
helper's scalar actual arguments, including nonidentity parameter conversions.
The pointer actual must still be exactly the unique owned head. This extends
the [pointwise-map contract](OWNED_LIST_PAYLOAD_MAPS.md); builder arguments keep
their existing unchanged-identifier, identical-type contract. General calls,
aliasing arguments and external pointer contracts remain unsupported.

## Example

```c
static void map_payload(struct Node *cursor, unsigned char delta) {
    while (cursor) {
        cursor->value = cursor->value + delta;
        cursor = cursor->next;
    }
}
/* After checked construction: */
map_payload(head, delta + 260);
```

For entry `delta=2`, the actual expression evaluates to `262`, then the
parameter conversion yields `6`. Each node receives `old_value+6`, with its
payload assignment conversion preserved. It does not receive `old_value+262`.
The [complete example](../examples/clang_list_argument_conversions.c) builds a
chain, maps it, reverses it and consumes it. Selecting 100 successful
allocations yields `5550`, conditional on that allocation outcome.

```sh
python -m llmloop.symbolic_cli examples/clang_list_argument_conversions.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"list_calls","allocation_count":100,"loop_summaries":{"__list_scan":{"__list_call_total":"__list_scan*(__list_scan-1)//2+__list_scan*((delta+260)%256)"}}}' \
  --parameter-bounds '{"n":[0,1000000],"delta":[0,2]}' \
  --inputs '{"n":1000000,"delta":2}'
```

This example supplies a modular fold candidate. Automatic mathematical
extraction deliberately omits machine casts and may propose a wrong candidate;
the independent typed source check rejects it. No safety claim is made merely
because an expression or closed form was generated.

## Why evaluating the helper body is insufficient

C evaluates an actual argument before entering its callee, including an actual
whose formal is unused and a helper whose chain is empty. For example:

```c
void map(struct Node *cursor, int unused) {
    while (cursor) {
        cursor->value = cursor->value;
        cursor = cursor->next;
    }
}
/* An empty chain does not make this argument defined when delta == 0. */
map(head, 1 / delta);
```

Expanding only the loop would erase the actual expression when the formal is
unused or the loop executes zero times. The new rule independently verifies
each actual and its parameter conversion in the full entry domain before
allowing any successful list-call report. This also covers the first
allocation failing, nonpositive builder counts, invalid shifts and signed
overflow before a narrowing or boolean parameter conversion.

## Checked rule

Each scalar formal must have an admitted ABI integer type. Each actual may
contain integer literals, immutable entry scalar parameters, integer casts,
pure unary/binary arithmetic, comparisons, logical operators and conditional
expressions. Calls, assignments, increments, pointer observations, address or
dereference operations, payload/array reads, comma expressions and unsupported
types are refused, including such syntax in unselected branches. Existing
typed-kernel resource limits also apply. At most 16 scalar actuals per map call
are admitted; the shared eight-heap-stage limit is unchanged.

For each actual the rule emits a scalar proof function that initializes a
temporary of the exact formal type from that actual, then returns that stored
value. The existing typed CFG kernel checks every evaluated intermediate,
conversion, short-circuit/conditional guard and complete exit for all declared
entry inputs. This is a finite expression proof with no heap operations. It
does not impose the bounded heap kernel's object/iteration limits on the
inductive list. Every actual is checked even when another is safe or both
formals are unused.

Only after recording those checks does the composition bind a formal read to
the actual wrapped in its formal-type conversion. Helper frame names are
renamed before inserting caller expressions; a caller parameter named like
the callee cursor must remain the caller parameter. Bindings are simultaneous,
and record tags/member names are preserved. Original explicit casts and
compiler-normalized implicit casts remain in the typed witness.

Actuals are pure, observe only immutable entry values and are independently
defined. Repeating their converted values at pointwise reads is consequently
unobservable within the declared proof domain. C's unspecified sibling
argument order introduces no interaction for this fragment. The witness's
equivalence rule is **conditional on successful eager argument proofs**;
executing an expanded witness alone is not an argument-validity check and no
equivalence is claimed for rejected source programs.

The pointwise source matcher and typed map proof then recheck the complete
expanded stage, preserving payload-store conversions, ownership, links and
failure-prefix behavior. LP64/ILP32/LLP64 determine integer widths; plain `char`
signedness follows the selected model/compiler flag. Signed narrowing follows
the typed kernel's explicit two's-complement modular implementation choice,
rather than claiming an implementation-independent choice for all C targets.

## Reports and validation

`certificate.composition.argument_checks` records each callee/formal, actual,
formal assignment type, scalar proof source/hash, converted-value SMT term and
full proof report. Map binding metadata refers to those checks by index.
`eager_argument_evaluation_checked_even_for_empty_chain` is reported on success.
An unproved argument returns `UNKNOWN` with all safety/termination flags false,
the failing argument and its proof; an empty chain cannot bypass this gate.

```sh
python -m pytest -q --forked tests/test_list_call_arguments.py
python scripts/check_list_arguments_native.py --output experiments/v036/native.json
python scripts/run_v036_experiments.py
```

The native oracle compares original, Clang-normalized and, for proved programs,
composed C with the symbolic result and independent integer-conversion/payload
formulas at GCC `-O0`/`-O2` with UBSan. It covers negative/zero/positive actuals,
narrow/wide/boolean parameters, guarded division, mixed arguments, unused
formals, every selected allocation-failure prefix, identity/order/payload and
live-node checks. Rejected empty/unused argument programs and first-allocation
failure must retain their original/normalized UBSan failures. Native execution
is LP64; typed/compiler tests additionally check ILP32/LLP64, plain unsigned
`char` and original adjusted-array parameter rejection.

See the [experiment report](../experiments/v036/report.md). The structural
matcher, parameter-binding rule, Clang bridge and typed kernels remain trusted
components; native checks supplement universal obligations. Arbitrary builder
arguments, mutable/stateful actuals, effectful sibling calls, general ownership
or recursion contracts, heap graphs, arbitrary branch closed forms and complete
C/LLVM semantics remain open. KLEE is not integrated.
