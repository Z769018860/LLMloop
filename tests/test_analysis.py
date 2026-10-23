import json
from pathlib import Path
import pytest
import sympy as s
from llmloop.core import LoopAnalyzer,PeriodicSystem,AnalysisError
from llmloop.nested import NestedAnalyzer
from llmloop.expressions import parse,ExpressionError,integer_value
from llmloop.cli import main
EX=Path(__file__).resolve().parents[1]/"examples"
def load(name):return json.loads((EX/name).read_text())
def test_alternating():
    obj=load("alternating.json")
    a=LoopAnalyzer(PeriodicSystem.load(obj))
    expr=a.exact_trip_count(obj["guard"])
    assert a.verify_cycle_candidate({"i":"i+2","p":"p","x":"x+4"})["accepted"]
    assert not a.verify_cycle_candidate({"i":"i+2","p":"p","x":"x+5"})["accepted"]
    for n in range(51):
        env={"n":n}
        k=integer_value(expr,env)
        assert k==n
        assert a.after_steps(k,env)==a.concrete(k,env)
        assert a.after_steps(k,env)=={"i":n,"p":n%2,"x":4*(n//2)+n%2}
def test_two_phase():
    obj=load("progress_every_two.json")
    a=LoopAnalyzer(PeriodicSystem.load(obj))
    formula=a.exact_trip_count(obj["guard"])
    for n in range(101):
        k=integer_value(formula,{"n":n})
        assert k==2*n
        assert a.after_steps(k,{"n":n})==a.concrete(k,{"n":n})
def test_nested():
    a=NestedAnalyzer(load("nested_triangular.json"))
    assert str(a.total)=="n*(n + 1)/2"
    for n in range(21):
        output=a.run({"n":n})
        steps=n*(n+1)//2
        assert output["total_inner_steps"]==steps
        assert output["final_state"]==a.concrete({"n":n})
        assert output["final_state"]["x"]==4*(steps//2)+steps%2
def test_bad_inputs():
    a=LoopAnalyzer(PeriodicSystem.load(load("alternating.json")))
    with pytest.raises(AnalysisError):a.after_steps(2,{})
def test_non_affine_and_wrong_phase():
    obj=load("alternating.json")
    obj["phases"][0]["updates"]["x"]="x*x"
    with pytest.raises(AnalysisError,match="Non-affine"):
        LoopAnalyzer(PeriodicSystem.load(obj))
    obj=load("alternating.json")
    obj["phases"][0]["when"]="p == 1"
    with pytest.raises(AnalysisError,match="phase guard"):
        LoopAnalyzer(PeriodicSystem.load(obj))
def test_no_progress():
    obj=load("alternating.json")
    for phase in obj["phases"]: phase["updates"]["i"]="i"
    a=LoopAnalyzer(PeriodicSystem.load(obj))
    with pytest.raises(AnalysisError,match="No proven finite progress"):
        a.exact_trip_count(obj["guard"])
def test_safe_parser():
    n=s.Symbol("n",integer=True)
    for expr in ["__import__('os').system('id')","n.real","open('f')","(lambda:0)()"]:
        with pytest.raises(ExpressionError):parse(expr,{"n":n})
    assert integer_value(parse("n // 2",{"n":n}),{"n":5})==2
def test_cli(tmp_path):
    output=tmp_path/"out.json"
    assert main(["analyze",str(EX/"alternating.json"),"--input","n=5",
                 "--check-range","0:15","--output",str(output)])==0
    report=json.loads(output.read_text())
    assert report["evaluation"]["final_state"]["x"]==9
    assert report["concrete_checks"]["passed"]==16
    assert main(["analyze",str(EX/"nested_triangular.json"),
                 "--input","n=4","--check-range","0:10"])==0
