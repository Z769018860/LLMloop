import hashlib
import json
from pathlib import Path
import shutil

import pytest
import z3

from llmloop.llvm_benchmarks import (ROOT,VENDOR,UPSTREAM_COMMIT,cases,verify_vendor,
    independent_value,sample_inputs,compilation_database,analyze_case,functional_proof)
from llmloop.smt_spath import SMTGraphError


CASES=cases()
FILES=json.loads((VENDOR/'manifest.json').read_text())['files']


def test_upstream_revision_license_and_complete_denominator_are_explicit():
    verified=verify_vendor()
    assert verified['files_verified']==20 and verified['all_match_upstream_git_blobs']
    assert verified['upstream_commit']==UPSTREAM_COMMIT
    assert verified['license']=='Apache-2.0 WITH LLVM-exception'
    assert len(CASES)==15 and len({c['function'] for c in CASES})==13
    assert sum(c['expected_safety']=='UNKNOWN' for c in CASES)==6


@pytest.mark.parametrize('entry',FILES,ids=[Path(e['path']).name for e in FILES])
def test_each_vendored_source_or_header_matches_immutable_upstream_blob(entry):
    data=(ROOT/entry['path']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==entry['sha256']
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==entry['git_blob_sha']
    assert '/'+UPSTREAM_COMMIT+'/' in entry['upstream_url']


def test_tampered_vendor_bytes_are_rejected_before_benchmark_execution(tmp_path):
    destination=tmp_path/'benchmarks/llvm_compiler_rt';shutil.copytree(VENDOR,destination)
    (destination/'popcountsi2.c').write_text((destination/'popcountsi2.c').read_text().replace('0x55555555','0x55555554'))
    with pytest.raises(SMTGraphError,match='differs from pinned bytes'):verify_vendor(tmp_path)


@pytest.mark.parametrize('case',CASES,ids=[c['name'] for c in CASES])
def test_seeded_inputs_are_unique_reproducible_and_inside_declared_domains(case):
    inputs=sample_inputs(case)
    assert inputs==sample_inputs(case) and len(inputs)==256
    assert len({tuple(row.values()) for row in inputs})==256
    for row in inputs:
        assert set(row)==set(case['types'])
        for key,value in row.items():assert case['bounds'][key][0]<=value<=case['bounds'][key][1]
        assert type(independent_value(case,row)) is int


@pytest.mark.parametrize('count',[0,15,4097,True])
def test_sample_budget_is_not_silently_changed(count):
    with pytest.raises(SMTGraphError):sample_inputs(CASES[0],count)


@pytest.mark.parametrize('name,inputs,want',[
    ('popcount32',{'a':-1},32),('popcount64',{'a':-1},64),
    ('parity32',{'a':-2147483648},1),('bswap32',{'u':1},1<<24),('bswap64',{'u':1},1<<56),
    ('clzsi2_positive',{'a':1},31),('clzsi2_negative',{'a':-2147483648},0),
    ('ctzsi2_positive',{'a':2},1),('ctzsi2_negative',{'a':-2147483648},31),
    ('union_parity64',{'a':-1},0),('union_unsigned_compare64',{'a':1<<63,'b':0},2),
    ('union_signed_compare64',{'a':-1,'b':0},0),('external_abort_abs',{'a':-100},100),
    ('external_abort_negate',{'a':-100},100),('builtin_loop_udiv32',{'a':4294967295,'b':3},1431655765),
])
def test_independent_references_cover_signedness_high_halves_and_boundary_values(name,inputs,want):
    assert independent_value(next(c for c in CASES if c['name']==name),inputs)==want


@pytest.mark.parametrize('name', ['clzsi2_positive','ctzsi2_positive','builtin_loop_udiv32','external_abort_abs','external_abort_negate'])
def test_library_preconditions_are_enforced_in_the_oracle(name):
    case=next(c for c in CASES if c['name']==name)
    inputs={'a':0,'b':0} if case['oracle']=='udiv' else {'a':-2147483648 if case['oracle'] in ('abs','negate') else 0}
    with pytest.raises(SMTGraphError):independent_value(case,inputs)


@pytest.mark.parametrize('name',['union_unsigned_compare64','union_signed_compare64','builtin_loop_udiv32'])
def test_oracle_bindings_are_independent_of_dictionary_order(name):
    case=next(c for c in CASES if c['name']==name)
    assert independent_value(case,{'a':12,'b':3})==independent_value(case,{'b':3,'a':12})


@pytest.fixture
def database(tmp_path):return compilation_database(tmp_path)


@pytest.mark.parametrize('case',CASES,ids=[c['name'] for c in CASES])
def test_original_upstream_tus_and_headers_through_compilation_database(case,database):
    request,report,unused=analyze_case(case,database)
    assert report['status']==case['expected_safety'],report
    front=report['clang_frontend']
    assert front['status']=='CLANG_FRONTEND_READY'
    assert front['source']['sha256']==hashlib.sha256((VENDOR/case['file']).read_bytes()).hexdigest()
    assert front['compilation_database']['sha256']==hashlib.sha256(database.read_bytes()).hexdigest()
    assert not list(database.parent.glob('*.o')) and not list(database.parent.glob('*.d'))
    proved=case['expected_safety']!='UNKNOWN'
    assert report.get('c_overflow_verified',False)==proved
    assert report.get('memory_safety_verified',False)==proved
    assert report.get('termination_proved',False)==proved


@pytest.mark.parametrize('case',[c for c in CASES if c['expected_safety']!='UNKNOWN'],ids=[c['name'] for c in CASES if c['expected_safety']!='UNKNOWN'])
def test_independent_bit_reference_is_separate_from_safety_and_replayable(case,database):
    unused,report,unused=analyze_case(case,database)
    query,model=functional_proof(case,report['normalization']['source'])
    if case['name']=='popcount64':
        assert query['status'] in ('PROVED_FUNCTIONAL_QF_BV','UNKNOWN')
    else:
        assert query['status']=='PROVED_FUNCTIONAL_QF_BV',query
        solver=z3.SolverFor('QF_BV');solver.set(timeout=5000);solver.from_string(query['refutation_smt2'])
        assert solver.check()==z3.unsat


def test_defined_wrong_algorithm_is_not_mistaken_for_functional_correctness(database,tmp_path):
    case=next(c for c in CASES if c['name']=='popcount32')
    source=tmp_path/'wrong.c';source.write_text((VENDOR/case['file']).read_text().replace('0x55555555','0x55555554'))
    unused,report,unused=analyze_case(case,database,source)
    assert report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG',report
    query,unused=functional_proof(case,report['normalization']['source'])
    assert query['status']=='REFUTED_FUNCTIONAL_QF_BV' and query['counterexample']


def test_real_signed_shift_mutation_keeps_undefinedness_obligations(database,tmp_path):
    case=dict(next(c for c in CASES if c['name']=='bswap32'));case['bounds']={'u':[0,255]}
    source=tmp_path/'unsafe.c';source.write_text((VENDOR/case['file']).read_text().replace('uint32_t u','int32_t u'))
    unused,report,unused=analyze_case(case,database,source)
    assert report['status']=='UNKNOWN' and not report['c_overflow_verified']
    assert report['reason']=='counterexample to the universal obligation'
