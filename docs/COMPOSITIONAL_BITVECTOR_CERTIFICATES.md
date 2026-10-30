# Checked bit-vector cuts and bounded integer certificates (v0.40)

The original 64-bit compiler-rt popcount passed source safety in v0.39, while its
independent monolithic functional QF_BV query timed out at 5000 ms. This release
keeps the same source, declared domain and balanced per-bit reference circuit,
but proves their equivalence compositionally. It does not replace safety checks
or increase the total functional proof budget.

## Checked cuts, not assumed algorithm facts

The source executor supplies its complete bit-vector return expression. A small
structural search proposes one 32/64-bit packed-byte subexpression using a
low-nibble mask. This shape is only a candidate: every byte must independently
match the balanced sum of its eight original input bits, with result at most 8.
The byte queries are unconditional, so their bounds do not rely on a guessed C
invariant or a favorable sample. A separate query checks exhaustive byte packing.

Fresh four-bit counters replace the proved byte counts in both expressions.
All original input dependencies must disappear after substitution; residual
dependencies or ambiguous candidates refuse this proof method. The original
reference remains the same balanced bit sum, with its actual byte subterms
replaced by the same counters. The final theorem quantifies over every counter
combination in `[0,8]`, including a conservative overapproximation if needed.

The small remaining word equation is translated to unsigned integer arithmetic:
concatenation becomes positional addition, extraction and fixed logical shifts
become positive division/modulo, and word arithmetic keeps exact modular wrap.
Only explicitly implemented operators are admitted. Signed shifts/extensions,
variable shifts, arbitrary masks, unsupported operations, unbound variables,
mixed integer-theory terms in QF_BV queries, quantifiers and function symbols
are refused rather than approximated.

## Exact bounded affine quotient/remainder rule

For positive integer `D`, each affine coefficient is decomposed exactly to form
`A = D*Q + R`. If explicit variable bounds enclose `R` in a single quotient
interval `[k*D, (k+1)*D-1]`, then:

\[
\lfloor A/D\rfloor=Q+k,\qquad A\bmod D=R-kD.
\]

Every rewrite records the residual interval, adjusted quotient/remainder and
an independently simplified polynomial identity audit. Negative coefficients
and negative variable bounds use Euclidean division with positive `D`. Missing
bounds, nonlinear terms, nonpositive divisors and budget exhaustion never yield
a guessed rewrite. This rule is a proof normalization under explicit hypotheses;
it is not C interval inference and never supplies an assumed source-safety fact.

Here the counter bounds were already proved by the byte lemmas. Normalization
reduces both remaining popcount equations to the same linear sum. A final QF_LIA
query checks the bounded integer equality. The resulting status is
`PROVED_FUNCTIONAL_BV_CUTS`, distinct from a monolithic QF_BV certificate.

## Budget, failure and evidence contracts

After typed source execution builds the return expression, cut preparation,
every byte/packing query, integer normalization and the final query share one
5000 ms deadline. Each solver receives only the remaining time. There
are no retries. If a cut is refused/unproved, the original whole-output query may
use only the remaining budget. An intermediate SAT cut is **not** a functional
counterexample: a different implementation may compensate for that intermediate
value. Only the original output/spec query can produce the fallback's refutation.
Tests include a correct compensated implementation with a failed intermediate
cut, and a wrong implementation that is still correct in a narrow declared domain.

The certificate retains every query/result/logic/timeout, the original cut and
byte reference expressions, substitution bindings, reduced BV equations, exact
integer translations and affine audits. Its top-level `refutation_smt2` is only
the final bounded integer query: it is insufficient on its own. All preceding
steps and the recorded translations/composition are required. Queries can each
be replayed with their recorded logic. Composition, translation and normalization
remain trusted, tested code; this is not a proof-assistant theorem or a verified
compiler-equivalence claim.

Primary source safety is unchanged and still proved separately. Native GCC
O0/O2 comparisons remain finite supplementary evidence. A wrong 64-bit source
mask must pass source safety, fail the functional proof, and disagree with both
native reference oracles. The direct 5000 ms baseline runs separately for
comparison; its timeout is measured rather than required for success.

```sh
python -m pytest -q --forked tests/test_bv_cut_certificates.py
python scripts/check_popcount_functional.py --output experiments/v040/popcount_demo.json
python scripts/check_popcount_functional.py --strategy direct --output /tmp/popcount_direct.json
python scripts/run_v040_experiments.py
```

See [actual frozen-source results](../experiments/v040/report.md). This closes the
pilot's former popcount functional timeout when its obligations pass. The
division/builtin/helper case remains unsupported; general heap/alias/external
contracts, arbitrary recurrence discovery and complete C/LLVM semantics remain
open. No KLEE is added.
