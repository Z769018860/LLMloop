"""Untrusted typed-summary proposals, source certification and explicit fallback.

This coordinator never calls a model or interprets a rejected candidate as UB.
Each attempt uses a fresh existing verifier on the same source/domain/ABI.
"""
import copy
import hashlib
import json
import time
from .smt_spath import SMTGraphError


BASE={'source','function','parameter_bounds','abi','char_signed','max_paths','inputs'}
BACKENDS={'typed_recurrence':('closed_forms','PROVED_DEFINED_TYPED_C_RECURRENCE'),
          'typed_nested':('loop_summaries','PROVED_DEFINED_TYPED_C_NESTED')}


def analyze_portfolio(request,analyze):
    if set(request)-BASE-{'frontend','summary_backend','proposals','fallback'}:
        raise SMTGraphError('Invalid typed summary portfolio options')
    if not isinstance(request.get('source'),str) or not request['source'] or len(request['source'])>200000:
        raise SMTGraphError('Portfolio source must be a nonempty string of at most 200000 characters')
    backend=request.get('summary_backend','typed_recurrence')
    if not isinstance(backend,str) or backend not in BACKENDS:raise SMTGraphError('Portfolio requires typed_recurrence or typed_nested')
    proposals=request.get('proposals')
    if not isinstance(proposals,list) or not 1<=len(proposals)<=8:raise SMTGraphError('Portfolio requires 1..8 supplied proposals')
    # Validate every envelope before solving; candidates cannot replace source,
    # domain, ABI, proof limits or success flags, even in an unattempted suffix.
    seen=set()
    for p in proposals:
        if not isinstance(p,dict) or set(p)!={'id','summary'}:raise SMTGraphError('Proposal requires only id and summary')
        name=p['id'];summary=p['summary']
        if not isinstance(name,str) or not 1<=len(name)<=64 or name in seen:raise SMTGraphError('Proposal ids must be unique nonempty strings of at most 64 characters')
        seen.add(name)
        if not isinstance(summary,dict) or len(summary)>16:raise SMTGraphError('Proposal summary must be a map with at most 16 coordinates/loops')
        maps=[summary] if backend=='typed_recurrence' else list(summary.values())
        if any(not isinstance(k,str) or not 1<=len(k)<=128 for k in summary):raise SMTGraphError('Invalid summary coordinate/loop name')
        for mapping in maps:
            if not isinstance(mapping,dict) or len(mapping)>16:raise SMTGraphError('Nested proposals require coordinate maps, not automatic mode')
            if any(not isinstance(k,str) or not 1<=len(k)<=128 or not isinstance(v,str) or not 1<=len(v)<=5000 for k,v in mapping.items()):
                raise SMTGraphError('Proposal coordinates require bounded formula strings')
        if len(json.dumps(summary,ensure_ascii=True))>40000:raise SMTGraphError('Proposal payload budget exceeded')
    fallback=request.get('fallback')
    if 'fallback' in request and (not isinstance(fallback,dict) or set(fallback)!={'max_steps'} or type(fallback['max_steps']) is not int or not 1<=fallback['max_steps']<=512):
        raise SMTGraphError('Fallback requires only max_steps in 1..512')
    for field in ('parameter_bounds','inputs'):
        if field not in request:continue
        mapping=request[field]
        if not isinstance(mapping,dict) or len(mapping)>64:raise SMTGraphError('Invalid portfolio '+field)
        for key,value in mapping.items():
            if not isinstance(key,str) or not 1<=len(key)<=128:raise SMTGraphError('Invalid portfolio parameter name')
            values=value if field=='parameter_bounds' else [value]
            if not isinstance(values,(list,tuple)) or field=='parameter_bounds' and len(values)!=2:
                raise SMTGraphError('Portfolio bounds require endpoint pairs')
            if any(v is not None and (type(v) is not int or v.bit_length()>1024) or field=='inputs' and v is None for v in values):
                raise SMTGraphError('Portfolio inputs/bounds require bounded integers')
    if 'function' in request and (not isinstance(request['function'],str) or not 1<=len(request['function'])<=128):raise SMTGraphError('Invalid portfolio function')
    if 'abi' in request and (not isinstance(request['abi'],str) or request['abi'] not in ('LP64','ILP32','LLP64')):raise SMTGraphError('Invalid portfolio ABI')
    if 'char_signed' in request and type(request['char_signed']) is not bool:raise SMTGraphError('Invalid portfolio char policy')
    if 'max_paths' in request and (type(request['max_paths']) is not int or not 1<=request['max_paths']<=512):raise SMTGraphError('Invalid portfolio path limit')
    base=copy.deepcopy({k:v for k,v in request.items() if k in BASE})
    started=time.perf_counter();trials=[]
    metadata={'source_sha256':hashlib.sha256(base['source'].encode()).hexdigest(),
              'request_context_sha256':hashlib.sha256(json.dumps(base,sort_keys=True,allow_nan=False).encode()).hexdigest(),
              'summary_backend':backend,'proposal_origin':'supplied_untrusted',
              'remote_model_called':False,'policy':'first_certified_in_supplied_order',
              'certified_summary':False,'fallback_used':False,'trials':trials,
              'candidate_limit':8,'per_query_budget_increased':False,
              'notice':'Candidate failure/UNKNOWN is not a source-undefinedness proof. Bounded fallback is not an accelerated summary.'}
    field,success=BACKENDS[backend]
    def finish(result):
        metadata['unattempted_ids']=[p['id'] for p in proposals[len(trials):]]
        metadata['total_verification_seconds']=time.perf_counter()-started
        return {**result,'schema_version':1,'summary_portfolio':metadata}
    for p in proposals:
        tick=time.perf_counter()
        result=analyze({**copy.deepcopy(base),'frontend':backend,field:copy.deepcopy(p['summary'])})
        accepted=(result.get('status')==success and result.get('c_overflow_verified') is True and result.get('termination_proved') is True)
        trials.append({'id':p['id'],'summary_sha256':hashlib.sha256(json.dumps(p['summary'],sort_keys=True).encode()).hexdigest(),
                       'certified':accepted,'verification_seconds':time.perf_counter()-tick,'result':copy.deepcopy(result)})
        if accepted:
            metadata.update(certified_summary=True,selected_id=p['id'])
            return finish(result)
    if fallback is not None:
        metadata['fallback_used']=True;tick=time.perf_counter()
        result=analyze({**copy.deepcopy(base),'frontend':'typed_cfg_heap','max_steps':fallback['max_steps']})
        metadata['fallback']={'backend':'typed_cfg_heap','max_steps':fallback['max_steps'],
                              'verification_seconds':time.perf_counter()-tick,'status':result.get('status')}
        return finish(result)
    return finish({'status':'UNKNOWN','reason':'No supplied trajectory was certified; fallback not requested',
                   'c_overflow_verified':False,'termination_proved':False})
