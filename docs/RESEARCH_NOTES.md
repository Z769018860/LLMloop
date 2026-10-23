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
- General lexicographic/piecewise termination rankings beyond the v0.7 affine template bank.
- Validated array/pointer heap-state invariants (QCP-inspired).
- Solver-independent proof-certificate replay and cross-tool benchmark suite.


## v0.5 bounded CFG and invariant discovery

Added a scalar C frontend that expands nested and sequential if/else blocks
into SPaths while rewriting later predicates through earlier assignments.
Added a template generator for threshold intervals, monotone bounds and
pairwise affine equalities. Candidates remain hypotheses until Z3 proves
initiation, path coverage and consecution. The frontend is path-bounded and
the template search is incomplete; neither claims general C analysis.


## v0.7 verification layer

Whole-graph initial-state bounded verification and universally checked affine
ranking templates are implemented; see VERIFICATION_API.md. They complement
SCC summaries rather than treating may-edges as execution schedules. Bounded
verification does not imply unbounded safety when an active execution remains.
