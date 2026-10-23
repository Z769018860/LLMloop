# Experimental comparison and future research

The v0.4 changes focus on **avoiding false exact summaries** for complex SCCs.
They implement existential path reachability, invariant-assisted refinement,
LLM candidate generation, and certified restricted acceleration. They do not
claim superiority to LoopSCC or any new soundness theorem for unrestricted C.

## Suggested baseline evaluation

1. Reproduce the original public LoopSCC benchmark in a separate virtualenv.
2. Match mathematical-integer semantics and SPath encoding where applicable.
3. Evaluate SPath edge precision (SAT/UNSAT/UNKNOWN), SCC count, certified
   invariant count, and exact accelerated loop coverage separately.
4. Compare end-to-end runtime (include SMT/LLM overhead) and against concrete
   interpreter execution on finite domains.
5. Report failures, timeouts, vacuous constraints and unsupported language
   features explicitly.
6. Test difficult cases: nonfunctional SCC, transient SCC, overlapping guards,
   unreachable paths, unknown solver results, cross-inner-loop phase retention,
   and nonterminating loops. A SAT SCC alone is not proof of a valid cycle.

## Next work not implemented

- Generic SPath extraction from arbitrary CFG including path-exponential choices.
- SCC-specific parametric region discovery using abstract interpretation.
- General oscillatory intervals for arbitrary piecewise-affine recurrences.
- Symbolic nested-loop effects with interleaved outer body mutations.
- Termination/ranking synthesis for non-monotone progress.
- Validated array/pointer heap-state invariants (QCP-inspired).
- Solver-independent proof-certificate replay and cross-tool benchmark suite.
