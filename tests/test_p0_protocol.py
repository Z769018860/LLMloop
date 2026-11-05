import copy,json
from pathlib import Path
from llmloop.api import analyze_request
from scripts.p0_experiments import controls,request,expected


def test_periodic_candidate_restriction_keeps_real_source_verifier():
    c=next(c for c in controls() if c['name']=='unsigned_period')
    before=copy.deepcopy(c)
    full=analyze_request(request(c,'full_trajectory'))
    restricted=analyze_request(request(c,'affine_candidates'))
    assert full['status']=='PROVED_DEFINED_TYPED_C_NESTED'
    assert full['evaluation']['value']==64
    assert restricted['status']=='UNKNOWN' and not restricted['c_overflow_verified']
    assert c==before


def test_flat_ablation_cannot_replace_nested_source_with_flattened_program():
    c=next(c for c in controls() if c['name']=='nested_product')
    q=request(c,'flat_trajectory')
    assert q['source']==c['source'] and q['parameter_bounds']==c['bounds']
    result=analyze_request(q)
    assert result['status']=='UNKNOWN' and 'nested' in str(result).lower()
    result=analyze_request(request(c,'full_trajectory'))
    assert result['status']=='PROVED_DEFINED_TYPED_C_NESTED'
    assert result['evaluation']['value']==3000000


def test_source_ub_survives_all_candidate_modes():
    c=next(c for c in controls() if c['name']=='canceled_overflow')
    for mode in ['affine_candidates','flat_trajectory','full_trajectory','automatic']:
        result=analyze_request(request(c,mode))
        assert result['status']=='UNKNOWN' and not result['c_overflow_verified']
        assert expected(c,mode) is False


def test_registered_public_split_has_no_shared_source_or_family():
    p=Path(__file__).resolve().parents[1]/'experiments/protocols/v061_p0.json'
    plan=json.loads(p.read_text());corpus=plan['public_corpus_partition']
    assert len(corpus)==35
    dev=[c for c in corpus if c['split']=='development'];test=[c for c in corpus if c['split']=='future_test']
    assert dev and test
    assert not {c['source_sha256'] for c in dev}&{c['source_sha256'] for c in test}
    assert not {c['family'] for c in dev}&{c['family'] for c in test}
    assert len(plan['external_cases'])==24
    assert len({(c['tool'],c['path']) for c in plan['external_cases']})==24
    assert plan['remote_model_calls']==0
