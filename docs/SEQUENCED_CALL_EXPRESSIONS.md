# Sequenced direct-call expressions (v0.33)

The `typed_cfg_calls` frontend and Clang `calls` backend extend the original
[single eager call contract](EAGER_CALL_EXPRESSIONS.md). They still prove
bounded complete exits over finite typed memory, rather than unbounded loop or
recursive summaries. Standard allocation failure and every reachable source
operation remain checked. No compiler-success or purity result is a safety proof.

```sh
python -m llmloop.symbolic_cli examples/clang_sequenced_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"calls","max_steps":512,"max_paths":64}' \
  --parameter-bounds '{"n":[-2,8]}' --inputs '{"n":4}'
```

The example returns 42 for `n=4`. Its condition helper also updates a counter,
including the final false test. `continue` still executes the increment helper.
The conditional selects one heap-update helper; the logical expression skips
its right operand for zero input; the nested scalar arguments retain their
parameter conversions.

## Supported evaluations

| Context | Expansion rule | Main condition |
| --- | --- | --- |
| `a && f()` / `a || f()` | Snapshot the left truth value; execute the right prefix only in the selected branch | Original lazy arithmetic/memory checks remain guarded |
| `a ? f() : g()` | Snapshot the condition; conditionally execute one call prefix; retain the typed conditional value expression | Both arm result types and usual conversions preserved |
| `f(g(n))` | Evaluate the inner call before binding outer formals | One active argument with stable scalar siblings, or independent pure scalar argument expressions |
| `f(n)+g(n)` | Choose one witness order only after checking independence | Scalar-only pure callees and stable operands/arguments |
| `f(),g()` | Execute discarded left expression, then right expression | Comma operator is distinct from argument separators |
| Loop condition/increment | Execute prefix at its actual loop phase | Complete-exit, step, path, heap and call budgets still apply |
| Discarded lazy/cast expressions | Observe all original operations before discarding value | No arithmetic definedness checks removed |
| Scalar `x += f()` and other scalar compound assignments | Keep original compound arithmetic after the call prefix | Identifier target whose value cannot be changed by callee aliasing |

Clang normalization also retains comma operators and discarded conditional/cast
statements, including `(void)helper()`. General assignment/increment expressions
inside Clang operands remain unsupported. The direct normalized-C route admits
sequenced statement increments before a later comma operand; it does not infer
an order for side-effecting function arguments.

## Lazy prefixes and type preservation

Generated selector integers store only a condition's truth value, before any
selected helper can mutate condition memory. The helper result slots retain
their declared integer or pointer types. Generated result/selector declarations
needed outside a branch are exposed at the containing scope; their original
evaluations and return-completion guards stay inside the selected arm. Zero
initializers for inactive result slots do not assert that skipped helpers ran
or returned normally.

The conditional value remains a C conditional AST over the original typed
values, rather than an arbitrary `int` result temporary. This retains common
signed/unsigned conversions even for the unselected arm's type. Callee return
narrowing, explicit caller casts and original arithmetic intermediates remain
in the receiving typed kernel. Every nonvoid helper still needs a checked return
under the project's existing conservative complete-return contract, including
when its result is discarded.

## Independence of unordered operands

A syntactic greatest-fixed-point analysis identifies scalar-only call graphs
without memory observations, pointer parameters/locals, array/record accesses,
address-taking, global/static storage, builtins or unavailable external calls.
All dependencies must satisfy the same condition. Local scalar updates and
recursive scalar dependencies may be included. Recursive execution still needs
explicit opt-in and proof that every depth frontier is unreachable.

This property establishes no arithmetic or termination result. The original
expanded body is checked for overflow, division/shift validity, initialization,
returns and complete exits. Unsafe pure functions therefore remain UNKNOWN.
The receiving frontend excludes global state and scalar-address aliasing, so
the admitted stable caller scalar reads cannot be changed by these callees.

For a nested call in one argument, every other argument must be a stable scalar
expression. Multiple active arguments require pure scalar expressions throughout.
An effectful call beside a memory read, another effectful call, an increment or
a pointer-valued sibling is refused. Such a C source can be valid; refusal means
the engine has not established independence across every permitted order.

## Loop continuation and function boundaries

Call-bearing loop headers become checked `while` witnesses with a test prefix
at each original evaluation point. A `for` has an explicit continuation label
before its increment; a `do` has one before its post-body condition. Only
`continue` statements belonging to that loop are redirected; nested loops keep
their own continuation targets, including continues inside switches. Breaks,
original returns/gotos, helper frame exits and automatic-object lifetime edges
remain in the CFG.

Original function context is checked before expansion. A helper cannot borrow
the caller's loop to legitimize an invalid `break`/`continue`, or capture an
undeclared caller variable by name. Unsupported function/prototype specifiers
such as `_Noreturn` require a separate contract and are refused. Existing local
shadowing, pointer, qualifier and declaration restrictions remain in force.

## Evidence, metadata and remaining limits

`call_model` records the pure-function set, expression/loop expansion events,
expanded C and SHA-256, bounded call sites and recursion frontiers. Clang's
normalization provenance remains separate. `source_equivalence_machine_proved`
is false: the structural lowering and proof kernels are trusted implementation
components, not a machine-verified compiler theorem.

The 16 expanded-site, 8-object/64-cell and existing CFG/solver limits are
unchanged. Administrative witness nodes count toward the CFG budget. There is
no unknown frontier treated as a neutral return. General unordered aliasing
effects, arbitrary C evaluation contexts, complex memory lvalue call stores,
aggregate initializer calls, external/indirect calls, unbounded recursion,
arbitrary heap summaries and general closed-form discovery remain open.
Direct `sizeof(call())` is refused without evaluating the call; the Clang route
can already normalize ordinary static `sizeof` from the compiler's operand type.

```sh
python -m pytest -q --forked tests/test_sequenced_calls.py
python scripts/check_sequenced_calls_native.py --output experiments/v033/native.json
```

Native checks compare original C, Clang-normalized C, expanded witness C and an
independent expected-result/model pair with GCC `-O0`/`-O2` and UBSan. Counters
expose invocation order/counts and allocation/free effects. Separate active
overflow/division controls require UNKNOWN plus actual UBSan failure. Native
evidence is LP64; ILP32 and LLP64 use compiler/SMT tests. See the
[experiment report](../experiments/v033/report.md).

The sequencing rules follow WG14's
[C11 committee draft N1570](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf),
sections 6.5.2.2, 6.5.13–6.5.15, 6.5.17, 6.8.5 and 6.8.6.2. No general
left-to-right operand order is assumed. KLEE is not integrated.
