"""Optional LLM-guided invariant proposals, with *mandatory* algebraic checks.

No user source code is sent to a model unless this function is explicitly
called. The model cannot approve its own candidate. No prompts, API keys or
model outputs are included in universal proof certificates.
"""
from __future__ import annotations
import json,os
from urllib import request
from .graph import GraphAnalyzer
from .invariants import check_invariant

class ProposalError(RuntimeError):pass

def verify_proposals(graph:GraphAnalyzer, candidates:list[str], minima:dict[str,int]|None=None):
    if not isinstance(candidates,list) or len(candidates)>30:
        raise ProposalError('Expected at most 30 invariant strings')
    output=[]
    for expr in candidates:
        if not isinstance(expr,str) or len(expr)>400:
            output.append({'candidate':str(expr)[:40],'proved':False,'reason':'Invalid candidate'})
            continue
        output.append({'candidate':expr,**check_invariant(graph,expr,minima)})
    return {'candidates':output,'proved_count':sum(bool(x.get('proved')) for x in output),
            'status':'VERIFIED_PROPOSALS_ONLY'}

def propose_and_verify(graph:GraphAnalyzer,model:str,inputs:dict[str,int]|None=None,
                       minima:dict[str,int]|None=None,
                       base_url:str='https://api.openai.com/v1',timeout:int=30):
    secret=os.getenv('OPENAI_API_KEY')
    if not secret:raise ProposalError('OPENAI_API_KEY is required for opt-in LLM calls')
    sample_inputs=inputs or {name:0 for name in graph.parameters}
    # A short trace is explanation only. It is never used as a proof.
    trace=[graph.after_steps(k,sample_inputs) for k in range(min(5,graph.transient_len+graph.macro_steps))]
    prompt={'task':'Suggest integer loop invariants as a JSON object: {"candidates":["i >= 0",...]}.',
            'supported_relations':['==','>=','<='],
            'state':graph.variables,'paths':graph.phases,
            'example_symbolic_trace':trace,'parameter_minima':minima or {},
            'instructions':'Propose at most 12 concise relations. No prose. Do not assume unlisted input bounds.'}
    payload={'model':model,'temperature':0,'max_tokens':900,
             'messages':[{'role':'system','content':'Propose candidate mathematical relations; only the verifier may certify them.'},
                         {'role':'user','content':json.dumps(prompt)}]}
    req=request.Request(base_url.rstrip('/')+'/chat/completions',
        data=json.dumps(payload).encode('utf-8'),method='POST',
        headers={'Content-Type':'application/json','Authorization':'Bearer '+secret})
    try:
        with request.urlopen(req,timeout=timeout) as response:result=json.load(response)
        text=result['choices'][0]['message']['content']
        if not isinstance(text,str) or len(text)>12000:raise ValueError('Oversize response')
        obj=json.loads(text)
        proposals=obj['candidates']
    except Exception as exc:raise ProposalError('Model proposal failed: '+str(exc)) from exc
    return {'model':model,'source':'untrusted LLM',
            **verify_proposals(graph,proposals,minima)}
