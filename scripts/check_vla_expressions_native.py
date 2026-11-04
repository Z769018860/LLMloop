"""Pure VLA bound expressions against independent native and scalar oracles."""
import argparse
from collections import Counter
import json
from pathlib import Path
import tempfile

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from scripts.check_clang_arrays_native import native,source_report
from scripts.check_bounded_vla_native import replay


def fixtures():
    def row(name,body,oracle,header='int api(int n);',helper='int api(int n){return n;}'):
        return dict(name=name,header=header,helper=helper,main='int entry(int n){'+body+'}',oracle=oracle)
    return [
        row('macro_saved_arithmetic','int old=n;int a[VLA_COUNT(n)];a[n]=n;n=1;return a[old]+(int)sizeof(a);',lambda n:5*n+4,header='#define VLA_COUNT(x) ((x)+1)\nint api(int n);'),
        row('multiple_scalar_leaves','int m=2;int old=n+m;int a[n+m];a[old-1]=old;n=1;m=7;return a[old-1]+(int)sizeof(a);',lambda n:5*(n+2)),
        row('unsigned_shift','int a[1U<<n];a[0]=n;return a[0]+(int)sizeof(a);',lambda n:n+4*(1<<n)),
        row('lazy_unsafe_arm','int a[n>0?n+1:1/(n-n)];return (int)sizeof(a);',lambda n:4*(n+1)),
        row('mixed_unsigned','int a[(unsigned)n-1U+1U];return (int)sizeof(a);',lambda n:4*n),
        row('narrow_conversion','int a[(unsigned char)(n+256)+1];return (int)sizeof(a);',lambda n:4*(n+1)),
        row('fresh_loop_extents','int sum=0;for(int i=1;i<=n;i++){int a[i+1];a[i]=i;sum+=(int)sizeof(a)+a[i];}return sum;',lambda n:5*n*(n+1)//2+4*n),
        row('saved_for_initializer','int sum=0;for(int a[n+1];n>0;n--){sum+=(int)sizeof(a);}return sum;',lambda n:4*n*(n+1)),
        row('division_remainder','int a[n/2+n%2+1];return (int)sizeof(a);',lambda n:4*(n//2+n%2+1)),
        row('converted_helper_formal','return api(n+256);',lambda n:4*(n+1),header='int api(unsigned char m);',helper='int api(unsigned char m){int a[m+1];m=1;return (int)sizeof(a);}'),
        row('helper_initializes_leaf','int m=api(n);int a[m+1];return (int)sizeof(a);',lambda n:4*(n+2),helper='int api(int n){return n+1;}'),
        row('static_entry_capacity','int a[n+1];a[1]=n;return api(a);',lambda n:n,header='int api(int p[static 2]);',helper='int api(int *p){return p[1];}'),
    ]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    cases=[];negative=[];frontiers=[];symbolic=[];matches=models=traps=memory=frontier_matches=0;queries=Counter()
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-vla-expressions-') as temp:
        root=Path(temp)
        for case in fixtures():
            values=[1,2,3];path=root/case['name'];report,forms=source_report(path,case,values)
            assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',(case['name'],report)
            replays=replay(report);queries.update(replays);expected=[str(case['oracle'](n)) for n in values];observations=[]
            for tag,compiler in compilers.items():
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,values)
                    for run in outputs.values():
                        assert run['exit_code']==0 and not run['stderr'] and run['stdout'].splitlines()==expected,(case['name'],tag,opt,run,expected)
                        matches+=len(expected)
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            for n in values:
                r=analyze_request({'source':forms['normalized'][0],'function':'entry','frontend':'typed_cfg_calls','parameter_bounds':{'n':[1,3]},'inputs':{'n':n},'max_steps':256})
                assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS' and r['evaluation']['value']==case['oracle'](n),(case['name'],n,r)
                models+=1
            cases.append({'name':case['name'],'header':case['header'],'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'independent_expected':expected,'observations':observations})
            print(case['name'],'native/model passed',flush=True)
        for name,expression,address in [
            ('signed_bound_overflow','n+2147483647',False),('bound_zero_divisor','n/(n-1)',False),
            ('bound_shift_width','1<<(n+31)',False),('nonpositive_expression','n-1',False),
            ('actual_dynamic_bounds','n+1',True),
        ]:
            values=[3] if address else [1]
            body='int a['+expression+'];'+('a[n+1]=n;' if address else '')+'return 7;'
            case=dict(name=name,header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){'+body+'}')
            path=root/name;report,forms=source_report(path,case,values)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            replays=replay(report);queries.update(replays);observations=[]
            for tag,compiler in compilers.items():
                if address and tag!='gcc':continue
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,values,address=address)
                    for run in outputs.values():
                        if address:
                            assert run['exit_code']!=0 and (any(s in run['stderr'] for s in ('dynamic-stack-buffer-overflow','stack-buffer-overflow','insufficient space for an object')) or 'index 4 out of bounds for type' in run['stderr']),run
                            memory+=1
                        else:assert run['exit_code']==-4,(name,tag,opt,run);traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':name,'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'observations':observations})
        case=dict(name='defined_nine_cell_frontier',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n+6];return (int)sizeof(a);}')
        path=root/case['name'];report,forms=source_report(path,case,[3])
        assert report['status']=='UNKNOWN' and report['analysis_limit']=='bounded_vla_capacity_frontier'
        replays=replay(report);queries.update(replays);observations=[]
        for tag,compiler in compilers.items():
            for opt in ('-O0','-O2'):
                outputs,commands=native(path,compiler,tag,opt,forms,[3])
                for run in outputs.values():assert run['exit_code']==0 and not run['stderr'] and run['stdout']=='36\n',run;frontier_matches+=1
                observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
        frontiers.append({'name':case['name'],'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'forms':forms,'observations':observations,'native_source_defined':True,'model_capacity_unchanged':8})
        for name,body,prefix in [
            ('uninitialized_next_iteration','int sum=0;for(int i=0;i<2;i++){int a[n+1];if(i==0)a[0]=n;else sum=a[0];}return sum;',''),
            ('expired_block_alias','int *p=0;{int a[n+1];a[0]=n;p=a;}return p[0];',''),
            ('expired_iteration_alias','int *p=0;int sum=0;for(int i=0;i<2;i++){int a[n+1];if(i==0){a[0]=n;p=a;}else sum=p[0];}return sum;',''),
            ('expired_for_initializer','int *p=0;for(int a[n+1];n>0;n--){a[0]=n;p=a;}return p[0];',''),
            ('unused_static_minimum','int a[n+1];return api(a);','int api(int p[static 3]){return 7;}'),
        ]:
            request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':'clang_proof','proof':{'backend':'calls','parameter_bounds':{'n':[1,3]},'max_steps':256}}
            report=analyze_request(request)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            assert all(q['proved'] for q in report['memory_model']['bounded_local_vla']['queries'])
            if name=='unused_static_minimum':assert report['failed_obligation'].startswith('static array minimum extent')
            symbolic.append({'name':name,'request':request,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'native_sanitizer_detection_claimed':False})
    assert (matches,models,traps,memory,frontier_matches,len(symbolic))==(432,36,48,6,12,5)
    result={'passed':True,'case_count':len(cases),'native_output_matches':matches,'independent_model_matches':models,'expected_ubsan_traps':traps,'expected_memory_failures':memory,'defined_capacity_frontier_matches':frontier_matches,'symbolic_controls':len(symbolic),'query_replays':dict(queries),'cases':cases,'negative_controls':negative,'capacity_frontiers':frontiers,'symbolic_control_records':symbolic,'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],'scope':'Pure typed integer VLA bounds; each expression evaluated once per declaration execution. No effects, memory reads, calls, general sizeof, typedef casts, VLA parameters or multidimensional layouts; existing eight-cell/eight-object budgets retained.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','capacity_frontiers','symbolic_control_records')}),flush=True)


if __name__=='__main__':main()
