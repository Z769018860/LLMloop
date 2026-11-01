"""Separate-object record calls: native values, layouts, ownership and UB."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from llmloop.api import analyze_request

if __package__:
    from .check_clang_linked_native import compact
else:
    from check_clang_linked_native import compact


NODE='struct Node{int value;struct Node *next;};'
MAKE='struct Node *make(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return 0;p->value=n;p->next=0;return p;}'
ENTRY='struct Node *make(int);int entry(int n){struct Node *p=make(n);if(!p)return -1;int value=p->value;free(p);return value;}'
ALLOC_HEADER='#include <stdlib.h>\nvoid *fixture_calloc(size_t,size_t);void fixture_free(void *);\n#define calloc fixture_calloc\n#define free fixture_free\n'
ALLOC_HARNESS='''static int fail_at,attempts,frees,live,order;static void *owned[8];
void *fixture_calloc(size_t n,size_t z){attempts++;if(attempts==fail_at)return 0;void *p=calloc(n,z);if(p){owned[attempts-1]=p;live++;}return p;}
void fixture_free(void *p){if(p){int found=0;for(int i=0;i<8;i++)if(owned[i]==p){owned[i]=0;order=order*10+i+1;found=1;break;}if(!found)abort();frees++;live--;}free(p);}
'''


def fixtures():
    def row(name,record,main,provider,oracle,objects=1,values=range(8),extra=None,provider_only=False):
        units=['#include <stdlib.h>\n'+('' if provider_only else record)+main,'#include <stdlib.h>\n'+record+provider]
        if extra:units.append('#include <stdlib.h>\n'+record+extra)
        return dict(name=name,record=record,units=units,oracle=oracle,objects=objects,values=list(values))
    rows=[row('returned_record',NODE,ENTRY,MAKE,lambda n:n)]
    rows.append(row('three_unit_mutation',NODE,'struct Node *make(int);int consume(struct Node *,int);int entry(int n){struct Node *p=make(n);if(!p)return -1;return consume(p,n);}',MAKE,lambda n:2*n+1,
        extra='int consume(struct Node *p,int n){struct Node *alias=p;alias->value+=n+1;int x=p->value;free(p);return x;}'))
    pair='struct Node *make(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return 0;struct Node *q=calloc(1,sizeof(struct Node));if(!q){free(p);return 0;}p->value=n;q->value=n+1;p->next=q;q->next=0;return p;}'
    pair_entry='struct Node *make(int);int entry(int n){struct Node *p=make(n);if(!p)return -1;struct Node *q=p->next;int x=p->value+q->value;free(q);free(p);return x;}'
    rows.append(row('two_node_ownership',NODE,pair_entry,pair,lambda n:2*n+1,objects=2,values=range(4)))
    mutual='struct Left;struct Right;struct Left{int value;struct Right *next;};struct Right{long value;struct Left *back;};'
    body='int helper(int n){struct Left *p=calloc(1,sizeof(struct Left));if(!p)return -1;struct Right *q=calloc(1,sizeof(struct Right));if(!q){free(p);return -1;}p->value=n;q->value=n+3;p->next=q;q->back=p;int x=q->back->value+p->next->value;free(q);free(p);return x;}'
    rows.append(row('provider_private_mutual_graph',mutual,'int helper(int);int entry(int n){return helper(n);}',body,lambda n:2*n+3,objects=2,values=range(4),provider_only=True))
    box='struct Box{int *slot;};'
    rows.append(row('caller_integer_payload',box,'int touch(struct Box *);int entry(int n){int a[1]={n};struct Box *p=calloc(1,sizeof(struct Box));if(!p)return -1;p->slot=a;touch(p);int x=a[0];free(p);return x;}',
        'int touch(struct Box *p){p->slot[0]+=2;return p->slot[0];}',lambda n:n+2))
    narrow='typedef unsigned char Byte;struct Node{Byte value;struct Node *next;};'
    rows.append(row('narrow_member_store',narrow,ENTRY,MAKE.replace('p->value=n;','p->value=n+260;'),lambda n:(n+260)%256,values=range(16)))
    wide='struct Wide{char first;long long value;int *payload;};'
    rows.append(row('wide_member_alignment',wide,'struct Wide *make(int);int entry(int n){struct Wide *p=make(n);if(!p)return -1;int x=p->value+p->first;free(p);return x;}',
        'struct Wide *make(int n){struct Wide *p=calloc(1,sizeof(struct Wide));if(!p)return 0;p->first=n+1;p->value=n+9;p->payload=0;return p;}',lambda n:2*n+10))
    rows.append(row('private_function_collision',NODE,'struct Node *make(int);static int adjust(struct Node *p){p->value+=2;return p->value;}int entry(int n){struct Node *p=make(n);if(!p)return -1;int x=adjust(p);free(p);return x;}',
        'static int adjust(struct Node *p){p->value+=1;return p->value;}'+MAKE.replace('p->next=0;','p->next=0;adjust(p);'),lambda n:n+3))
    return rows


def execute(command,negative=False):
    result=subprocess.run(command,text=True,capture_output=True,timeout=90,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'})
    if not negative and (result.returncode or result.stderr):raise AssertionError((command,result.returncode,result.stderr))
    return result


def native(path,units,normalized,record,layouts,values,failures,opt,negative=False,address=False):
    flags=['-std=c11',opt,'-fsanitize='+('address,undefined' if address else 'undefined'),'-fno-sanitize-recover=all']
    (path/'alloc.h').write_text(ALLOC_HEADER);commands=[];objects=[]
    for i,code in enumerate(units+[normalized]):
        p=path/('source'+str(i)+'.c');p.write_text(code);obj=path/('object'+str(i)+'.o')
        command=['cc',*flags,*(['-include','stdlib.h'] if negative else ['-include',str(path/'alloc.h')]),'-c',str(p),'-o',str(obj)]
        execute(command);commands.append(command);objects.append(str(obj))
    observations={}
    for tag,parts in [('original',objects[:-1]),('normalized',objects[-1:])]:
        lines=''
        for name,layout in layouts.items():
            args=[f'(unsigned long long)sizeof(struct {name})',f'(unsigned long long)_Alignof(struct {name})']+[f'(unsigned long long)offsetof(struct {name},{f})' for f,_ in layout['member_offsets']]
            lines+='printf("L '+name+' '+' '.join(['%llu']*len(args))+'\\n",'+','.join(args)+');'
        for fail in failures:
            for n in values:
                if negative:lines+=f'printf("%d\\n",entry({n}));'
                else:lines+=f'fail_at={fail};attempts=frees=live=order=0;for(int i=0;i<8;i++)owned[i]=0;value=entry({n});printf("V {n} {fail} %d %d %d %d %d\\n",value,attempts,frees,live,order);'
        harness='#include <stdio.h>\n#include <stdlib.h>\n#include <stddef.h>\n'+record+'int entry(int);\n'+('' if negative else ALLOC_HARNESS)+'int main(void){int value=0;(void)value;'+lines+'return 0;}'
        p=path/'harness.c';p.write_text(harness);command=['cc',*flags,str(p),*parts,'-o',str(path/tag)]
        execute(command);commands.append(command)
        r=execute([str(path/tag)],negative=negative)
        observations[tag]={'exit_code':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
    return observations,commands


def expected(row,failures,layouts):
    result=['L '+name+' '+' '.join(str(x) for x in [p['size_bytes'],p['alignment_bytes'],*[offset for _,offset in p['member_offsets']]]) for name,p in layouts.items()]
    for fail in failures:
        for n in row['values']:
            failed=0<fail<=row['objects'];attempts=fail if failed else row['objects'];frees=fail-1 if failed else row['objects']
            order=1 if frees==1 else 21 if frees==2 else 0
            result.append(f'V {n} {fail} {-1 if failed else row["oracle"](n)} {attempts} {frees} 0 {order}')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);args=parser.parse_args()
    rows=[];negative=[];refusals=[];matches=models=layouts_checked=0
    with tempfile.TemporaryDirectory(prefix='llmloop-record-native-') as temp:
        root=Path(temp)
        for case in fixtures():
            path=root/case['name'];path.mkdir();sources=[]
            for i,text in enumerate(case['units']):
                p=path/('unit'+str(i)+'.c');p.write_text(text);sources.append(str(p))
            bounds=[min(case['values']),max(case['values'])]
            report=analyze_request({'source_file':sources[0],'function':'entry','frontend':'clang_proof','clang':{'linked_sources':sources[1:]},'proof':{'backend':'calls','parameter_bounds':{'n':bounds},'max_steps':512}})
            if report['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':raise AssertionError((case['name'],report.get('reason'),report.get('failed_obligation')))
            norm=report['normalization'];compat=norm['translation_unit_linking']['record_compatibility']
            if not compat['proof_model_layouts_checked']:raise AssertionError('Missing per-unit model check')
            layouts=norm['record_layout_correspondence'];failures=list(range(case['objects']+2));want=expected(case,failures,layouts)
            scenarios=len(case['values'])*len(failures);observations=[]
            for opt in ('-O0','-O2'):
                native_outputs,commands=native(path,case['units'],norm['source'],case['record'],layouts,case['values'],failures,opt)
                for tag,output in native_outputs.items():
                    if output['stdout'].splitlines()!=want:raise AssertionError((case['name'],tag,opt,output['stdout'],want))
                    matches+=scenarios;layouts_checked+=len(layouts)
                models+=scenarios;observations.append({'optimization':opt,'commands':commands,'outputs':native_outputs,'independent_expected':want})
            rows.append({'name':case['name'],'source_units':case['units'],'proof':compact(report),'observations':observations})
        controls=[('member_overflow','p->value=2147483647+n;return p->value;',1,'signed integer overflow',False),
            ('member_division','return p->value/n;',0,'division by zero',False),
            ('freed_member','free(p);return p->value;',1,'heap-use-after-free',True),
            ('alias_double_free','struct Node *q=p;free(p);free(q);return 0;',1,'double-free',True)]
        for name,body,n,diagnostic,address in controls:
            path=root/name;path.mkdir()
            units=['#include <stdlib.h>\n'+NODE+'int api(struct Node *,int);int entry(int n){struct Node *p=calloc(1,sizeof(struct Node));if(!p)return -1;p->value=n;p->next=0;int x=api(p,n);free(p);return x;}',
                '#include <stdlib.h>\n'+NODE+'int api(struct Node *p,int n){'+body+'}']
            p=path/'unit.c';p.write_text(units[1])
            report=analyze_request({'source':units[0],'function':'entry','frontend':'clang_proof','clang':{'linked_sources':[str(p)]},'proof':{'backend':'calls','parameter_bounds':{'n':[n,n]},'max_steps':128}})
            if report['status']!='UNKNOWN' or not report.get('failed_obligation'):raise AssertionError((name,report.get('reason'),report.get('failed_obligation')))
            for opt in ('-O0','-O2'):
                outputs,commands=native(path,units,report['normalization']['source'],NODE,{},[n],[0],opt,negative=True,address=address)
                for tag,output in outputs.items():
                    if output['exit_code']==0 or diagnostic not in output['stderr']:raise AssertionError((name,opt,tag,output))
                    negative.append({'name':name,'optimization':opt,'source_form':tag,'observation':output,'commands':commands,'source_proof':compact(report)})
        for name,record in [('signedness','struct Node{unsigned int value;struct Node *next;};'),('field_name','struct Node{int other;struct Node *next;};'),
            ('field_order','struct Node{struct Node *next;int value;};'),('pointee','struct Node{int value;int *next;};'),
            ('packed','struct __attribute__((packed)) Node{int value;struct Node *next;};'),('incomplete','struct Node;')]:
            p=root/'incompatible.c';p.write_text(record+'struct Node *make(int n){return 0;}')
            report=analyze_request({'source':'#include <stdlib.h>\n'+NODE+ENTRY,'function':'entry','frontend':'clang_proof','clang':{'linked_sources':[str(p)]},'proof':{'backend':'calls','parameter_bounds':{'n':[0,2]}}})
            if report['status']!='UNKNOWN' or any(report.get(k) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):raise AssertionError(name)
            refusals.append({'name':name,'provider_source':p.read_text(),'report':compact(report)})
    result={'passed':True,'case_count':len(rows),'native_output_matches':matches,'model_matches':models,'native_layout_matches':layouts_checked,'expected_sanitizer_failures':len(negative),'record_refusals':len(refusals),
        'separate_original_object_compilation':True,'cases':rows,'negative_controls':negative,'compatibility_refusals':refusals,
        'compiler':execute(['cc','--version']).stdout.splitlines()[0],'scope':'native LP64 values/layouts and allocation/free identity/order observations supplement bounded source proofs; no general heap/linker/C support'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','negative_controls','compatibility_refusals')}),flush=True)


if __name__=='__main__':main()
