"""Isolated solver contexts preserve counterexamples and fail-closed results."""
import pytest
import z3

from llmloop.guarded_recurrence import ProofFailure
from llmloop.typed_cfg_heap import TypedCFGHeap


def model():
    return TypedCFGHeap('int entry(int n){return n;}',function='entry',parameter_bounds={'n':[0,10]})


def test_isolated_query_counterexample_retains_source_parameter_value():
    m=model();n=m.witness['n']
    with pytest.raises(ProofFailure) as caught:m.check('cross-context counterexample',n==7,n==0)
    failure=caught.value
    assert failure.answer==z3.sat and failure.witness=={'n':'7'}


def test_isolated_query_unknown_does_not_use_a_model_or_certify(monkeypatch):
    m=model();count=len(m.checks)
    class Unknown:
        def __init__(self,*,ctx):self.ctx=ctx;assert ctx is not z3.main_ctx()
        def set(self,**options):assert options=={'timeout':5000}
        def add(self,*terms):assert all(term.ctx is self.ctx for term in terms)
        def check(self):return z3.unknown
        def reason_unknown(self):return 'controlled isolated unknown'
        def model(self):raise AssertionError('UNKNOWN must not use a model')
    monkeypatch.setattr(z3,'Solver',Unknown)
    with pytest.raises(ProofFailure) as caught:m.check('unknown',m.witness['n']>=0,m.witness['n']==0)
    assert caught.value.answer==z3.unknown and caught.value.reason=='controlled isolated unknown'
    assert caught.value.witness is None and len(m.checks)==count
