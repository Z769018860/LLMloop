# Periodic coupled candidate discovery (v0.19)

Automatic summaries now discover a restricted class of cyclic dependencies in
addition to the existing triangular polynomial lifts. This includes coordinate
swaps, finite rotations, signed rotations, drifting accumulators, finite
polynomial lifts of such updates, static finite-cell permutations and supported
nested compositions. The old swap rejection control is now a proved success.

```sh
python -m llmloop.symbolic_cli examples/typed_coupled_rotation.c \
  --c-typed-nested --auto-summaries \
  --parameter-bounds '{"n":[0,1000000]}' --inputs '{"n":999999}'
```

This returns -1 with a `PROVED_DEFINED_TYPED_C_NESTED` certificate. API and
per-loop manual/automatic mixing use the existing v0.18 interface.

## Exact block decomposition

After the finite monomial lift establishes its polynomial closure identities,
let M be the lifted transition matrix. The generator searches p=2,...,8 for a
block B=M^p whose off-diagonal dependency graph is acyclic and whose diagonal
entries belong to {-1,0,1}. The previous direct triangular path is unchanged.
Only bounded integer coefficient matrices enter the cyclic search; symbolic
cyclic coefficients are rejected before expansion. Integer entry sizes are
limited to 128 bits initially and 1024 bits during block search. The existing
16-coordinate lift and degree/resource limits still apply.

The block power B^q is proved with the existing exact base/successor identity
checker, including its finite singular-transient handling. For k=pq+r,
0<=r<p, reconstruct M^k=M^r B^q. The residue factors and their boundary identity
M M^(p-1)=B are checked exactly. `power_certificate` records the block size,
residue identities and block-power certificate. This is a proof for arbitrary
nonnegative counts in the mathematical model, rather than finite simulation.
The block size need not equal the state period: a block with diagonal -1 can
alternate sign on successive blocks.

The implementation multiplies the entry vector within each residue before
constructing Piecewise coordinates. This avoids combinatorial combinations of
identical residue partitions; it does not truncate states or approximate values.

## Original C remains the acceptance test

Discovery still approximates casts and ignores intermediate undefined behavior.
Consequently, every candidate is separately checked through the original typed
source executor: actual condition, original arithmetic intermediates, scalar and
memory range/initialization/lifetime checks, successor, exit and termination.
A cyclic candidate cannot hide an overflowing `(t+1)-1`, and a mathematical
narrow-wrap feedback formula is rejected when it does not match the C program.
The signed rotation example is checked under LP64, ILP32 and LLP64; native
UBSan comparisons use the actual LP64 host.

Fibonacci-like exponential systems, cyclic parameter coefficients, permutation
periods outside the search budget and general branching trajectories remain
unsupported by automatic discovery. Supplied formulas and other mathematical
frontends retain their previous capabilities. `UNKNOWN` is not certification,
and unsupported safe source is not necessarily an unsafe program.

General escaping/dynamic heaps, allocation failure, arbitrary CFG/early exits,
and representative real-library validation remain outstanding. The existing
finite-memory and successful-allocation assumptions are unchanged.

See [the v0.19 experiment report](../experiments/v019/report.md) for complete
local regression, native C/UBSan and positive/rejecting control evidence. These
controlled examples make no universal C or performance claim.
