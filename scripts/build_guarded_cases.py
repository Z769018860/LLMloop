"""Deterministic experiment fixtures; includes positive and negative controls."""
import copy
import json
from pathlib import Path


def cases():
    base = json.loads((Path(__file__).resolve().parents[1]/'examples/guarded_saturation.json').read_text())
    result = []
    def add(name,obj,expected='CERTIFIED_GUARDED_RECURRENCE_CLOSED_FORM',inputs=None):
        request = {'ir':obj}
        if inputs is not None:request['inputs'] = inputs
        result.append({'name':name,'request':request,'expected_status':expected})
    add('unbounded_saturation',copy.deepcopy(base))
    add('billion_iteration_saturation',copy.deepcopy(base),inputs={'n':1000000000,'k':1000000001})
    for bound in [0,1,7]:
        obj=copy.deepcopy(base);obj['parameter_bounds']['n']=[bound,bound]
        add('fixed_threshold_'+str(bound),obj)
    countdown = {'kind':'guarded_recurrence','state':{'x':'n'},'parameters':['n'],
                 'parameter_bounds':{'n':[0,None]},
                 'branches':[{'guard':'x>0','updates':{'x':'x-1'}},{'guard':'x<=0','updates':{}}],
                 'closed_forms':{'x':'Max(n-k,0)'}}
    add('unbounded_countdown',countdown)
    add('absolute_value_transient',{'kind':'guarded_recurrence','state':{'x':'a'},'parameters':['a'],
         'branches':[{'guard':'x<0','updates':{'x':'-x'}},{'guard':'x>=0','updates':{}}],
         'closed_forms':{'x':'a if k == 0 else Abs(a)'}})
    add('nonperiodic_step_change',{'kind':'guarded_recurrence','state':{'x':0},'parameters':['n'],
         'parameter_bounds':{'n':[0,None]},
         'branches':[{'guard':'k<n','updates':{'x':'x+1'}},{'guard':'k>=n','updates':{'x':'x+2'}}],
         'closed_forms':{'x':'k if k<n else 2*k-n'}})
    add('nonlinear_idempotent',{'kind':'guarded_recurrence','state':{'x':'a'},'parameters':['a'],
         'parameter_bounds':{'a':[0,1]},'branches':[{'guard':True,'updates':{'x':'x*x'}}],
         'closed_forms':{'x':'a'}})
    add('modular_reset',{'kind':'guarded_recurrence','state':{'x':0},
         'branches':[{'guard':'x<2','updates':{'x':'x+1'}},{'guard':'x>=2','updates':{'x':0}}],
         'closed_forms':{'x':'k%3'}})
    mutations = [
        ('wrong_base',lambda o:o['closed_forms'].update(x='Min(k,n)+1')),
        ('wrong_successor',lambda o:o['closed_forms'].update(x='Min(k,n)+k')),
        ('late_failure',lambda o:o['closed_forms'].update(x='Min(k,n) if k<1000000 else Min(k,n)+1')),
        ('overlapping_branches',lambda o:o['branches'][1].update(guard=True)),
        ('missing_branch',lambda o:o['branches'][1].update(guard='x>n')),
        ('empty_parameter_domain',lambda o:o['parameter_bounds'].update(n=[2,1])),
        ('partial_division',lambda o:o['closed_forms'].update(x='k//k')),
        ('unsupported_exponential_candidate',lambda o:o['closed_forms'].update(x='2**k')),
    ]
    for name,mutate in mutations:
        obj=copy.deepcopy(base);mutate(obj);add(name,obj,'UNKNOWN')
    return result


if __name__ == '__main__':
    path=Path(__file__).resolve().parents[1]/'experiments/v014/cases.json'
    path.write_text(json.dumps(cases(),indent=2)+'\n')
