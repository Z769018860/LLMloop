from scripts.nonllm_ablation import graph,analyze
from llmloop.smt_spath import SMTPathGraph
def case(maximum=32):return {'weights':[1,2],'maximum':maximum,'graph':graph([1,2],maximum)}
def test_invariant_only_never_calls_acceleration(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('acceleration called in invariant-only mode')
    monkeypatch.setattr(SMTPathGraph,'try_accelerate',forbidden)
    assert analyze(case(),'invariant_relational')['certified']
    assert not analyze(case(),'invariant_range')['certified']
def test_bounded_mode_retains_universal_exit_frontier():
    assert analyze(case(),'bounded')['certified']
    assert not analyze(case(1000000),'bounded')['certified']
def test_original_range_invariants_can_enable_exact_scc_state():
    assert analyze(case(),'scc_range')['certified']
    assert not analyze(case(),'scc_no_invariants')['certified']
