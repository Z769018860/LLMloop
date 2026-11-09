"""v0.70 SV-COMP-derived corpus: hand translations of sosy-lab/sv-benchmarks (commit 2e1723f) loop programs into the verifier's function format.
Translation rules (documented, applied uniformly): `__VERIFIER_nondet_*` reads become parameters whose ranges come from the program's `assume`-style early returns; a reachability
assertion `__VERIFIER_assert(c)` at the end becomes `return 1/(c)` (division by zero, i.e. UB, iff the assertion fails), so 'no undefined behaviour' == 'assertion holds for all inputs'.
C89-style index declarations and `while` loops are kept as in the originals (handled by the trusted normalizers). `reference` = hand-written invariants (never shown to models)."""

SRC = 'sosy-lab/sv-benchmarks@2e1723f'


def case(name, origin, source, bounds, ref=None, role=None, trigger=None, family='V_svcomp', **extra):
    return dict(extra, name=name, family=family, origin=origin, source=source, backend='typed_invariant_tree', parameter_bounds=bounds, inputs={k: hi for k, (lo, hi) in bounds.items()}, reference=ref, role=role, trigger=trigger)


def iv(lo, hi=None): return {'lo': lo, 'hi': hi if hi is not None else lo}


def build():
    C = []
    C.append(case('sum04_2', 'loops/sum04-2.c', 'int f(int z){int i;int sn=0;for(i=1;i<=8;i++){sn=sn+2;}return 1/((sn==16)||(sn==0));}', {'z': [0, 0]}, {'i': {'sn': iv('2*i')}}, min_unwind=12))
    C.append(case('sum01_2', 'loops/sum01-2.c', 'int f(int n){int i;int sn=0;for(i=1;i<=n;i++){sn=sn+2;}return 1/((sn==n*2)||(sn==0));}', {'n': [-999, 999]}, {'i': {'sn': iv('2*i')}}))
    C.append(case('const_1_1', 'loop-acceleration/const_1-1.c', 'int f(int z){unsigned int x=1;unsigned int y=0;while(y<1024){x=0;y++;}return 1/(x==0);}', {'z': [0, 0]}, {'y': {'x': iv('1 if y==0 else 0')}}, min_unwind=1030))
    C.append(case('gauss_sum', 'loop-new/gauss_sum.c', 'int f(int n){int sum=0;int i;for(i=1;i<=n;i++){sum=sum+i;}return 1/(2*sum==n*(n+1));}', {'n': [1, 1000]}, {'i': {'sum': iv('(i*(i+1))//2')}}))
    C.append(case('half', 'loop-new/half.c', 'int f(int k){int i=0;int n=0;for(i=0;i<2*k;i++){if(i%2==0){n++;}}return 1/((k<0)||(n==k));}', {'k': [-1000000, 1000000]}, {'i': {'n': iv('(i+1)//2')}}, unwind_factor=2))
    C.append(case('nested_1', 'loop-new/nested-1.c', 'int f(int n,int m){int k=0;int i,j;for(i=0;i<n;i++){for(j=0;j<m;j++){k++;}}return 1/(k>=100);}', {'n': [10, 10000], 'm': [10, 10000]}, {'i': {'k': iv('m*i')}, 'j': {'k': iv('m*i+j')}}))
    # assertion violations in the originals (SV-COMP expected verdict false): trigger = input that fails the assertion
    C.append(case('sum04_1', 'loops/sum04-1.c', 'int f(int z){int i;int sn=0;for(i=1;i<=8;i++){if(i<4)sn=sn+2;}return 1/((sn==16)||(sn==0));}', {'z': [0, 0]}, role='unsafe_source_control', trigger={'z': 0}, min_unwind=12))
    C.append(case('sum01_1', 'loops/sum01-1.c', 'int f(int n){int i;int sn=0;for(i=1;i<=n;i++){if(i<10)sn=sn+2;}return 1/((sn==n*2)||(sn==0));}', {'n': [0, 100000]}, role='unsafe_source_control', trigger={'n': 10}))
    C.append(case('sum01_bug02', 'loops/sum01_bug02.c', 'int f(int n){int i;int j=10;int sn=0;for(i=1;i<=n;i++){if(i<j)sn=sn+2;j--;}return 1/((sn==n*2)||(sn==0));}', {'n': [0, 100000]}, role='unsafe_source_control', trigger={'n': 20}))
    C.append(case('const_1_2', 'loop-acceleration/const_1-2.c', 'int f(int z){unsigned int x=1;unsigned int y=0;while(y<1024){x=0;y++;}return 1/(x==1);}', {'z': [0, 0]}, role='unsafe_source_control', trigger={'z': 0}, min_unwind=1030))
    return C
