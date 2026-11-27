"""Frozen v0.62 held-out corpus for the live-LLM trajectory-proposal study.

Programs were written before any model output was collected and are disjoint
by source from the v0.59/v0.60 development fixtures used in the prompt
examples. `reference` is a maintainer-written candidate used ONLY to classify a
program as provable-by-some-candidate (corpus validation); it is never shown to
a model and never used for scoring a model.
"""


def P(name, source, backend, bounds, inputs, role, reference=None, note=''):
    return dict(name=name, source=source, backend=backend, parameter_bounds=bounds,
                inputs=inputs, role=role, reference=reference, note=note)


CORPUS = [
 P('h_countdown', 'long f(int n){long x=n;for(int i=0;i<n;i++){x--;}return x;}',
   'typed_recurrence', {'n': [0, 20000000]}, {'n': 20000000}, 'provable',
   {'x': 'n-i'}),
 P('h_sum_index', 'long f(int n){long s=0;for(int i=0;i<n;i++){s+=i;}return s;}',
   'typed_recurrence', {'n': [0, 100000]}, {'n': 100000}, 'provable',
   {'s': 'i*(i-1)//2'}),
 P('h_u8_step3', 'int f(int n){unsigned char a=0;for(int i=0;i<n;i++){a+=3;}return a;}',
   'typed_recurrence', {'n': [0, 20000000]}, {'n': 20000000}, 'provable',
   {'a': '(3*i)%256'}),
 P('h_two_counters', 'long f(int n){int a=0;long b=0;for(int i=0;i<n;i++){a+=2;b+=a;}return b+a;}',
   'typed_recurrence', {'n': [0, 30000]}, {'n': 30000}, 'provable',
   {'a': '2*i', 'b': 'i*(i+1)'}),
 P('h_alternating', 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i%2==0){x+=1;}else{x+=3;}}return x;}',
   'typed_recurrence', {'n': [0, 20000000]}, {'n': 20000000}, 'provable',
   {'x': '2*i-(i%2)'}),
 P('h_floor_zero', 'int f(int n){int x=1000000;for(int i=0;i<n;i++){if(x>0){x--;}}return x;}',
   'typed_recurrence', {'n': [0, 2000000]}, {'n': 1500000}, 'provable',
   {'x': 'Max(1000000-i,0)'}),
 P('h_toggle', 'int f(int n){unsigned char b=0;for(int i=0;i<n;i++){b^=1;}return b;}',
   'typed_recurrence', {'n': [0, 20000001]}, {'n': 20000001}, 'provable',
   {'b': 'i%2'}, 'bitwise xor body; DSL has no xor'),
 P('h_threshold_step', 'long f(int n){long x=0;for(int i=0;i<n;i++){if(i<100){x+=2;}else{x+=1;}}return x;}',
   'typed_recurrence', {'n': [0, 20000000]}, {'n': 20000000}, 'provable',
   {'x': 'i+Min(i,100)'}),
 P('h_u16_triangular', 'int f(int n){unsigned short s=0;for(int i=0;i<n;i++){s+=i;}return s;}',
   'typed_recurrence', {'n': [0, 60000]}, {'n': 60000}, 'provable',
   {'s': '(i*(i-1)//2)%65536'}),
 P('h_mod3_ramp', 'long f(int n){long x=0;for(int i=0;i<n;i++){x+=i%3;}return x;}',
   'typed_recurrence', {'n': [0, 20000000]}, {'n': 20000000}, 'hard_unconfirmed',
   None, 'two maintainer formulas (3*(i//3)+(i%3)*((i%3)-1)//2 and 3*(i//3)+(i%3)//2) both hit the 5 s solver timeout during corpus validation; a correct closed form exists but certification is unconfirmed'),
 P('h_nest_const', 'long f(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x+=2;}}return x;}',
   'typed_nested', {'n': [0, 4000], 'm': [0, 4000]}, {'n': 4000, 'm': 4000}, 'provable',
   {'i': {'x': '2*i*m'}, 'j': {'x': 'entry("x")+2*j'}}),
 P('h_nest_triangle', 'long f(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<i;j++){x++;}}return x;}',
   'typed_nested', {'n': [0, 5000]}, {'n': 5000}, 'provable',
   {'i': {'x': 'i*(i-1)//2'}, 'j': {'x': 'entry("x")+j'}}),
 P('h_nest_u8wrap', 'int f(int n){unsigned char c=0;for(int i=0;i<n;i++){for(int j=0;j<4;j++){c+=1;}}return c;}',
   'typed_nested', {'n': [0, 5000000]}, {'n': 5000000}, 'provable',
   {'i': {'c': '(4*i)%256'}, 'j': {'c': '(entry("c")+j)%256'}}),
 P('h_fib_mod', 'int f(int n){unsigned char a=0,b=1;for(int i=0;i<n;i++){unsigned char t=a+b;a=b;b=t;}return a;}',
   'typed_recurrence', {'n': [0, 1000000]}, {'n': 1000000}, 'frontier_no_known_closed_form',
   None, 'Fibonacci mod 256: period 384, no polynomial/DSL closed form known to maintainers'),
 P('h_exp_mod', 'unsigned f(int n){unsigned x=1;for(int i=0;i<n;i++){x*=3;}return x%1000;}',
   'typed_recurrence', {'n': [0, 1000000]}, {'n': 1000000}, 'frontier_no_known_closed_form',
   None, 'needs variable exponent; unsupported by DSL'),
 P('h_overflow_accum', 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=1000000000;}return x;}',
   'typed_recurrence', {'n': [0, 5]}, {'n': 2}, 'unsafe_source_control',
   None, 'signed overflow reachable at n>=3; no candidate may be certified'),
 P('h_div_zero', 'int f(int n){int x=0;for(int i=0;i<n;i++){x+=10/i;}return x;}',
   'typed_recurrence', {'n': [1, 10]}, {'n': 5}, 'unsafe_source_control',
   None, 'division by zero at i=0; no candidate may be certified'),
]
