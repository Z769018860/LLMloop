"""Original/snapshot/normalized finite VLA oracles and independent UB controls."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

import z3

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from scripts.check_clang_arrays_native import native, source_report, execute


def fixtures():
    return [
        dict(name='saved_sizeof',header='int api(int n);',helper='int api(int n){return n;}',
             main='int entry(int n){int a[n];n=1;return (int)sizeof(a);}',oracle=lambda n:4*n),
        dict(name='initialize_last',header='int api(int *p,int n);',helper='int api(int *p,int n){for(int i=0;i<n;i++){p[i]=i+1;}return p[n-1];}',
             main='int entry(int n){int a[n];return api(a,n);}',oracle=lambda n:n),
        dict(name='provider_vla_long',header='int api(unsigned char n);',helper='int api(unsigned char n){long a[n];n=1;return (int)sizeof(a);}',
             main='int entry(int n){return api(n+256);}',oracle=lambda n:8*n),
        dict(name='static_capacity',header='int api(int p[static 3]);',helper='int api(int *p){p[2]=7;return p[2];}',
             main='int entry(int n){if(n<3)return 0;int a[n];return api(a);}',oracle=lambda n:0 if n<3 else 7),
        dict(name='ordinary_interior_slice',header='int api(int p[],int n);',helper='int api(int p[],int n){p[0]=n;return p[0]+p[1];}',
             main='int entry(int n){if(n<3)return 0;int a[n];a[2]=n+1;return api(a+1,n);}',oracle=lambda n:0 if n<3 else 2*n+1),
        dict(name='two_saved_extents',header='int api(int n);',helper='int api(int n){return n;}',
             main='int entry(int n){int a[n];n=2;int b[n];return (int)(sizeof(a)+sizeof(b));}',oracle=lambda n:4*(n+2)),
        dict(name='sizeof_bool',header='int api(int n);',helper='int api(int n){return n;}',
             main='int entry(int n){_Bool a[n];return (int)sizeof(a);}',oracle=lambda n:n),
        dict(name='repeated_helper_frames',header='int api(int n);',helper='int api(int n){int a[n];return (int)sizeof(a);}',
             main='int entry(int n){int x=api(n);return x+api(2);}',oracle=lambda n:4*(n+2)),
    ]


def replay(report):
    counts=Counter()
    for q in report['memory_model']['bounded_local_vla']['queries']:
        solver=z3.Solver();solver.set(timeout=5000);solver.from_string(q['smt2']);answer=str(solver.check())
        assert answer==('unsat' if q['proved'] else 'sat'),q
        counts[answer]+=1
    return dict(counts)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    rows=[];negative=[];frontiers=[];matches=models=traps=memory=0;queries=Counter()
    compilers={'gcc':'gcc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='bounded-vla-native-') as directory:
        root=Path(directory)
        for case in fixtures():
            values=list(range(1,9));path=root/case['name'];report,forms=source_report(path,case,values)
            assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',(case['name'],report)
            assert report['normalization']['bounded_vla_declarations']
            assert report['memory_model']['bounded_local_vla']['extent_assumed'] is False
            replays=replay(report);queries.update(replays)
            expected=[str(case['oracle'](n)) for n in values];observations=[]
            for tag,compiler in compilers.items():
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,values)
                    for form,run in outputs.items():
                        assert run['exit_code']==0 and not run['stderr'] and run['stdout'].splitlines()==expected,(case['name'],tag,opt,form,run,expected)
                        matches+=len(expected)
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            for n in values:
                evaluated=analyze_request({'source':forms['normalized'][0],'function':'entry','frontend':'typed_cfg_calls',
                    'parameter_bounds':{'n':[1,8]},'inputs':{'n':n},'max_steps':256})
                assert evaluated['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS' and evaluated['evaluation']['value']==case['oracle'](n)
                models+=1
            rows.append({'name':case['name'],'forms':forms,'header':case['header'],
                'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,
                'independent_expected':expected,'observations':observations})
            print(case['name'],'native and model passed',flush=True)
        controls=[
            dict(name='zero_bound',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];return 7;}',values=[0]),
            dict(name='negative_bound',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];return 7;}',values=[-1]),
            dict(name='body_overflow',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];a[0]=2147483647;return a[0]+1;}',values=[3]),
            dict(name='body_bounds',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];a[n]=7;return a[n];}',values=[3],address=True),
        ]
        for case in controls:
            path=root/case['name'];report,forms=source_report(path,case,case['values'])
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            replays=replay(report);queries.update(replays);observations=[]
            for tag,compiler in compilers.items():
                if case.get('address') and tag!='gcc':continue
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,case['values'],address=case.get('address',False))
                    for form,run in outputs.items():
                        if case.get('address'):
                            assert run['exit_code']!=0 and (any(label in run['stderr'] for label in ('dynamic-stack-buffer-overflow','stack-buffer-overflow','insufficient space for an object'))
                                or 'index 3 out of bounds for type' in run['stderr']),run
                            memory+=1
                        else:
                            assert run['exit_code']==-4,(case['name'],tag,opt,form,run)
                            traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':case['name'],'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},
                'query_replays':replays,'observations':observations})
        # Nine cells are defined C in this native environment, but exceed this
        # proof representation. Do not turn a resource frontier into source UB.
        case=dict(name='nine_cell_frontier',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];return (int)sizeof(a);}')
        path=root/case['name'];report,forms=source_report(path,case,[9]);assert report['analysis_limit']=='bounded_vla_capacity_frontier'
        queries.update(replay(report));observations=[]
        for tag,compiler in compilers.items():
            for opt in ('-O0','-O2'):
                outputs,commands=native(path,compiler,tag,opt,{'original':forms['original']},[9])
                assert outputs['original']=={'exit_code':0,'stdout':'36\n','stderr':''},outputs
                observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
        frontiers.append({'name':case['name'],'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},
            'observations':observations,'claimed_source_unsafe':False,'counted_as_proved':False})
    assert (matches,models,traps,memory)==(768,64,36,6),(matches,models,traps,memory)
    result={'passed':True,'case_count':len(rows),'native_output_matches':matches,'independent_model_matches':models,
        'expected_ubsan_traps':traps,'expected_memory_failures':memory,'query_replays':dict(queries),
        'capacity_frontiers':len(frontiers),'native_valid_frontier_runs':4,'compilers':['gcc','clang'],
        'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],
        'cases':rows,'negative_controls':negative,'frontier_controls':frontiers,
        'scope':'Bounded local integer VLA with scalar-parameter bound and <=8 represented cells. '
                'No VLA parameters, bound effects, nested declarations, source goto, general arrays or LLVM semantics.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','frontier_controls')}),flush=True)


if __name__=='__main__':main()
