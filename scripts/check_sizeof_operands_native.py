"""Unevaluated sizeof expression operands against independent native and scalar oracles."""
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
        row('postincrement_type_only','int b[n+sizeof(n++)];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('nested_size_and_zero_divisor','int a[n];int b[n+sizeof(sizeof(a))/sizeof(void*)+sizeof(1/0)];return n+(int)sizeof(b);',lambda n:5*n+20),
        row('null_dereference_type','int *p=0;int b[n+sizeof(*p)];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('uninitialized_index_type','int a[1];int b[n+sizeof(a[n++])];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('assignment_not_executed','int b[n+sizeof(n=1/0)];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('compound_assignment_type','unsigned char c=1;int b[n+sizeof(c+=300)];return n+c+(int)sizeof(b);',lambda n:5*n+5),
        row('conditional_promotes_char','unsigned char c=1;int b[n+sizeof(n?c:c)];return n+(int)sizeof(b);',lambda n:5*n+16),
        row('pointer_increment_not_executed','int *p=0;int b[n+sizeof(p++)/sizeof(p)];if(p)return 99;return n+(int)sizeof(b);',lambda n:5*n+4),
        row('conditional_array_decay','int a[n];int c[1];int b[n+sizeof(n++?a:c)/sizeof(int*)];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('pointer_arithmetic_type','int *p=0;int b[n+sizeof(n+p+1000000)/sizeof(p)];return n+(int)sizeof(b);',lambda n:5*n+4),
        row('saved_array_vs_element_size','int a[n];n=7;int b[sizeof(a)/sizeof(int)+sizeof(a[n++])];return n+(int)sizeof(b);',lambda n:4*n+23),
        row('converted_formal_and_quoted_bracket','return api(n+256);',lambda n:5*n+8,header='int api(unsigned char m);',helper="int api(unsigned char m){int b[m+sizeof(m++)+sizeof('[')/sizeof(int)];return m+(int)sizeof(b);}"),
    ]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    cases=[];negative=[];frontiers=[];symbolic=[];matches=models=traps=memory=frontier_matches=0;queries=Counter()
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-sizeof-operands-') as temp:
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
            ('evaluated_signed_overflow','sizeof(n++)+(n+2147483647)',False),
            ('evaluated_zero_divisor','sizeof(n/0)+n/(n-1)',False),
            ('evaluated_shift','sizeof(n<<100)+(1<<(n+31))',False),
            ('nonpositive_extent','sizeof(n++)-n-3',False),
            ('actual_bounds','n+sizeof(n++)',True),
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
        case=dict(name='defined_nine_cell_frontier',header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){int b[n+sizeof(n++)+2];return (int)sizeof(b);}')
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
            ('uninitialized_cell_still_unsafe','int a[n];int b[n+sizeof(a[n++])];return a[0];',''),
            ('null_pointer_still_unsafe','int *p=0;int b[n+sizeof(*p)];return p[0];',''),
            ('expired_pointer_still_unsafe','int *p=0;{int a[n];a[0]=n;p=a;}int b[n+sizeof(*p)];return p[0];',''),
            ('executed_body_overflow','int a[n+sizeof(n++)];return n+2147483647;',''),
            ('unused_static_minimum','int a[n+sizeof((unsigned char)n++)];return api(a);','int api(int p[static 5]){return 7;}'),
        ]:
            request={'source':prefix+'int entry(int n){'+body+'}','function':'entry','frontend':'clang_proof','proof':{'backend':'calls','parameter_bounds':{'n':[1,3]},'max_steps':256}}
            report=analyze_request(request)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            assert all(q['proved'] for q in report['memory_model']['bounded_local_vla']['queries'])
            if name=='unused_static_minimum':assert report['failed_obligation'].startswith('static array minimum extent')
            symbolic.append({'name':name,'request':request,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'native_sanitizer_detection_claimed':False})
    assert (matches,models,traps,memory,frontier_matches,len(symbolic))==(432,36,48,6,12,5)
    result={'passed':True,'case_count':len(cases),'native_output_matches':matches,'independent_model_matches':models,'expected_ubsan_traps':traps,'expected_memory_failures':memory,'defined_capacity_frontier_matches':frontier_matches,'symbolic_controls':len(symbolic),'query_replays':dict(queries),'cases':cases,'negative_controls':negative,'capacity_frontiers':frontiers,'symbolic_control_records':symbolic,'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],'scope':'Type-only integer/data-pointer sizeof expression operands, with no execution of increments, assignments, arithmetic or memory accesses. Static constraints checked even on unexecuted declarations. Calls/comma/strings/VM type names and pointer-to-array forms remain refused; existing bounds and budgets remain.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','capacity_frontiers','symbolic_control_records','sanitizer_coverage_records')}),flush=True)


if __name__=='__main__':main()
