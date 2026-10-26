# Clang scalar AST to typed proof kernels (v0.28)

The `clang_proof` frontend goes beyond compiler readiness. It consumes one real
Clang function AST, normalizes an admitted scalar fragment to typed C, then runs
an existing independent typed proof kernel. It does not interpret LLVM instruction
semantics or run KLEE. The Clang compiler and the structural normalizer are trusted
frontend components; this is not a machine-checked compiler-equivalence theorem.

## End-to-end project example

```
python -m llmloop.symbolic_cli examples/clang_proof_project/count.c \
  --c-clang-proof --function clang_count \
  --clang-config '{"compilation_database":"examples/clang_proof_project"}' \
  --clang-proof-config '{"backend":"nested"}' \
  --parameter-bounds '{"n":[0,1000000]}' --inputs '{"n":1000000}' \
  --output proof.json
```

Clang resolves the header's `Counter` typedef and compilation database's STEP=5.
The nested backend automatically proposes a trajectory and independently proves
original normalized typed operations, range, successor, exit and return obligations.
The return for n=1000000 is 5000000. The proof covers every declared input, not only
that evaluation point, and does not unfold a million iterations. See the
[actual proof export](../experiments/v028/clang_proof_demo.json).

API requests use exactly one `source` or `source_file`, `frontend:"clang_proof"`,
optional `function`, compiler options under `clang`, and proof options under `proof`:

```python
from llmloop.api import analyze_request
r = analyze_request({
    "source": "int entry(int n){return n+2;}",
    "frontend": "clang_proof", "function": "entry",
    "proof": {"backend": "cfg", "parameter_bounds": {"n": [0, 100]},
              "inputs": {"n": 3}}
})
```

Compiler project options use the [Clang adapter contract](CLANG_ADAPTER.md).
`include_ast` must remain true. CLI `--clang-proof-config` accepts the proof JSON;
explicit CLI bounds/inputs and nondefault step/path budgets override those fields.
The ABI and plain-char signedness come from the Clang target/configuration,
not the legacy `--abi`/`--char-unsigned` switches.

## Backends and result states

| proof.backend | Kernel | Success state | Boundary |
| --- | --- | --- | --- |
| cfg (default) | TypedCFGHeap scalar CFG execution | PROVED_DEFINED_CLANG_SCALAR_CFG | All paths return within max_steps/max_paths |
| nested | TypedCNested induction and optional candidate synthesis | PROVED_DEFINED_CLANG_SCALAR_NESTED | Admitted counted loops and source domain; no per-iteration unfolding |
| recurrence | TypedCRecurrence candidate induction | PROVED_DEFINED_CLANG_SCALAR_RECURRENCE | Supplied closed_forms for one canonical counted loop |

Proof options are `backend`, `parameter_bounds`, `inputs`, `max_steps`, `max_paths`,
`closed_forms` and `loop_summaries`. Kernel-specific options must match the selected
backend. For nested, omitted summaries default to `auto`; supplied summaries retain
the existing entry-relative formula convention. Recurrence requires supplied
formulas. See existing typed-kernel contracts for exact loop/candidate limits.

The nested `clang_frontend` result still says CLANG_FRONTEND_READY/NOT_PROVED,
because compiler ingestion alone proves no runtime property. Only the top-level
proof status/certificate describes the subsequent checked scalar program. A timeout,
wrong formula, unsupported AST/ABI, incomplete CFG, undefined operation or input
outside the domain returns UNKNOWN. No prefix or compilation success substitutes
for a safety certificate.

## Normalization contract

The admitted source has scalar integer parameters/return/automatic locals and
supported integer expressions, assignments, if/switch, for/while/do, early return,
goto, break and continue. Typedefs/macros/includes are resolved by Clang, rather
than reparsed as unresolved names. Integer/character literals retain compiler types
and appropriate suffixes. Integral promotions/narrowing/boolean casts remain explicit
or are performed by the identical typed declaration assignment context; explicit
C casts remain in the emitted expression. Lvalue-to-rvalue/no-op wrappers do not
add a new C operation. Unevaluated scalar `sizeof` is emitted as `sizeof(type)` and
never executes its operand. Short-circuit and conditional evaluation remain lazy.
Original arithmetic is not replaced with a folded trajectory or sample result.

Declaration identities, not spellings, resolve local references. Shadowed locals
are alpha-renamed, while entry parameters retain their input names. Labels have a
separate mapping. Counted-summary backends currently reject renamed/shadowed local
sets rather than guessing formula-name bindings. Scalar declarations need an
initializer; volatile/atomic/static/thread-local storage and declaration attributes
are unsupported. Canonical-loop syntax is checked on the emitted typed source.

The current ABI contract admits x86-64 Linux GNU/musl LP64, x86-64 Windows GNU/MSVC
LLP64 and i386-family Linux GNU/musl ILP32 targets, with the existing explicit
integer-kernel implementation choices. ARM and x32 are refused even if Clang can
compile them. Pointers, arrays/VLA, record values, calls, globals, floating point,
GNU statement expressions, nested side-effecting expressions, and variadics remain
outside this proof bridge. These may still be ingested by the separate Clang
frontend, or handled by an existing restricted handwritten memory/call frontend.

Each proof export contains the full Clang ingestion result, normalized source,
AST/source hashes, selected kernel/ABI, alpha-renaming map and its checked
obligations. `compiler_equivalence_machine_proved:false` explicitly records the
trusted translation boundary. Included headers/environment must remain stable
during compiler stages as required by the adapter. The certificate is for that
captured typed AST and emitted program/domain, not an arbitrary future on-disk
revision. Native three-way checks supplement this contract; they are not a universal
translation-equivalence proof.

## Experiments and outstanding work

The new tests cover three target data models, narrowing, unsigned-char mode,
shadowing, lazy division, unevaluated increment, switches/goto/continue, million-count
recurrence and nested induction, modular byte wrap, two-level nesting and real
header/database input. Wrong trajectories, overwritten intermediate overflow,
division by zero, infinite/over-budget CFGs and unsupported AST nodes fail closed.
The native oracle compares original C, normalized C and the proved model at GCC
-O0/-O2, including million-iteration evaluations. It separately requires expected
UBSan diagnostics for intentional proof-rejected overflow/division cases.

See [v0.28 evidence](../experiments/v028/report.md) and results.json. Frontend-only
Clang acceptance and scalar proof certificates have separate counters. These are
controlled regressions, not representative library coverage or a speedup claim.

This phase does not complete arbitrary C coverage. General LLVM/memory/call
normalization, KLEE execution with matching LLVM/runtime dependencies, unbounded
heap shape summaries, arbitrary branching closed-form synthesis and unrestricted
CFG/recursive termination remain outstanding. No KLEE execution was reported or
counted in this phase; the execution environment had no KLEE executable/package.

### Reproducible solver-context isolation

The expanded monolithic pytest run exceeded its former 600-second aggregate budget
and failed an existing cubic-prefix check. The 38 affected counter-phase/memory
regressions passed with fresh per-test processes and unchanged assertions/query
budgets. The final protocol therefore uses `pytest --forked` on POSIX and a fresh
Python/SMT context for every API fixture. Install the updated `.[test,smt]` extra.
The aggregate pytest allowance is 1200 seconds for the enlarged isolated suite;
individual typed obligations remain 5 seconds and legacy graph queries 10 seconds.
API experiment processes have a 60-second cap. Limits and failures remain explicit:
no timeout is a safety certificate. This isolation is an experiment protocol, not
a guarantee that every request sequence in a long-lived service has the same
solver performance. No runtime speedup is claimed.

### Exact candidate range enclosures

A cold-start cubic-prefix regression still timed out on its signed-64-bit candidate
range obligation. The typed recurrence checker now first attempts an exact rational
interval certificate for labels ending in `range`. It derives integer-variable
bounds only from conjunctive premises, propagates finite bounds, and encloses
supported polynomial/conditional/floor/positive-division/modulo expressions.
Unsupported, contradictory, unbounded or insufficient enclosures fall back to SMT.
Certificates and their derived boxes are recorded on the range obligation. This
is a mathematical enclosure proof, not a sampled estimate or a range assumption;
independent SMT-domain tests validate the enclosure rules and unsafe/unbounded
negative controls refuse certificates. Original source definedness, base,
successor and exit obligations are retained. No solver timeout is reclassified as
proof. The interval routine is an additional trusted proof component, not a
machine-verified theorem prover.
