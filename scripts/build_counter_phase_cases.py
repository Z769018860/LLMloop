"""Additive counter-threshold source proofs and original-operation controls."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LINEAR='long phase_linear(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x+=i;}else{x+=2L*i;}}return x;}'
STEPS='long phase_steps(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x+=1;}else{x+=2;}}return x;}'
MISSING_ELSE='long phase_optional(int n,int t){long x=0;for(int i=0;i<n;i++){if(i>=t){x+=3;}}return x;}'
CELLS='int phase_cells(int n,int t){unsigned char a[1]={0};for(int i=0;i<n;i++){if(i<t){a[0]+=1;}else{a[0]+=2;}}return a[0];}'
MULTI='long phase_multi(int n,int t){long x=7;long y=0;for(int i=0;i<n;i++){if(i>t){x+=2;y+=4L*i;}else{x-=1;y+=2L*i;}}return x+y;}'
RAW_CUBIC='long phase_cubic(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x+=1L*i*i*i;}else{x+=2L*i*i*i;}}return x;}'
CUBIC=RAW_CUBIC.replace('+=1L','+=4L').replace('+=2L','+=8L')
NESTED='long phase_nested(int n){long x=0;for(int i=0;i<n;i++){for(int j=0;j<4;j++){if(j<2){x+=1;}else{x+=2;}}}return x;}'
FEEDBACK='long phase_feedback(int n,int t){long x=1;for(int i=0;i<n;i++){if(i<t){x*=2;}else{x++;}}return x;}'


def cases():
    rows=json.loads((ROOT/'experiments/v019/cases.json').read_text())
    for row in rows:
        if row['name']=='auto_general_branch_unsupported':
            row['name']='auto_counter_threshold_now_supported'
            row['request']['parameter_bounds']={'n':[0,1000000]}
            row['expected_status']='PROVED_DEFINED_TYPED_C_NESTED'
    def add(name,source,frontend='typed_nested',abi='LP64',expected=None,bounds=None,inputs=None):
        rows.append({'name':name,'request':{'source':source,'frontend':frontend,'abi':abi,
            'loop_summaries':'auto','parameter_bounds':bounds or {'n':[0,1000],'t':[-1000,1000]},
            'inputs':inputs or {'n':1000,'t':500}},'expected_status':expected or
            ('PROVED_DEFINED_TYPED_C_MEMORY' if frontend=='typed_memory' else 'PROVED_DEFINED_TYPED_C_NESTED')})
    example=(ROOT/'examples/typed_counter_phases.c').read_text()
    for abi in ['LP64','ILP32','LLP64']:
        add('counter_phase_'+abi,example,abi=abi,bounds={'n':[0,1000],'threshold':[-1000,1000]},inputs={'n':10,'threshold':3})
        add('counter_phase_cells_'+abi,CELLS,'typed_memory',abi)
    for name,source in [('linear',LINEAR),('missing_else',MISSING_ELSE),('multiple_coordinates',MULTI),('cubic',CUBIC)]:add('counter_phase_'+name,source)
    add('counter_phase_nested',NESTED,bounds={'n':[0,1000000]},inputs={'n':1000000})
    add('counter_phase_fractional_cubic',RAW_CUBIC)
    add('counter_phase_billion',STEPS,bounds={'n':[0,1000000000],'t':[-1000000000,1000000000]},inputs={'n':1000000000,'t':999999999})
    add('counter_phase_feedback_unsupported',FEEDBACK,expected='UNKNOWN')
    add('counter_phase_cast_guard_refuted','long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<(unsigned char)t){x+=1;}else{x+=2;}}return x;}',expected='UNKNOWN')
    add('counter_phase_erased_overflow','int f(int n,int t){int x=0;for(int i=0;i<n;i++){if(i<t){x+=(i+2147483647)-2147483647;}else{x++;}}return x;}',expected='UNKNOWN')
    add('counter_phase_guard_overflow','long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t+2147483647){x++;}else{x+=2;}}return x;}',expected='UNKNOWN')
    add('counter_phase_degree_budget','long f(int n,int t){long x=0;for(int i=0;i<n;i++){if(i<t){x+=1L*i*i*i*i;}else{x++;}}return x;}',expected='UNKNOWN')
    return rows

if __name__=='__main__':
    (ROOT/'experiments/v020/cases.json').write_text(json.dumps(cases(),indent=2)+'\n')
