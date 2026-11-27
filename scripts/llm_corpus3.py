"""v0.67 loop-tree corpus: seeded, random constants; families exercise the tree-mode extensions.
S sequential loops | D depth-3 nests | P stepped/inclusive/descending shapes | M mixed nesting (statements around inner loops, two inner loops) | X unsafe controls.
`reference` = generator-known loop-keyed interval invariants (counts, not index values); used only to classify programs, never shown to a model."""
import random

SEED = 20261120


def case(name, family, source, bounds, ref=None, role=None, note=''):
    inputs = {k: hi for k, (lo, hi) in bounds.items()}
    return dict(name=name, family=family, source=source, backend='typed_invariant_tree', parameter_bounds=bounds, inputs=inputs, reference=ref, role=role, note=note)


def iv(hi, lo='0'): return {'lo': lo, 'hi': hi}


def build(seed=SEED):
    r = random.Random(seed); C = []; k = [0]
    def nm(f):
        k[0] += 1; return '%s%02d' % (f, k[0])
    B7 = 10000000
    # S: sequential loops
    for _ in range(2):
        a, b = r.randint(1, 9), r.randint(1, 9)
        C.append(case(nm('seq'), 'S_sequential', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){x+=%d;}for(int j=0;j<m;j++){x+=%d;}return x;}' % (a, b), {'n': [0, B7], 'm': [0, B7]},
                      {'i': {'x': iv('%d*i' % a)}, 'j': {'x': iv('%d+%d*j' % (a * B7, b))}}))
    c1, c2, c3 = [r.randint(1, 250) for _ in range(3)]
    C.append(case(nm('seq'), 'S_sequential', 'int f(int n,int m,int p){unsigned char x=0;for(int i=0;i<n;i++){x+=%d;}for(int j=0;j<m;j++){x+=%d;}for(int k=0;k<p;k++){x+=%d;}return x;}' % (c1, c2, c3),
                  {'n': [0, B7], 'm': [0, B7], 'p': [0, B7]}, {l: {'x': iv('255')} for l in 'ijk'}))
    a, b, T = r.randint(1, 5), r.randint(1, 5), r.randint(10, 500)
    C.append(case(nm('seq'), 'S_sequential', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){if(i<%d){x+=%d;}else{x+=%d;}}for(int j=0;j<m;j++){x-=1;}return x;}' % (T, a, b), {'n': [0, B7], 'm': [0, 1000]},
                  {'i': {'x': iv('%d*i' % max(a, b))}, 'j': {'x': iv('%d' % (max(a, b) * B7), lo='-j')}}))
    a = r.randint(1, 6)
    C.append(case(nm('seq'), 'S_sequential', 'long f(int n){long x=0;long y=0;for(int i=0;i<n;i++){x+=%d;}for(int j=0;j<n;j++){y+=x;}return x+y;}' % a, {'n': [0, 20000]},
                  {'i': {'x': iv('%d*i' % a), 'y': iv('0')}, 'j': {'x': iv('%d' % (a * 20000)), 'y': iv('%d*j' % (a * 20000))}}))
    u = r.randint(1, 100)
    C.append(case(nm('seq'), 'S_sequential', 'int f(int n){unsigned short x=0;for(int i=0;i<n;i++){x+=%d;}for(int j=0;j<n;j++){x++;}return x;}' % (u + 1000), {'n': [0, B7]}, {l: {'x': iv('65535')} for l in 'ij'}))
    a = r.randint(2, 5)
    C.append(case(nm('seq'), 'S_sequential', 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=%d;}for(int j=0;j<3;j++){x+=1;}return x;}' % a, {'n': [0, B7]},
                  {'i': {'x': iv('%d*i' % a)}, 'j': {'x': iv('%d+j' % (a * B7))}}))
    # D: depth-3 nests
    for _ in range(2):
        a = r.randint(1, 5)
        C.append(case(nm('deep'), 'D_depth3', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n;j++){for(int k=0;k<n;k++){x+=%d;}}}return x;}' % a, {'n': [0, 1000]},
                      {'i': {'x': iv('%d*1000000*i' % a)}, 'j': {'x': iv('%d*1000000*i+%d*1000*j' % (a, a))}, 'k': {'x': iv('%d*1000000*i+%d*1000*j+%d*k' % (a, a, a))}}))
    a = r.randint(1, 4)
    C.append(case(nm('deep'), 'D_depth3', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<i;j++){for(int k=0;k<j;k++){x+=%d;}}}return x;}' % a, {'n': [0, 1000]},
                  {'i': {'x': iv('%d*1000000*i' % a)}, 'j': {'x': iv('%d*1000000*i+%d*1000*j' % (a, a))}, 'k': {'x': iv('%d*1000000*i+%d*1000*j+%d*k' % (a, a, a))}}))
    c = r.randint(1, 250)
    C.append(case(nm('deep'), 'D_depth3', 'int f(int n,int m){unsigned char x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<3;k++){x+=%d;}}}return x;}' % c, {'n': [0, 100000], 'm': [0, 100000]}, {l: {'x': iv('255')} for l in 'ijk'}))
    a = r.randint(1, 3)
    C.append(case(nm('deep'), 'D_depth3', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=i;j<n;j++){for(int k=j;k<n;k++){x+=%d;}}}return x;}' % a, {'n': [0, 500]},
                  {'i': {'x': iv('%d*250000*i' % a)}, 'j': {'x': iv('%d*250000*i+%d*500*j' % (a, a))}, 'k': {'x': iv('%d*250000*i+%d*500*j+%d*k' % (a, a, a))}}))
    a = r.randint(1, 4)
    C.append(case(nm('deep'), 'D_depth3', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<n;k++){x+=%d;}}}return x;}' % a, {'n': [0, 300], 'm': [0, 300]},
                  {'i': {'x': iv('%d*90000*i' % a)}, 'j': {'x': iv('%d*90000*i+%d*300*j' % (a, a))}, 'k': {'x': iv('%d*90000*i+%d*300*j+%d*k' % (a, a, a))}}))
    # P: stepped / inclusive / descending
    for _ in range(2):
        s, a = r.randint(2, 7), r.randint(1, 9)
        C.append(case(nm('step'), 'P_shapes', 'long f(int n){long x=0;for(int i=0;i<n;i+=%d){x+=%d;}return x;}' % (s, a), {'n': [0, B7]}, {'i': {'x': iv('%d*i' % a)}}))
    a = r.randint(1, 5)
    C.append(case(nm('step'), 'P_shapes', 'long f(int n){long x=0;for(int i=1;i<=n;i++){x+=i*%d;}return x;}' % a, {'n': [0, 40000]}, {'i': {'x': iv('%d*40000*i' % a)}}))
    a = r.randint(1, 9)
    C.append(case(nm('step'), 'P_shapes', 'long f(int n){long x=0;for(int i=n;i>0;i--){x+=%d;}return x;}' % a, {'n': [0, B7]}, {'i': {'x': iv('%d*i' % a)}}))
    s, a = r.randint(2, 5), r.randint(1, 9)
    C.append(case(nm('step'), 'P_shapes', 'long f(int n){long x=0;for(int i=n;i>=0;i-=%d){x+=%d;}return x;}' % (s, a), {'n': [0, B7]}, {'i': {'x': iv('%d*i' % a)}}))
    s, a = r.randint(2, 6), r.randint(1, 5)
    C.append(case(nm('step'), 'P_shapes', 'long f(int n,int m){long x=0;for(int i=0;i<n;i+=%d){for(int j=0;j<m;j+=%d){x+=%d;}}return x;}' % (s, s, a), {'n': [0, 3000], 'm': [0, 3000]},
                  {'i': {'x': iv('%d*3000*i' % a)}, 'j': {'x': iv('%d*3000*i+%d*j' % (a, a))}}))
    c = r.randint(1, 250)
    C.append(case(nm('step'), 'P_shapes', 'int f(int n){unsigned char x=0;for(int i=0;i<=n;i+=%d){x+=%d;}return x;}' % (r.randint(2, 9), c), {'n': [0, B7]}, {'i': {'x': iv('255')}}))
    s = r.randint(2, 4)
    C.append(case(nm('step'), 'P_shapes', 'long f(int n){long x=0;for(int i=0;i<n;i+=%d){x+=1;}return x;}' % (s * 100000), {'n': [0, 2000000000]}, {'i': {'x': iv('i')}}, note='index near INT_MAX but representable for n<=2e9'))
    # M: mixed nesting
    a, b, c = r.randint(1, 4), r.randint(1, 4), r.randint(1, 4)
    C.append(case(nm('mix'), 'M_mixed', 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=%d;for(int j=0;j<3;j++){x+=%d;}x+=%d;}return x;}' % (a, b, c), {'n': [0, B7]},
                  {'i': {'x': iv('%d*i' % (a + 3 * b + c))}, 'j': {'x': iv('%d*i+%d+%d*j' % (a + 3 * b + c, a, b))}}))
    a = r.randint(1, 5)
    C.append(case(nm('mix'), 'M_mixed', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int a=0;a<2;a++){x+=%d;}for(int b=0;b<2;b++){x+=%d;}}return x;}' % (a, a + 1), {'n': [0, B7]},
                  {'i': {'x': iv('%d*i' % (2 * a + 2 * (a + 1)))}, 'a': {'x': iv('%d*i+%d*a' % (2 * a + 2 * (a + 1), a))}, 'b': {'x': iv('%d*i+%d+%d*b' % (2 * a + 2 * (a + 1), 2 * a, a + 1))}}))
    a = r.randint(1, 5)
    C.append(case(nm('mix'), 'M_mixed', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=%d;}}for(int k=0;k<n;k++){for(int l=0;l<m;l++){x+=%d;}}return x;}' % (a, a), {'n': [0, 2000], 'm': [0, 2000]},
                  {'i': {'x': iv('%d*2000*i' % a)}, 'j': {'x': iv('%d*2000*i+%d*j' % (a, a))}, 'k': {'x': iv('%d*4000000+%d*2000*k' % (a, a))}, 'l': {'x': iv('%d*4000000+%d*2000*k+%d*l' % (a, a, a))}}))
    c = r.randint(1, 200)
    C.append(case(nm('mix'), 'M_mixed', 'int f(int n){unsigned char x=0;for(int i=0;i<n;i++){x+=%d;for(int j=0;j<n;j++){x+=1;}}return x;}' % c, {'n': [0, 100000]}, {l: {'x': iv('255')} for l in 'ij'}))
    a = r.randint(1, 3)
    C.append(case(nm('mix'), 'M_mixed', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n;j++){x+=%d;}x+=1;}for(int k=0;k<n;k++){x+=2;}return x;}' % a, {'n': [0, 3000]},
                  {'i': {'x': iv('%d*3001*i' % a)}, 'j': {'x': iv('%d*3001*i+%d*j' % (a, a))}, 'k': {'x': iv('%d*9003000+2*k' % a)}}))
    a = r.randint(1, 4)
    C.append(case(nm('mix'), 'M_mixed', 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i<100){x+=%d;}else{x+=1;}for(int j=0;j<2;j++){x+=1;}}return x;}' % a, {'n': [0, B7]},
                  {'i': {'x': iv('%d*i' % (a + 2))}, 'j': {'x': iv('%d*i+%d+j' % (a + 2, a))}}))
    # X: unsafe controls (UB reachable inside the domain)
    big = r.randint(700000000, 1000000000)
    C.append(case(nm('uns'), 'X_unsafe', 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){x+=1;}for(int j=0;j<m;j++){x+=%d;}return x;}' % big, {'n': [0, 100], 'm': [0, 4]}, None, 'unsafe_source_control', 'overflow only in the second sequential loop'))
    C.append(case(nm('uns'), 'X_unsafe', 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){for(int k=0;k<m;k++){x+=100/k;}}}return x;}', {'n': [0, 4], 'm': [0, 4]}, None, 'unsafe_source_control', 'division by zero at the innermost level'))
    C.append(case(nm('uns'), 'X_unsafe', 'long f(int n){long x=0;for(int i=0;i<n;i+=%d){x+=1;}return x;}' % 1000000, {'n': [0, 2147483647]}, None, 'unsafe_source_control', 'index increment overflows INT_MAX'))
    C.append(case(nm('uns'), 'X_unsafe', 'int f(int n,int m){int x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=1<<j;}}return x;}', {'n': [0, 4], 'm': [0, 40]}, None, 'unsafe_source_control', 'shift count out of range'))
    C.append(case(nm('uns'), 'X_unsafe', 'int f(int n,int m){int x=1;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x*=2;}}return x;}', {'n': [0, 4], 'm': [0, 20]}, None, 'unsafe_source_control', 'multiplicative overflow in nest'))
    C.append(case(nm('uns'), 'X_unsafe', 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1;}for(int j=0;j<n;j++){x+=2;}for(int k=0;k<n;k++){x+=%d;}return x;}' % big, {'n': [0, 4]}, None, 'unsafe_source_control', 'overflow only in the third sequential loop'))
    return C
