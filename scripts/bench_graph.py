"""Local bounded correctness/efficiency smoke experiment. Never run in CI."""
from __future__ import annotations
import argparse,json,time
from pathlib import Path
from llmloop.graph import GraphAnalyzer

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--source',default='examples/three_scc.json')
    p.add_argument('--n',type=int,default=300)
    a=p.parse_args()
    if not 0<=a.n<=3000:raise SystemExit('--n must be in [0,3000] for direct comparison')
    analyzer=GraphAnalyzer(json.loads(Path(a.source).read_text()))
    inputs={analyzer.parameters[0]:a.n}
    t0=time.perf_counter(); summary=analyzer.execute_until_exit(inputs);t1=time.perf_counter()
    oracle=analyzer.concrete(summary['trip_count'],inputs);t2=time.perf_counter()
    assert summary['final_state']==oracle
    print(json.dumps({'n':a.n,'steps':summary['trip_count'],
        'accelerated_s':round(t1-t0,6),'direct_s':round(t2-t1,6),
        'same_final_state':True},indent=2))
if __name__=='__main__':main()
