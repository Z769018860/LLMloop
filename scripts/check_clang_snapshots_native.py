"""Original objects, Clang snapshots and normalized C versus independent oracles."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from scripts.check_clang_linked_native import compact, compile_forms, run


def fixtures():
    return [
        dict(name='macro_pointer_alias',header='#define PTR(name) int *name\nint *api(PTR());',
             main='int entry(int n){int a[3]={3,5,7};int *q=api(a);q[0]=n;return a[0]+a[1]+a[2];}',
             helper='int *api(PTR(p)){p[0]+=1;return p+1;}',oracle=lambda n:n+11),
        dict(name='header_static_helper',header='static int bump(int *p){p[0]+=1;return p[0];}\nint api(int *);',
             main='int entry(int n){int a[1]={n};return api(a);}',
             helper='int api(int *p){int x=bump(p);return bump(p)+x;}',oracle=lambda n:2*n+3),
        dict(name='header_record_allocation',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Node{long value;struct Node *next;};int api(struct Node *);',
             main='int entry(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;p->next=0;int x=api(p);free(p);return x;}',
             helper='int api(struct Node *p){return p->value+1;}',oracle=lambda n:n+1,heap=True),
    ]


def observe(path,source,snapshots,normalized,entry,values,opt,heap=False,negative=False):
    first,commands=compile_forms(path,*source,normalized,entry,values,opt,heap,negative)
    second,more=compile_forms(path,*snapshots,normalized,entry,values,opt,heap,negative)
    if first['normalized']!=second['normalized']:
        raise AssertionError('Repeated normalized native observation differs')
    return {**first,'preprocessed':second['original']},commands+more


def alignment_control(path):
    path.mkdir()
    header='int api(int *p __attribute__((align_value(32))));\n'
    provider='#include "api.h"\nint api(int *p __attribute__((align_value(32)))){return p[0];}\n'
    entry='#include "api.h"\nint entry(int n){int a[1]={n};return api(a);}\n'
    (path/'api.h').write_text(header);(path/'provider.c').write_text(provider)
    report=analyze_request({'source':entry,'frontend':'clang_proof','function':'entry',
        'clang':{'preprocess':True,'args':['-I'+str(path)],'linked_sources':[str(path/'provider.c')]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
    if report['status']!='UNKNOWN' or 'parameter attributes' not in report.get('reason','') or any(report.get(k) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):
        raise AssertionError('Unmodeled parameter alignment promise accepted')
    # Explicit alignment makes data+1 violate the promise independently of
    # incidental stack placement. This is a refused interface, not a proof.
    harness='#include "api.h"\n_Alignas(32) int data[9]={0};int main(void){return api(data+1);}\n'
    (path/'harness.c').write_text(harness)
    observations=[]
    for opt in ('-O0','-O2'):
        argv=[compiler_path(),'-std=c11',opt,'-fsanitize=undefined','-fsanitize-trap=all',str(path/'provider.c'),str(path/'harness.c'),'-o',str(path/'alignment')]
        run(argv)
        r=subprocess.run([str(path/'alignment')],text=True,capture_output=True,timeout=10)
        if r.returncode>=0:raise AssertionError(('alignment sanitizer trap missing',opt,r.returncode))
        observations.append({'command':argv,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
    return {'header':header,'provider':provider,'proof_entry':entry,'native_harness':harness,
            'source_interface_refused':True,'source_report':compact(report),'native_traps':len(observations),'observations':observations,
            'scope':'native harness passes an explicitly misaligned argument at the refused interface; no normalized execution or positive proof correspondence claimed'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    cases=[];controls=[];native=models=0
    with tempfile.TemporaryDirectory(prefix='llmloop-snapshot-native-') as temp:
        root=Path(temp)
        negative=[dict(name='pointer_overflow',header='int api(int *);',main='int entry(int n){int a[1]={n};return api(a);}',helper='int api(int *p){return p[0]+2147483647;}',values=[1],diagnostic='signed integer overflow'),
                  dict(name='pointer_zero_division',header='int api(int *);',main='int entry(int n){int a[1]={n};return api(a);}',helper='int api(int *p){return 12/p[0];}',values=[0],diagnostic='division by zero')]
        for fixture in fixtures()+negative:
            path=root/fixture['name'];path.mkdir();(path/'api.h').write_text(fixture['header']+'\n')
            source=['#include "'+str(path/'api.h')+'"\n'+fixture[k] for k in ('main','helper')]
            provider=path/'provider.c';provider.write_text(source[1]);values=fixture.get('values',list(range(17)))
            is_negative='diagnostic' in fixture
            r=analyze_request({'source':source[0],'frontend':'clang_proof','function':'entry',
                'clang':{'preprocess':True,'linked_sources':[str(provider)]},
                'proof':{'backend':'calls','parameter_bounds':{'n':[min(values),max(values)]},'inputs':{'n':values[-1]},'max_steps':256}})
            if is_negative:
                if r['status']!='UNKNOWN' or any(r.get(k) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):
                    raise AssertionError((fixture['name'],r['status']))
            elif r['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':
                raise AssertionError((fixture['name'],r.get('reason'),r.get('failed_obligation')))
            normalization=r['normalization'];units=r['clang_frontend']['linked_translation_units']
            snapshots=[u['preprocessing']['source'] for u in units]
            observations=[]
            for opt in ('-O0','-O2'):
                outputs,commands=observe(path,source,snapshots,normalization['source'],
                    normalization['translation_unit_linking']['entry']['normalized'],values,opt,fixture.get('heap',False),is_negative)
                if is_negative:
                    for form,result in outputs.items():
                        if result['exit_code']==0 or fixture['diagnostic'] not in result['stderr']:
                            raise AssertionError((fixture['name'],opt,form,result))
                        controls.append({'name':fixture['name'],'optimization':opt,'form':form,'observation':result})
                else:
                    expected=[str(fixture['oracle'](n)) for n in values]
                    if fixture.get('heap'):
                        expected=[str(fixture['oracle'](n))+' 1 1 0' for n in values]+['-1 1 0 0' for n in values]
                    for form,result in outputs.items():
                        if result['exit_code'] or result['stderr'] or result['stdout'].splitlines()!=expected:
                            raise AssertionError((fixture['name'],opt,form,result,expected))
                        native+=len(expected)
                    models+=len(expected)
                observations.append({'optimization':opt,'commands':commands,'outputs':outputs,
                                     **({'independent_expected':expected} if not is_negative else {})})
            cases.append({'name':fixture['name'],'negative':is_negative,'header':fixture['header'],'original_units':source,
                'preprocessed_units':[u['preprocessing'] for u in units],
                'original_sha256':[hashlib.sha256(s.encode()).hexdigest() for s in source],
                'proof':compact(r),'observations':observations})
        alignment=alignment_control(root/'alignment_control')
    result={'passed':True,'case_count':3,'native_output_matches':native,'model_matches':models,
        'expected_ubsan_failures':len(controls),'forms':['original','preprocessed','normalized'],
        'separate_original_object_compilation':True,'optimizations':['-O0','-O2'],
        'compiler':run(['cc','--version']).stdout.splitlines()[0],'cases':cases,'negative_controls':controls,
        'parameter_attribute_refusals':1,'expected_alignment_traps':alignment['native_traps'],'alignment_control':alignment,
        'scope':'native LP64 observations and independent finite arithmetic/allocation oracles supplement bounded source obligations; no general preprocessing/compiler equivalence theorem'}
    assert (native,models,len(controls))==(408,136,12),(native,models,len(controls))
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','alignment_control')}),flush=True)


if __name__=='__main__':main()
