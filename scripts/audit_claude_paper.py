"""Recompute paper counts from the frozen Claude-branch evidence.

No external tool or model calls. A matching aggregate is not a soundness proof,
a fresh baseline execution, or a verification of source-to-source equivalence.
"""
import collections, hashlib, json, math, random, statistics, subprocess
from pathlib import Path
from scripts.certificate_identity import certificate_key
ROOT=Path(__file__).resolve().parents[1]
BASE='18d66724bfe94094afc5148ab2bac3dfaef3085d'
OUT=ROOT/'experiments/claude_paper_audit_20261122'
FILES={}

def read(name):
    p=ROOT/name;data=p.read_bytes();FILES[name]=hashlib.sha256(data).hexdigest()
    return [json.loads(l) for l in data.decode().splitlines()] if p.suffix=='.jsonl' else json.loads(data)

def proved(rows):return {r['program'] for r in rows if r.get('status',r.get('final'))=='PROVED'}
def exact_p(a,b):return min(1.0,2*sum(math.comb(a+b,k) for k in range(min(a,b)+1))/2**(a+b)) if a+b else 1.0

def certificate_counts(folder,hybrid):
    rows=read(f'experiments/{folder}/results.jsonl') if hybrid else sum((read(f'experiments/{folder}/{n}.json')['rows'] for n in ['ours','ours_poly']),[])
    groups=collections.defaultdict(dict)
    for r in rows:
        if r.get('status',r.get('final'))!='PROVED':continue
        text=json.dumps(r['invariant']);groups[(r['program'],text[:600])][text]=r
    collisions=[]
    for (program,prefix),variants in groups.items():
        if len(variants)>1:collisions.append({'program':program,'distinct_certificates':len(variants),'full_sha256':[hashlib.sha256(v.encode()).hexdigest() for v in variants]})
    return {'prefix_scheduled':len(groups),'full_distinct':sum(map(len,groups.values())),'lossless_scheduled':len({certificate_key(r['program'],r['invariant']) for r in rows if r.get('status',r.get('final'))=='PROVED'}),'collisions':collisions}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    trans=read('experiments/v099_fresh/translated.json');admitted={r['dir']+'/'+r['file'] for r in trans if r['stage'].startswith('in_')};allnames={r['dir']+'/'+r['file'] for r in trans}
    default=read('experiments/v099_fresh/ours.json')['rows'];poly=read('experiments/v099_fresh/ours_poly.json')['rows'];hybrid=read('experiments/v099_fresh_hybrid/results.jsonl')
    ours=proved(default)|proved(poly)|proved(hybrid);nonllm=proved(default)|proved(poly)
    ur=read('experiments/v099_fresh/ultimate.json');ultimate={r['program'] for r in ur if r['ultimate']=='TRUE'}
    witnesses={r['program'] for f in ['falsifier.json','falsifier_long_unproved.json'] for r in read('experiments/v099_fresh/'+f) if r['result']=='OVERFLOW_WITNESS'}
    trivial=set()
    for r in default:
        if r['status']!='PROVED' or not r['invariant']:continue
        groups=r['invariant'] if isinstance(r['invariant'][0],list) else [r['invariant']]
        if all(a=='True' for group in groups for a in group):trivial.add(r['program'])
    nontrivial=admitted-trivial;a=len(ours-ultimate);b=len(ultimate-ours);da=len((ours|witnesses)-ultimate);db=len(ultimate-(ours|witnesses))
    assert len(trans)==len(allnames)==165 and len(admitted)==93
    assert all(len(rows)==93 and {r['program']for r in rows}==admitted for rows in [default,poly,ur])
    assert not ours&witnesses and not ultimate&witnesses
    rng=random.Random(20261122);bootstrap=[];ns=sorted(nontrivial)
    for _ in range(10000):bootstrap.append(statistics.mean((n in ours)-(n in ultimate) for n in rng.choices(ns,k=len(ns))))
    bootstrap.sort()
    cert=[certificate_counts(f,h) for f,h in [('v099_fresh',False),('v099_fresh_hybrid',True),('v096_nooverflow_noassert',False),('v097_hybrid',True)]]
    raw_cert=[]
    for path in ['v099_fresh/flat_recheck_fresh.json','v099_fresh/flat_recheck_fresh_hybrid.json','v096_nooverflow_noassert/flat_recheck_nooverflow.json','v096_nooverflow_noassert/flat_recheck_hybrid.json']:raw_cert+=read('experiments/'+path)
    old=read('experiments/v091/cert_recheck_cbmc.json')
    llm_rows=read('experiments/v097_hybrid/results.jsonl')+hybrid
    from scripts.synth_bench_v102 import explore
    spec={'inputs':['a'],'loc':['x','y'],'lo':0,'hi':0,'inits':{'x':'0','y':'0'},'cond':'nd','body':[('if','nd','x = 0;','x = 2147483647 + 1;')]}
    correlated_result=explore(spec)
    guard_bug=None
    try:explore({**spec,'cond':'x < 1 && nd'})
    except Exception as e:guard_bug=type(e).__name__+': '+str(e)
    by_model={}
    for model in sorted({r['model'] for r in hybrid}):
        rows=[r for r in hybrid if r['model']==model];s=proved(rows);by_model[model]={'proofs':len(s),'extra_over_nonllm_union':sorted(s-nonllm),'successful_repairs':sum(r['final']=='PROVED'and r['rounds'][-1]['round']>0 for r in rows)}
    result={'audited_claude_commit':BASE,'scope':'read-only recomputation of existing evidence plus targeted semantic reproductions; no fresh baseline/model run',
       'corpus':{'total':165,'admitted':93,'excluded':72,'stages':dict(collections.Counter(r['stage'].split(':')[0]for r in trans)),'admitted_directories':dict(collections.Counter(n.split('/')[0]for n in admitted)),
                 'nooverflow_labels':dict(collections.Counter(r['expected_unreach']for r in trans)),'coverage':93/165,'excluded_names':sorted(allnames-admitted)},
       'proofs':{'default':len(proved(default)),'poly':len(proved(poly)),'nonllm_union':len(nonllm),'hybrid_any':len(proved(hybrid)),'all_union':len(ours),'ultimate_true':len(ultimate),'ultimate_statuses':dict(collections.Counter(r['ultimate']for r in ur)),
                 'proof_pair':[a,b],'proof_pair_exact_p':exact_p(a,b),'decided_pair':[da,db],'decided_pair_exact_p':exact_p(da,db),'witnesses':sorted(witnesses),'total_decided':len(ours|witnesses),'own_proof_witness_contradictions':[]},
       'nontrivial':{'excluded_literal_true_proofs':len(trivial),'programs':len(nontrivial),'default':len(proved(default)&nontrivial),'ours_union':len(ours&nontrivial),'ultimate':len(ultimate&nontrivial),'paired':[len((ours-ultimate)&nontrivial),len((ultimate-ours)&nontrivial)],'descriptive_paired_bootstrap_95':[bootstrap[249],bootstrap[9749]],'unit':'program; conditional on the selected admitted corpus; not external generalization'},
       'llm':{'fresh_rows':len(hybrid),'fresh_models_by_endpoint_alias':by_model,'fresh_extra_over_nonllm_union':sorted(proved(hybrid)-nonllm),'combined_rows':len(llm_rows),'rows_without_usage_tokens_latency':sum(not any(k in r for k in ['usage','tokens','seconds','latency'])for r in llm_rows),'raw_provider_responses_stored_in_these_rows':False},
       'certificate_scheduling':{'groups':cert,'stored_rechecks':len(raw_cert),'stored_results':dict(collections.Counter(r['result']for r in raw_cert)),'full_distinct_within_study_groups':sum(r['full_distinct']for r in cert),'missing_distinct_planned':sum(r['full_distinct']-r['prefix_scheduled']for r in cert),'new_rechecks_executed_by_this_readonly_counter':0},
       'v091_rechecks':{'rows':len(old),'statuses':dict(collections.Counter(r['cbmc']for r in old))},
       'reproduction_gaps':{'setup_script_exists':(ROOT/'scripts/setup_env.sh').exists(),'fresh_ultimate_long_result_exists':(ROOT/'experiments/v099_fresh/ultimate_long.json').exists(),'fresh_ultimate_rejected_result_exists':(ROOT/'experiments/v099_fresh/ultimate_rejected.json').exists()},
       'old_oracle_reproductions':{'correlated_choice_case_reported':correlated_result,'correct_expected':'OVERFLOW (guard choice 1, body choice 0)','conjunctive_guard_error':guard_bug},'input_sha256':FILES}
    (OUT/'audit.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({k:result[k]for k in ['corpus','proofs','nontrivial','certificate_scheduling','v091_rechecks','reproduction_gaps','old_oracle_reproductions']},ensure_ascii=False,default=str)[:4500])
if __name__=='__main__':main()
