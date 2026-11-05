"""Official supplied-bound smoke, native compatibility environment, no LLM."""
import argparse, json, sys
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);a=p.parse_args()
    root=a.root.resolve();tmp=a.workspace.resolve();tmp.mkdir(parents=True,exist_ok=True)
    sys.path[:0]=[str(root/'code/Guess_Check'),str(root/'code'),str(root)]
    from Check_loop_bound_newiter import BoogieVerifier,extract_variables_from_bpl
    from K_Transform import K_Transformer
    class ScopedVerifier(BoogieVerifier):
        def _kill_related_processes(self):
            pass  # Parent owns this process group; no global process-name kills.
    origin=root/'experiment/benchmarks-Instrumented/for_bounded_loop1_false-unreach-call_true-termination-simplified/for_bounded_loop1_false-unreach-call_true-termination-simplified.bpl'
    transformer=K_Transformer(str(tmp),str(origin),'i')
    verifier=ScopedVerifier(transformer.fileName,str(origin),learner='dt_penalty',varlist=extract_variables_from_bpl(str(origin)),project_dir=str(root))
    verifier.ensure_varlist_contains('i');verifier.timeout=20
    verifier.GenerateConcreteBplFile([('i','n - _i')])
    transformer.GenerateConcreteBplFile(1,withinv=True)
    ret,inv,cex=verifier.run_verification(transformer.K_fileName)
    print(json.dumps({'result':ret,'kind':'provided_bound_no_llm_smoke','remote_model_calls':0,'cleanup_adaptation':'upstream name-wide cleanup disabled; parent owns process group'}))
    if ret!=1:raise SystemExit(1)

if __name__=='__main__':main()
