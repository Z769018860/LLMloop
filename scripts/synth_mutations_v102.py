"""Three oracle mutations tested by concrete semantic controls; not mutation coverage of the entire verifier."""
import hashlib, inspect, json
from pathlib import Path
from scripts.synth_bench_v102 import explore, INT_MIN, INT_MAX
ROOT=Path(__file__).resolve().parents[1]

def case(cond,body):
    return {'inputs':['a'],'loc':['x','y'],'lo':0,'hi':0,'inits':{'x':'0','y':'0'},'cond':cond,'body':body}

def main():
    source=inspect.getsource(explore)
    tasks=[
        ('correlated_calls','value = next(it); used.append(value); return value', 'value = next(it); value = sequence[0]; used.append(value); return value',
         case('nd',[('if','nd','x = 0;','x = 2147483647 + 1;')]),'OVERFLOW'),
        ('ignore_intermediate_overflow','if not INT_MIN <= r <= INT_MAX: raise Ovf()', 'if False: raise Ovf()',
         case('x < 1',[('asg','x = (2147483647 + 1) - 1;')]),'OVERFLOW'),
        ('lose_short_circuit',"r = bool(ev(v, env, choose))", "r = bool(ev(v, env, choose)); extra = [ev(w, env, choose) for w in n.values]",
         case('x < 0 && 2147483647 + 1 > 0',[('asg','x = 1;')]),'SAFE')]
    rows=[]
    for name,old,new,spec,expected in tasks:
        assert old in source
        mutated=source.replace(old,new);scope={'INT_MIN':INT_MIN,'INT_MAX':INT_MAX};exec(compile(mutated,name,'exec'),scope)
        baseline=explore(spec);actual=scope['explore'](spec)
        rows.append({'mutation':name,'baseline_expected':expected,'baseline':baseline,'mutant':actual,'detected':baseline==expected and actual!=expected,
                     'mutant_sha256':hashlib.sha256(mutated.encode()).hexdigest(),'replaced':old,'replacement':new,'spec':spec})
    out=ROOT/'experiments/v102/oracle_mutations.json'
    out.write_text(json.dumps({'scope':'three targeted oracle semantic mutants; no complete verifier/translator mutation score','all_detected':all(r['detected']for r in rows),'rows':rows},indent=2)+'\n')
    print([(r['mutation'],r['detected'])for r in rows])
if __name__=='__main__':main()
