# Original typed CFG and dynamic finite heaps (v0.21)

`typed_cfg_heap` is an independent bounded exhaustive verifier, separate from the
unbounded compositional trajectory frontends. It executes the original AST
through a CFG without synthesizing a branch schedule or replacing a general
state recurrence with a guessed closed form. A successful certificate proves
that every execution in the declared parameter and allocator domain returns
within the configured budgets and that all executed integer/memory operations
are defined under the selected ABI and implementation choices.

```sh
python -m llmloop.symbolic_cli examples/typed_cfg_heap.c \
  --c-typed-cfg-heap --parameter-bounds '{"n":[1,3],"select":[0,2]}' \
  --max-steps 128 --inputs '{"n":3,"select":1}'
```

The example allocates a variable-length array, saves an alias outside the
allocation's lexical block, branches through a `switch` in a `do` loop, jumps to
a cleanup label and frees the saved base. Failure returns -1; successful
allocation returns 11 for these inputs. Default evaluation reports allocator
dependence instead of pretending the return is one deterministic integer.

The JSON API accepts `frontend: "typed_cfg_heap"`, `max_steps` (default 128),
`max_paths` (default 48), `allocation_failure` (default true), the existing ABI,
parameter bounds and optional concrete inputs. CLI `--assume-allocation-success`
sets `allocation_failure: false` explicitly. That assumption appears in the
report; it is never silently inherited from the older memory frontend.

## What is implemented

- State-dependent scalar updates and branches are executed exactly within the
  finite complete-exit domain, including mutable parameters. No counter-only,
  periodic or additive-update restriction applies to this route.
- `if`, `for`, `while`, `do/while`, early returns, `break`, `continue`, flat
  `switch` case/default with fallthrough, and forward/backward `goto` are lowered
  to original-operation CFG instructions. `continue` preserves the appropriate
  for-loop increment; `break` exits the nearest loop/switch.
- Typed integer arrays and same-element-type mutable pointers support aliases,
  pointer increments/rebinding, variable-length malloc/calloc extents, multiple
  dynamic instances of one allocation point and heap aliases that outlive a
  declaring block. Object identity is distinct from pointer-variable identity.
- Lexical-scope exit, including goto/break/continue edges, invalidates automatic
  arrays and removes local names. Heap object state remains alive independently
  of local aliases until free. Dangling stack aliases and use after free are
  rejected. Initialized-cell flags are tracked separately from cell values.
- Allocation failure is fresh nondeterminism at each executed allocation.
  Callee argument conversions to size_t are modeled. A calloc product that
  cannot fit size_t forces failure, rather than inventing a wrapped successful
  allocation. Only calloc calls with matching integer element size are handled;
  malloc extents use the actual converted byte count divided by element size.
- Actual typed guard arithmetic, conversions, intermediate overflow, lazy
  boolean/ternary evaluation, addresses, bounds, initialization, base-only free
  and liveness feed guarded proof obligations. Observed faults remain obligations
  even if later source statements discard their computed values.

The frontend expects the same parser-oriented source fragment as the other C
frontends: integer types and modeled allocator names without preprocessor
headers or allocator redeclarations. Native tests prepend standard headers and
compile the original function bodies. It does not call external functions or
model arbitrary typedefs, qualifiers, pointer-to-integer casts or pointer cells.

## Completeness and budgets

`PROVED_DEFINED_TYPED_C_CFG_HEAP` requires all reachable paths to return and all
original-operation safety obligations to hold. A remaining path at `max_steps`
is `UNKNOWN`, not a bounded-prefix safety certificate. SMT unknown/timeout and
resource exhaustion also return `UNKNOWN`. Solver obligations retain a 5-second
limit; the experiment runner's aggregate pytest allowance is 600 seconds as the
suite grows. Increasing that suite allowance does not change proof limits.

Limits are 1..512 CFG steps per path, 1..64 paths, 512 CFG nodes, source AST
4096 nodes/depth 64, 8 represented object instances, 8 cells per object and 64
cells total. Allocation instances remain distinct even after free. The limits
are finite representation budgets, not a claim about physical allocation
capacity or a general heap-shape abstraction.

Pointer equality is supported for null, same-object offsets and strict interior
positions of distinct live objects. Distinct objects can be adjacent at a
one-past boundary, so such comparisons are rejected instead of assuming that
synthetic object IDs imply unequal addresses. Pointer ordering/subtraction,
external pointer parameters, pointer-valued heap cells and structs are outside
the model. Escaping means across local lexical blocks in one scalar-returning
function, not arbitrary interprocedural or pointer-returning escape.

This route proves no general closed-form recurrence, no general unbounded-loop
termination, no leak freedom, no recursion or linked heap graph, and no full C
coverage. The earlier unbounded summary routes remain available for their own
supported fragments. General branch recurrence synthesis, heap-shape summaries
and arbitrary unbounded control flow therefore remain outstanding.

## Evidence

The [v0.21 experiment report](../experiments/v021/report.md) retains all earlier
checks and adds ABI proofs for combined dynamic-heap/CFG and state-branch cases.
The native oracle runs successful allocation and deterministic allocation-failure
builds over the same original function bodies. Failure builds replace allocator
results only. Three deliberate UAF, dynamic-bound and signed-overflow controls
run in separate ASan/UBSan subprocesses; they are expected fault correspondences,
not safe executions. Unit controls also cover mixed allocator outcomes, scope
exit, null short circuit, type preservation in an unexecuted null leaf, ambiguous
adjacent-pointer comparison, missing return and resource rejection.

These remain controlled examples rather than representative real-library
benchmarks. There is no performance or universal C claim.

## Existing fractional-prefix stability correction

The first full v0.21 run exposed a timeout in the earlier unscaled cubic-prefix
unit, although all native suites and proof/control fixtures passed. This was
not accepted as a passing regression. The final implementation normalizes SMT
floor-polynomials exactly: split rational coefficients into an integral
polynomial Q and residual R, prove their polynomial reconstruction identity,
and use floor(Q+R)=Q+floor(R) for integer atoms. Successive prefix expressions
then share the same residual floor and cancel algebraically. Negative-argument,
real-atom rejection, source-renaming and universal affine-equivalence controls
cover the transformation. Conservative degree, term, denominator, AST and bit
budgets skip normalization when the fragment is unsupported. Original C safety
conditions are constructed first and remain in the obligations. No timeout is
waived and no overflow semantics are changed by this logical normalization.

## v0.25 pointer storage extension

The bounded frontend now also admits finite typed pointer cells and up to three
levels of integer-pointer indirection. Earlier integer-element-only restrictions
are superseded for the [pointer-cell fragment](TYPED_POINTER_CELLS.md). Structs,
external roots and general heap shapes remain unsupported.

## v0.26 record graph extension

The bounded heap model now admits allocated single named records with typed
integer/pointer members and finite linked/cyclic graphs. Earlier blanket struct
restrictions are superseded only for [this fragment](BOUNDED_STRUCT_HEAP.md).
