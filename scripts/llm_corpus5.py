"""v0.69 if-loop corpus: loops inside if/else branches (branch-selected loops, state-dependent guards, loops under a guard inside loop bodies). X_unsafe: UB for exactly one parameter value; confirmed natively (UBSan)."""
import random

SEED = 20261215


def case(name, family, source, bounds, ref=None, role=None, trigger=None):
    inputs = {k: hi for k, (lo, hi) in bounds.items()}
    return dict(name=name, family=family, source=source, backend='typed_invariant_tree', parameter_bounds=bounds, inputs=inputs, reference=ref, role=role, trigger=trigger)


def iv(hi, lo='0'): return {'lo': lo, 'hi': hi}


def build(seed=SEED):
    r = random.Random(seed); C = []; k = [0]
    def nm(f):
        k[0] += 1; return '%s%02d' % (f, k[0])
    B7 = 10000000
    for _ in range(4):
        a, b, T = r.randint(1, 9), r.randint(1, 9), r.randint(3, 15)
        C.append(case(nm('br'), 'I_branch', 'long f(int n,int m){long x=0;if(m>%d){for(int i=0;i<n;i++){x+=%d;}}else{for(int j=0;j<n;j++){x+=%d;}}return x;}' % (T, a, b), {'n': [0, B7], 'm': [0, 20]},
                      {'i': {'x': iv('%d*i' % a)}, 'j': {'x': iv('%d*j' % b)}}))
    for _ in range(2):
        a, b, T = r.randint(1, 250), r.randint(1, 250), r.randint(3, 15)
        C.append(case(nm('br'), 'I_branch', 'int f(int n,int m){unsigned char x=0;if(m>%d){for(int i=0;i<n;i++){x+=%d;}}else{for(int j=0;j<n;j++){x+=%d;}}return x;}' % (T, a, b), {'n': [0, B7], 'm': [0, 20]},
                      {'i': {'x': iv('255')}, 'j': {'x': iv('255')}}))
    for _ in range(5):
        a, b, T = r.randint(1, 9), r.randint(1, 9), r.randint(3, 50)
        C.append(case(nm('gd'), 'I_guard', 'long f(int n){long x=0;long y=0;for(int i=0;i<n;i++){x+=%d;}if(x>%d){for(int j=0;j<n;j++){y+=%d;}}return x+y;}' % (a, T, b), {'n': [0, 1000000]},
                      {'i': {'x': iv('%d*i' % a), 'y': iv('0')}, 'j': {'x': iv('%d*n' % a), 'y': iv('%d*j' % b)}}))
    for _ in range(5):
        a, mod = r.randint(1, 9), r.randint(2, 4)
        C.append(case(nm('ns'), 'I_nested', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){if(i%%%d==0){for(int j=0;j<m;j++){x+=%d;}}}return x;}' % (mod, a), {'n': [0, 1000], 'm': [0, 1000]},
                      {'i': {'x': iv('%d*m*i' % a)}, 'j': {'x': iv('%d*m*i+%d*j' % (a, a))}}))
    for _ in range(3):
        a, b, T = r.randint(1, 9), r.randint(1, 9), r.randint(3, 15)
        C.append(case(nm('el'), 'I_noelse', 'long f(int n,int m){long x=0;if(m>%d){for(int i=0;i<n;i++){x+=%d;}}for(int j=0;j<n;j++){x+=%d;}return x;}' % (T, a, b), {'n': [0, B7], 'm': [0, 20]},
                      {'i': {'x': iv('%d*i' % a)}, 'j': {'x': iv('%d*n+%d*j' % (a, b))}}))
    # unsafe controls: division by (m - T) is zero exactly at m == T
    T = [r.randint(5, 15) for _ in range(5)]
    U = ['long f(int n,int m){long x=0;if(m>%d){for(int i=0;i<n;i++){x+=2;}}else{for(int j=0;j<n;j++){x+=3;}}return 100/(m-%d);}',
         'long f(int n,int m){long x=0;if(m>3){for(int i=0;i<n;i++){x+=2;}}return x+100/(m-%d);}',
         'long f(int n,int m){long x=0;for(int i=0;i<n;i++){if(i%%2==0){for(int j=0;j<m;j++){x+=1;}}}return x+100/(m-%d);}',
         'long f(int n,int m){long x=0;if(m>%d){for(int i=0;i<n;i++){x+=2;}}for(int j=0;j<n;j++){x+=1;}return x+100/(m-%d);}',
         'long f(int n,int m){long x=0;long y=0;for(int i=0;i<n;i++){x+=1;}if(x>2){for(int j=0;j<n;j++){y+=2;}}return y+100/(m-%d);}']
    for i, (tpl, t) in enumerate(zip(U, T)):
        src = tpl % ((t, t) if tpl.count('%d') == 2 else (t,))
        C.append(case(nm('uns'), 'X_unsafe', src, {'n': [0, 1000], 'm': [0, 20]}, role='unsafe_source_control', trigger={'n': 5, 'm': t}))
    return C
