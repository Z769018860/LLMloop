"""Relational (@rel) conjuncts in typed_invariant_tree: sound acceptance, rejection of false/non-inductive relations, unsafe never certified."""
import pytest
from llmloop.api import analyze_request

SRC = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){if(i%3==0){x++;}else{y++;}}return 100/(x+y-n+1);}'
BASE = {'source': SRC, 'frontend': 'typed_invariant_tree', 'parameter_bounds': {'n': [0, 100000]}, 'abi': 'LP64'}
BOX = {'x': {'lo': '0', 'hi': 'n'}, 'y': {'lo': '0', 'hi': 'n'}}


def run(inv, **kw):
    return analyze_request({**BASE, 'range_invariants': inv, **kw})


def test_boxes_alone_do_not_prove_but_relation_does():
    assert run({'i': BOX})['status'] == 'UNKNOWN'
    r = run({'i': {**BOX, '@rel': {'eq': ['x+y-i']}}})
    assert r['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'


def test_relation_without_boxes_is_enough():
    assert run({'i': {'@rel': {'eq': ['x+y-i'], 'le': ['-x', '-y']}}})['status'].startswith('PROVED')


def test_false_or_noninductive_relation_rejected():
    assert run({'i': {**BOX, '@rel': {'eq': ['x+y-i-1']}}})['status'] == 'UNKNOWN'   # fails at entry
    assert run({'i': {**BOX, '@rel': {'eq': ['x-y']}}})['status'] == 'UNKNOWN'        # not inductive


def test_malformed_rel_rejected():
    for bad in ({'foo': ['x']}, {}, {'eq': 'x'}, {'eq': ['x+y-i'] * 9}):
        assert run({'i': {**BOX, '@rel': bad}})['status'] == 'UNKNOWN'


def test_unsafe_program_not_certified_with_relation():
    src = 'int f(int n){int x=0;int y=0;for(int i=0;i<n;i++){if(i%3==0){x++;}else{y++;}}return 100/(x+y-n);}'
    r = analyze_request({**BASE, 'source': src, 'range_invariants': {'i': {**BOX, '@rel': {'eq': ['x+y-i']}}}})
    assert r['status'] != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'


def test_portfolio_accepts_rel_and_still_certifies_only_safe():
    inv = {'i': {**BOX, '@rel': {'eq': ['x+y-i']}}}
    req = lambda src: {'source': src, 'frontend': 'typed_summary_portfolio', 'summary_backend': 'typed_invariant_tree', 'proposals': [{'id': 'c0', 'summary': inv}],
                       'parameter_bounds': {'n': [0, 100000]}, 'inputs': {'n': 100000}, 'abi': 'LP64'}
    assert analyze_request(req(SRC))['status'] == 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    unsafe = SRC.replace('x+y-n+1', 'x+y-n')
    assert analyze_request(req(unsafe))['status'] != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
    bad = req(SRC); bad['proposals'][0]['summary'] = {'i': {**BOX, '@rel': {'eq': 'x'}}}
    assert analyze_request(bad)['status'] != 'PROVED_DEFINED_TYPED_C_INVARIANT_TREE'
