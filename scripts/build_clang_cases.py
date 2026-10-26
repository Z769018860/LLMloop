"""Clang ingestion expectations are frontend acceptance, never proof outcomes."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SOURCES={
 'scalar':'int entry(int n){int sum=0;for(int i=0;i<n;i++){sum+=i;}return sum;}',
 'narrow':'int entry(int n){unsigned char x=n;return x+1;}',
 'control':'int entry(int n){int x=0;while(n>0){switch(n){case 1:x+=2;break;default:x++;}n--;if(x>10){goto done;}}done:return x;}',
 'packed':'struct __attribute__((packed)) P{char tag;int value;};int entry(int n){struct P p={1,n};return sizeof(struct P)+p.value;}',
 'vla':'int entry(int n){int a[n+1];a[0]=n+2;return a[0];}'}
FAULTS=[('signed_overflow','int entry(int n){return 2147483647+n;}',1,'signed integer overflow'),
        ('vla_bound','int entry(int n){int a[n];a[0]=3;return a[0];}',0,'variable length array bound')]

def cases():
    rows=json.loads((ROOT/'experiments/v026/cases.json').read_text())
    def add(name,source,expected='CLANG_FRONTEND_READY',**options):
        rows.append({'name':name,'request':{'source':source,'frontend':'clang','function':'entry','clang':{'include_ast':False,**options}},'expected_status':expected})
    for name,source in SOURCES.items():add('clang_frontend_'+name,source)
    for name,source,_,_ in FAULTS:add('clang_compiles_but_not_proved_'+name,source)
    source='struct S{char c;long x;int *p;};int entry(void){return sizeof(struct S);}'
    for target in ['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu']:add('clang_target_'+target,source,target=target)
    for name,source in [('bad_member','struct S{int x;};int entry(void){struct S s;return s.missing;}'),('bad_type','int entry(void){int *p=3.5;return 0;}'),('syntax','int entry( {')]:add('clang_rejected_'+name,source,expected='UNKNOWN')
    add('clang_reject_unknown_semantics',SOURCES['scalar'],expected='UNKNOWN',args=['-fwrapv'])
    add('clang_reject_plugin',SOURCES['scalar'],expected='UNKNOWN',args=['-Xclang','-load','bad.so'])
    add('clang_missing_binary',SOURCES['scalar'],expected='UNKNOWN',executable='/missing/clang')
    return rows

if __name__=='__main__':(ROOT/'experiments/v027/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
