import json
import pytest
from llmloop.api import analyze_request
from llmloop.symbolic_cli import main

TYPED='int f(unsigned char x){unsigned char y=x;y=y+1;return y;}'
PRIVATE='int f(int n){int x=0;int i=0;for(i=0;i<n;i=i+1){int *p=calloc(1,sizeof(int));p[0]=i+1;x=x+p[0];free(p);}return x;}'
SCAN='int f(int n){int *p=calloc(n,sizeof(int));int i=0;p[0]=1;for(i=1;i<n;i=i+1){p[i]=p[i-1]+2;}return p[n-1];}'


@pytest.mark.parametrize('source,options,status,expected,flag,cli_options',[
    (TYPED,{'frontend':'typed_c','inputs':{'x':255}},'PROVED_DEFINED_TYPED_C_FUNCTION',0,'--c-typed',['--inputs','{"x":255}']),
    (PRIVATE,{'frontend':'private_allocations','parameter_mins':{'n':0},'inputs':{'n':5}},'CERTIFIED_PRIVATE_ALLOCATION_FOLD',15,'--c-private',['--parameter-mins','{"n":0}','--inputs','{"n":5}']),
    (SCAN,{'frontend':'memory_scan','parameter_bounds':{'n':[1,1000]},'int_bits':32,'inputs':{'n':5}},'CERTIFIED_UNBOUNDED_LINEAR_MEMORY_SCAN',9,'--c-scan',['--parameter-bounds','{"n":[1,1000]}','--int-bits','32','--inputs','{"n":5}']),
])
def test_source_api_and_cli_routes(tmp_path,source,options,status,expected,flag,cli_options):
    def returned(report):
        if status=='PROVED_DEFINED_TYPED_C_FUNCTION':return report['evaluation']['value']
        if status=='CERTIFIED_PRIVATE_ALLOCATION_FOLD':return report['return_value']
        return report['queries'][0]['value']
    report=analyze_request({'source':source,**options})
    assert report['status']==status and returned(report)==expected
    path=tmp_path/'source.c';path.write_text(source);output=tmp_path/'output.json'
    assert main([str(path),flag,*cli_options,'--output',str(output)])==0
    report=json.loads(output.read_text())
    assert report['status']==status and returned(report)==expected


def test_abi_plain_char_policy_and_open_parameter_bounds():
    source='int f(char x){return x;}'
    report=analyze_request({'source':source,'frontend':'typed_c','char_signed':False,'parameter_bounds':{'x':[0,None]},'inputs':{'x':255}})
    assert report['status']=='PROVED_DEFINED_TYPED_C_FUNCTION' and report['evaluation']['value']==255
    assert analyze_request({'source':source,'frontend':'typed_c','inputs':{'x':255}})['status']=='UNKNOWN'


def test_scan_free_metadata_cannot_be_queried_as_live_memory():
    report=analyze_request({'source':SCAN.replace('return p[n-1];','free(p);return 0;'),'frontend':'memory_scan','parameter_bounds':{'n':[1,1000]},'int_bits':32})
    assert report['status']=='CERTIFIED_UNBOUNDED_LINEAR_MEMORY_SCAN'
    assert report['memory_alive_after_function'] is False
