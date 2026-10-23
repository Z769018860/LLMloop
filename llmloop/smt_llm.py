"""Optional LLM hypothesis generation, always gated by SMT proof obligations."""
from __future__ import annotations
import json, os
from urllib import request
from .smt_spath import SMTPathGraph, SMTGraphError, _check, _z3_expr

class SMTProposalError(ValueError):pass


def check_proposals(analyzer:SMTPathGraph,data:dict):
    """Accept no guessed formula or boundary without independent Z3 checks."""
    if not isinstance(data,dict):raise SMTProposalError('Proposals must be a JSON object')
    inv=data.get('invariants',[])
    cycles=data.get('cycles',[])
    boundaries=data.get('phase_boundaries',[])
    if not isinstance(inv,list) or not isinstance(cycles,list) or not isinstance(boundaries,list):
        raise SMTProposalError('Expect invariants, cycles, phase_boundaries arrays')
    if len(inv)>30 or len(cycles)>20 or len(boundaries)>30:
        raise SMTProposalError('Too many candidates')
    invariant_checks=analyzer.certify_invariants(inv)
    phase_checks=[]
    for b in boundaries:
        try:
            name=b['path'];claim=b['when']
            if name not in analyzer.paths: raise SMTProposalError('Unknown path name')
            claimed=_z3_expr(claim,analyzer.env)
            import z3
            diff=z3.Xor(claimed,analyzer.paths[name].guard)
            result=_check(analyzer.pre,analyzer._invariant(),analyzer.loop_guard,diff)
            phase_checks.append({'path':name,'candidate':claim,'certified':result=='unsat',
                                 'method':'SMT predicate equivalence', 'solver':result})
        except (KeyError, TypeError, SMTGraphError) as exc:
            phase_checks.append({'certified':False,'reason':str(exc)})
    cycle_checks=[analyzer.verify_cycle_proposal(p) for p in cycles]
    acceleration=analyzer.try_accelerate()
    return {'status':'VERIFIED_CANDIDATES_ONLY','invariants':invariant_checks,
            'phase_boundaries':phase_checks,'cycles':cycle_checks,
            'acceleration':acceleration,
            'notice':'Candidates are not proofs; accepted results have independent SMT certificates'}


def propose_and_check(analyzer:SMTPathGraph,model:str,
                      base_url:str='https://api.openai.com/v1',timeout:int=30):
    key=os.getenv('OPENAI_API_KEY')
    if not key:raise SMTProposalError('OPENAI_API_KEY is required for opt-in LLM analysis')
    prompt={'task':'Propose loop invariants, phase boundaries and periodic macro candidates.',
            'output_schema':{'invariants':['x >= 0 and x <= 7'],
               'phase_boundaries':[{'path':'p0','when':'p == 0'}],
               'cycles':[{'phase_sequence':['p0','p1'],
                          'macro_map':{v:'expression' for v in analyzer.variables}}]},
            'semantics':'mathematical integers, simultaneous state updates',
            'program':{'state':analyzer.obj.get('state'),
                       'paths':analyzer.obj.get('paths'),
                       'loop_guard':analyzer.obj.get('loop_guard'),
                       'parameters':list(analyzer.parameters),
                       'parameter_bounds':analyzer.lower_bounds},
            'spath_overapproximation':analyzer.analyze()['spath_edges'],
            'requirements':'JSON only. At most 8 candidates per type; no proofs claimed.'}
    payload={'model':model,'temperature':0,'max_tokens':1600,
             'messages':[{'role':'system','content':'You only propose candidates. A separate SMT verifier decides validity.'},
                         {'role':'user','content':json.dumps(prompt)}]}
    req=request.Request(base_url.rstrip('/')+'/chat/completions',
          data=json.dumps(payload).encode(),method='POST',
          headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with request.urlopen(req,timeout=timeout) as response:r=json.load(response)
        content=r['choices'][0]['message']['content']
        if not isinstance(content,str) or len(content)>30000:raise ValueError('Oversized response')
        proposal=json.loads(content)
    except Exception as exc:
        raise SMTProposalError('LLM transport or JSON failed: '+str(exc)) from exc
    return {'model':model,'origin':'untrusted LLM','results':check_proposals(analyzer,proposal)}
