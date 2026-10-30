"""Pinned compiler-rt integer pilot: provenance, independent oracles and specs.

This is deliberately a small external-code benchmark, not a whole-library or
whole-C coverage claim. UNKNOWN rows remain part of the denominator.
"""
import hashlib
import json
from pathlib import Path
import random
import time

import z3

from .api import analyze_request
from .smt_spath import SMTGraphError
from .typed_c import TypedCFunction


ROOT=Path(__file__).resolve().parents[1]
VENDOR=ROOT/'benchmarks/llvm_compiler_rt'
UPSTREAM_COMMIT='3b5b5c1ec4a3095ab096dd780e84d7ab81f3d7ff'
BASELINE_COMMIT='95fb055f523fb8476068c783d20466f68aafe03a'
SEED=370018


def verify_vendor(root=ROOT):
    root=Path(root);manifest=json.loads((root/'benchmarks/llvm_compiler_rt/manifest.json').read_text())
    if manifest.get('upstream_commit')!=UPSTREAM_COMMIT:raise SMTGraphError('Unexpected upstream benchmark revision')
    for entry in manifest['files']:
        data=(root/entry['path']).read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256'] or blob!=entry['git_blob_sha']:
            raise SMTGraphError('Upstream benchmark file differs from pinned bytes: '+entry['path'])
    return {'upstream_commit':UPSTREAM_COMMIT,'upstream_tag':manifest['upstream_tag'],
            'files_verified':len(manifest['files']),'all_match_upstream_git_blobs':True,
            'manifest_sha256':hashlib.sha256((root/'benchmarks/llvm_compiler_rt/manifest.json').read_bytes()).hexdigest(),
            'license':manifest['license']}


def cases():
    result=[]
    def add(name,function,types,oracle,supported=True,bounds=None,backend=None):
        bounds=bounds or {key:[-(1<<(width-1)),(1<<(width-1))-1] if signed else [0,(1<<width)-1] for key,(width,signed) in types.items()}
        result.append({'name':name,'function':'__'+function,'file':function+'.c','types':types,'oracle':oracle,
                       'bounds':bounds,'expected_safety':('PROVED_DEFINED_CLANG_CFG_CALLS' if backend=='calls' else 'PROVED_DEFINED_CLANG_SCALAR_CFG') if supported else 'UNKNOWN',
                       'backend':backend or ('cfg' if supported else 'calls')})
    add('popcount32','popcountsi2',{'a':(32,True)},'popcount')
    add('popcount64','popcountdi2',{'a':(64,True)},'popcount')
    add('parity32','paritysi2',{'a':(32,True)},'parity')
    add('bswap32','bswapsi2',{'u':(32,False)},'bswap')
    add('bswap64','bswapdi2',{'u':(64,False)},'bswap')
    for function,oracle in [('clzsi2','clz'),('ctzsi2','ctz')]:
        add(function+'_positive',function,{'a':(32,True)},oracle,bounds={'a':[1,2147483647]})
        add(function+'_negative',function,{'a':(32,True)},oracle,bounds={'a':[-2147483648,-1]})
    add('union_parity64','paritydi2',{'a':(64,True)},'parity',backend='calls')
    add('union_unsigned_compare64','ucmpdi2',{'a':(64,False),'b':(64,False)},'compare',backend='calls')
    add('union_signed_compare64','cmpdi2',{'a':(64,True),'b':(64,True)},'compare',backend='calls')
    add('external_abort_abs','absvsi2',{'a':(32,True)},'abs',bounds={'a':[-2147483647,2147483647]},backend='calls')
    add('external_abort_negate','negvsi2',{'a':(32,True)},'negate',bounds={'a':[-2147483647,2147483647]},backend='calls')
    add('builtin_loop_udiv32','udivsi3',{'a':(32,False),'b':(32,False)},'udiv',False,{'a':[0,4294967295],'b':[1,4294967295]})
    return result


def independent_value(case,inputs):
    if set(inputs)!=set(case['types']):raise SMTGraphError('Benchmark input keys differ from declared parameters')
    for key,value in inputs.items():
        lo,hi=case['bounds'][key]
        if type(value) is not int or not lo<=value<=hi:raise SMTGraphError('Benchmark input outside declared domain')
    values=[inputs[key] for key in case['types']];width=next(iter(case['types'].values()))[0]
    bits=values[0]&((1<<width)-1);kind=case['oracle']
    if kind=='popcount':return bits.bit_count()
    if kind=='parity':return bits.bit_count()%2
    if kind=='bswap':return int.from_bytes(bits.to_bytes(width//8,'little'),'big')
    if kind in ('clz','ctz'):
        if not bits:raise SMTGraphError('Upstream zero-input precondition violated')
        return width-bits.bit_length() if kind=='clz' else (bits&-bits).bit_length()-1
    if kind=='compare':return 1+int(values[0]>values[1])-int(values[0]<values[1])
    if kind=='abs':return abs(values[0])
    if kind=='negate':return -values[0]
    if kind=='udiv':return values[0]//values[1]
    raise SMTGraphError('Unknown independent benchmark specification')


def sample_inputs(case,count=256):
    if type(count) is not int or not 16<=count<=4096:raise SMTGraphError('Benchmark sample count must be 16..4096')
    keys=list(case['types']);columns=[]
    for key,(width,signed) in case['types'].items():
        lo,hi=case['bounds'][key];mask=(1<<width)-1
        unsigned={0,1,2,3,mask,mask-1,int('aa'*(width//8),16),int('55'*(width//8),16)}
        for bit in range(width):unsigned.update({1<<bit,((1<<bit)-1)&mask,((1<<bit)+1)&mask})
        numbers={x-(1<<width) if signed and x>(1<<(width-1))-1 else x for x in unsigned}
        numbers.update({lo,hi,-1,0,1});columns.append(sorted(x for x in numbers if lo<=x<=hi))
    rows=[];seen=set()
    def append(values):
        values=tuple(values)
        if values not in seen and len(rows)<count:seen.add(values);rows.append(dict(zip(keys,values)))
    boundary=[]
    if len(keys)==1:
        boundary=[(value,) for value in columns[0]]
    else:
        # Preserve equality, ordering and wide high/low halves in pair controls.
        for index,a in enumerate(columns[0]):
            boundary.append((a,columns[1][(index+len(columns[1])//3)%len(columns[1])]))
            if case['bounds'][keys[1]][0]<=a<=case['bounds'][keys[1]][1]:boundary.append((a,a))
        for a in columns[0][:4]+columns[0][-4:]:
            for b in columns[1][:4]+columns[1][-4:]:boundary.append((a,b))
    budget=count//2
    selected=boundary if len(boundary)<=budget else [boundary[i*(len(boundary)-1)//(budget-1)] for i in range(budget)]
    for row in selected:append(row)
    rng=random.Random(SEED+sum(case['name'].encode()))
    while len(rows)<count:append(rng.randint(*case['bounds'][key]) for key in keys)
    return rows


def compilation_database(directory):
    directory=Path(directory);database=directory/'compile_commands.json'
    entries=[]
    for source in sorted(VENDOR.glob('*.c')):
        entries.append({'directory':str(VENDOR),'file':str(source),
                        'arguments':['clang','-std=c11','-O0','-fno-builtin','-I',str(VENDOR),'-c',str(source),
                                     '-o',str(directory/(source.stem+'.o')),'-MMD','-MF',str(directory/(source.stem+'.d'))]})
    database.write_text(json.dumps(entries,indent=2)+'\n')
    return database


def analyze_case(case,database,source_file=None):
    request={'source_file':str(source_file or VENDOR/case['file']),'function':case['function'],'frontend':'clang_proof',
             'clang':{'compilation_database':str(database)} if source_file is None else {'args':['-I',str(VENDOR),'-fno-builtin']},
             'proof':{'backend':case['backend'],'parameter_bounds':case['bounds'],'max_steps':128}}
    start=time.monotonic();report=analyze_request(request)
    return request,report,round(time.monotonic()-start,3)


def bit_reference(case,model):
    term=next(iter(model.engine.variables.values()));x=term.value;width=term.type.bits
    output=model.engine.expression.value.size();bits=[z3.Extract(i,i,x) for i in range(width)]
    if case['oracle']=='popcount':
        parts=bits
        while len(parts)>1:parts=[z3.ZeroExt(1,parts[i])+z3.ZeroExt(1,parts[i+1]) for i in range(0,len(parts),2)]
        return z3.ZeroExt(output-parts[0].size(),parts[0])
    if case['oracle']=='parity':
        parity=bits[0]
        for bit in bits[1:]:parity=parity^bit
        return z3.ZeroExt(output-1,parity)
    if case['oracle']=='bswap':return z3.Concat(*(z3.Extract(i+7,i,x) for i in range(0,width,8)))
    if case['oracle']=='abs':return z3.If(x<0,-x,x)
    if case['oracle']=='negate':return -x
    if case['oracle']=='compare':
        a,b=[model.engine.variables[key] for key in case['types']]
        less=a.value<b.value if a.type.signed else z3.ULT(a.value,b.value)
        return z3.If(less,z3.BitVecVal(0,output),z3.If(a.value==b.value,z3.BitVecVal(1,output),z3.BitVecVal(2,output)))
    if case['oracle'] in ('clz','ctz'):
        result=z3.BitVecVal(width,output)
        order=range(width) if case['oracle']=='clz' else reversed(range(width))
        for i in order:result=z3.If(bits[i]==1,z3.BitVecVal(width-1-i if case['oracle']=='clz' else i,output),result)
        return result
    raise SMTGraphError('No universal bit-vector reference for this benchmark')


def functional_proof(case,source,strategy='auto'):
    # A separate typed bit-vector source executor is paired with an independent
    # reference circuit. This is distinct from the primary integer-lift safety
    # certificate and is only requested after original-source safety succeeds.
    if strategy not in ('auto','direct'):raise SMTGraphError('Functional proof strategy must be auto/direct')
    execution_source=source
    if case['backend']=='calls':
        from .typed_cfg_calls import CallExpansion
        execution_source=CallExpansion(source,function=case['function']).source
    model=TypedCFunction(execution_source,function=case['function'],parameter_bounds=case['bounds'],max_unroll=0)
    domain=[]
    for key,term in model.engine.variables.items():
        lo,hi=case['bounds'][key];x=term.value;lo=z3.BitVecVal(lo,term.type.bits);hi=z3.BitVecVal(hi,term.type.bits)
        domain.extend([x>=lo,x<=hi] if term.type.signed else [z3.UGE(x,lo),z3.ULE(x,hi)])
    from .bv_cuts import qfbv_terms,packed_popcount_proof
    start=time.monotonic();reference=bit_reference(case,model);difference=model.engine.expression.value!=reference
    # The source-safety predicate contains BV2Int terms and belongs to the
    # primary mixed-theory safety proof, not a SolverFor('QF_BV') query.
    qfbv_terms([*domain,difference]);cut_result=None
    common={'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'reference_sha256':hashlib.sha256(reference.sexpr().encode()).hexdigest(),
            'execution_source':execution_source,'execution_source_sha256':hashlib.sha256(execution_source.encode()).hexdigest(),
            'external_calls_assumed_defined':False,'strategy':strategy}
    if strategy=='auto' and case['oracle']=='popcount' and len(model.engine.variables)==1:
        word=next(iter(model.engine.variables.values())).value
        if word.size()==64:
            remaining=5000-int((time.monotonic()-start)*1000)
            if remaining>0:cut_result=packed_popcount_proof(model.engine.expression.value,reference,word,remaining)
            if cut_result is not None and cut_result['status']=='PROVED_FUNCTIONAL_BV_CUTS':
                return {**cut_result,**common,'elapsed_seconds':round(time.monotonic()-start,6),'total_timeout_ms':5000},model
    remaining=5000-int((time.monotonic()-start)*1000)
    if remaining<=0:
        return {**common,'status':'UNKNOWN','query_result':'unknown','timeout_ms':5000,'total_timeout_ms':5000,
                'reason':'total functional proof budget exhausted','elapsed_seconds':round(time.monotonic()-start,6),
                'compositional_attempt':cut_result,'refutation_smt2':None},model
    solver=z3.SolverFor('QF_BV');solver.set(timeout=remaining)
    solver.add(*domain,difference)
    answer=solver.check()
    result={'status':'PROVED_FUNCTIONAL_QF_BV' if answer==z3.unsat else 'REFUTED_FUNCTIONAL_QF_BV' if answer==z3.sat else 'UNKNOWN',
            'query_result':str(answer),'timeout_ms':remaining,'total_timeout_ms':5000,'elapsed_seconds':round(time.monotonic()-start,3),
            'method':'independent bit reference versus separate typed bit-vector execution of normalized source; source safety proved separately',
            'refutation_smt2':solver.to_smt2(),**common}
    if cut_result is not None:result['compositional_attempt']=cut_result
    if answer==z3.unknown:result['reason']=solver.reason_unknown()
    if answer==z3.sat:result['counterexample']=model.engine.witness(solver.model())
    return result,model


def model_values(case,source,inputs,report):
    # Evaluate the actual certified primary return expression. Reconstructing a
    # second model would prove a different query with different fresh symbols.
    if not report['status'].startswith('PROVED_DEFINED_CLANG_') or report.get('normalization',{}).get('source_sha256')!=hashlib.sha256(source.encode()).hexdigest():
        raise SMTGraphError('Primary model samples require the matching successful source report')
    symbols=report.get('parameter_symbols',{})
    if set(symbols)!=set(case['types']) or len(set(symbols.values()))!=len(symbols):raise SMTGraphError('Primary parameter symbol bindings missing or ambiguous')
    variables={name:z3.Int(symbol) for name,symbol in symbols.items()};decls={symbols[name]:term for name,term in variables.items()}
    value=z3.parse_smt2_string('(assert (= 0 '+report['return_smt2']+'))',decls=decls)[0].arg(1)
    domain=z3.parse_smt2_string('(assert '+report['domain_smt2']+')',decls=decls)[0]
    result=[]
    for row in inputs:
        independent_value(case,row)
        substitutions=[(term,z3.IntVal(row[name])) for name,term in variables.items()]
        if not z3.is_true(z3.simplify(z3.substitute(domain,*substitutions))):raise SMTGraphError('Primary model sample outside certified domain')
        selected=z3.simplify(z3.substitute(value,*substitutions))
        if not z3.is_int_value(selected):raise SMTGraphError('Benchmark model did not evaluate to an integer')
        result.append(selected.as_long())
    return result
