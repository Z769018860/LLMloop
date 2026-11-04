"""Sizeof-dependent VLA bounds against independent native and scalar oracles."""
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
        row('const_scalar_object_size','const int m=2;int b[n+sizeof(m)];n=1;return (int)sizeof(b);',lambda n:4*(n+4)),
        row('void_pointer_type_size','int b[n+sizeof(void*)/sizeof(void*)];return (int)sizeof(b);',lambda n:4*(n+1)),
        row('null_pointer_object_size','int *p=0;int b[n+sizeof(p)/sizeof(int)];return (int)sizeof(b);',lambda n:4*(n+2)),
        row('saved_extent_after_mutation','int old=n;int a[n];n=7;int b[sizeof(a)/sizeof(int)];b[old-1]=old;return (int)sizeof(b)+b[old-1];',lambda n:5*n),
        row('uninitialized_fixed_array_size','int a[2];int b[n+sizeof(a)/sizeof(int)];return (int)sizeof(b);',lambda n:4*(n+2)),
        row('three_array_size_chain','int a[n];int b[sizeof(a)/sizeof(int)];int c[sizeof(b)/sizeof(int)];return (int)(sizeof(a)+sizeof(b)+sizeof(c));',lambda n:12*n),
        row('loop_dependent_storage','int sum=0;for(int i=1;i<=n;i++){int a[i];int b[sizeof(a)/sizeof(int)];b[i-1]=i;sum+=(int)sizeof(b)+b[i-1];}return sum;',lambda n:5*n*(n+1)//2),
        row('dependent_for_initializer','int a[n];int sum=0;for(int b[sizeof(a)/sizeof(int)];n>0;n--){sum+=(int)sizeof(b);}return sum;',lambda n:4*n*n),
        row('expired_pointee_size_only','int *p=0;{int a[n];p=a;}int b[n+sizeof(p)/sizeof(int)];return (int)sizeof(b);',lambda n:4*(n+2)),
        row('converted_formal_size','return api(n+256);',lambda n:4*(n+1),header='int api(unsigned char m);',helper='int api(unsigned char m){int a[m];m=7;int b[sizeof(a)/sizeof(int)+sizeof(m)];return (int)sizeof(b);}'),
        row('adjusted_parameter_pointer_size','int a[1]={0};return api(a,n);',lambda n:4*(n+2),header='int api(int p[],int m);',helper='int api(int p[],int m){int b[m+sizeof(p)/sizeof(int)];return (int)sizeof(b);}'),
        row('dependent_static_capacity','int a[n];int b[sizeof(a)/sizeof(int)+1];b[1]=n;return api(b);',lambda n:n,header='int api(int p[static 2]);',helper='int api(int *p){return p[1];}'),
    ]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    cases=[];negative=[];frontiers=[];symbolic=[];sanitizer_gaps=[];matches=models=traps=memory=frontier_matches=gap_traps=gap_misses=0;queries=Counter()
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-vla-sizeof-') as temp:
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
            ('signed_size_overflow','(int)sizeof(a)+2147483647',False),('size_zero_divisor','sizeof(a)/(n-n)',False),
            ('size_shift_width','(int)sizeof(a)<<(n+31)',False),('nonpositive_size_expression','sizeof(a)/sizeof(int)-n',False),
            ('unsafe_executed_initializer','n+sizeof(m)',False),('actual_dependent_bounds','sizeof(a)/sizeof(int)',True),
        ]:
            values=[3] if address else [1]
            body='int a[n];'+('int m=n/(n-1);' if name=='unsafe_executed_initializer' else '')+'int b['+expression+'];'+('b[n]=n;return 7;' if address else 'return '+('m+' if name=='unsafe_executed_initializer' else '')+'(int)sizeof(b);')
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
                            assert run['exit_code']!=0 and (any(s in run['stderr'] for s in ('dynamic-stack-buffer-overflow','stack-buffer-overflow','insufficient space for an object')) or 'index 3 out of bounds for type' in run['stderr']),run
                            memory+=1
                        else:assert run['exit_code']==-4,(name,tag,opt,run);traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':name,'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'observations':observations})
        # Preserve an unused-result control separately: sanitizer silence on
        # optimized UB must never replace the guarded source obligation.
        case=dict(name='unused_overflow_sanitizer_coverage',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];int b[(int)sizeof(a)+2147483647];return 7;}')
        path=root/case['name'];report,forms=source_report(path,case,[1])
        assert report['status']=='UNKNOWN' and report['failed_obligation'].startswith('VLA bound positive')
        observations=[]
        for tag,compiler in compilers.items():
            for opt in ('-O0','-O2'):
                outputs,commands=native(path,compiler,tag,opt,forms,[1])
                for run in outputs.values():
                    if run['exit_code']==-4:gap_traps+=1
                    else:
                        assert run['exit_code']==0 and run['stdout']=='7\n' and not run['stderr'],run
                        gap_misses+=1
                observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
        sanitizer_gaps.append({'name':case['name'],'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'forms':forms,'observations':observations,'sanitizer_silence_is_not_definedness':True})
        case=dict(name='defined_nine_cell_frontier',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int a[n];int b[sizeof(a)/sizeof(int)+6];return (int)sizeof(b);}')
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
            ('uninitialized_next_iteration','int sum=0;for(int i=0;i<2;i++){int a[n];int b[sizeof(a)/sizeof(int)];if(i==0)b[0]=n;else sum=b[0];}return sum;',''),
            ('expired_block_alias','int *p=0;{int a[n];int b[sizeof(a)/sizeof(int)];b[0]=n;p=b;}return p[0];',''),
            ('expired_iteration_alias','int *p=0;int sum=0;for(int i=0;i<2;i++){int a[n];int b[sizeof(a)/sizeof(int)];if(i==0){b[0]=n;p=b;}else sum=p[0];}return sum;',''),
            ('expired_for_initializer','int *p=0;int a[n];for(int b[sizeof(a)/sizeof(int)];n>0;n--){b[0]=n;p=b;}return p[0];',''),
            ('unused_static_minimum','int a[n];int b[sizeof(a)/sizeof(int)];return api(b);','int api(int p[static 4]){return 7;}'),
        ]:
            request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':'clang_proof','proof':{'backend':'calls','parameter_bounds':{'n':[1,3]},'max_steps':256}}
            report=analyze_request(request)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            assert all(q['proved'] for q in report['memory_model']['bounded_local_vla']['queries'])
            if name=='unused_static_minimum':assert report['failed_obligation'].startswith('static array minimum extent')
            symbolic.append({'name':name,'request':request,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'native_sanitizer_detection_claimed':False})
    assert (matches,models,traps,memory,frontier_matches,len(symbolic))==(432,36,60,6,12,5)
    assert gap_traps+gap_misses==12
    result={'passed':True,'case_count':len(cases),'native_output_matches':matches,'independent_model_matches':models,'expected_ubsan_traps':traps,'expected_memory_failures':memory,'defined_capacity_frontier_matches':frontier_matches,'symbolic_controls':len(symbolic),'unused_overflow_sanitizer_traps':gap_traps,'unused_overflow_sanitizer_misses':gap_misses,'sanitizer_coverage_records':sanitizer_gaps,'query_replays':dict(queries),'cases':cases,'negative_controls':negative,'capacity_frontiers':frontiers,'symbolic_control_records':symbolic,'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],'scope':'Sizeof non-VM integer/data-pointer type names and declared scalar/pointer/integer-array objects. Size-only identifiers are not read; VLA arrays use saved extents. No complex sizeof operands, VM type names, typedef casts, VLA parameters or general layouts; eight-cell/eight-object budgets retained.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','capacity_frontiers','symbolic_control_records','sanitizer_coverage_records')}),flush=True)


if __name__=='__main__':main()
