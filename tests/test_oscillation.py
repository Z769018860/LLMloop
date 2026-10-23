import json
from copy import deepcopy
from pathlib import Path
import pytest
from llmloop.oscillation import OscillationAnalyzer, OscillationError
from llmloop.oscillation_c import translate_oscillation_c
from llmloop.oscillation_cli import main as json_main
from llmloop.oscillation_c_cli import main as c_main

E=Path(__file__).resolve().parents[1]/'examples'
BASE=json.loads((E/'oscillation_threshold.json').read_text())

def check_equal(a,n):
    fast,slow=a.run({'n':n}),a.concrete({'n':n})
    assert (fast['trip_count'],fast['final_state'])==(slow['trip_count'],slow['final_state'])

def test_interval_cycle_and_scc():
    a=OscillationAnalyzer(BASE)
    out=a.summary()
    assert out['interval']==[0,6]
    assert out['period']==7
    assert out['spath_sccs']==[['at_or_above','below']]
    assert out['below_steps_per_period']==5
    assert out['at_or_above_steps_per_period']==2
    assert out['progress_per_period']==23
    for n in range(-10,310):check_equal(a,n)

def test_preperiod_and_parameter_initials():
    for below in (1,2,3,7,13):
        for above in (1,2,5,8):
            for start in (-113,-1,0,1,5,20,257):
                obj=deepcopy(BASE)
                obj['branches']['below']['x']='x + '+str(below)
                obj['branches']['at_or_above']['x']='x - '+str(above)
                obj['state']['x']=start
                a=OscillationAnalyzer(obj)
                for n in (0,1,3,5,7,15,30,80,300):check_equal(a,n)

def test_zero_progress_proves_nontermination():
    data=deepcopy(BASE)
    data['branches']['below']['i']='i'
    data['branches']['at_or_above']['i']='i'
    a=OscillationAnalyzer(data)
    assert a.run({'n':0})['trip_count']==0
    with pytest.raises(OscillationError,match='NONTERMINATING'):
        a.run({'n':10})

def test_input_overflow_is_not_claimed():
    data=deepcopy(BASE)
    data['state']['x']='n'
    a=OscillationAnalyzer(data)
    check_equal(a,15)
    assert a.summary()['semantics'].startswith('mathematical integers')

def test_reject_non_affine_and_bad_drift():
    for name,update in [('x','2*x'),('i','i - 1'),('y','x + y')]:
        data=deepcopy(BASE)
        data['branches']['below'][name]=update
        with pytest.raises(OscillationError):OscillationAnalyzer(data)

def test_c_frontend_equivalence():
    data=translate_oscillation_c((E/'oscillation_threshold.c').read_text())
    a=OscillationAnalyzer(data)
    for n in range(0,150):check_equal(a,n)
    assert data['threshold']==5
    assert c_main([str(E/'oscillation_threshold.c'),'--input','n=77','--check-range','0:20'])==0

def test_reject_unsafe_c():
    src=(E/'oscillation_threshold.c').read_text()
    with pytest.raises((OscillationError,ValueError)):
        translate_oscillation_c(src.replace('if (x < 5)','if (x * x < 5)'))
    with pytest.raises((OscillationError,ValueError)):
        OscillationAnalyzer(translate_oscillation_c(src.replace('x = x + 2','x = x * 2')))

def test_cli():
    assert json_main([str(E/'oscillation_threshold.json'),'--input','n=88','--check-range','0:40'])==0

def test_extremely_large_iteration_bound_without_unrolling():
    a=OscillationAnalyzer(BASE)
    output=a.run({'n':10**15})
    assert output['trip_count']>10**14
    state=output['final_state']
    assert state['i']>=10**15
    prev=a.after_steps(output['trip_count']-1,{'n':10**15})
    assert prev['i']<10**15
