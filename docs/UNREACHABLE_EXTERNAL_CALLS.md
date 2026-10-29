# Unreachable external-call evaluations (v0.38)

An available function body is still required for an executed direct call. This
release additionally admits a direct external declaration when the entire call
evaluation is proved unreachable in the declared domain. It does not supply
external return values, heap effects, purity, termination or `noreturn` contracts.

## Proof rule and scope

The typed calls frontend retains unmatched external prototypes separately from
available definitions. For each external call site it emits a hygienic analysis
frontier before any argument or result evaluation. Every reachable frontier is
rejected by an explicit false obligation. A successful complete CFG certificate
therefore excludes the entire original call, including all argument evaluations.
Unknown reachability queries are never treated as unreachable.

The normalized marker uses an intentionally failing division as a conservative
fallback for other receiving source kernels. It is not a statement that the
original external call has undefined behavior. `TypedCFGCalls` checks the explicit
frontier obligation first and reports `analysis_limit=external_call_frontier`,
`counterexample_kind=reachable_external_analysis_frontier`, and an input witness.
Every safety/termination flag remains false for this UNKNOWN result. No dummy
return can become reachable in a successful proof.

Short-circuit, conditional, comma, discarded-expression, loop-header, switch and
helper-frame sequencing use the existing call expansion. Parameter narrowing
and actual caller state still determine reachability. External functions and
helpers depending on them are not inferred pure; unordered potentially observing
siblings remain refused. Unsafe conditions before a call retain their original
definedness obligations.

Current external results are integer or void. Prototypes must have matching
arity; conflicting declarations, variadic/old-style typed calls and external
pointer results are refused. There are at most 32 external declarations and 32
combined external/depth frontiers. Existing CFG/heap/call limits remain.

The Clang calls bridge retains original callee names, argument expressions,
ordinary string literals and compiler-expanded `__func__` values. It exports
external declaration metadata and records each opaque call site. Strings are
admitted only as opaque external arguments, with no reachable string-memory
semantics. External attributes are not used as proof assumptions. Other Clang
backends do not gain external semantics. Definitions continue to be normalized
and executed rather than treated as external declarations.

## Original compiler-rt evidence

The pinned LLVM sources and license are unchanged from v0.37. `__absvsi2` and
`__negvsi2` now pass source safety over `[-INT_MAX, INT_MAX]`, where their abort
calls are unreachable. Widening either domain to include `INT_MIN` must return
UNKNOWN with that input as an external-frontier witness. Native original and
normalized code still link the real upstream abort implementation, and both
optimization levels must actually abort at that input. No abort stub is used.

Independent functional queries compare a separate bit-vector execution of the
expanded normalized source with mathematical absolute-value/negation circuits.
The QF_BV query checks values after the independent primary source-safety proof;
it never sends mixed BV2Int safety predicates to a QF_BV solver. A sort check
rejects a reference query containing integer-theory terms. This remains trusted
source evaluation and normalization, not a verified compiler equivalence theorem.

Every primary benchmark analysis runs once in a fresh process with no retries.
This isolates solver contexts: long sequential mixed-theory runs can change
timeout behavior even for equivalent fresh-symbol queries. The individual query
limit remains 5000 ms. Concrete primary samples replay the **actual certified**
return expression using saved parameter symbol bindings, source hash and domain
checks. They do not reconstruct and independently reprove a different model.
Unknown/stale/mismatched certificates and out-of-domain samples are rejected.

## Reproduction

```sh
python -m pytest -q --forked tests/test_external_call_frontiers.py
python scripts/check_llvm_builtins.py --compare-baseline --output experiments/v038/upstream.json
python scripts/run_v038_experiments.py
python -m llmloop.symbolic_cli examples/clang_unreachable_external.c --c-clang-proof --function entry --clang-proof-config '{"backend":"calls"}' --parameter-bounds '{"x":[0,1000]}' --inputs '{"x":100}'
```

See [frozen-source results](../experiments/v038/report.md). Reachable external
contracts, union storage/type punning, builtin/helper closure, general heap
graphs/aliases/ownership and arbitrary branch discovery remain open. A remaining
64-bit popcount functional timeout is still UNKNOWN. This work neither implements
complete C/LLVM semantics nor adds KLEE.
