import copy
import pytest
pytest.importorskip('z3')
from llmloop.sweep_memory import SweepMemory
from llmloop.sweep_c import translate_sweep_c
from llmloop.smt_spath import SMTGraphError


def specification():
    return {'kind':'sweep_memory','parameters':['n','m'],'parameter_bounds':{'n':[1,None],'m':[1,None]},
            'objects':{'a':{'length':'n*m','init':0,'storage':'heap'}},
            'pointers':{'p':{'object':'a','offset':0},'q':{'pointer':'p','offset':0}},
            'body':[{'sweep':{'pointer':'p','dimensions':[{'index':'i','count':'n'},{'index':'j','count':'m'}],
                               'updates':['old+1','old*2']}}],
            'queries':[{'pointer':'q','index':'n*m-1'}]}


def test_symbolic_length_billion_by_billion_without_unrolling():
    result=SweepMemory(specification()).report({'n':10**9,'m':10**9})
    assert result['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'
    assert result['queries'][0]['value']==2
    assert result['regions'][0]['old_cell_only']
    assert all(x['result']=='unsat' for x in result['obligations'])


def test_coordinates_decode_and_overlapping_alias_sweeps_compose_in_order():
    obj=specification();obj['parameter_bounds']={'n':[1,4],'m':[1,4]}
    obj['body'][0]['sweep']['updates']=['old+i+j']
    obj['pointers']['r']={'pointer':'p','offset':1}
    # The second sweep overlaps all but the first cell. It sees previous writes.
    obj['body'].append({'sweep':{'pointer':'r','dimensions':[{'index':'t','count':'n*m-1'}],'updates':['old+10']}})
    for n in range(1,5):
        for m in range(1,5):
            result=SweepMemory(obj).report({'n':n,'m':m})
            assert result['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'
            assert result['queries'][0]['value']==n+m-2+(10 if n*m>1 else 0)


def test_pointer_parameter_value_remains_symbolic_instead_of_inventing_input_memory():
    obj=specification();obj['objects']['a']['init']='symbolic'
    result=SweepMemory(obj).report({'n':1,'m':2})
    assert 'value_smt2' in result['queries'][0] and 'value' not in result['queries'][0]


def test_empty_domains_never_dereference_memory():
    obj=specification();obj['parameter_bounds']={'n':[0,0],'m':[0,None]};obj['queries']=[]
    obj['body'].insert(0,{'free':'q'})
    assert SweepMemory(obj).report()['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'


@pytest.mark.parametrize('mutate',[
    lambda o:o['objects']['a'].update(length='n*m-1'),
    lambda o:o['body'].insert(0,{'free':'q'}),
    lambda o:o['body'].extend([{'free':'q'},{'free':'p'}]),
    lambda o:o['objects']['a'].update(storage='stack') or o['body'].insert(0,{'free':'p'}),
    lambda o:o['pointers'].update(r={'pointer':'p','offset':'n*m+1'}),
])
def test_bounds_lifetime_double_free_and_pointer_formation_are_checked(mutate):
    obj=specification();mutate(obj)
    report=SweepMemory(obj).report()
    assert report['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'
    assert 'witness' in report


def test_single_width_checks_intermediates_even_after_cancellation():
    obj=specification();obj['signed_bits']=8;obj['parameter_bounds']={'n':[1,3],'m':[1,3]}
    obj['objects']['a']['init']=127;obj['body'][0]['sweep']['updates']=['(old+1)-1']
    report=SweepMemory(obj).report()
    assert report['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'
    assert report['obligation']=='sweep arithmetic intermediates'
    assert report['witness']['indices']['old']==127


def test_safe_integer_sweep_and_unconstrained_old_value_overflow():
    obj=specification();obj['signed_bits']=8;obj['parameter_bounds']={'n':[1,3],'m':[1,3]}
    assert SweepMemory(obj).report()['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'
    obj['objects']['a']['init']='symbolic'
    assert SweepMemory(obj).report()['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'


SOURCE='''int f(int n,int m){int *p=calloc(n*m,sizeof(int));int i=0;int j=0;
for(i=0;i<n;i=i+1){for(j=0;j<m;j=j+1){p[i*m+j]=p[i*m+j]+i+j;}}
return p[n*m-1];}'''


def test_c_frontend_preserves_dynamic_index_and_selected_integer_checks():
    obj=translate_sweep_c(SOURCE,parameter_bounds={'n':[1,4],'m':[1,4]},signed_bits=32)
    for n in range(1,5):
        for m in range(1,5):
            report=SweepMemory(obj).report({'n':n,'m':m})
            assert report['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'
            assert report['queries'][0]['value']==n+m-2


def test_c_index_cancellation_cannot_hide_intermediate_overflow():
    source=SOURCE.replace('p[i*m+j]','p[i*m+j+(n+127)-(n+127)]')
    report=SweepMemory(translate_sweep_c(source,parameter_bounds={'n':[1,2],'m':[1,2]},signed_bits=8)).report()
    assert report['status']=='POSSIBLE_UNDEFINED_MEMORY_OR_INTEGER_OPERATION'


@pytest.mark.parametrize('source',[
    SOURCE.replace('p[i*m+j]+i+j','p[0]+1'),
    SOURCE.replace('i*m+j','i+j'),
    SOURCE.replace('return p[n*m-1];','for(i=0;i<j;i=i+1){p[i]=1;}return 0;'),
])
def test_cross_cell_nonbijective_and_stale_counter_uses_fail_closed(source):
    with pytest.raises((ValueError,SMTGraphError)):translate_sweep_c(source)


def test_pointer_parameters_require_explicit_length_contracts():
    source='int f(int *p,int n){int i=0;for(i=0;i<n;i=i+1){p[i]=p[i]+1;}return 0;}'
    with pytest.raises(SMTGraphError,match='length contract'):translate_sweep_c(source)
    obj=translate_sweep_c(source,parameter_bounds={'n':[0,None]},memory_layout={'p':'n'})
    assert SweepMemory(obj).report()['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'


def test_reports_do_not_reexecute_mutating_sweeps_or_free():
    engine=SweepMemory(specification())
    engine.report()
    assert engine.report({'n':2,'m':3})['queries'][0]['value']==2
    assert engine.report({'n':3,'m':2})['queries'][0]['value']==2
    assert len(engine.region_certificates)==1


def test_multiple_pointer_parameters_need_alias_contract_instead_of_assumed_disjointness():
    source='int f(int *p,int *q,int n){int i=0;for(i=0;i<n;i=i+1){p[i]=1;}for(i=0;i<n;i=i+1){q[i]=2;}return 0;}'
    with pytest.raises(SMTGraphError,match='alias contract'):
        translate_sweep_c(source,memory_layout={'p':'n','q':'n'})


def test_source_api_and_cli_dynamic_mode(tmp_path):
    import json
    from llmloop.api import analyze_request
    from llmloop.symbolic_cli import main
    request={'source':SOURCE,'frontend':'sweep_memory','parameter_bounds':{'n':[1,3],'m':[1,3]},
             'int_bits':32,'inputs':{'n':3,'m':2}}
    report=analyze_request(request)
    assert report['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY' and report['queries'][0]['value']==3
    source=tmp_path/'sweep.c';source.write_text(SOURCE);output=tmp_path/'report.json'
    assert main([str(source),'--c-sweep','--parameter-bounds','{"n":[1,3],"m":[1,3]}',
                 '--int-bits','32','--inputs','{"n":3,"m":2}','--output',str(output)])==0
    assert json.loads(output.read_text())['queries'][0]['value']==3


def test_negative_for_count_is_unsupported_domain_not_claimed_c_undefined_behavior():
    obj=specification();obj['parameter_bounds']={'n':[-1,-1],'m':[-1,-1]};obj['queries']=[]
    report=SweepMemory(obj).report()
    assert report['status']=='UNSUPPORTED_SWEEP_COUNT_DOMAIN'


def test_wide_c_literals_are_unsupported_instead_of_misclassified_as_single_width_ub():
    source=SOURCE.replace('+i+j','+2147483648')
    with pytest.raises(SMTGraphError,match='outside the selected single-width'):translate_sweep_c(source,signed_bits=32)


def test_void_parameter_function_and_lifetime_without_queries():
    source='int f(void){int *p=calloc(3,sizeof(int));int i=0;for(i=0;i<3;i=i+1){p[i]=p[i]+1;}free(p);return 0;}'
    assert SweepMemory(translate_sweep_c(source,signed_bits=32)).report()['status']=='CERTIFIED_UNBOUNDED_POINTWISE_MEMORY'
