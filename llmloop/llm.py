"""Optional LLM proposals; no language-model output is considered a proof."""
from __future__ import annotations
import json
import os
from urllib import request
from .core import LoopAnalyzer
class LLMError(RuntimeError):
    pass
def propose_cycle_map(analyzer:LoopAnalyzer,model:str,base_url:str="https://api.openai.com/v1",
                      api_key:str|None=None,timeout:int=30)->dict:
    key=api_key or os.getenv("OPENAI_API_KEY")
    if not key: raise LLMError("Set OPENAI_API_KEY")
    prompt={"task":"Propose a complete full-cycle state transformation.",
            "semantics":"mathematical integers, simultaneous affine assignments",
            "variables":list(analyzer.variables),"phases":analyzer.phases,
            "schema":{"cycle_map":{v:"expression" for v in analyzer.variables}},
            "rules":"JSON object only; use only +,-,*,integer constants and state names."}
    req=request.Request(base_url.rstrip("/")+"/chat/completions",
       data=json.dumps({"model":model,"temperature":0,"max_tokens":700,
         "messages":[{"role":"system","content":"Return a candidate JSON object, not a proof."},
                     {"role":"user","content":json.dumps(prompt)}]}).encode(),
       headers={"Content-Type":"application/json","Authorization":"Bearer "+key},method="POST")
    try:
        with request.urlopen(req,timeout=timeout) as response: result=json.load(response)
        raw=result["choices"][0]["message"]["content"]
        if not isinstance(raw,str) or len(raw)>10000: raise ValueError("Oversized response")
        proposal=json.loads(raw)
        candidate=proposal["cycle_map"]
        if not isinstance(candidate,dict): raise ValueError("Missing cycle_map object")
    except Exception as exc:
        raise LLMError("LLM request or response failed: "+str(exc)) from exc
    verified=analyzer.verify_cycle_candidate(candidate)
    return {"model":model,"candidate":candidate,"verification":verified,
            "used_for_proof":bool(verified["accepted"])}
