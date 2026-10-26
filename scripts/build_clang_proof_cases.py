"""Clang typed-AST scalar proof expectations, distinct from frontend readiness."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
NARROW='#define ADD 1\ntypedef unsigned char Byte;int entry(int n){Byte x=n;return x+ADD;}'
CONTROL='int entry(int n){int x=0;do{if(n<=0){goto done;}switch(n){case 1:x+=2;break;default:x++;}n--;if(n==2){continue;}}while(n>0);done:return x;}'
SUM='#define STEP 2\ntypedef long Word;Word entry(int n){Word x=0;for(int i=0;i<n;i++){x+=STEP;}return x;}'
MOD='int entry(int n){unsigned char x=0;for(int i=0;i<n;i++){x++;}return x;}'
NEST='long entry(int n,int m){long x=0;for(int i=0;i<n;i++){for(int j=0;j<m;j++){x++;}}return x;}'
SHADOW='int entry(int n){int x=n;{int x=7;x++;}return x;}'
LAZY='int entry(int n){return n==0 || 8/n>0;}'
FAULTS=[('clang_normalized_overflow','int entry(int n){int x=2147483647+n;x=0;return x;}',{'n':[1,1]},'signed integer overflow'),
        ('clang_normalized_div_zero','int entry(int n){return n/(n-1);}',{'n':[1,1]},'division by zero')]
TARGETS=['x86_64-unknown-linux-gnu','i386-unknown-linux-gnu','x86_64-w64-windows-gnu']

def cases():
    rows=json.loads((ROOT/'experiments/v027/cases.json').read_text())
    def add(name,source,bounds,backend='cfg',expected=None,options=None,**proof):
        rows.append({'name':name,'request':{'source':source,'frontend':'clang_proof','function':'entry','clang':options or {},'proof':{'backend':backend,'parameter_bounds':bounds,**proof}},'expected_status':expected or 'PROVED_DEFINED_CLANG_SCALAR_'+backend.upper()})
    for target in TARGETS:
        opts={'target':target}
        add('clang_proof_narrow_'+target,NARROW,{'n':[254,257]},options=opts)
        add('clang_proof_control_'+target,CONTROL,{'n':[0,4]},options=opts,max_steps=256)
        add('clang_proof_million_nested_'+target,SUM,{'n':[0,1000000]},backend='nested',options=opts)
        add('clang_proof_million_recurrence_'+target,SUM,{'n':[0,1000000]},backend='recurrence',options=opts,closed_forms={'x':'2*i'})
        add('clang_proof_million_modular_'+target,MOD,{'n':[0,1000000]},backend='nested',options=opts,loop_summaries={'i':{'x':'i%256'}})
    add('clang_proof_nested_two_levels',NEST,{'n':[0,1000],'m':[0,1000]},backend='nested')
    add('clang_proof_shadowed_locals',SHADOW,{'n':[0,3]})
    add('clang_proof_lazy_division',LAZY,{'n':[0,4]})
    for name,source,bounds,_ in FAULTS:add(name,source,bounds,expected='UNKNOWN')
    add('clang_proof_wrong_summary',SUM,{'n':[0,100]},backend='recurrence',closed_forms={'x':'i'},expected='UNKNOWN')
    add('clang_proof_cfg_frontier',CONTROL,{'n':[0,4]},max_steps=2,expected='UNKNOWN')
    for target in ['aarch64-unknown-linux-gnu','x86_64-unknown-linux-gnux32']:add('clang_proof_unsupported_abi_'+target,'int entry(int n){return n;}',{'n':[0,3]},options={'target':target},expected='UNKNOWN')
    for name,source in [('memory','int entry(int n){int a[1]={n};return a[0];}'),('call','int f(int n){return n;}int entry(int n){return f(n);}'),('global','int x=3;int entry(int n){return x;}'),('unsequenced','int entry(int n){return n++ + n;}'),('volatile','int entry(int n){volatile int x=n;return x;}')]:add('clang_proof_unsupported_'+name,source,{'n':[0,3]},expected='UNKNOWN')
    return rows

if __name__=='__main__':(ROOT/'experiments/v028/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
