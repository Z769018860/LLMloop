# Verified threshold oscillation acceleration

## Supported loop class

One integer control variable x, threshold T, positive a and b:

- When x<T, x'=x+a; otherwise x'=x-b.
- Each other mutable state variable is a scalar accumulator modified by
  a branch-dependent CONSTANT integer increment, and cannot affect branching.
- The exit guard is i<n with stable integer n, and i has nonnegative
  branch increments.

This class is an independent, strictly scoped engineering extension based
on the LoopSCC oscillatory-interval motivation. It does not claim to implement
LoopSCC's general symbolic algorithm.

## Arithmetic proof

The inclusive integer interval I=[T-b,T+a-1] is inductive:
both branches preserve the interval. From x outside I, the exact entry
count is ceil((T-b-x)/a) when x<T-b, or ceil((x-(T+a-1))/b)
when x>T+a-1.

Once in I, define u=x-(T-b), width W=a+b. Then

    u_next=(u+a) mod W.

After k steps, the number of above-threshold visits is exactly

    B(k)=floor((u0+k*a)/W),

with A(k)=k-B(k) below-threshold visits. This immediately gives exact
closed-form formulas for x and all scalar accumulator variables.

Writing g=gcd(a,b), the orbit length is P=(a+b)/g, with b/g
below-branch and a/g other-branch visits. If the two progress increments
are r_below,r_above, the total per-orbit progress is

    D=(b/g)*r_below+(a/g)*r_above.

When D>0, exact first exit skips complete orbits and binary searches a
single orbit. Complexity depends logarithmically on orbit width, not on
the number of concrete loop iterations. If D=0 and the exit guard is
true initially, the restricted loop is nonterminating.

SPath edges are obtained by exact interval intersection of branch
pre/post regions. Tarjan SCCs summarize these existential edges.
This does not mean every arbitrary walk in the abstract graph is feasible.

## Run

~~~bash
pip install -e '.[test]'
llmloop-oscillation examples/oscillation_threshold.json --input n=1000000000000
llmloop-oscillation examples/oscillation_threshold.json --check-range=0:300
llmloop-oscillation-c examples/oscillation_threshold.c --input n=1000000 --check-range=0:100
pytest -q tests/test_oscillation.py
~~~

Outputs: inductive interval, orbit period, SPath graph/SCC, per-branch visit
counts, closed-form transition, exact first-exit count and final state.

The concrete interpreter is an additional regression oracle, not a proof.
The derivation above uses mathematical unbounded integers: the C frontend
does NOT model or prove signed-overflow absence. Unsupported pointers,
arrays, general multi-branch SCCs, nonconstant updates, aliasing, arbitrary
nested loops and nonmonotone exits fail closed or are not accepted. A proper
research comparison still requires running original LoopSCC under matching
semantics and hardware.
