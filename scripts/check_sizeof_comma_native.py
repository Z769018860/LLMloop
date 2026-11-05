"""Unevaluated comma and void-discard sizeof operands against independent native and scalar oracles."""
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
        row('discarded_increment','unsigned char c=1;int b[n+sizeof((n++,c))];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('discarded_zero_divisor_assignment','unsigned char c=1;int b[n+sizeof((n=1/0,c))];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('discarded_invalid_shift','unsigned char c=1;int b[n+sizeof((1<<100,c))];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('discarded_null_index','int *p=0;unsigned char c=1;int b[n+sizeof((p[n++],c))];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('last_uninitialized_element','int a[1];int b[n+sizeof((n++,a[n]))];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('last_array_decays','int a[n];int b[n+sizeof((n++,a))/sizeof(int*)];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('narrow_result_not_promoted','unsigned char c=2;int b[n+sizeof((n=0,c))];return n+c+(int)sizeof(b);',lambda n:5*n+6),
        row('void_discard_assignment','int b[n+sizeof(((void)(n=0),n))];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('void_conditional_discard','int *p=0;unsigned char c=1;int b[n+sizeof((n?(void)*p:(void)(n=0),c))];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('saved_vla_and_comma','int a[n];unsigned char c=1;n=7;int b[sizeof(a)/sizeof(int)+sizeof((n=0,c))];return n+(int)sizeof(b);',lambda n:4*n+11),
        row('converted_helper_formal','return api(n+256);',lambda n:5*n+4,header='int api(unsigned char m);',helper='int api(unsigned char m){int b[m+sizeof(((void)(m=0),m))];return m+(int)sizeof(b);}'),
        row('promotion_after_comma','unsigned char c=1;int b[n+sizeof(+(n++,c))];return n+(int)sizeof(b);',lambda n:5*n+16),
    ]



def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    cases=[];negative=[];frontiers=[];symbolic=[];matches=models=traps=memory=frontier_matches=0;queries=Counter()
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-sizeof-comma-') as temp:
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
            ('evaluated_signed_overflow','sizeof((n++,n))+(n+2147483647)',False),
            ('evaluated_zero_divisor','sizeof((n/0,n))+n/(n-1)',False),
            ('evaluated_shift','sizeof((n<<100,n))+(1<<(n+31))',False),
            ('nonpositive_extent','sizeof((n++,n))-n-3',False),
            ('actual_bounds','n+sizeof((n++,n))',True),
        ]:
            values=[3] if address else [1]
            body='int b['+expression+'];'+('b[n+4]=n;return 7;' if address else 'return (int)sizeof(b);')
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
                            assert run['exit_code']!=0 and (any(s in run['stderr'] for s in ('dynamic-stack-buffer-overflow','stack-buffer-overflow','insufficient space for an object')) or 'index 7 out of bounds for type' in run['stderr']),run
                            memory+=1
                        else:assert run['exit_code']==-4,(name,tag,opt,run);traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':name,'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'observations':observations})
        case=dict(name='defined_nine_cell_frontier',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int b[n+sizeof((n++,n))+2];return (int)sizeof(b);}')
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
            ('uninitialized_cell_still_unsafe','int a[n];int b[n+sizeof((n++,a[n++]))];return a[0];',''),
            ('null_pointer_still_unsafe','int *p=0;int b[n+sizeof(((void)n,*p))];return p[0];',''),
            ('expired_pointer_still_unsafe','int *p=0;{int a[n];a[0]=n;p=a;}int b[n+sizeof(((void)n,*p))];return p[0];',''),
            ('executed_body_overflow','int a[n+sizeof((n++,n))];return n+2147483647;',''),
            ('unused_static_minimum','int a[n+sizeof((n++,(unsigned char)n))];return api(a);','int api(int p[static 5]){return 7;}'),
        ]:
            request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':'clang_proof','proof':{'backend':'calls','parameter_bounds':{'n':[1,3]},'max_steps':256}}
            report=analyze_request(request)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            assert all(q['proved'] for q in report['memory_model']['bounded_local_vla']['queries'])
            if name=='unused_static_minimum':assert report['failed_obligation'].startswith('static array minimum extent')
            symbolic.append({'name':name,'request':request,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'native_sanitizer_detection_claimed':False})
    assert (matches,models,traps,memory,frontier_matches,len(symbolic))==(432,36,48,6,12,5)
    result={'passed':True,'case_count':len(cases),'native_output_matches':matches,'independent_model_matches':models,'expected_ubsan_traps':traps,'expected_memory_failures':memory,'defined_capacity_frontier_matches':frontier_matches,'symbolic_controls':len(symbolic),'query_replays':dict(queries),'cases':cases,'negative_controls':negative,'capacity_frontiers':frontiers,'symbolic_control_records':symbolic,'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],'scope':'Non-VM comma and plain-void cast operands inside sizeof. Every operand is type checked without execution; final arrays decay and final narrow integers retain their type. Calls, strings, VM/type-name arrays, function pointers and sizeof(void result) remain refused. Evaluated comma bounds and existing budgets are unchanged.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','capacity_frontiers','symbolic_control_records','sanitizer_coverage_records')}),flush=True)


if __name__=='__main__':main()
