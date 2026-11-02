"""Native valid calls, explicit rejected contracts and replayed span obligations."""
import argparse
import json
from pathlib import Path
import tempfile

import z3

from llmloop.clang_adapter import compiler_path
from llmloop.api import analyze_request
from scripts.check_clang_arrays_native import native,source_report,execute


def fixtures():
    return [
        dict(name='unused_uninitialized',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return 7;}',main='int entry(int n){int a[3];return api(a);}',oracle=lambda n,f:('7',None)),
        dict(name='static_is_lower_bound',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return p[3];}',main='int entry(int n){int a[4]={n,n+1,n+2,n+3};return api(a);}',oracle=lambda n,f:(str(n+3),None)),
        dict(name='header_only_write',header='int api(int p[static 3]);',helper='int api(int *p){p[0]=4;p[1]=5;p[2]=6;return p[0]+p[1]+p[2];}',main='int entry(int n){int a[3];return api(a);}',oracle=lambda n,f:('15',None)),
        dict(name='aliased_parameters',header='int api(int p[static 2],int q[static 3]);',helper='int api(int p[static 2],int q[static 3]){p[0]+=1;q[0]+=1;return p[0];}',main='int entry(int n){int a[3]={n};return api(a,a);}',oracle=lambda n,f:(str(n+2),None)),
        dict(name='pointer_cells',header='int api(int *p[static 2]);',helper='int api(int *p[static 2]){p[1][0]+=1;return p[0][0];}',main='int entry(int n){int a[1]={n};int *p[2]={a,a};return api(p);}',oracle=lambda n,f:(str(n+1),None)),
        dict(name='private_contract_names',header='int api(int p[static 3]);',helper='static int same(int p[static 3]){return 2;}int api(int p[static 3]){return same(p);}',main='static int same(int p[static 1]){return 1;}int entry(int n){int a[1]={n};int b[3]={n};int x=same(a);return x+api(b);}',oracle=lambda n,f:('3',None)),
        dict(name='record_one',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{long value;};int api(struct Box p[static 1]);',helper='int api(struct Box p[static 1]){return p[0].value+1;}',main='int entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p);free(p);return x;}',heap=True,oracle=lambda n,f:(str(-1 if f else n+1),'1 0 0' if f else '1 1 0')),
        dict(name='dynamic_heap_capacity',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);int api(int p[static 3]);',helper='int api(int p[static 3]){return 7;}',main='int entry(int n){if(n<3)return 0;int *p=calloc(n,sizeof(int));if(!p)return -1;int x=api(p);free(p);return x;}',heap=True,values=list(range(9)),oracle=lambda n,f:('0','0 0 0') if n<3 else ('-1','1 0 0') if f else ('7','1 1 0')),
    ]


def replay(report):
    rows=[]
    for query in report['call_model']['static_array_queries']:
        solver=z3.Solver();solver.set(timeout=5000);solver.from_string(query['smt2']);answer=solver.check()
        expected=z3.unsat if query['proved'] else z3.sat
        if answer!=expected:raise AssertionError(('span replay mismatch',query['obligation'],str(answer),str(expected)))
        rows.append({'obligation':query['obligation'],'result':str(answer),'proved':query['proved']})
    return rows


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];refusals=[];unsafe=[];matches=models=replayed=sat=silent=traps=memory=0
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-static-array-') as temp:
        root=Path(temp)
        for case in fixtures():
            values=case.get('values',list(range(17)));path=root/case['name'];report,forms=source_report(path,case,values)
            if report['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':raise AssertionError((case['name'],report.get('reason'),report.get('failed_obligation')))
            if report['call_model']['static_array_contracts_assumed']:raise AssertionError('Assumed precondition')
            queries=replay(report);replayed+=len(queries)
            expected=[]
            for fail in ((0,1) if case.get('heap') else (0,)):
                for n in values:
                    value,counters=case['oracle'](n,fail);expected.append(value+(' '+counters if counters is not None else ''))
            observations=[]
            for opt in ('-O0','-O2'):
                models+=len(expected)
                for tag,compiler in compilers.items():
                    outputs,commands=native(path,compiler,tag,opt,forms,values,heap=case.get('heap',False))
                    for form,result in outputs.items():
                        if result['exit_code'] or result['stderr'] or result['stdout'].splitlines()!=expected:raise AssertionError((case['name'],tag,opt,form,result,expected))
                        matches+=len(expected)
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands,'independent_expected':expected})
            rows.append({'name':case['name'],'header':case['header'],'forms':forms,
                'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'span_replays':queries,'observations':observations})
        invalid=[
            dict(name='short_unused',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return 7;}',main='int entry(int n){int a[1]={n};return api(a);}'),
            dict(name='null_unused',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return 7;}',main='int entry(int n){return api(0);}'),
            dict(name='zero_heap_unused',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);int api(int p[static 1]);',helper='int api(int p[static 1]){return 7;}',main='int entry(int n){int *p=calloc(0,sizeof(int));if(!p)return 0;int x=api(p);free(p);return x;}'),
        ]
        for case in invalid:
            path=root/case['name'];report,forms=source_report(path,case,[1])
            if report['status']!='UNKNOWN' or not report.get('failed_obligation','').startswith('static array'):raise AssertionError(('bad contract accepted',case['name']))
            queries=replay(report);sat+=sum(q['result']=='sat' for q in queries);replayed+=len(queries)
            observations=[]
            for opt in ('-O0','-O2'):
                for tag,compiler in compilers.items():
                    outputs,commands=native(path,compiler,tag,opt,forms,[1])
                    silent+=sum(o['exit_code']==0 and not o['stderr'] for o in outputs.values())
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands,'positive_correspondence_claimed':False})
            refusals.append({'name':case['name'],'header':case['header'],'forms':forms,
                'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'span_replays':queries,'observations':observations,
                'scope':'Rejected source contract; even a sanitizer-silent native return is not a defined execution or positive correspondence.'})
        bad_bodies=[dict(name='body_overflow',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return p[0]+2147483647;}',main='int entry(int n){int a[3]={n};return api(a);}'),
                    dict(name='body_bounds',header='int api(int p[static 3]);',helper='int api(int p[static 3]){return p[3];}',main='int entry(int n){int a[3]={n};return api(a);}',address=True)]
        for case in bad_bodies:
            path=root/case['name'];report,forms=source_report(path,case,[1])
            if report['status']!='UNKNOWN' or report.get('failed_obligation','').startswith('static array'):raise AssertionError(('body safety lost',case['name']))
            queries=replay(report);replayed+=len(queries)
            observations=[]
            for opt in ('-O0','-O2'):
                for tag,compiler in compilers.items():
                    if case.get('address') and tag!='gcc':continue
                    outputs,commands=native(path,compiler,tag,opt,forms,[1],address=case.get('address',False))
                    for form,result in outputs.items():
                        if case.get('address'):
                            if result['exit_code']==0 or not ('stack-buffer-overflow' in result['stderr'] or 'runtime error: load of address' in result['stderr'] and 'insufficient space' in result['stderr']):raise AssertionError((case['name'],tag,opt,form,result))
                            memory+=1
                        else:
                            if result['exit_code']!=-4:raise AssertionError(('arithmetic trap missing',tag,opt,form,result))
                            traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            unsafe.append({'name':case['name'],'forms':forms,'header':case['header'],
                'proof':{k:v for k,v in report.items() if k!='clang_frontend'},'span_replays':queries,'observations':observations})
        vm_source='int entry(int n){typedef int A[n++];return n;}'
        vm_report=analyze_request({'source':vm_source,'function':'entry','frontend':'clang_proof',
            'proof':{'backend':'cfg','parameter_bounds':{'n':[1,2]},'inputs':{'n':1}}})
        if vm_report['status']!='UNKNOWN' or 'Variably modified typedef' not in vm_report.get('reason',''):
            raise AssertionError('VLA typedef evaluation was erased')
        vm_path=root/'vla_typedef.c';vm_path.write_text(vm_source+'int main(void){return entry(1);}')
        vm_observations=[]
        for opt in ('-O0','-O2'):
            for tag,compiler in compilers.items():
                binary=root/('vla_'+tag+opt)
                command=[compiler,'-std=c11',opt,str(vm_path),'-o',str(binary)]
                built=execute(command)
                if built.returncode:raise AssertionError(built)
                run=execute([str(binary)]);observed={'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr}
                if observed['exit_code']!=2 or observed['stderr']:raise AssertionError(observed)
                vm_observations.append({'compiler':tag,'optimization':opt,'command':command,'result':observed})
        vm_control={'source':vm_source,'current_report':vm_report,'original_native_observations':vm_observations,
            'scope':'Original source returns 2; unsupported runtime typedef effects must not be erased into a proof returning 1.'}
    assert (matches,models,sat,traps,memory)==(1848,308,3,12,6),(matches,models,sat,traps,memory)
    result={'passed':True,'case_count':len(rows),'native_output_matches':matches,'model_matches':models,
        'contract_refusals':len(refusals),'static_query_replays':replayed,'sat_contract_counterexamples':sat,
        'sanitizer_silent_invalid_observations':silent,'silent_invalid_runs_counted_as_positive':False,
        'expected_body_arithmetic_traps':traps,'expected_body_memory_failures':memory,
        'vla_typedef_source_refusals':1,'vla_typedef_original_native_checks':len(vm_observations),'vla_typedef_control':vm_control,
        'compilers':['gcc','clang'],'optimizations':['-O0','-O2'],'forms':['original','preprocessed','normalized'],
        'separate_original_object_compilation':True,'static_contracts_assumed':False,'cases':rows,'contract_negative_controls':refusals,'body_negative_controls':unsafe,
        'scope':'native LP64 finite samples supplement checked source entry predicates; invalid-contract observations never establish definedness; whole-object bases and constant minima 1..8 only'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','contract_negative_controls','body_negative_controls','vla_typedef_control')}),flush=True)


if __name__=='__main__':main()
