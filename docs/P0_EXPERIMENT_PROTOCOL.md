# P0 experiment scope and acceptance

This milestone freezes 24 external inputs before evaluation: the first twelve
lexicographically sorted ELBA SMT2 benchmarks and the first twelve LoopSCC
Python input files at the exact revisions in the JSON protocol. It retains
errors, timeouts, unsupported inputs, and missing direct-source comparisons.
Three randomized repetitions are executed. ELBA uses its default configuration,
not its multi-configuration portfolio. A printed bound is a tool-reported result,
not automatically an independent correctness certificate.

The LoopSCC snapshot is the public `hahaleyile/LoopSCC` repository. Equivalence to
the ICSE 2026 anonymous artifact has not been established. Analysis source files
are unchanged. The worker executes their declarative assignments and explicitly
calls summary construction, rather than their 1,000-print sample driver. It
uses the first three author inputs and three predeclared uniform small states.
The author raw Python program is observed with a return-frame tracer capped at
30,000 events. Missing/unfinished oracle executions remain visible and are not
matches. These are mathematical-integer point checks, not typed-C certificates
or universal correctness results.

All 35 public LoopSCC input files also have a registered source- and
family-disjoint future split: `leap*` is the future test family, other families
are development. This freezes a later model evaluation protocol; it does not
claim that models have been run or that training contamination has been ruled
out. Original source hashes and paths are retained; licensing must be resolved
before redistributing third-party source files.

Eight controlled C configurations isolate bounded execution, affine candidate
language, flat trajectory checking, compositional trajectory checking and
deterministic candidate synthesis. They use five actual existing API modes and
three randomized repetitions. The affine mode deliberately restricts supplied
formulas and includes invalid candidates; it is a candidate-language control,
not a switch for a fully implemented periodic-invariant synthesis algorithm.
Flat mode checks the same original program with the original scalar verifier;
it does not silently flatten a nested source. All original typed-definedness
checks remain enabled. Unsafe intermediates must remain UNKNOWN.

Known expectations apply only to these controlled cases. External outcomes are
observations and cannot be changed to success to make the harness pass. Study
execution acceptance means complete capture and unchanged frozen files, plus
all declared control expectations. It does not mean every external algorithm
succeeds. No UNKNOWN/proof speedup is reported.

ELBA is compiled from unaltered sources with a forced standard `<deque>` include,
GCC 13, Boost 1.83, GMP 6.3 and Z3 4.13.0. This compatibility build differs from
the repository's CMake dependency pins. The initial failure with Z3 5.3 is
retained. LIFT's supplied-bound smoke is separately attempted using native Mono
6.8 and the pinned artifact; its unsafe name-wide process cleanup is disabled,
while process-group cleanup is retained. No logical validation is disabled.
Neither compatibility execution is claimed as the authors' exact environment.

Genuine LLM execution remains blocked without a configured endpoint/model and
credential. MALICE and the conference LoopSCC artifact are not replaced by
unverified lookalikes. The P0 ledger must therefore remain open until these
required evidence items actually exist. No KLEE or GitHub Actions are used.
