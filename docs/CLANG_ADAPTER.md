# Clang C ingestion adapter (v0.27)

The `clang` frontend invokes a real Clang compiler for C preprocessing, parsing,
Sema/type checking, implicit conversions, target layouts and LLVM generation.
It does not use pycparser or the handwritten layout model to interpret this input.
This first integration uses the Clang driver and its JSON AST/layout dumps; it
is not a C++ LibTooling plugin and has not yet lowered general LLVM semantics
into the LLMloop proof engine. Existing proof frontends remain independently
available.

## Install and run

Install a Clang executable (for example `sudo apt install clang` on Ubuntu, or
an LLVM distribution for your platform). Python bindings alone are insufficient.
The adapter discovers `clang`, versioned clang-22 through clang-14, or
`LLMLOOP_CLANG`; an explicit `clang.executable` takes priority. Integration here
was tested against Ubuntu Clang 18.1.3. Other versions must pass the adapter's
integration checks; JSON/layout dumps and LLVM text are version-sensitive.

```
python -m llmloop.symbolic_cli examples/clang_project/demo.c \
  --c-clang --function clang_demo \
  --clang-config '{"compilation_database":"examples/clang_project/compile_commands.json"}' \
  --output clang_demo.json
```

The checked-in project includes a header, macro, typedef, record, union and VLA.
Its compilation database selects `BASE=7`; this setting is preserved, giving
returns n+9 for the tested nonnegative small inputs. The generated JSON contains
AST/source coordinates, compiler-owned layouts, target triple/data layout, LLVM
IR and basic-block edges. LLVM blocks include UBSan checks and must not be
counted as source-level MEMS reads/writes.

For an inline string:

```python
from llmloop.api import analyze_request
result = analyze_request({
    "frontend": "clang",
    "source": "int entry(unsigned char n) { return n + 1; }",
    "function": "entry",
    "clang": {"standard": "c11", "include_ast": True}
})
```

For an existing project file, use exactly one `source_file` instead of `source`.
The compiler runs in the matching compilation command's directory. If a source
has several entries, explicitly choose zero-based `clang.command_index`; the
adapter refuses an ambiguous configuration. `arguments` form is preferred.
POSIX `command` form is tokenized without a shell, so substitutions and shell
operators are never executed. Compiler launchers and Windows shell command
strings are not automatically interpreted; supply direct argument arrays.

## Result contract

`CLANG_FRONTEND_READY` means all compiler/export stages succeeded. It is **not**
a safety or termination certificate. `analysis_status` remains `NOT_PROVED`,
and overflow, memory safety, termination and unbounded-summary flags remain
false. A program with reachable signed overflow can compile successfully and
still receive this readiness state. Diagnostics, missing tools, unsupported
configuration, timeout or output-budget exhaustion return UNKNOWN.

Exports include:

- `compiler`, executed stage argv/cwd/diagnostics and source SHA-256;
- compilation database identity/hash, selected command and preserved/removed flags;
- function types and Clang JSON AST including implicit casts, ranges and macro locations;
- compiler record sizes, alignments and member offsets, plus the authoritative raw dump;
- LLVM target triple/data layout, textual IR/hash and basic-block successor graphs.

The AST is Clang's version-specific representation; opaque AST IDs are local to
that invocation. Layout summaries are parsed observations of Clang's dump, not a
new ABI calculation. Raw dumps retain complex/unnamed/bitfield information that
may not fit the convenience summary. Source coordinates are retained where Clang
emits them, including macro spelling/expansion locations; this is not yet a
complete source-MEMS-to-LLVM cost mapping.

## Compilation options

`clang` options are `executable`, `args`, `compilation_database`, `command_index`,
`working_directory`, `target`, `standard`, `timeout`, `include_ast`, `include_dependencies` and `sanitize`.
The database supplies the working directory, so do not combine it with an
explicit `working_directory`. Inline includes have the selected working directory
added as a quote-include fallback; use `source_file` for project-accurate file
context. Compiler environment/header trees must remain stable across stages;
only the main source is checked unchanged. These exports are not a hermetic build
certificate.

Admitted compiler flags include common defines/include/sysroot/target/C-standard
options, selected character/ABI flags, warning flags, PIC/PIE and optimization/debug
settings. Supplied optimization and PIC flags are preserved because they affect
predefined macros such as `__OPTIMIZE__`/`__PIC__`; only absent optimization defaults
to `-O0`. Default debug information is line tables unless a debug flag is supplied.
Target/standard options explicitly given in the adapter configuration override
the database via final command-line position. The reported target comes from LLVM,
not from inferring an ABI name in Python.

By default every frontend/export stage uses `-fsanitize=undefined` and
`-fno-sanitize-recover=all`. LLVM therefore contains available source-language UB
checks, including signed overflow. This is instrumentation, not a proof or a claim
that every C UB is checked. Sanitizer feature macros, where applicable, describe
this instrumented compilation in all stages. Set `sanitize:false` to ingest an
uninstrumented translation unit. Defined unsigned wrapping is not converted into
an unsigned-overflow safety obligation.

Build actions, output paths and dependency-file emission are removed. Unknown
semantic flags, plugins, response files and arbitrary driver forwarding are
rejected rather than silently dropped or guessed. In particular `-fwrapv` and
`-Ofast` require future explicit contracts. Extra input files, linker flags,
compiler wrappers and joined `-oFILE` outputs are not currently accepted.
The original compiler name in a database is recorded but never executed; the
configured Clang executable supplies the frontend.

The adapter executes compiler argv directly, writes only private stage outputs,
and never runs the compiled program. Resource limits are 1 MiB main source,
4 MiB compilation database, 256 compiler arguments, 250000 AST nodes, 128 exported
function definitions, 16 MiB AST/IR output and 1 MiB diagnostics per stage. Timeout
is 1..60 seconds per compiler stage (default 30). Hosts exposing this API still
own process/filesystem isolation and trust policy for compiler paths, source
includes and compilation configuration.

## Verification and next stage

Unit checks cover real macros/headers, typedefs, unions, packed/bitfield layouts,
VLA, implicit casts, three target data models, original diagnostics, compilation
commands, output suppression, flag preservation, timeout, API/CLI and readiness
versus proof. The native oracle compiles exported LLVM IR back to an object and
compares its results with original C at GCC `-O0`/`-O2`; intentional overflow and
VLA-bound failures exercise the IR's UBSan hooks. These are finite differential
tests, not universal semantic-equivalence proofs or real-library benchmarks.

See [v0.27 experiment results](../experiments/v027/report.md) and the committed
[actual project export](../experiments/v027/clang_demo.json). Full experiments
require a real Clang executable: the native oracle fails when it is missing,
instead of treating skipped integration as success.

Next work is certified normalization from typed AST/LLVM operations into the
SCC/summary proof interfaces, with source-cost mappings, and a separately bounded
KLEE backend. KLEE has not been invoked or integrated by this adapter. General
LLVM instruction/memory semantics, unbounded heap summaries and arbitrary
recursive/branching closed-form proofs remain incomplete.

References: [Clang tooling interfaces](https://clang.llvm.org/docs/Tooling.html),
[compilation databases](https://clang.llvm.org/docs/JSONCompilationDatabase.html),
[Clang UBSan](https://clang.llvm.org/docs/UndefinedBehaviorSanitizer.html).

## v0.28 proof connection

An admitted scalar typed-AST fragment now connects to the existing typed CFG and
inductive summary kernels via [clang_proof](CLANG_SCALAR_PROOF.md). The compiler-only
frontend still returns readiness, not proof. General LLVM/memory semantics and KLEE
execution remain pending. Typedef metadata is also exported for canonical return
and local type resolution.

## v0.29 dependency export and memory/call connection

`include_dependencies:true` exports complete record declarations and function definitions from the same AST invocation (up to 128 each, requires include_ast). The proof bridge selects the direct reachable closure and admitted records. See [Clang memory and owned-list contracts](CLANG_MEMORY_AND_HEAP_SUMMARIES.md); this is not general LLVM interpretation or KLEE integration.
