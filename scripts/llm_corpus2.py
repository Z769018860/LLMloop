"""Procedurally generated v0.63 corpora (random constants, fixed seed).

Constants are drawn from a seeded PRNG after the models' training cutoffs, so
exact programs cannot have been memorised. Structure families are chosen by us.
`reference` is a generator-known closed form used only to classify a program as
`provable` (verifier certifies it) or `hard_unconfirmed` (verifier does not,
within budget); models never see it.
"""
import random

SEED = 20261108


def case(name, family, source, backend, bounds, inputs, ref=None, role=None, note=''):
    return dict(name=name, family=family, source=source, backend=backend, parameter_bounds=bounds,
                inputs=inputs, reference=ref, role=role, note=note)


def build():
    r = random.Random(SEED)
    C = []
    k = 0

    def nm(fam):
        nonlocal k
        k += 1
        return '%s%02d' % (fam, k)
    N7 = {'n': [0, 10000000]}; I7 = {'n': 10000000}
    # A: wrap counters (style overlaps the worked prompt examples)
    for t, mod, lo, hi in [('unsigned char', 256, 1, 250), ('unsigned char', 256, 1, 250), ('unsigned short', 65536, 100, 9000), ('unsigned short', 65536, 100, 9000)]:
        c = r.randint(lo, hi)
        C.append(case(nm('wrap'), 'A_wrap', 'int f(int n){%s a=0;for(int i=0;i<n;i++){a+=%d;}return a;}' % (t, c),
                      'typed_recurrence', N7, I7, {'a': '(%d*i)%%%d' % (c, mod)}))
    for _ in range(2):
        c1, c2 = r.randint(1, 250), r.randint(2, 40)
        C.append(case(nm('wrap'), 'A_wrap', 'long f(int n){unsigned char a=0;long y=0;for(int i=0;i<n;i++){a+=%d;y+=%d;}return y+a;}' % (c1, c2),
                      'typed_recurrence', N7, I7, {'a': '(%d*i)%%256' % c1, 'y': '%d*i' % c2}))
    # B: piecewise / saturation / mod-select
    for _ in range(2):
        T, a, b = r.randint(10, 500), r.randint(1, 9), r.randint(1, 9)
        while b == a: b = r.randint(1, 9)
        C.append(case(nm('piece'), 'B_piecewise', 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i<%d){x+=%d;}else{x+=%d;}}return x;}' % (T, a, b),
                      'typed_recurrence', N7, I7, {'x': '%d*Min(i,%d)+%d*Max(i-%d,0)' % (a, T, b, T)}))
    for _ in range(2):
        s0 = r.randint(0, 100); L = r.randint(150, 255)
        C.append(case(nm('piece'), 'B_piecewise', 'int f(int n){unsigned char x=%d;for(int i=0;i<n;i++){if(x<%d){x++;}}return x;}' % (s0, L),
                      'typed_recurrence', N7, I7, {'x': 'Min(%d+i,%d)' % (s0, L)}))
    for _ in range(2):
        K = r.randint(1000, 90000); d = r.randint(2, 9)
        C.append(case(nm('piece'), 'B_piecewise', 'int f(int n){int x=%d;for(int i=0;i<n;i++){if(x>=%d){x-=%d;}}return x;}' % (K, d, d),
                      'typed_recurrence', N7, I7, {'x': '%d-%d*Min(i,%d)' % (K, d, K // d)}))
    for _ in range(2):
        m = r.randint(3, 9); a, b = r.randint(2, 9), r.randint(1, 4)
        C.append(case(nm('piece'), 'B_piecewise', 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i%%%d==0){x+=%d;}else{x+=%d;}}return x;}' % (m, a, b),
                      'typed_recurrence', N7, I7, {'x': '%d*i+%d*((i+%d)//%d)' % (b, a - b, m - 1, m)}))
    # C: periodic phases and bitwise
    for _ in range(4):
        m = r.randint(3, 6); vals = [r.randint(1, 9) for _ in range(m)]
        chain = ''.join(('if(i%%%d==%d){x+=%d;}' if j == 0 else 'else if(i%%%d==%d){x+=%d;}') % (m, j, vals[j]) for j in range(m))
        pre = [0]
        for v in vals: pre.append(pre[-1] + v)
        expr = '0'
        for j in range(m - 1, -1, -1):
            expr = '(%d if i%%%d==%d else %s)' % (pre[j], m, j, expr) if j < m - 1 else '%d' % pre[j]
        C.append(case(nm('per'), 'C_periodic', 'long f(int n){long x=0;for(int i=0;i<n;i++){%s}return x;}' % chain,
                      'typed_recurrence', N7, I7, {'x': '%d*(i//%d)+%s' % (sum(vals), m, expr)}))
    for _ in range(2):
        c = r.randint(2, 255)
        C.append(case(nm('xor'), 'C_periodic', 'int f(int n){unsigned char b=0;for(int i=0;i<n;i++){b^=%d;}return b;}' % c,
                      'typed_recurrence', {'n': [0, 10000001]}, {'n': 10000001}, {'b': '(i%%2)*%d' % c}))
    # D: polynomial / coupled
    c = r.randint(1, 7)
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){long s=0;for(int i=0;i<n;i++){s+=%d*i;}return s;}' % c,
                  'typed_recurrence', {'n': [0, 20000]}, {'n': 20000}, {'s': '%d*(i*(i-1)//2)' % c}))
    c1 = r.randint(1, 6)
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){int a=0;long b=0;for(int i=0;i<n;i++){a+=%d;b+=a;}return b;}' % c1,
                  'typed_recurrence', {'n': [0, 20000]}, {'n': 20000}, {'a': '%d*i' % c1, 'b': '%d*(i*(i+1)//2)' % c1}))
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){long s=0;for(int i=0;i<n;i++){s+=i*i;}return s;}',
                  'typed_recurrence', {'n': [0, 40000]}, {'n': 40000}, {'s': 'i*(i-1)*(2*i-1)//6'}))
    m5 = r.choice([5, 7])
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){long s=0;for(int i=0;i<n;i++){s+=i%%%d;}return s;}' % m5,
                  'typed_recurrence', N7, I7, {'s': '%d*(i//%d)+(i%%%d)*((i%%%d)-1)//2' % (m5 * (m5 - 1) // 2, m5, m5, m5)}))
    ca, cb = r.randint(2, 6), r.randint(1, 5)
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){long a=0,b=0;for(int i=0;i<n;i++){a+=%d;b+=a+%d;}return b;}' % (ca, cb),
                  'typed_recurrence', {'n': [0, 20000]}, {'n': 20000}, {'a': '%d*i' % ca, 'b': '%d*(i*(i+1)//2)+%d*i' % (ca, cb)}))
    C.append(case(nm('poly'), 'D_polynomial', 'long f(int n){int a=0;int b=0;for(int i=0;i<n;i++){a++;b+=a%3;}return b;}',
                  'typed_recurrence', {'n': [0, 5000000]}, {'n': 5000000}, {'a': 'i', 'b': '3*(i//3)+(i%3)*((i%3)+1)//2'}))
    # E: nested
    c = r.randint(1, 5)
    C.append(case(nm('nest'), 'E_nested', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=%d;}}return x;}' % c,
                  'typed_nested', {'n': [0, 3000], 'm': [0, 3000]}, {'n': 3000, 'm': 3000},
                  {'i': {'x': '%d*i*m' % c}, 'j': {'x': 'entry("x")+%d*j' % c}}))
    c = r.randint(1, 5)
    C.append(case(nm('nest'), 'E_nested', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<i;j++){x+=%d;}}return x;}' % c,
                  'typed_nested', {'n': [0, 4000]}, {'n': 4000},
                  {'i': {'x': '%d*(i*(i-1)//2)' % c}, 'j': {'x': 'entry("x")+%d*j' % c}}))
    C.append(case(nm('nest'), 'E_nested', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<i+1;j++){x++;}}return x;}',
                  'typed_nested', {'n': [0, 4000]}, {'n': 4000},
                  {'i': {'x': 'i*(i+1)//2'}, 'j': {'x': 'entry("x")+j'}}))
    kk, d = r.randint(2, 9), r.randint(1, 60)
    C.append(case(nm('nest'), 'E_nested', 'int f(int n){unsigned char c=0;for(int i=0;i<n;i++){for(int j=0;j<%d;j++){c+=%d;}}return c;}' % (kk, d),
                  'typed_nested', {'n': [0, 3000000]}, {'n': 3000000},
                  {'i': {'c': '(%d*i)%%256' % (d * kk)}, 'j': {'c': '(entry("c")+%d*j)%%256' % d}}))
    C.append(case(nm('nest'), 'E_nested', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=j;}}return x;}',
                  'typed_nested', {'n': [0, 2000], 'm': [0, 2000]}, {'n': 2000, 'm': 2000},
                  {'i': {'x': 'i*(m*(m-1)//2)'}, 'j': {'x': 'entry("x")+j*(j-1)//2'}}))
    a, b = r.randint(1, 5), r.randint(1, 5)
    C.append(case(nm('nest'), 'E_nested', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){x+=%d;for(int j=0;j<m;j++){x+=%d;}}return x;}' % (a, b),
                  'typed_nested', {'n': [0, 3000], 'm': [0, 3000]}, {'n': 3000, 'm': 3000},
                  {'i': {'x': 'i*(%d+%d*m)' % (a, b)}, 'j': {'x': 'entry("x")+%d*j' % b}}))
    C.append(case(nm('nest'), 'E_nested', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<n-i;j++){x++;}}return x;}',
                  'typed_nested', {'n': [0, 4000]}, {'n': 4000},
                  {'i': {'x': 'i*n-i*(i-1)//2'}, 'j': {'x': 'entry("x")+j'}}))
    d = r.randint(1, 9)
    C.append(case(nm('nest'), 'E_nested', 'int f(int n){unsigned short c=0;for(int i=0;i<n;i++){for(int j=0;j<%d;j++){c+=%d;}}return c;}' % (kk, 1000 + d),
                  'typed_nested', {'n': [0, 3000000]}, {'n': 3000000},
                  {'i': {'c': '(%d*i)%%65536' % ((1000 + d) * kk)}, 'j': {'c': '(entry("c")+%d*j)%%65536' % (1000 + d)}}))
    # F: frontier, no DSL-expressible closed form known to us
    F = [('unsigned char a=0,b=1;for(int i=0;i<n;i++){unsigned char t=a+b;a=b;b=t;}return a;', 'fibonacci mod 256'),
         ('unsigned char x=%d;for(int i=0;i<n;i++){x=x*5+%d;}return x;' % (r.randint(1, 9), r.randint(1, 9)), 'LCG mod 256'),
         ('unsigned x=1;for(int i=0;i<n;i++){x*=%d;}return x%%1000;' % r.choice([3, 7, 11]), 'power mod 2^32'),
         ('unsigned x=%d;for(int i=0;i<n;i++){x=x*x+1;}return x%%1000;' % r.randint(1, 9), 'quadratic map mod 2^32'),
         ('int a=%d;for(int i=0;i<n;i++){a=(a*7+3)%%101;}return a;' % r.randint(1, 50), 'LCG mod prime'),
         ('unsigned char x=%d;for(int i=0;i<n;i++){x^=(unsigned char)(x<<1);}return x;' % r.randint(1, 9), 'xorshift'),
         ('long x=1;for(int i=0;i<n;i++){if(x%2==0){x=x/2;}else{x=3*x+1;if(x>1000000){x=1;}}}return x;', 'collatz-like'),
         ('unsigned x=%d;for(int i=0;i<n;i++){x=x+(x>>3)+1;}return x%%1000;' % r.randint(1, 9), 'shift-add recurrence')]
    for body, why in F:
        C.append(case(nm('hard'), 'F_frontier', 'long f(int n){' + body + '}', 'typed_recurrence',
                      {'n': [0, 1000000]}, {'n': 1000000}, None, 'frontier_no_known_closed_form', why))
    # G: unsafe source controls (any certified candidate would be a soundness failure)
    big = r.randint(700000000, 1000000000)
    G = [('int x=0;for(int i=0;i<n;i++){x+=%d;}return x;' % big, {'n': [0, 6]}, {'n': 2}, 'overflow add'),
         ('int x=1;for(int i=0;i<n;i++){x*=2;}return x;', {'n': [0, 40]}, {'n': 5}, 'overflow mul'),
         ('int x=0;for(int i=0;i<n;i++){x+=1<<i;}return x;', {'n': [0, 40]}, {'n': 5}, 'shift count out of range'),
         ('int x=0;for(int i=0;i<n;i++){x+=100/(i-%d);}return x;' % r.randint(2, 7), {'n': [0, 10]}, {'n': 1}, 'division by zero mid-loop'),
         ('int x=0;for(int i=1;i<n;i++){x+=7%%(i%%%d);}return x;' % r.randint(2, 4), {'n': [0, 10]}, {'n': 2}, 'modulo by zero'),
         ('long x=0;for(int i=0;i<n;i++){x+=(unsigned char)i*(1<<%d);}return (int)x;' % r.randint(24, 28), {'n': [0, 300]}, {'n': 2}, 'narrowing/overflow in conversion')]
    for body, bnd, inp, why in G:
        C.append(case(nm('unsafe'), 'G_unsafe', 'long f(int n){' + body + '}', 'typed_recurrence', bnd, inp, None, 'unsafe_source_control', why))
    return C


def build_cycles():
    r = random.Random(SEED + 1)
    out = []
    for idx in range(30):
        k = r.choice([2, 2, 3, 3, 4, 5, 6, 8])
        nv = r.choice([1, 2, 2, 3])
        vars_ = ['x', 'y', 'z'][:nv]
        param = r.random() < 0.25
        phases = []
        for _ in range(k):
            ups = {}
            for vi, v in enumerate(vars_):
                if r.random() < (0.9 if vi == 0 else 0.5):
                    terms = [v]
                    for dep in vars_[:vi]:
                        if r.random() < 0.6:
                            terms.append(('%d*%s' % (r.randint(1, 3), dep)) if r.random() < .4 else dep)
                    if param and r.random() < 0.4:
                        terms.append('n')
                    terms.append(str(r.randint(0, 9)))
                    ups[v] = ' + '.join(terms)
            if not ups:
                ups = {vars_[0]: vars_[0] + ' + 1'}
            phases.append({'updates': ups})
        init = {v: r.randint(0, 5) for v in vars_}
        out.append({'name': 'g%02d_p%d_v%d%s' % (idx, k, nv, 'n' if param else ''),
                    'obj': {'kind': 'loop', 'name': 'g%02d' % idx, 'parameters': ['n'] if param else [], 'state': init, 'phases': phases},
                    'period': k})
    return out
