"""Analyzer rejections versus independent ASan/UBSan controlled failures.

Only deliberately faulty local fixtures are executed, in separate subprocesses.
Uninitialized reads and pointer formation alone are not claimed as ASan checks.
"""
import os
from pathlib import Path
import subprocess
import tempfile
from llmloop.api import analyze_request

CASES=[
    ('stack_bounds','''int f(int n){int a[1]={0};for(int i=0;i<n;i++){a[0]=0;}return a[n];}''',
     {'i':{'a[0]':'0'}},'out of bounds'),
    ('use_after_free','''int f(int n){int *p=calloc(1,sizeof(int));for(int i=0;i<n;i++){p[0]=0;}
        free(p);return p[0];}''',{'i':{'p[0]':'0'}},'heap-use-after-free'),
    ('double_free','''int f(int n){int *p=calloc(1,sizeof(int));int *q=p;for(int i=0;i<n;i++){p[0]=0;}
        free(p);free(q);return 0;}''',{'i':{'p[0]':'0'}},'double-free'),
    ('interior_free','''int f(int n){int *p=calloc(2,sizeof(int));for(int i=0;i<n;i++){p[0]=0;}
        free(p+1);return 0;}''',{'i':{'p[0]':'0','p[1]':'0'}},'not malloc'),
    ('signed_intermediate','''int f(int n){int a[1]={1};for(int i=0;i<n;i++){int temp=a[0]+2147483647;a[0]=temp-2147483647;}return a[0];}''',
     {'i':{'a[0]':'1'}},'signed integer overflow')
]


def main():
    env=dict(os.environ);env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1';env['UBSAN_OPTIONS']='halt_on_error=1'
    count=0
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,source,forms,diagnostic in CASES:
            report=analyze_request({'source':source,'frontend':'typed_memory','loop_summaries':forms,'parameter_bounds':{'n':[1,1]}})
            if report['status']!='UNKNOWN':raise AssertionError((name,report))
            cfile=path/(name+'.c');binary=path/name
            cfile.write_text('#include <stdlib.h>\n'+source+'\nint main(void){return f(1);}\n')
            subprocess.run(['cc','-std=c11','-O0','-fsanitize=address,undefined','-fno-sanitize-recover=undefined',str(cfile),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
            if result.returncode==0 or diagnostic not in result.stderr:raise AssertionError((name,result.returncode,result.stderr[:2000]))
            count+=1
    # Keep the canceled-expression observation too: sanitizer diagnostics are
    # not guaranteed after compiler simplification, and their absence is not a
    # source-level definedness proof.
    erased='int f(int n){int a[1]={1};for(int i=0;i<n;i++){a[0]=(a[0]+2147483647)-2147483647;}return a[0];}'
    report=analyze_request({'source':erased,'frontend':'typed_memory','loop_summaries':{'i':{'a[0]':'1'}},'parameter_bounds':{'n':[1,1]}})
    if report['status']!='UNKNOWN':raise AssertionError(report)
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory);source=path/'erased.c';binary=path/'erased'
        source.write_text('#include <stdlib.h>\n'+erased+'\nint main(void){return f(1);}')
        subprocess.run(['cc','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(source),'-o',str(binary)],check=True,capture_output=True)
        observation=subprocess.run([str(binary)],env=env,capture_output=True,text=True)
    print('Canceled intermediate observation: analyzer=UNKNOWN, native_exit='+str(observation.returncode)+
          ', signed_overflow_diagnostic='+str('signed integer overflow' in observation.stderr))
    print(f'Unsafe memory source rejections / native ASan+UBSan: {count}/{count} matched')


if __name__=='__main__':main()
