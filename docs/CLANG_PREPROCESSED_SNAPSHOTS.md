# Opt-in compiler-expanded snapshots

Set `clang.preprocess: true` with `clang` or `clang_proof` to expand each
translation unit once with Clang `-E`. Its exact UTF-8 output, including line
markers, becomes the physical input of AST, layout and LLVM stages through
`-x cpp-output`. These stages never reopen included files. Defaults and proof
budgets are unchanged. This is compiler-owned preprocessing, not a
machine-checked preprocessing equivalence theorem.

Function/parameter byte offsets now address one retained snapshot. Project
header and macro pointer declarations can retain checked spellings without
guessing header offsets against the main file. Every original declaration in
each reachable binding chain still contributes its canonical type and expanded
declarator checks. Adjusted arrays, static array lengths, VLA bounds/entry
effects and unsupported qualifiers/attributes remain UNKNOWN. Named records
still require compatible ordered fields and each unit's compiler/model layout.

For a header containing `int api(int *);`, a provider containing
`int api(int *p){return p[0]+1;}`, and an entry returning `api(a)` for a local
`int a[1]={n};`, use:

```json
{
  "frontend": "clang_proof",
  "source_file": "entry.c",
  "function": "entry",
  "clang": {"preprocess": true, "linked_sources": ["provider.c"]},
  "proof": {"backend": "calls", "parameter_bounds": {"n": [0, 2]}}
}
```

Compilation databases, command selection, include/define flags, ABI and static
linkage remain explicit. Each frontend retains the expanded text, its SHA-256
and input hash; linked certificates identify each snapshot hash. Input and
snapshot must stay unchanged during ingestion. Linked main files stay checked
through proof completion. Headers/environment must be stable during each
preprocessing invocation. Separate units are not a hermetic simultaneous build.

Expanded input is capped at 1 MiB per unit. Invalid UTF-8 and NUL are refused.
Source-location builtins (`__builtin_LINE`, `__builtin_COLUMN`, `__builtin_FILE`,
`__builtin_FILE_NAME`, `__builtin_FUNCTION`, `__builtin_source_location`) are
conservatively refused before compiling relocated tokens; their spelling in
strings can also cause refusal. Ordinary macros such as `__LINE__` and
`__COUNTER__` expand in the original compiler context. No assumption is added
for external calls, arbitrary heap shapes or termination.

Tests cover header/macro interfaces, three record ABIs, database selection,
unchanged defaults, arrays/VLAs, unsafe bodies, modified inputs/snapshots,
size/encoding errors and compiler failures. Native experiments separately
compile original units, expanded text and normalized C at GCC O0/O2, with
independent result/allocation oracles and required UBSan failures. Run:

```sh
python scripts/run_v049_experiments.py
```
