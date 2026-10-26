import sympy as s
import pytest
from llmloop.api import analyze_request
from llmloop.candidate_synthesis import render
from llmloop.closed_forms import parse_closed

BRANCHES=[
 ('if(i<t){x+=1;}else if(i<2*t){x+=2;}else{x+=3;}',270),
 ('if(i<t && i<2*t){x+=2;}else{x+=3;}',290),
 ('if(i<t || i>=2*t){x+=2;}else{x+=3;}',210),
 ('if(i<t){if(i%2==0){x+=2;}else{x+=3;}}else{x+=4;}',385),
 ('if(i<t){x+=i;}else if(i<2*t){x+=2*i;}else{x+=3*i;}',14615),
 ('if(i==t){x+=7;}else{x+=1;}',106),
 ('if(i<t){x+=1;}else{x+=2;}if(i<2*t){x+=3;}else{x+=4;}',570),
 ('if(2*i+1<t){x+=2;}else{x+=3;}',295),
 ('if(i%2==0){x+=2;}else{x+=3;}',250),
]

@pytest.mark.parametrize('body,value',BRANCHES)
def test_boolean_nested_sequential_and_residue_branch_prefixes(body,value):
    r=analyze_request({'source':'long entry(int n,int t){long x=0;for(int i=0;i<n;i++){'+body+'}return x;}','frontend':'typed_nested','loop_summaries':'auto','parameter_bounds':{'n':[0,100],'t':[0,10]},'inputs':{'n':100,'t':10}})
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    assert r['evaluation']['value']==value
    assert r['summary_synthesis'][0]['candidate_only']
    assert any(x['method']=='disjoint Boolean branch interval/residue prefix candidate' for x in r['summary_synthesis'][0]['mathematical_derivations'])

@pytest.mark.parametrize('body',[
 'if((-i)%2==1){x+=2;}else{x+=3;}', # C remainder differs from mathematical Mod
 'if(i%2==0){x+=2147483647+i;}else{x+=1;}', # candidate cannot erase intermediate overflow
 'if(x<t){x+=2;}else{x+=3;}', # general feedback discovery stays UNKNOWN
 'if(i%9==0){x+=2;}else{x+=3;}', # explicit residue budget
 'if(i*i<t){x+=2;}else{x+=3;}', # nonlinear guard not guessed
])
def test_bad_or_unsupported_candidates_never_become_proof(body):
    r=analyze_request({'source':'long entry(int n,int t){long x=0;for(int i=0;i<n;i++){'+body+'}return x;}','frontend':'typed_nested','loop_summaries':'auto','parameter_bounds':{'n':[0,100],'t':[0,10]}})
    assert r['status']=='UNKNOWN',r
    assert not r.get('c_overflow_verified',False)

@pytest.mark.parametrize('func',[s.floor,s.ceiling])
def test_floor_ceiling_rational_render_keeps_negative_and_positive_values(func):
    k=s.Symbol('k',integer=True);expr=func((k-1)/2);text=render(expr,{})
    parsed=parse_closed(text,{'k':k})
    for n in range(-10,11):assert parsed.subs(k,n)==expr.subs(k,n),(text,n)

CONTROL_BODY='if(phase==0){phase=2;sum+=i;}else if(phase==2){phase=5;sum+=2*i;}else{phase=0;sum+=3*i;}'

@pytest.mark.parametrize('body,initial,n,expected',[
 (CONTROL_BODY,0,1000000,999998666667),
 ('if(phase==9){phase=0;sum+=7;}else if(phase==0){phase=2;sum+=2;}else{phase=0;sum+=3;}',9,1000000,2500004),
 ('if(phase==0){phase=1;sum+=2;}else{phase=0;sum+=3;}',0,1000000,2500000),
])
def test_state_dependent_finite_control_orbits_with_independent_induction(body,initial,n,expected):
    source=f'long long entry(int n){{int phase={initial};long long sum=0;for(int i=0;i<n;i++){{{body}}}return sum;}}'
    r=analyze_request({'source':source,'frontend':'typed_nested','loop_summaries':'auto','parameter_bounds':{'n':[0,n]},'inputs':{'n':n}})
    assert r['status']=='PROVED_DEFINED_TYPED_C_NESTED',r
    assert r['evaluation']['value']==expected
    e=r['summary_synthesis'][0]['mathematical_derivations'][0]
    assert e['method']=='finite state-dependent control orbit with polynomial accumulator prefixes' and e['candidate_only']

@pytest.mark.parametrize('body',[
 'if(phase==0){phase=(unsigned char)256;sum+=1;}else{phase=0;sum+=2;}',
 'if(phase>=0){phase++;sum++;}else{sum+=2;}',
])
def test_control_orbit_candidate_mismatch_or_exploration_frontier_stays_unknown(body):
    r=analyze_request({'source':f'long long entry(int n){{int phase=0;long long sum=0;for(int i=0;i<n;i++){{{body}}}return sum;}}','frontend':'typed_nested','loop_summaries':'auto','parameter_bounds':{'n':[0,1000]}})
    assert r['status']=='UNKNOWN',r


def test_residue_certificate_exhaustive_and_wrong_claim_rejected():
    import z3
    from llmloop.residue_certificate import prove_residues
    k=z3.Int('residue_test_counter')
    c=prove_residues(k>=0,3*(k/3)+k%3==k,{'k':k})
    assert c and c['period']==3 and len(c['cases'])==3
    assert prove_residues(k>=0,k%3==0,{'k':k}) is None
