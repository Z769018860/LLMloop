# Closed bounded recursive calls (v0.23)

The direct-call CFG frontend now has opt-in bounded recursion. It unfolds direct
self/mutual calls to the configured depth and places a failing analysis obligation
at every unexpanded call frontier. Certification requires those frontiers to be
unreachable for every parameter/allocation execution in the declared domain.
A frontier is never a successful, zero-valued or unconstrained return summary.

```sh
python -m llmloop.symbolic_cli examples/typed_recursive_calls.c \
  --c-typed-cfg-calls --function recursive_heap --allow-recursion \
  --max-call-depth 4 --max-steps 512 --max-paths 64 \
  --parameter-bounds '{"n":[0,3]}' --inputs '{"n":3}'
```

The example allocates in a recursive base case, returns the same heap object
through surviving frames, and adds the current argument through aliases. Under
successful allocation it returns 6; failure propagates to -1. Default output
preserves allocation dependence. Successful-allocation assumptions remain an
explicit separate option.

The API uses the existing `typed_cfg_calls` frontend with `allow_recursion: true`.
The default remains false, preserving the previous rejection of recursive call
graphs. `max_call_depth` bounds helper frames beyond the selected root; a
recursive root can also call itself. The full CFG step/path/object budgets still
apply across all expanded frames.

## Why a finite expansion can certify complete execution

Every admitted call before the boundary keeps original operations, argument and
return conversions, parameter copies, shared object identities, and frame exit
lifetimes. At the boundary, a unique marker represents an obligation that no
execution can reach that call. If the marker is reached, verification immediately
returns `UNKNOWN` with `analysis_limit: "call_depth_frontier"` and a parameter
witness when available. A failing marker also remains in the expanded analysis
source, so analyzing that source through the base heap frontend fails closed.

A successful complete-exit proof has covered all paths, preserved all original
safety obligations and excluded every marker. Therefore no actual call for that
input/allocator domain lies outside the expansion. The certificate records
`bounded_recursion_enabled`, `depth_frontiers`, and
`all_frontiers_proved_unreachable`. This is finite domain closure, not a ranking
argument, a recurrence closed form, or arbitrary unbounded-recursion induction.

For a helper called initially with n=3 that decrements to a base case n<=0,
helper depth 4 can close all calls; depth 2 remains unknown. Ignoring a recursive
result, returning constant zero afterwards or wrapping a narrow argument does
not make a reachable frontier safe. A larger domain can require more depth and
may exceed the independent resource caps.

## Types, declarations and limits

Recursion uses the v0.22 explicitly sequenced call positions, pure arguments and
integer/pointer signature restrictions. Matching internal forward prototypes
are now accepted to express well-typed mutual recursion. Every prototype must
have an available definition and the same conservative declarator shape;
parameter names are ignored. This is narrower than all C-compatible declaration
forms. Unmatched/external prototypes, globals and typedefs remain unsupported.

Existing limits include 1..8 helper depth, 16 expanded non-frontier call sites,
32 frontier markers, 16 definitions/arguments, and the finite source/CFG/heap
budgets. Branching recursion can exhaust the static site budget even when some
calls would be unreachable. No nodes or branches are silently truncated into a
certificate. Recursive frame arrays stay distinct; callee frees remain visible
to surviving frames, and returned pointers into expired frames are rejected.
Allocation failure remains nondeterministic by default.

General recursive summaries, linked/struct heap graphs, arbitrary nested
expression calls, external pointer inputs, indirect calls, and unbounded CFG or
recursion proofs remain outstanding. These are restricted complete-exit proofs.

## Independent evidence

The [v0.23 experiment report](../experiments/v023/report.md) includes original
recursive C/UBSan oracles for sum, factorial, parity through mutual recursion,
branching Fibonacci, recursive root entry, unsigned-char parameters, independent
stack frames, void alias updates and recursive heap-pointer returns. Native code
uses real recursion, not the verifier's expanded source. Both successful and
forced-failure calloc configurations are compared. Separate ASan/UBSan
subprocesses confirm recursive-free UAF and an intermediate signed overflow.
These two controls are expected fault correspondences rather than safe runs.

Proof controls retain insufficient-depth, large-domain, byte-wrap, ignored-result,
dangling-frame, prototype-mismatch and actual fault rejections. ABI proof cases
cover LP64, ILP32 and LLP64; native execution uses LP64. No universal-C,
representative-library or performance claim is made.
