# LLMloop — Certified Periodic Loop Acceleration

A reproducible Python research prototype for **certified integer-loop state
summarization without per-iteration symbolic unfolding**.

This repository implements a restricted, explicit **JSON transition IR**.
It does **not** implement complete C parsing, QCP, LoopSCC, arbitrary nesting,
pointer semantics, or universal loop acceleration. Unsupported semantics
return an explicit error rather than a guessed answer.

## Features

- Symbolic *simultaneous* affine phase updates with persistent variables
- Exact full-period transition matrices and binomial closed forms when the
  augmented full-cycle matrix is unipotent
- Symbolic verification of each phase-equality invariant across all cycles
- Exact first-exit iteration bound for monotone constant progress per phase,
  including cases where progress occurs only once per period
- Restricted triangular nested-loop composition with shared phase and state,
  avoiding the common bug of resetting an inner-loop phase each outer iteration
- Optional OpenAI-compatible LLM full-cycle formula proposals, verified as
  universal symbolic identities before use
- CLI, independent bounded interpreter, unit tests and GitHub Actions CI

## Install

Python >=3.10:

~~~bash
python -m pip install -e '.[test]'
pytest -q
llmloop analyze examples/alternating.json --input n=5 --check-range 0:40
llmloop analyze examples/progress_every_two.json --input n=100
llmloop analyze examples/nested_triangular.json --input n=4 --check-range 0:20
~~~

Export JSON with the --output report.json option.

For an **optional** LLM proposal, set OPENAI_API_KEY and run:

~~~bash
llmloop analyze examples/alternating.json --llm-model YOUR_MODEL
~~~

You may specify --llm-url for an OpenAI-compatible endpoint. The candidate
is rejected unless it matches the exact full-cycle transition for every
possible integer state. LLM assertions are never trusted as proofs.

## Three demonstrators

1. **Alternating loop**: each iteration increments i, updates p=1-p,
   and adds 1 or 3 to x. With i=0 and condition i<n, the exact trip
   count is n when n>=0. The final x is 4*floor(n/2)+(n mod 2).
2. **Two-step progress**: i advances only on every second iteration.
   A simple loop bound n is wrong; the exact number of iterations is 2*n.
3. **Triangular nested**: outer iterations j=1..n, with j inner steps,
   operating on one globally persistent x,p state. The total inner
   steps equal n(n+1)/2. Phase p is **not reset** at an outer boundary.

## Soundness boundary

All updates are over **unbounded mathematical integers**; C signed-overflow
and bit-vector semantics are NOT modeled. Each phase is visited in its
given deterministic cyclic order. The phase optional guard must be an
equality (e.g. p == 0) established algebraically for all cycle indices.
State updates must be affine (linear in mutable state, plus expressions of
immutable parameters). The full-cycle augmented affine matrix B must
satisfy (B-I)^d=0 for some finite d.

Under these checks, the binomial matrix formula

    B^q = sum_{j=0}^{d-1} binomial(q,j)*(B-I)^j

is an exact identity for any integer q>=0. Phase prefixes yield the exact
state at every residue. For the supported termination guard, the chosen
variable must make nonnegative **constant** progress on each phase in
the exit direction, and strictly positive progress each cycle. The
residue-wise minimum first-crossing formula is therefore exact.

Triangular nested-loop composition is valid only when the only side
effects are repeated uses of that same body transformer, with no
intervening outer-state mutations, and with nonnegative inner lengths.
Outer-iteration count is a nonnegative stable parameter symbol.

Concrete checks are an independent *finite regression oracle* and are
not substituted for the symbolic algebraic proof.

## JSON IR

Ordinary loop:

~~~json
{
  "kind": "loop",
  "parameters": ["n"],
  "state": {"i": 0, "x": 0},
  "phases": [{"updates": {"i": "i + 1", "x": "x + 2"}}],
  "guard": {"var": "i", "op": "<", "bound": "n"}
}
~~~

Each update is simultaneous and omitted variables remain unchanged.
Only safe arithmetic expressions with whitelisted syntax are accepted.
For triangular nested loops, see examples/nested_triangular.json.

The program outputs an explicit **EXACT_AFFINE_PERIODIC** or
**EXACT_TRIANGULAR_COMPOSITION** status, symbolic cycle map, closed-form
residue maps, a trip expression when applicable, and certificate metadata.
Unsupported inputs exit with code 2 and a **UNKNOWN** message.

## Relationship to the literature

Inspired by (but **not a reimplementation of**) LoopSCC (ICSE 2026),
MALICE (ICML 2026), Exact Loop Bound Analysis (PLDI 2025), and QCP.
The IR and its mathematical proof boundary are documented above.
Research extensions include an actual C frontend, variable-dependent
phase graphs, array/heap summaries, SMT-verifiable certificates,
general nested-loop composition, ranking functions, and comparative
performance evaluation. None of these are claimed complete.

MIT license.
