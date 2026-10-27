# Clang memory and direct-call proof bridge (v0.30)

The finite-kernel contracts below remain unchanged. A separate `list` backend
adds [inductive fresh-list summaries](UNBOUNDED_LIST_HEAP.md) without the finite
represented-object cutoff for its admitted builder/fold/free normal form.
A separate `list_calls` backend adds
[checked builder/caller/consumer ownership composition](INTERPROCEDURAL_LIST_HEAP.md)
for that shape fragment; it does not relax the finite `calls` backend's limits.

The `clang_proof` API adds two backends to the existing scalar bridge. The
compiler resolves macros, headers, typedefs, implicit integer conversions and
record layouts. A structural normalizer then emits admitted typed C for an
existing proof kernel. Clang and the normalizer remain trusted components;
this is not a verified compiler or an LLVM/KLEE interpreter.

| `proof.backend` | Kernel | Success status | Scope |
| --- | --- | --- | --- |
| `memory` | `typed_memory` | `PROVED_DEFINED_CLANG_FINITE_MEMORY` | Counted nested-loop induction over finite integer cells; no iteration-count unfolding |
| `calls` | `typed_cfg_calls` | `PROVED_DEFINED_CLANG_CFG_CALLS` | Complete-exit bounded CFG, direct helpers, finite typed pointer/record heaps and optional bounded recursion |

## Run the linked-heap example

```sh
python -m llmloop.symbolic_cli examples/clang_heap_calls.c \
  --c-clang-proof --function entry \
  --clang-proof-config '{"backend":"calls","max_steps":256}' \
  --parameter-bounds '{"n":[0,100]}' --inputs '{"n":7}'
```

Both allocation sites may fail. The model returns `-1` for the first failure,
`-2` for the second failure and `2*n+1` if both succeed. A returned allocation
survives its helper frame; returned stack objects expire. A certificate checks
all modeled allocation outcomes and complete exits within the configured
budgets. It does not prove leak freedom or unbounded heap shapes.

An unroll-free static-array request is:

```python
from llmloop.api import analyze_request
r = analyze_request({
    "source": "int entry(int n){int a[2]={1,2};for(int i=0;i<n;i++){a[0]+=2;}return a[0]+a[1];}",
    "frontend": "clang_proof", "function": "entry",
    "proof": {"backend": "memory", "parameter_bounds": {"n": [0, 1000000]},
              "inputs": {"n": 1000000}}
})
```

This proves the declared domain and evaluates to `2000003`, using automatic
candidate synthesis followed by original normalized-source obligations.
`loop_summaries` may also contain supplied candidates. The receiving finite
memory kernel retains its existing successful-allocation assumptions. This is
separate from the failure-aware `calls` backend.

## Admitted syntax and checks

One-dimensional integer/data-pointer arrays have 1..8 constant cells. Clang's
semantic initializer order and zero filler are retained, including supported
designated initializers. Pointer declarations, indexed/dereferenced stores,
known aliases, pointer tables, null tests, same-type pointer casts and allocator
result conversions connect to the receiving kernel. Physical address casts and
pointer reinterpretation remain unsupported. Integer narrowing and evaluated
intermediates are retained; algebraic cancellation does not remove overflow.

The call backend collects up to 16 reachable direct definitions, emits matching
prototypes, and uses the existing hygienic frame expander. Its existing eager
call-frame and finite-heap restrictions still apply. The
[sequenced expression extension](SEQUENCED_CALL_EXPRESSIONS.md) now admits lazy
branches, comma evaluation, nested argument calls, loop headers and independent
pure sibling calls. Unordered observable sibling effects, arbitrary nested
assignment/increment expressions, external functions without contracts,
function pointers and external pointer layouts are refused. `max_steps`, `max_paths`,
`max_call_depth` and `allow_recursion` are proof options. Recursion needs explicit
opt-in and every depth frontier must be proved unreachable.

Only literal main-file pointer parameter declarators are currently admitted.
The raw spelling in every original declaration, including forward prototypes,
must resolve to the same pointer type. Array/VLA parameter
declarators and macro/header pointer-parameter spellings are refused because
Clang's adjusted pointer type omits array-entry evaluations and `static` minimum
length requirements. Scalar header-defined helpers remain subject to the
ordinary AST checks. A rejection is explicit `UNKNOWN`.

`malloc`, `calloc` and `free` use the existing standard-library contracts. Their
Clang declarations must match the target ABI signatures; user-defined bodies,
assembly-name redirection and unsupported attributes are refused. The host is
responsible for linking the standard functions. Allocation failure is enabled
by default in `calls`; `allocation_failure:false` is an explicit assumption.

Named allocated records may contain integer or typed-pointer fields, including
links and bounded cycles already admitted by the kernel. Only needed record
definitions are emitted. Bitfields, packed/aligned/attributed records, embedded
records and record arrays are refused. Before reporting success, compiler and
model sizes, alignments and every field offset must agree. Results record this
correspondence. Pointer-cell initialization/lifetime checks remain mandatory;
zero bytes from `calloc` do not silently establish typed null pointer cells.

The inherited bounded kernel represents at most 8 object instances, 8 cells per
object and 64 total cells. The `memory` and `calls` backends have different
contracts: a complete bounded execution is not an unbounded acceleration proof.
Arbitrary branching closed forms, unrestricted control flow/recursion and
unbounded escaping heap summaries remain open. No KLEE backend was added.

## Reproduction

```sh
python -m pytest -q --forked tests/test_clang_memory_proof.py tests/test_clang_proof.py tests/test_clang_adapter.py
python scripts/check_clang_memory_native.py --output experiments/v030/native.json
python scripts/check_clang_proof_native.py
```

The native check compares original C, normalized C and the proved model at GCC
`-O0`/`-O2` with UBSan. A wrapper independently forces each allocation failure
position. These checks supplement the universal obligations and do not prove
translation equivalence. See [recorded results](../experiments/v030/report.md).
