# Single eager direct-call expressions (v0.24)

This records the original v0.24 contract. The v0.33
[sequenced expression extension](SEQUENCED_CALL_EXPRESSIONS.md) supersedes the
lazy/nested/multiple-call, cast, comma and loop-header exclusions below under its
explicit sequencing, purity and bounded-complete-exit conditions.

The `typed_cfg_calls` frontend accepts a single direct helper call inside an
arithmetic/comparison expression used by a return, declaration initializer,
simple `=` assignment, `if` condition or `switch` selector. For example:

```c
int factorial(int n) {
    if (n <= 1) return 1;
    return n * factorial(n - 1);
}
int recursive_expression(int n) { return factorial(n) + 2; }
```

```
python -m llmloop.symbolic_cli examples/typed_recursive_expression.c \
  --c-typed-cfg-calls --function recursive_expression --allow-recursion \
  --max-call-depth 4 --max-steps 512 --parameter-bounds '{"n":[0,4]}' \
  --inputs '{"n":4}'
```

The return is 26. This is a bounded complete-exit proof for the specified input
domain, with unreachable recursion-depth frontiers; it is not recursive induction.

## Expansion contract

Only one call may occur in the entire expression. Outside that call the admitted
syntax is integer/character constants, scalar local/parameter identifiers,
unary `+ - ~ !`, and eager binary operators. Each identifier must be declared as
a scalar in the input inventory and never declared as a pointer/array elsewhere
in that inventory (a conservative name-collision restriction). Hygienically
renamed helper scalar locals and parameters are also tracked. The existing
frontend excludes globals and scalar-address aliasing, so a helper cannot change
these sibling scalar values. It can change pointed-to integer cells, which are
therefore excluded from sibling operands.

The helper runs in a fresh frame with the existing argument, typed return,
initialization, allocation, lifetime and return-completion checks. Its result slot
has the helper's declared type, so narrowing happens before the surrounding
arithmetic. Every original arithmetic node remains in that surrounding expression
and retains its intermediate overflow/undefined-operation obligation. Conditions
execute the call once before branching or selecting a switch label. Loop-body
calls still execute on every reached iteration.

The contract rejects memory reads (`*p`, `a[i]`), pointer-valued sibling identifiers,
`&&`, `||`, ternaries, `sizeof(call())`, casts containing calls, multiple sibling
calls, nested argument calls, and side-effecting arguments. A whole-call builtin
allocation expression retains the existing heap rules. Calls in loop conditions
and increments remain unsupported: hoisting them once would change execution.
Calls in an array initializer list and compound assignment also remain unsupported.

The native oracle compiles the **original** source with UBSan at both `-O0` and
`-O2`. It includes recursion, if/switch control, result narrowing and a deliberately
invalid intermediate overflow. Finite native comparisons supplement the symbolic
checks and do not establish general C coverage.
