"""v0.68 relational corpus: programs where a coupling between state variables (x+y==i, x==y, ...) makes the return/narrow-type operation defined.
Each safe program has TWO generator references: `reference_box` (exact interval boxes, floors allowed) and `reference_rel` (loose boxes + @rel).
Families: R_split (conditional split), R_diff (equal increments), R_comp (complementary counters), R_weight (weighted counters), R_nested, R_narrow (unsigned char), X_unsafe (UB for some n)."""
import random

SEED = 20261201


def case(name, family, source, bounds, ref_box=None, ref_rel=None, role=None, trigger=None):
    inputs = {k: hi for k, (lo, hi) in bounds.items()}
    return dict(name=name, family=family, source=source, backend='typed_invariant_tree', parameter_bounds=bounds, inputs=inputs, reference=ref_rel, reference_box=ref_box, reference_rel=ref_rel, role=role, trigger=trigger)


def same(lo, hi=None): return {'lo': lo, 'hi': hi if hi is not None else lo}


def build(seed=SEED):
    r = random.Random(seed); C = []; k = [0]
    def nm(f):
        k[0] += 1; return '%s%02d' % (f, k[0])
    B = {'n': [0, 1000000]}
    for _ in range(5):
        m, K = r.randint(2, 6), r.randint(10, 999)
        x = '(i+%d)//%d' % (m - 1, m)
        C.append(case(nm('split'), 'R_split', 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){if(i%%%d==0){x++;}else{y++;}}return %d/(x+y-n+1);}' % (m, K), B,
                      {'i': {'x': same(x), 'y': same('i-' + x)}}, {'i': {'x': {'lo': '0', 'hi': 'i'}, 'y': {'lo': '0', 'hi': 'i'}, '@rel': {'eq': ['x+y-i']}}}))
    for _ in range(4):
        a, K = r.randint(1, 9), r.randint(10, 999)
        C.append(case(nm('diff'), 'R_diff', 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){x+=%d;y+=%d;}return %d/(x-y+1);}' % (a, a, K), B,
                      {'i': {'x': same('%d*i' % a), 'y': same('%d*i' % a)}}, {'i': {'x': {'lo': '0', 'hi': '%d*i' % a}, 'y': {'lo': '0', 'hi': '%d*i' % a}, '@rel': {'eq': ['x-y']}}}))
    for _ in range(3):
        K = r.randint(10, 999)
        C.append(case(nm('comp'), 'R_comp', 'int f(int n){int x=n;int y=0;for(int i=0;i<n;i++){x--;y++;}return %d/(x+y-n+1);}' % K, B,
                      {'i': {'x': same('n-i'), 'y': same('i')}}, {'i': {'x': {'lo': '0', 'hi': 'n'}, 'y': {'lo': '0', 'hi': 'n'}, '@rel': {'eq': ['x+y-n', 'y-i']}}}))
    for _ in range(3):
        a, b, K = r.randint(1, 9), r.randint(1, 9), r.randint(10, 999)
        C.append(case(nm('wgt'), 'R_weight', 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){x+=%d;y+=%d;}return %d/(%d*x-%d*y+1);}' % (a, b, K, b, a), B,
                      {'i': {'x': same('%d*i' % a), 'y': same('%d*i' % b)}}, {'i': {'x': {'lo': '0', 'hi': '%d*i' % a}, 'y': {'lo': '0', 'hi': '%d*i' % b}, '@rel': {'eq': ['%d*x-%d*y' % (b, a)]}}}))
    for _ in range(4):
        a, K = r.randint(1, 5), r.randint(10, 999)
        NB = {'n': [0, 1000], 'm': [0, 1000]}
        C.append(case(nm('nest'), 'R_nested', 'int f(int n,int m){int x=0;int y=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=%d;y+=%d;}}return %d/(x-y+1);}' % (a, a, K), NB,
                      {'i': {'x': same('%d*m*i' % a), 'y': same('%d*m*i' % a)}, 'j': {'x': same('%d*m*i+%d*j' % (a, a)), 'y': same('%d*m*i+%d*j' % (a, a))}},
                      {'i': {'x': {'lo': '0', 'hi': '%d*m*i' % a}, 'y': {'lo': '0', 'hi': '%d*m*i' % a}, '@rel': {'eq': ['x-y']}}, 'j': {'x': {'lo': '0', 'hi': '%d*m*i+%d*j' % (a, a)}, 'y': {'lo': '0', 'hi': '%d*m*i+%d*j' % (a, a)}, '@rel': {'eq': ['x-y']}}}))
    for _ in range(3):
        c, K = r.randint(1, 250), r.randint(10, 999)
        C.append(case(nm('narrow'), 'R_narrow', 'int f(int n){unsigned char x=0;unsigned char y=0;for(int i=0;i<n;i++){x+=%d;y+=%d;}return %d/(x-y+1);}' % (c, c, K), B,
                      {'i': {'x': same('(%d*i)%%256' % c), 'y': same('(%d*i)%%256' % c)}}, {'i': {'x': {'lo': '0', 'hi': '255'}, 'y': {'lo': '0', 'hi': '255'}, '@rel': {'eq': ['x-y']}}}))
    # unsafe controls: zero divisor only when n == t (inside the bounds); `trigger` = native input that hits it
    t = [r.randint(3, 9) for _ in range(5)]
    SP = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){if(i%%2==0){x++;}else{y++;}}return 100/(x+y-n+%d-n);}'
    DF = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){x+=3;y+=3;}return 100/(x-y+%d-n);}'
    CP = 'int f(int n){int x=n;int y=0;for(int i=0;i<n;i++){x--;y++;}return 100/(x+y-n+%d-n);}'
    WG = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){x+=2;y+=5;}return 100/(5*x-2*y+%d-n);}'
    NS = 'int f(int n,int m){int x=0;int y=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=2;y+=2;}}return 100/(x-y+%d-n);}'
    for src, tt in zip((SP, DF, CP, WG, NS), t):
        bounds = {'n': [0, 1000], 'm': [0, 1000]} if src is NS else B
        C.append(case(nm('uns'), 'X_unsafe', src % tt, bounds, role='unsafe_source_control', trigger={'n': tt, 'm': 1} if src is NS else {'n': tt}))
    return C
