"""Clang/GCC separate-unit and snapshot oracles for ordinary array parameters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile

from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path


def fixtures():
    return [
        dict(name='short_actual',header='int api(int p[32]);',helper='int api(int p[7]){return p[0]+1;}',
             main='int entry(int n){int a[1]={n};return api(a);}',oracle=lambda n:n+1),
        dict(name='long_actual',header='int api(int p[1]);',helper='int api(int p[1]){return p[2];}',
             main='int entry(int n){int a[3]={n,n+1,n+2};return api(a);}',oracle=lambda n:n+2),
        dict(name='null_unaccessed',header='int api(int p[5]);',helper='int api(int p[]){return 7;}',
             main='int entry(int n){return api(0);}',oracle=lambda n:7),
        dict(name='parameter_sizeof',header='int api(int p[100]);',helper='int api(int p[5]){return (int)sizeof(p)+p[0];}',
             main='int entry(int n){int a[1]={n};return api(a);}',oracle=lambda n:n+struct.calcsize('P')),
        dict(name='pointer_elements',header='#define PARAM(name) int *name[5]\nint api(PARAM());',helper='int api(PARAM(p)){p[0][0]+=1;return p[0][0];}',
             main='int entry(int n){int a[1]={n};int *p[1]={a};return api(p);}',oracle=lambda n:n+1),
        dict(name='static_helper',header='static int bump(int p[]){p[0]+=1;return p[0];}\nint api(int p[9]);',helper='int api(int p[9]){int x=bump(p);return bump(p)+x;}',
             main='int entry(int n){int a[1]={n};return api(a);}',oracle=lambda n:2*n+3),
        dict(name='record_allocation',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{long value;};int api(struct Box p[9]);',
             helper='int api(struct Box p[]){return p[0].value+1;}',
             main='int entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->value=n;int x=api(p);free(p);return x;}',oracle=lambda n:n+1,heap=True),
    ]


ALLOC='''static int failure,attempts,frees,live;
void *__real_calloc(size_t,size_t);void __real_free(void *);
void *__wrap_calloc(size_t n,size_t s){attempts++;if(failure)return 0;void *p=__real_calloc(n,s);if(p)live++;return p;}
void __wrap_free(void *p){if(p){frees++;live--;}__real_free(p);}
'''


def execute(argv):
    return subprocess.run(argv,text=True,capture_output=True,timeout=90,
        env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'})


def native(path,compiler,tag,opt,forms,values,*,heap=False,address=False):
    flags=['-std=c11',opt,'-fno-builtin','-Werror=implicit-function-declaration']
    if address:flags+=['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-pie']
    else:flags+=['-fsanitize=undefined','-fsanitize-trap=all' if tag=='clang' else '-fsanitize-undefined-trap-on-error']
    calls=''
    for fail in ((0,1) if heap else (0,)):
        for n in values:
            if heap:calls+=f'failure={fail};attempts=frees=live=0;value=entry({n});printf("%d %d %d %d\\n",value,attempts,frees,live);'
            else:calls+=f'printf("%d\\n",entry({n}));'
    harness='#include <stdio.h>\n#include <stdlib.h>\nint entry(int);\n'+(ALLOC if heap else '')+'int main(void){'+('int value=0;' if heap else '')+calls+'return 0;}\n'
    hp=path/'harness.c';hp.write_text(harness)
    observations={};commands=[]
    def compile(argv):
        r=execute(argv);commands.append({'argv':argv,'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr})
        if r.returncode:raise AssertionError(('native compile',commands[-1]))
    for form,units in forms.items():
        objects=[]
        for i,source in enumerate(units):
            p=path/(form+str(i)+('.i' if form=='preprocessed' else '.c'));p.write_text(source)
            obj=path/(form+str(i)+'.o');objects.append(str(obj))
            # The proof fragment uses checked built-in allocator contracts;
            # standalone native C supplies their exact standard declarations.
            support=['-include','stdlib.h'] if form=='normalized' else []
            compile([compiler,*flags,*support,*(['-x','cpp-output'] if form=='preprocessed' else []),'-c',str(p),'-o',str(obj)])
        binary=path/(form+'-'+tag)
        compile([compiler,*flags,*(['-no-pie'] if address else []),str(hp),*objects,
                 *(['-Wl,--wrap=calloc','-Wl,--wrap=free'] if heap else []),'-o',str(binary)])
        r=execute([str(binary)])
        observations[form]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    return observations,commands


def source_report(path,fixture,values):
    path.mkdir();(path/'api.h').write_text(fixture['header']+'\n')
    units=['#include "api.h"\n'+fixture[k] for k in ('main','helper')]
    provider=path/'provider.c';provider.write_text(units[1])
    r=analyze_request({'source':units[0],'function':'entry','frontend':'clang_proof',
        'clang':{'preprocess':True,'args':['-fno-builtin','-I'+str(path)],'linked_sources':[str(provider)]},
        'proof':{'backend':'calls','parameter_bounds':{'n':[min(values),max(values)]},'inputs':{'n':values[-1]},'max_steps':256}})
    forms={'original':units,'preprocessed':[u['preprocessing']['source'] for u in r['clang_frontend']['linked_translation_units']],
           'normalized':[r['normalization']['source']]}
    return r,forms


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    cases=[];negative=[];matches=models=traps=memory=0;memory_diagnostics={}
    compilers={'gcc':'cc','clang':compiler_path()}
    with tempfile.TemporaryDirectory(prefix='llmloop-arrays-native-') as temp:
        root=Path(temp)
        for fixture in fixtures():
            path=root/fixture['name'];values=list(range(17));r,forms=source_report(path,fixture,values)
            if r['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':raise AssertionError((fixture['name'],r.get('reason'),r.get('failed_obligation')))
            adjustments=r['normalization']['translation_unit_linking']['array_parameter_adjustments']
            if not adjustments or any(a['minimum_extent_assumed'] or a['bound_evaluation_required'] for a in adjustments):raise AssertionError('Invented array precondition')
            expected=[str(fixture['oracle'](n)) for n in values]
            if fixture.get('heap'):expected=[str(fixture['oracle'](n))+' 1 1 0' for n in values]+['-1 1 0 0' for n in values]
            observations=[]
            for opt in ('-O0','-O2'):
                models+=len(expected)
                for tag,compiler in compilers.items():
                    outputs,commands=native(path,compiler,tag,opt,forms,values,heap=fixture.get('heap',False))
                    for form,result in outputs.items():
                        if result['exit_code'] or result['stderr'] or result['stdout'].splitlines()!=expected:
                            raise AssertionError((fixture['name'],tag,opt,form,result,expected))
                        matches+=len(expected)
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands,'independent_expected':expected})
            cases.append({'name':fixture['name'],'header':fixture['header'],'forms':forms,
                'source_sha256':{k:[hashlib.sha256(s.encode()).hexdigest() for s in v] for k,v in forms.items()},
                'proof':{k:v for k,v in r.items() if k!='clang_frontend'},'observations':observations})
        failures=[
            dict(name='overflow',header='int api(int p[100]);',helper='int api(int p[]){return p[0]+2147483647;}',main='int entry(int n){int a[1]={n};return api(a);}',values=[1]),
            dict(name='zero_division',header='int api(int p[100]);',helper='int api(int p[]){return 12/p[0];}',main='int entry(int n){int a[1]={n};return api(a);}',values=[0]),
            dict(name='actual_bounds',header='int api(int p[100]);',helper='int api(int p[]){return p[1];}',main='int entry(int n){int a[1]={n};return api(a);}',values=[1],address=True,diagnostic='stack-buffer-overflow'),
            dict(name='freed_record',header='typedef __SIZE_TYPE__ Size;void *calloc(Size,Size);void free(void *);struct Box{int value;};int api(struct Box p[9]);',helper='int api(struct Box p[]){return p[0].value;}',main='int entry(int n){struct Box *p=calloc(1,sizeof(struct Box));if(!p)return 0;p->value=n;free(p);return api(p);}',values=[1],address=True,diagnostic='heap-use-after-free'),
        ]
        for fixture in failures:
            path=root/fixture['name'];r,forms=source_report(path,fixture,fixture['values'])
            if r['status']!='UNKNOWN' or any(r.get(k) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):raise AssertionError(('unsafe source accepted',fixture['name']))
            observations=[]
            for opt in ('-O0','-O2'):
                for tag,compiler in compilers.items():
                    if fixture.get('address') and tag!='gcc':continue
                    outputs,commands=native(path,compiler,tag,opt,forms,fixture['values'],address=fixture.get('address',False))
                    for form,result in outputs.items():
                        if fixture.get('address'):
                            diagnostic=fixture['diagnostic'] if fixture['diagnostic'] in result['stderr'] else None
                            if (fixture['name']=='actual_bounds' and 'runtime error: load of address' in result['stderr']
                                    and 'insufficient space for an object of type' in result['stderr']):
                                diagnostic='ubsan-object-size'
                            if result['exit_code']==0 or diagnostic is None:
                                raise AssertionError((fixture['name'],tag,opt,form,result))
                            result['diagnostic_kind']=diagnostic
                            memory_diagnostics[diagnostic]=memory_diagnostics.get(diagnostic,0)+1
                            memory+=1
                        else:
                            if result['exit_code']>=0:raise AssertionError(('arithmetic trap missing',fixture['name'],tag,opt,form,result))
                            traps+=1
                    observations.append({'compiler':tag,'optimization':opt,'outputs':outputs,'commands':commands})
            negative.append({'name':fixture['name'],'header':fixture['header'],'forms':forms,
                'proof':{k:v for k,v in r.items() if k!='clang_frontend'},'observations':observations})
    assert (matches,models,traps,memory)==(1632,272,24,12),(matches,models,traps,memory)
    result={'passed':True,'case_count':len(cases),'native_output_matches':matches,'model_matches':models,
        'expected_arithmetic_traps':traps,'expected_memory_sanitizer_failures':memory,
        'memory_diagnostic_counts':memory_diagnostics,
        'compilers':{tag:execute([c,'--version']).stdout.splitlines()[0] for tag,c in compilers.items()},
        'optimizations':['-O0','-O2'],'forms':['original','preprocessed','normalized'],
        'separate_original_object_compilation':True,'allocator_interposition':'linker wrap with -fno-builtin; calls sequenced before counter observation',
        'cases':cases,'negative_controls':negative,
        'scope':'native LP64 finite differential/oracle evidence supplements declared-domain source proofs; memory controls use GCC ASan/UBSan; no general C/compiler equivalence theorem'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls')}),flush=True)


if __name__=='__main__':main()
