"""Structured block/loop VLA differential oracles with source safety controls."""
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
    plain='int api(int n);';noop='int api(int n){return n;}'
    def row(name,body,oracle,header=plain,helper=noop):
        return dict(name=name,header=header,helper=helper,main='int entry(int n){'+body+'}',oracle=oracle)
    triangle=lambda n:n*(n+1)//2
    return [
        row('nested_local_bound','int m=n+1;int sum=0;{int a[m];a[m-1]=m;sum=a[m-1]+(int)sizeof(a);}return sum;',lambda n:5*(n+1)),
        row('for_fresh_cells','int sum=0;for(int m=1;m<=n;m++){int a[m];a[m-1]=m;sum+=a[m-1]+(int)sizeof(a);}return sum;',lambda n:5*triangle(n)),
        row('while_changing_extent','int sum=0;while(n>0){int m=n;int a[m];a[m-1]=m;sum+=a[m-1]+(int)sizeof(a);n--;}return sum;',lambda n:5*triangle(n)),
        row('do_continue_scope','int sum=0;int m=n;do{int a[m];sum+=(int)sizeof(a);m--;if(m>0)continue;}while(m>0);return sum;',lambda n:4*triangle(n)),
        row('break_scope','int sum=0;while(1){int m=n;int a[m];a[m-1]=m;sum=a[m-1]+(int)sizeof(a);break;}return sum;',lambda n:5*n),
        row('for_initializer_extent','int sum=0;for(int a[n];n>0;n--){a[0]=n;sum+=(int)sizeof(a)+a[0];}return sum;',lambda n:4*n*n+triangle(n)),
        row('shadowed_array_objects','int a[n];int sum=(int)sizeof(a);{int m=2;int a[m];sum+=(int)sizeof(a);}return sum+(int)sizeof(a);',lambda n:8*n+8),
        row('borrow_scoped_array','int sum=0;for(int m=1;m<=n;m++){int a[m];sum+=api(a,m);}return sum;',triangle,
            'int api(int *p,int n);','int api(int *p,int n){p[n-1]=n;return p[n-1];}'),
        row('condition_call_continue','int sum=0;for(int a[n];api(n);n--){sum+=(int)sizeof(a);if(n>1)continue;}return sum;',lambda n:4*n*n,
            helper='int api(int n){return n>0;}'),
        row('increment_call_continue','int sum=0;for(int m=n;m>0;m=api(m)){int a[m];sum+=(int)sizeof(a);continue;}return sum;',lambda n:4*triangle(n),
            helper='int api(int m){return m-1;}'),
    ]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    rows=[];negative=[];symbolic=[];queries=Counter();matches=models=traps=memory=0
    compilers={'gcc':'gcc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='scoped-vla-native-') as directory:
        root=Path(directory)
        for case in fixtures():
            path=root/case['name'];values=[1,2,3];report,forms=source_report(path,case,values)
            assert report['status']=='PROVED_DEFINED_CLANG_CFG_CALLS',(case['name'],report)
            model=report['memory_model']['bounded_local_vla'];assert model['reexecuted_declarations_get_fresh_storage'] and not model['extent_assumed']
            assert len({i['object_name'] for i in model['instances']})==len(model['instances'])
            replays=replay(report);queries.update(replays);expected=[str(case['oracle'](n)) for n in values];observations=[]
            for tag,compiler in compilers.items():
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,values)
                    for form,run in outputs.items():
                        assert run['exit_code']==0 and not run['stderr'] and run['stdout'].splitlines()==expected,(case['name'],tag,opt,form,run,expected)
                        matches+=len(expected)
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            for n in values:
                r=analyze_request({'source':forms['normalized'][0],'function':'entry','frontend':'typed_cfg_calls','parameter_bounds':{'n':[1,3]},'inputs':{'n':n},'max_steps':256})
                assert r['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS' and r['evaluation']['value']==case['oracle'](n),(case['name'],n,r)
                models+=1
            rows.append({'name':case['name'],'forms':forms,'header':case['header'],'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'query_replays':replays,'independent_expected':expected,'observations':observations})
            print(case['name'],'native/model passed',flush=True)
        for name,body,values,address in [
            ('local_zero_bound','int m=n-1;{int a[m];return 7;}',[1],False),
            ('local_negative_bound','int m=-1;{int a[m];return 7;}',[1],False),
            ('scoped_body_overflow','int m=n;{int a[m];a[0]=2147483647;return a[0]+1;}',[3],False),
            ('scoped_body_bounds','for(int i=0;i<2;i++){int m=n;int a[m];a[m]=n;}return 7;',[3],True),
        ]:
            case=dict(name=name,header='int api(int n);',helper='int api(int n){return n;}',main='int entry(int n){'+body+'}')
            path=root/name;report,forms=source_report(path,case,values)
            assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            replays=replay(report);queries.update(replays);observations=[]
            for tag,compiler in compilers.items():
                if address and tag!='gcc':continue
                for opt in ('-O0','-O2'):
                    outputs,commands=native(path,compiler,tag,opt,forms,values,address=address)
                    for form,run in outputs.items():
                        if address:
                            assert run['exit_code']!=0 and (any(s in run['stderr'] for s in ('dynamic-stack-buffer-overflow','stack-buffer-overflow','insufficient space for an object')) or 'index 3 out of bounds for type' in run['stderr']),run
                            memory+=1
                        else:assert run['exit_code']==-4,(name,tag,opt,form,run);traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':name,'forms':forms,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'observations':observations,'query_replays':replays})
        for name,body in [
            ('previous_iteration_uninitialized','int sum=0;for(int i=0;i<2;i++){int m=n;int a[m];if(i==0)a[0]=n;else sum=a[0];}return sum;'),
            ('expired_iteration_alias','int *p=0;int sum=0;for(int i=0;i<2;i++){int m=n;int a[m];if(i==0){a[0]=n;p=a;}else sum=p[0];}return sum;'),
            ('expired_block_alias','int *p=0;{int m=n;int a[m];a[0]=n;p=a;}return p[0];'),
            ('expired_for_initializer_alias','int *p=0;for(int a[n];n>0;n--){a[0]=n;p=a;}return p[0];'),
        ]:
            request={'source':'int entry(int n){'+body+'}','function':'entry','frontend':'clang_proof','proof':{'backend':'calls','parameter_bounds':{'n':[1,3]},'max_steps':256}}
            report=analyze_request(request);assert report['status']=='UNKNOWN' and not any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved'))
            symbolic.append({'name':name,'request':request,'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'native_sanitizer_detection_claimed':False})
    assert (matches,models,traps,memory)==(360,30,36,6),(matches,models,traps,memory)
    result={'passed':True,'case_count':len(rows),'native_output_matches':matches,'independent_model_matches':models,'expected_ubsan_traps':traps,'expected_memory_failures':memory,'symbolic_lifetime_initialization_controls':len(symbolic),'query_replays':dict(queries),'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original separate objects','preprocessed','normalized'],'cases':rows,'negative_controls':negative,'symbolic_controls':symbolic,'scope':'Structured scoped local integer VLAs with unique visible initialized scalar bounds. Eight cells/object, eight cumulative represented objects and existing execution budgets; no general VLA expressions, source goto or arbitrary heap/LLVM theorem.'}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','symbolic_controls')}),flush=True)


if __name__=='__main__':main()
