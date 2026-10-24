# Unbounded finite-cell summaries, affine closed forms and typed integers (0.9)

These are separate analysis modes. Their certificates must not be combined
implicitly: mathematical-integer loop summaries do not establish absence of C
machine-integer overflow.

| Request | Implemented | Explicit remaining boundary |
| --- | --- | --- |
| Unbounded nested memory summaries | Counted loops with no iteration cap; finite initialized objects; static array cells/pointer aliases; affine body effects and interleaved outer mutations; fixed calloc objects | Dynamic indices/aliasing, allocation/lifetime changes, state-dependent trip counts and arbitrary control flow |
| General recurrence closed forms | General fixed affine matrix schedules, including exponential, alternating, coupled/Fibonacci and singular transient effects, when induction identities are proved | Arbitrary nonlinear or branching-SCC closed forms; no invented branch schedule |
| C integer semantics | Typed concrete expression kernel for LP64/ILP32/LLP64: promotions, usual arithmetic conversions, literals, casts, Boolean conversion, division/remainder, bitwise operations, shifts, lazy logic/conditionals and UB classification | Not integrated with all C syntax, memory, integer promotions in the symbolic scalar frontend or whole-program symbolic verification |

No analyzer can guarantee exact termination/closed-form results for all arbitrary
C loops. Unsupported cases must remain UNKNOWN; bounded checking and existential
may-graphs are not unbounded proofs.

## General affine recurrences

```bash
python -m llmloop.symbolic_cli examples/exponential_recurrence.json
```

The `affine_recurrence` IR supplies `state`, optional immutable `parameters`,
`updates`, and a fresh `counter` (default `k`). Updates are simultaneous.
For augmented affine matrix M, SymPy proposes a symbolic power F(k). The checker
requires F(0)=I and F(k+1)=M F(k) as exact symbolic identities. Singular matrix
powers may have a finite Kronecker-delta transient: all successor cases in that
prefix are proved explicitly, followed by a universal successor identity for
the entire tail. This is not a finite-sampling replacement for induction.
Denominators must be provably nonzero. Conditional/unevaluated formulas, floating
arithmetic and failed identities return UNKNOWN. The symbolic algebra library
is part of the trusted computing base; there is no independent proof-assistant
certificate replay.

`x'=2x+1, x(0)=0` gives `x(k)=2**k-1`. A recurrence schedule does not establish
that a branching SCC follows that schedule, or that a source loop terminates.
The existing SCC/guard/ranking checks remain necessary for those claims.

## Compositional unbounded memory IR

```json
{
  "kind": "counted_memory",
  "parameters": ["n", "m"],
  "parameter_mins": {"n": 0, "m": 0},
  "arrays": {"a": [1]},
  "pointers": {"p": {"array": "a", "index": 0}},
  "body": [
    {"repeat": "n", "body": [
      {"repeat": "m", "body": [{"assign": {"*p": "p+1"}}]},
      {"assign": {"a[0]": "2*a[0]"}}
    ]}
  ]
}
```

`assign` updates a simultaneous set of cells. Multiple statements execute
sequentially. `a[0]`, `p[0]`, or assignment target `*p` refer to the same cell;
in expression IR, the pointer identifier `p` denotes its pointed-to value.
These are value-summary IR references, not general C pointer expressions.
Two targets in one simultaneous assignment may not alias. Each nested repeat
is replaced by an induction-checked matrix power and composed with surrounding
updates in source order, including resets and zero-length loops. The repetition
count must be a nonnegative polynomial in immutable parameters, proved with a
conservative shifted-coefficient test. A maximum of 16 syntactic nesting levels,
128 statements and 15 total cells/scalars limits analysis size; there is **no
per-loop iteration bound**. A billion repetitions are still one matrix power.
Concrete evaluation can create enormous integers for exponential recurrences;
hosts must impose process time/memory/output limits.

## Canonical C adapter

```bash
python -m llmloop.symbolic_cli examples/unbounded_nested_memory.c \
  --c-counted --parameter-mins '{"n":0,"m":0}' --inputs '{"n":3,"m":2}'
```

Accepted `for` loops initialize an index to zero, use `index < immutable_bound`,
and increment that index by one. The body cannot write the index elsewhere.
Loop indices can occur in affine RHSs, preserving sums such as `a[0]+=i`.
Count bounds cannot depend on a mutable outer index. Declarations precede
statements; arrays are explicitly initialized; pointer copies retain static
identity. Fixed successful `calloc` is modeled as zero-filled cells. No `free`,
allocation failure, dynamic pointer motion or uninitialized memory is modeled.
Array/pointer indices must be static and in range. Final scalar/cell return
values are summarized. Unsupported declarations, loops or effects fail closed.

```python
from llmloop.api import analyze_request
report = analyze_request({
    "source": open("examples/unbounded_nested_memory.c").read(),
    "frontend": "counted_memory",
    "parameter_mins": {"n": 0, "m": 0},
    "inputs": {"n": 3, "m": 2}
})
```

The example's return value is 65. `c_overflow_verified` is explicitly false:
these summaries use unbounded mathematical integers and cannot be presented as
machine-C equivalence for inputs with undefined overflow.

## Typed C integer reference kernel

```bash
python -m llmloop.symbolic_cli examples/typed_integer_expression.json
```

`c_integer_expression` carries an `abi` (`LP64`, `ILP32`, `LLP64`), optional
`char_signed`, and a typed expression tree. Leaves are `{"literal":"0xffffffff"}`
or `{"value":-1,"type":"int"}` (an explicit conversion to that type).
Operators use `{"op":"+","args":[...]}`; casts use
`{"cast":"unsigned char","expr":...}`. Unary and binary integer operators,
`&&`, `||`, and ternary `?:` are supported. All operand types are checked, but
only selected conditional/logical operands are evaluated.

The model fixes 8-bit char, 16-bit short, 32-bit int and 64-bit long long. Long
is 64 bits in LP64 and 32 bits otherwise. `_Bool`, plain/signed/unsigned char,
short/int/long/long long and their unsigned counterparts have explicit ranks.
Decimal/octal/hexadecimal C integer literals select candidate types according
to base and U/L/LL suffixes. Division truncates toward zero and remainder follows
the dividend. Signed arithmetic overflow, division by zero/MIN divided by -1,
negative or excessive shift counts and invalid signed left shifts are explicit
`UNDEFINED_INTEGER_OPERATION` results. Unsigned arithmetic wraps.

Implementation-defined choices are **named**, not universally asserted:
representation is two's complement, out-of-range signed casts wrap modulo the
target width, and right shifts of negative signed values are arithmetic.
Other implementations need a different ABI policy. This does not model enums,
bitfields, character constants, extended integer types, atomics, assignment
side effects, compiler extensions or all C language syntax. In particular, it
is a concrete reference kernel, not a claim of complete symbolic C semantics.

## Reproduce evidence without Actions

```bash
python -m pip install -e '.[test,smt]'
python -m pytest -q
python scripts/check_counted_native.py
python scripts/check_integer_native.py
python scripts/check_memory_native.py
python scripts/check_ordered_native.py
```

Native checks require POSIX `cc`. Integer checks assert the LP64 host layout and
compare value, width, signedness and rank on 4549 defined expressions. The
108 nested-memory native executions are finite regression evidence; matrix
induction identities provide the unbounded argument for the accepted IR class.
They are not a general source-to-summary proof or cross-tool benchmark.
