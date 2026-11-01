"""Separately compiled original TUs versus normalized C and independent models."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request


def fixtures():
    return [
        dict(name='static_collisions',main='int api(int);static int same(int);int same(int x){return x+2;}int entry(int n){return api(n)+same(n);}',helper='static int same(int);extern int same(int x){return x+1;}int api(int x){return same(x);}',values=list(range(33)),oracle=lambda n:2*n+3),
        dict(name='typedef_narrowing',main='typedef unsigned char Byte;Byte api(Byte);int entry(int n){return api(n);}',helper='typedef unsigned char Octet;Octet api(Octet x){return x+1;}',values=list(range(250,266)),oracle=lambda n:(n+1)%256),
        dict(name='native_long_layout',main='long api(long);long entry(int n){return api(n);}',helper='long api(long x){return x+sizeof(long);}',values=list(range(33)),oracle=lambda n:n+8),
        dict(name='lazy_nested',main='int api(int);int entry(int n){return n==0 ? 7 : api(api(12/n));}',helper='int api(int x){return x+1;}',values=list(range(17)),oracle=lambda n:7 if n==0 else 12//n+2),
        dict(name='shared_pointer_object',main='int *api(int *);int entry(int n){int a[3]={3,5,7};int *q=api(a);q[0]=n;return a[0]+a[1]+a[2];}',helper='int *api(int *p){p[0]+=1;return p+1;}',values=list(range(33)),oracle=lambda n:n+11),
        dict(name='failure_aware_heap',main='#include <stdlib.h>\nint *api(int);int entry(int n){int *p=api(n);if(!p)return -1;p[0]=n+5;int x=p[0];free(p);return x;}',helper='#include <stdlib.h>\nint *api(int n){return calloc(n,sizeof(int));}',values=list(range(1,9)),oracle=lambda n:n+5,heap=True),
        dict(name='mutual_recursion',main='int api(int);int entry(int n){if(n<=0)return 0;return 1+api(n-1);}',helper='int entry(int);int api(int n){if(n<=0)return 0;return 1+entry(n-1);}',values=list(range(6)),oracle=lambda n:n,proof={'allow_recursion':True,'max_call_depth':7,'max_steps':512}),
        dict(name='shared_ctz_model',main='int api(unsigned int);int entry(unsigned int n){return __builtin_ctz(n)+api(n);}',helper='int api(unsigned int x){return __builtin_ctz(x);}',values=list(range(1,17)),oracle=lambda n:2*((n&-n).bit_length()-1),backend='bv_calls'),
    ]


ALLOC_HEADER='''#include <stdlib.h>
void *fixture_calloc(size_t,size_t);
void fixture_free(void *);
#define calloc fixture_calloc
#define free fixture_free
'''
ALLOC_HARNESS='''static int failure,attempts,frees,live;
void *fixture_calloc(size_t n,size_t z){attempts++;if(failure)return 0;void *p=calloc(n,z);if(p)live++;return p;}
void fixture_free(void *p){if(p){frees++;live--;}free(p);}
'''


def run(command):
    r=subprocess.run(command,text=True,capture_output=True,timeout=90)
    if r.returncode:raise AssertionError((command,r.returncode,r.stdout,r.stderr))
    return r


def compile_forms(path,main,helper,normalized,entry,values,opt,heap=False,negative=False):
    # Do not concatenate original TUs: that changes static linkage and types.
    for name,text in [('main.c',main),('helper.c',helper),('normalized.c',normalized)]:
        (path/name).write_text(text)
    (path/'allocation.h').write_text(ALLOC_HEADER)
    flags=['-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=all']
    compile_flags=flags+(['-include',str(path/'allocation.h')] if heap else [])
    commands=[]
    for name in ('main','helper','normalized'):
        command=['cc',*compile_flags,'-c',str(path/(name+'.c')),'-o',str(path/(name+'.o'))]
        run(command);commands.append(command)
    results={};failures=(0,1) if heap else (0,)
    for tag,symbol,objects in [('original','entry',['main','helper']),('normalized',entry,['normalized'])]:
        decl=('int' if 'shared_ctz' not in str(path) else 'unsigned int')
        # Return declaration matches each actual function; no assumed ABI cast.
        return_type='long' if main.lstrip().startswith('long api') else 'int'
        calls=''
        for fail in failures:
            for n in values:
                if heap:calls+=f'failure={fail};attempts=frees=live=0;printf("%lld %d %d %d\\n",(long long){symbol}({n}),attempts,frees,live);'
                else:calls+=f'printf("%lld\\n",(long long){symbol}({n}));'
        # Sequence the call before observing allocator counters (printf argument
        # order in C is unspecified).
        if heap:
            calls=''.join(f'failure={fail};attempts=frees=live=0;value={symbol}({n});printf("%lld %d %d %d\\n",value,attempts,frees,live);' for fail in failures for n in values)
        harness='#include <stdio.h>\n#include <stdlib.h>\n'+return_type+' '+symbol+'('+decl+');\n'+(ALLOC_HARNESS if heap else '')+'int main(void){long long value=0;(void)value;'+calls+'return 0;}\n'
        (path/'harness.c').write_text(harness)
        command=['cc',*flags,str(path/'harness.c'),*[str(path/(o+'.o')) for o in objects],'-o',str(path/tag)]
        run(command);commands.append(command)
        r=subprocess.run([str(path/tag)],text=True,capture_output=True,timeout=10)
        results[tag]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
        if not negative and (r.returncode or r.stderr):raise AssertionError((tag,opt,r.returncode,r.stderr))
    return results,commands


def compact(report):
    return {k:v for k,v in report.items() if k!='clang_frontend'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];negative=[];refusals=[];comparisons=models=0
    with tempfile.TemporaryDirectory(prefix='llmloop-linked-native-') as temp:
        root=Path(temp)
        for fixture in fixtures():
            name=fixture['name'];path=root/name;path.mkdir();helper=path/'helper.c';helper.write_text(fixture['helper'])
            values=fixture['values'];backend=fixture.get('backend','calls')
            req={'source':fixture['main'],'function':'entry','frontend':'clang_proof','clang':{'linked_sources':[str(helper)]},
                'proof':{'backend':backend,'parameter_bounds':{'n':[min(values),max(values)]},'inputs':{'n':values[-1]},**fixture.get('proof',{})}}
            report=analyze_request(req)
            if not report['status'].startswith('PROVED_DEFINED_CLANG_'):raise AssertionError((name,report.get('reason'),report.get('failed_obligation')))
            normalization=report['normalization'];cert=normalization['translation_unit_linking']
            if cert['external_semantics_assumed'] or not all(b['body_is_supplied_source'] for b in cert['bindings']):raise AssertionError('Assumed linkage')
            expected=[]
            for fail in ((0,1) if fixture.get('heap') else (0,)):
                for n in values:
                    expected.append(f'{-1 if fail else fixture["oracle"](n)} 1 {0 if fail else 1} 0' if fixture.get('heap') else str(fixture['oracle'](n)))
            observations=[]
            for opt in ('-O0','-O2'):
                outputs,commands=compile_forms(path,fixture['main'],fixture['helper'],normalization['source'],cert['entry']['normalized'],values,opt,fixture.get('heap',False))
                for tag,result in outputs.items():
                    if result['stdout'].splitlines()!=expected:raise AssertionError((name,opt,tag,result,expected))
                    comparisons+=len(expected)
                models+=len(expected)
                observations.append({'optimization':opt,'commands':commands,'outputs':outputs,'independent_expected':expected})
            rows.append({'name':name,'source_units':[fixture['main'],fixture['helper']],'source_sha256':[hashlib.sha256(fixture[k].encode()).hexdigest() for k in ('main','helper')],
                'proof':compact(report),'observations':observations,'oracle_scope':'independent Python arithmetic/alias/allocation result and allocation/free/live counters; native LP64'})
        for name,body,n,diagnostic in [('signed_overflow','return n+2147483647;',1,'signed integer overflow'),('division_zero','return 12/n;',0,'division by zero')]:
            path=root/name;path.mkdir();main_code='int api(int);int entry(int n){return api(n);}'
            helper_code='int api(int n){'+body+'}';helper=path/'helper.c';helper.write_text(helper_code)
            report=analyze_request({'source':main_code,'function':'entry','frontend':'clang_proof','clang':{'linked_sources':[str(helper)]},'proof':{'backend':'calls','parameter_bounds':{'n':[n,n]}}})
            if report['status']!='UNKNOWN' or 'normalization' not in report:raise AssertionError((name,report.get('reason')))
            if report.get('c_overflow_verified') or report.get('termination_proved'):raise AssertionError('Unsafe source certified')
            for opt in ('-O0','-O2'):
                outputs,commands=compile_forms(path,main_code,helper_code,report['normalization']['source'],'entry',[n],opt,negative=True)
                for tag,result in outputs.items():
                    if result['exit_code']==0 or diagnostic not in result['stderr']:raise AssertionError((name,opt,tag,result))
                    negative.append({'name':name,'optimization':opt,'source_form':tag,'observation':result,'commands':commands,'source_proof':compact(report)})
        for name,decl,body in [('return_type','long api(int);','int api(int n){return n;}'),('char_int','int api(unsigned char);','int api(int n){return n;}'),
                ('internal','static int api(int);','int api(int n){return n;}'),('not_external','int api(int);','static int api(int n){return n;}'),
                ('inherited_internal','int api(int);','static int api(int);extern int api(int n){return n;}'),
                ('attribute','int api(int) __attribute__((weak));','int api(int n){return n;}'),('old_prototype','int api();','int api(int n){return n;}')]:
            helper=root/'refused.c';helper.write_text(body)
            report=analyze_request({'source':decl+'int entry(int n){return api(n);}','function':'entry','frontend':'clang_proof','clang':{'linked_sources':[str(helper)]},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
            if report['status']!='UNKNOWN' or any(report.get(k) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):raise AssertionError((name,report['status']))
            refusals.append({'name':name,'source_units':[decl,body],'report':compact(report)})
    result={'passed':True,'case_count':len(rows),'native_output_matches':comparisons,'model_matches':models,'expected_ubsan_failures':len(negative),'binding_refusals':len(refusals),
        'separate_original_object_compilation':True,'optimizations':['-O0','-O2'],'compiler':run(['cc','--version']).stdout.splitlines()[0],
        'cases':rows,'negative_controls':negative,'link_refusals':refusals,'scope':'native LP64 observations supplement scoped source obligations; no general C/linker equivalence'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','link_refusals')}),flush=True)


if __name__=='__main__':main()
