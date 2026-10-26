# Clang memory, calls and owned-list summaries (v0.29)

Clang's typed AST now normalizes admitted memory and call operations into existing
checked kernels. A separate owned-list induction handles an escaping heap without
heap-instance unfolding. Branch discovery also supports Boolean counter schedules
and finite state-dependent control orbits. No KLEE dependency, adapter or execution
is included.

This is an expanded research fragment, not universal C coverage. Arbitrary shared
heap shapes, indirect/lazy/multiple calls, general CFG termination and arbitrary
branching closed-form discovery remain unsupported and return UNKNOWN.

## Compiler-to-kernel routes

Use `frontend:"clang_proof"` with the existing `clang` compiler/project options and
one of the following `proof.backend` values. Existing scalar cfg/nested/recurrence
backends retain their v0.28 scalar contracts.

| Backend | Checked kernel/result | Admission boundary |
| --- | --- | --- |
| memory | TypedCFGHeap / PROVED_DEFINED_CLANG_MEMORY_CFG | Complete bounded CFG; finite integer/pointer arrays, aliases, dynamic allocation/failure and natural named allocated records |
| calls | TypedCFGCalls / PROVED_DEFINED_CLANG_MEMORY_CALLS | Same heap, typed direct-call parameters/returns, helper-returned heap and opt-in bounded recursion with every depth frontier unreachable |
| memory_nested | TypedCMemory / PROVED_DEFINED_CLANG_MEMORY_NESTED | Existing finite local memory/static aliases plus counted induction; omitted loop_summaries defaults to auto |
| heap_summary | Owned-list rules plus independent TypedCNested arithmetic / PROVED_DEFINED_CLANG_OWNED_LIST_SUMMARY | Exact recognized constructor-returned owned list and consuming reverse payload fold; no heap-instance/iteration unfolding |

Example bounded pointer-returning helper:

```python
from llmloop.api import analyze_request
r = analyze_request({
    "source": """void *malloc(__SIZE_TYPE__);void free(void*);
      int *make(int n){int *p=malloc(sizeof(int));if(p){p[0]=n;}return p;}
      int entry(int n){int *p=make(n);if(!p){return -1;}
        int x=p[0];free(p);return x;}""",
    "frontend": "clang_proof", "function": "entry",
    "proof": {"backend": "calls", "parameter_bounds": {"n": [0, 100]},
              "inputs": {"n": 7}}
})
```

Allocation failure is modeled by default. Its return may be nondeterministic;
compilation or a successful branch alone never proves all allocations succeed.
`allocation_failure:false` is an explicit success assumption for memory/calls/list
backends, corresponding to CLI `--assume-allocation-success`. It is recorded in the
kernel or owned-list certificate. Physical memory capacity is never established.

Bounded memory/calls accept max_steps/max_paths and retain existing object/cell,
stack array (1..8), heap allocation (up to 8 represented elements), pointer depth
(3), record and path budgets. Calls additionally accept max_call_depth (1..8) and
allow_recursion; CLI --max-call-depth/--allow-recursion work with backend calls.
The call frontier must be universally unreachable. This is bounded call expansion,
not induction for arbitrary recursive procedures. memory_nested accepts the
existing loop_summaries/finite-memory contract; it does not inherit CFG failure
semantics or general dynamic aliases.

## Translation contract

Memory routes request `clang.include_dependencies:true` automatically. The adapter
exports function definitions and complete record declarations from the **same AST
invocation** as the selected entry. Export budgets are 128 functions/128 records;
the proof normalizer follows only direct reachable definitions, up to 16 functions,
and emits matching prototypes and needed named records. A supplementary Clang
AST pretty-print stage retains original definition parameter declarators: JSON
ParmVarDecl pointer types alone hide array/VLA evaluation and static minimum
contracts. Written array parameters are rejected; ordinary pointer parameters
remain supported. Parameter attributes, variably modified local typedefs and
attributed memory typedef aliases are refused. Natural record size, alignment and
field offsets must exactly match the compiler layout, including typedef alignment. Unrelated global objects
are not modeled; a reference to any global is rejected.

Declaration IDs resolve lexical locals independently in each function. Types are
canonical integers, up to three pointer levels, one-dimensional fixed arrays and
named records with admitted fields. Array decay, lvalue reads, literal null
conversions (including stdlib NULL), scalar assignment/common-type conversions,
sizeof, dereference, address formation, indexing and arrow-member operations retain
their C contexts. Explicit scalar casts remain. A redundant outer implicit scalar
RHS cast is omitted only when the identical assignment/common-type context performs
that conversion, as with declaration assignment conversions in v0.28.

Clang's semantic array initializer/filler is emitted with explicit zero slots;
designated constant positions are preserved. Implicit pointer value initialization
is a C null pointer, distinct from calloc's zero **bytes**, which the existing
kernel does not assume represent an initialized null pointer cell.

Standard malloc/calloc/free prototypes must match the target size_t/void-pointer
contract. C's implicit fresh-storage allocator conversion, explicit allocator
casts and literal-null casts are admitted. Other pointer reinterpretations,
integer/address casts, pointer-to-function calls, volatile/atomic/qualified memory,
VLA, packed/aligned/bitfield/union/by-value records and external calls are refused.
Standard allocator behavior is an explicit library-model assumption.

The ABI admission remains x86 Linux LP64/ILP32 and x86-64 Windows LLP64, with
compiler-selected plain-char signedness and documented integer implementation
choices. Unsupported target models still return UNKNOWN. Clang and the structural
normalizer remain trusted frontend components; native checks do not establish a
universal compiler-equivalence theorem or general LLVM semantics.

## Escaping owned-list induction

The real stdlib-header example and compilation database are in
`examples/clang_memory_project`. Run:

```sh
python -m llmloop.symbolic_cli examples/clang_memory_project/owned_list.c \
  --c-clang-proof --function entry \
  --clang-config '{"compilation_database":"examples/clang_memory_project"}' \
  --clang-proof-config '{"backend":"heap_summary"}' \
  --parameter-bounds '{"n":[0,1000000]}' --inputs '{"n":1000000}' \
  --output owned_list.json
```

The recognized constructor starts at null, iterates an int index from zero to n,
allocates exactly sizeof the record, returns its current root on failure,
initializes one integer payload and the self-pointer link, and publishes a fresh
head. The constructor returns that heap root to the selected consumer. The consumer
saves next and reads the payload before freeing the head, then advances to next.
Its only accumulator starts at zero and is returned. Every statement and field
must match this contract; a cycle, missing initialization, reordered free, extra
side effect or unknown mutation is refused.

The shape certificate records empty-list base, fresh disjoint cons, initialized
fields, acyclicity/exclusive ownership, escaping heap root, safe reads, consuming
free and decreasing length. These are **trusted checked syntax/ownership rules**
using standard abstract allocator freshness, not a machine-checked separation-logic
proof system. They do not prove physical address-space/allocation capacity.

If m allocations succeed before the first failure, 0 <= m <= max(0,n), the caller
consumes payloads in order m-1,...,0 and frees every owned node. There is no fixed
heap-object or loop-unrolling cap. C's int input range and declared input domain
still apply; “unbounded” means induction independent of concrete instance count.

Two separate scalar proofs are retained in full: construction count/index
arithmetic and the **reverse-order** payload fold. A fresh ghost m ranges over
[0,max(0,n_upper)]; this larger rectangular arithmetic domain may conservatively
reject valid programs. Payloads may read only the immutable count and construction
index. Fresh scalar names preserve identity even when constructor/caller spellings
collide. Original typed intermediates, payload conversions, accumulator narrowing,
all loop exits and return conversions must be proved. Samples or mathematical
sum formulas cannot hide signed intermediate overflow.

Default allocation-failure evaluation returns the possible prefix-length interval
and a symbolic return expression with its ghost SMT symbol. It does not fabricate
a deterministic sum. With explicit successful-allocation assumption, n=1000000
returns 499999500000 for payload i. This numeric evaluation does not execute or
allocate a million abstract objects in the prover.

## Branching closed-form candidates

The existing nested auto route adds two untrusted candidate generators:

* Disjoint Boolean interval/residue prefixes: nested if/else, sequential branches,
  &&/||/!, equality/inequality and constant-affine counter comparisons against
  immutable expressions; small counter-modulus schedules. Leaf increments must be
  additive, state-independent polynomials of degree at most 3. Guard effects and
  signed C remainder semantics are checked against original typed C, never assumed
  equal to the mathematical extractor's approximation.
* Finite state-dependent control orbits: control dependency closure is explored
  from concrete integer entries, with parameter/counter-independent control
  transitions. At most 32 mathematical states are explored; accepted prefix and
  period are at most 8 each. Other coordinates must have additive polynomial
  increments of degree at most 3. Whole-block and residue-tail sums yield candidates.

For example a control state visiting 0 -> 2 -> 5 -> 0 with increments i,2*i,3*i
returns 999998666667 after one million iterations. A one-step transient followed
by a two-state branch schedule is also covered. Neither exploration nor observing
a repeated state is a certificate. Original typed base, integrality/ranges,
executed intermediates, path coverage, **every** successor and actual exit/return
must pass. Narrow casts, wrong schedules and overflow controls remain UNKNOWN.

Boolean extraction is limited to 6 if nodes, 32 disjoint paths, residue lcm <=8,
128 interval/residue regions, existing expression/formula limits and a bounded
Boolean expansion. Finite-control successors can be proved by exhaustive integer
substitution k=p*q+r for every residue. Each subquery has the original 5000 ms
budget; at most 8 residues are attempted. Failed splitting falls back to SMT,
never a guessed schedule. Certificates expose all residue subcases.

General nonperiodic coupled feedback, nonlinear counter guards, unbounded control
exploration and arbitrary closed-form synthesis remain incomplete. Supplied
trajectories still use the existing general branch-wise verifier. A rejected
candidate or timeout is UNKNOWN; no completeness claim follows from these examples.

## Reproduction and evidence

Install `.[test,smt]` and a real Clang (tested with Ubuntu 18.1.3), then run:

```sh
python scripts/build_clang_memory_cases.py
python scripts/run_symbolic_experiments.py
```

The v0.29 manifest/report includes the full earlier regression suite and new
positive/negative controls. New native checks run each example in a fresh
interpreter and compare original C, normalized C and a separately checked model
at GCC -O0/-O2, using ASan/UBSan. Forced allocator budgets test all-success,
immediate failure and partial-list failure; explicit live-object accounting must
reach zero. LeakSanitizer is disabled because this execution environment denies its
/proc task scan. Deliberate use-after-free/out-of-bounds diagnostics are rejection
correspondences, not safe executions. These are controlled examples, not
representative real-library coverage or a speedup claim.
