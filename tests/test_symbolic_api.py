from pathlib import Path
import json
import pytest
from llmloop.api import analyze_request
from llmloop.symbolic_cli import main


def test_special_ir_api_and_typed_short_circuit():
    result=analyze_request({'ir':{'kind':'affine_recurrence','state':{'x':0},'updates':{'x':'2*x+1'}}})
    assert result['status']=='CERTIFIED_AFFINE_RECURRENCE_CLOSED_FORM'
    assert analyze_request({'ir':{'kind':'affine_recurrence','state':{'x':0},'updates':{}},'verify_steps':3})['status']=='UNKNOWN'
    division={'op':'/','args':[{'literal':'1'},{'literal':'0'}]}
    report=analyze_request({'ir':{'kind':'c_integer_expression','expression':{'op':'&&','args':[{'literal':'0'},division]}}})
    assert report['status']=='DEFINED_INTEGER_EXPRESSION' and report['value']==0
    assert analyze_request({'ir':{'kind':'c_integer_expression','expression':division}})['status']=='UNDEFINED_INTEGER_OPERATION'


def test_counted_source_api_and_symbolic_cli(tmp_path):
    source=Path('examples/unbounded_nested_memory.c').read_text()
    result=analyze_request({'source':source,'frontend':'counted_memory',
                            'parameter_mins':{'n':0,'m':0},'inputs':{'n':3,'m':2}})
    assert result['status']=='CERTIFIED_UNBOUNDED_COUNTED_MEMORY'
    assert result['return_value']==65
    assert result['c_overflow_verified'] is False
    output=tmp_path/'report.json'
    assert main(['examples/unbounded_nested_memory.c','--c-counted','--parameter-mins','{"n":0,"m":0}',
                 '--inputs','{"n":3,"m":2}','--output',str(output)])==0
    assert json.loads(output.read_text())['return_value']==65
    assert main(['examples/exponential_recurrence.json','--output',str(output)])==0
    assert json.loads(output.read_text())['status']=='CERTIFIED_AFFINE_RECURRENCE_CLOSED_FORM'
    assert main(['examples/typed_integer_expression.json','--output',str(output)])==0
    assert json.loads(output.read_text())['value']==0


@pytest.mark.parametrize('payload',[
    {'source':'int f(int n){int i=0;for(i=0;i<n;i=i+1){}return i;}','frontend':'counted_memory','parameter_mins':{}},
    {'ir':{'kind':'counted_memory','state':{'x':0},'body':[{'repeat':'x','body':[]}]}},
    {'ir':{'kind':'c_integer_expression','expression':{'literal':'1lL'}}},
    {'ir':{'kind':'counted_memory','arrays':{'a':[1]},'pointers':{'p':{'array':'a','index':10}}}},
])
def test_unknown_for_unsupported_or_unproven_semantics(payload):
    assert analyze_request(payload)['status']=='UNKNOWN'
