from pathlib import Path
import pytest
from llmloop.c_frontend import translate_c,translate_file
from llmloop.core import AnalysisError,LoopAnalyzer,PeriodicSystem
from llmloop.expressions import integer_value
EX=Path(__file__).resolve().parents[1]/"examples"
@pytest.mark.parametrize("source,expected",[
    ("alternating.c",lambda n:n),
    ("two_phase.c",lambda n:2*n)
])
def test_c_source_to_symbolic_ir(source,expected):
    obj=translate_file(EX/source)
    a=LoopAnalyzer(PeriodicSystem.load(obj))
    expr=a.exact_trip_count(obj["guard"])
    for n in range(15):
        steps=integer_value(expr,{"n":n})
        assert steps==expected(n)
        assert a.after_steps(steps,{"n":n})==a.concrete(steps,{"n":n})
def test_unsupported_c_is_rejected():
    source="int foo(int n){ int i=0; while(i<n) { i=i*2; } return i; }"
    obj=translate_c(source)
    a=LoopAnalyzer(PeriodicSystem.load(obj))
    with pytest.raises(AnalysisError):a.exact_trip_count(obj["guard"])
    with pytest.raises(AnalysisError):translate_c(
        "int f(int n){int i=0;for(i=0;i<n;i++){i=i+1;} return i;}")
    with pytest.raises(AnalysisError):translate_c(
        "int f(int n){int i=0;while(i<n){int a[3];i=i+1;}return i;}")
