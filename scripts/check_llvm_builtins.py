"""Offline compiler-rt pilot with exact provenance and independent controls."""
import argparse
import copy
import hashlib
import json
import resource
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types

import z3

from llmloop.api import analyze_request
from llmloop.llvm_benchmarks import (ROOT,VENDOR,BASELINE_COMMIT,verify_vendor,cases,
    independent_value,sample_inputs,compilation_database,analyze_case,functional_proof,model_values)


def compact_report(report):
    result={k:v for k,v in report.items() if k!='clang_frontend'}
    front=report.get('clang_frontend',{})
    result['clang_provenance']={k:front[k] for k in ('status','compiler','source','target','effective_flags','compilation_database') if k in front}
    return result


def native_harness(case,prefix):
    parameters=[];raw=[];addresses=[];scanf=[];actuals=[]
    for index,(key,(width,signed)) in enumerate(case['types'].items()):
        ctype=('int' if signed else 'uint')+str(width)+'_t'
        parameters.append(ctype);raw.append(('long long' if signed else 'unsigned long long')+' x'+str(index)+';')
        scanf.append('%lld' if signed else '%llu');addresses.append('&x'+str(index));actuals.append('('+ctype+')x'+str(index))
    unsigned=case['oracle'] in ('bswap','udiv')
    width=next(iter(case['types'].values()))[0]
    returned='uint'+str(width)+'_t' if unsigned else 'int'
    return '#include <stdio.h>\n#include <stdint.h>\nextern '+returned+' '+prefix+'('+','.join(parameters)+');\nint main(void){'+''.join(raw)+'while(scanf("'+' '.join(scanf)+'",'+','.join(addresses)+')=='+str(len(parameters))+'){'+returned+' value='+prefix+'('+','.join(actuals)+');printf("'+('%llu' if unsigned else '%lld')+'\\n",('+('unsigned long long' if unsigned else 'long long')+')value);}return 0;}'


def disable_core():resource.setrlimit(resource.RLIMIT_CORE,(0,0))


def native_run(directory,case,source,inputs,opt,tag):
    prefix='llmloop_fixture_'+case['function'].lstrip('_')
    harness=directory/(case['name']+tag+'_harness.c');harness.write_text(native_harness(case,prefix))
    executable=directory/(case['name']+tag+opt)
    command=['cc','-std=c11',opt,'-fno-builtin','-fno-lto','-fsanitize=undefined','-fno-sanitize-recover=undefined',
             '-I',str(VENDOR),'-D'+case['function']+'='+prefix,str(source),str(harness),str(VENDOR/'int_util.c'),'-o',str(executable)]
    built=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if built.returncode:raise AssertionError((case['name'],'native compilation failed',built.stderr))
    stdin=''.join(' '.join(str(row[key]) for key in case['types'])+'\n' for row in inputs)
    run=subprocess.run([str(executable)],input=stdin,capture_output=True,text=True,timeout=30,preexec_fn=disable_core)
    return {'command':command,'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,
            'input_sha256':hashlib.sha256(stdin.encode()).hexdigest()}


def baseline_case(name,database):
    # Run only in the dedicated child process. The immutable previous kernel is
    # loaded without writing or changing the active checkout's source files.
    from llmloop import typed_recurrence
    old=subprocess.check_output(['git','show',BASELINE_COMMIT+':llmloop/integer_lift.py'],cwd=ROOT,text=True)
    module=types.ModuleType('llmloop._benchmark_baseline_integer_lift');module.__package__='llmloop'
    exec(compile(old,'git:'+BASELINE_COMMIT+':llmloop/integer_lift.py','exec'),module.__dict__)
    typed_recurrence.IntegerLift=module.IntegerLift
    case=copy.deepcopy(next(c for c in cases() if c['name']==name));case['bounds']={'a':[-2147483648,2147483647]}
    request,report,elapsed=analyze_case(case,database)
    return {'base_commit':BASELINE_COMMIT,'integer_lift_source_sha256':hashlib.sha256(old.encode()).hexdigest(),
            'query_scope':'source definedness over all signed 32-bit inputs; no functional contract for zero',
            'request':request,'elapsed_seconds':elapsed,'report':compact_report(report)}


def isolated_analyze_case(case,database,source_file=None):
    """One fresh process/query context per source analysis; never retry."""
    command=[sys.executable,str(Path(__file__).resolve()),'--analyze-case',json.dumps(case),'--database',str(database)]
    if source_file is not None:command+=['--analyze-source',str(source_file)]
    run=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if run.returncode:raise AssertionError(('isolated source analysis failed',run.stderr))
    return json.loads(run.stdout)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--samples',type=int,default=256)
    parser.add_argument('--compare-baseline',action='store_true');parser.add_argument('--baseline-case',choices=['clzsi2_positive','ctzsi2_positive'])
    parser.add_argument('--database',type=Path);parser.add_argument('--functional-baseline',action='store_true');parser.add_argument('--analyze-case');parser.add_argument('--analyze-source',type=Path);args=parser.parse_args()
    provenance=verify_vendor()
    if args.analyze_case:
        request,report,elapsed=analyze_case(json.loads(args.analyze_case),args.database,args.analyze_source)
        front=report.get('clang_frontend',{})
        report={**compact_report(report),'clang_frontend':{k:front[k] for k in ('status','compiler','source','target','effective_flags','compilation_database') if k in front}}
        print(json.dumps([request,report,elapsed]));return 0
    if args.functional_baseline:
        case=next(c for c in cases() if c['name']=='popcount64')
        request,report,elapsed=analyze_case(case,args.database)
        if not report['status'].startswith('PROVED_DEFINED_'):raise AssertionError(report)
        query,unused=functional_proof(case,report['normalization']['source'],strategy='direct')
        print(json.dumps({'case':case['name'],'source_safety_status':report['status'],'query':query}));return 0
    if args.baseline_case:
        print(json.dumps(baseline_case(args.baseline_case,args.database)));return 0
    rows=[];native_comparisons=0;correspondences=0;model_comparisons=0;controls=[];baseline=[];functional_baseline=[]
    with tempfile.TemporaryDirectory(prefix='llmloop-llvm-bench-') as directory:
        path=Path(directory);database=compilation_database(path)
        for case in cases():
            inputs=sample_inputs(case,args.samples);expected=[independent_value(case,row) for row in inputs]
            request,report,elapsed=isolated_analyze_case(case,database)
            if report['status']!=case['expected_safety']:raise AssertionError((case['name'],report['status'],report.get('reason')))
            proved=report['status'].startswith('PROVED_DEFINED_')
            if not proved and any(report.get(k,False) for k in ('c_overflow_verified','memory_safety_verified','termination_proved')):raise AssertionError(report)
            front=report.get('clang_frontend',{})
            if front.get('status')!='CLANG_FRONTEND_READY':raise AssertionError((case['name'],'original source ingestion failed',report))
            forms=[('original',VENDOR/case['file'])];functionality=None;models=[]
            if proved:
                normalized=report['normalization']['source'];normalized_path=path/(case['name']+'_normalized.c');normalized_path.write_text(normalized)
                forms.append(('normalized',normalized_path))
                functionality,bv_model=functional_proof(case,normalized)
                if functionality['status']=='REFUTED_FUNCTIONAL_QF_BV':raise AssertionError((case['name'],functionality))
                selected=inputs[:32]+inputs[-32:]
                lifted=model_values(case,normalized,selected,report)
                for index,row in enumerate(selected):
                    substitutions=[(term.value,z3.BitVecVal(row[key],term.type.bits)) for key,term in bv_model.engine.variables.items()]
                    expression=bv_model.engine.expression
                    safe=z3.simplify(z3.substitute(expression.safe,*substitutions))
                    if not z3.is_true(safe):raise AssertionError((case['name'],row,'bit-vector source evaluator undefined'))
                    value=z3.simplify(z3.substitute(expression.value,*substitutions)).as_long()
                    if expression.type.signed and value>expression.type.maximum:value-=1<<expression.type.bits
                    want=independent_value(case,row)
                    if value!=want or lifted[index]!=want:raise AssertionError((case['name'],row,value,lifted[index],want))
                    models.append({'inputs':row,'independent':want,'integer_lift':lifted[index],'typed_bit_vector':value})
                model_comparisons+=2*len(selected)
            runs=[]
            for opt in ('-O0','-O2'):
                outputs={};commands=[]
                for tag,source in forms:
                    run=native_run(path,case,source,inputs,opt,tag)
                    if run['exit_code'] or run['stderr']:raise AssertionError((case['name'],tag,opt,run))
                    values=[int(line) for line in run['stdout'].splitlines()]
                    if values!=expected:raise AssertionError((case['name'],tag,opt,'native/reference mismatch'))
                    outputs[tag]=values;commands.append({k:v for k,v in run.items() if k!='stdout'})
                    native_comparisons+=len(inputs)
                correspondences+=len(inputs);runs.append({'optimization':opt,'outputs':outputs,'commands':commands})
            rows.append({'case':case,'request':request,'analysis_elapsed_seconds':elapsed,'analysis':compact_report(report),
                         'functional':functionality,'inputs':inputs,'independent_expected':expected,'model_samples':models,'native':runs})
            print(case['name'],report['status'],'functional',None if functionality is None else functionality['status'],len(inputs),'inputs x 2 optimizations',flush=True)
        # A defined algorithm can be wrong. Safety is not its functional spec.
        case=next(c for c in cases() if c['name']=='popcount32')
        wrong=path/'wrong_popcount.c';wrong.write_text((VENDOR/case['file']).read_text().replace('0x55555555','0x55555554'))
        request,report,elapsed=isolated_analyze_case(case,database,wrong)
        if report['status']!='PROVED_DEFINED_CLANG_SCALAR_CFG':raise AssertionError(report)
        query,unused=functional_proof(case,report['normalization']['source'])
        if query['status']!='REFUTED_FUNCTIONAL_QF_BV':raise AssertionError(query)
        witness=query['counterexample'];expected=independent_value(case,witness);native=[]
        for opt in ('-O0','-O2'):
            run=native_run(path,case,wrong,[witness],opt,'wrong')
            if run['exit_code'] or run['stderr'] or int(run['stdout'])==expected:raise AssertionError(run)
            native.append(run)
        controls.append({'control':'defined_but_wrong_algorithm','request':request,'safety_status':report['status'],
                         'source':wrong.read_text(),'source_sha256':hashlib.sha256(wrong.read_bytes()).hexdigest(),
                         'analysis':compact_report(report),'functional':query,'independent_expected':expected,'native':native})
        case=next(c for c in cases() if c['name']=='popcount64')
        wrong64=path/'wrong_popcount64.c';wrong64.write_text((VENDOR/case['file']).read_text().replace('0x5555555555555555','0x5555555555555554'))
        request,report,unused=isolated_analyze_case(case,database,wrong64)
        if report['status']!='PROVED_DEFINED_CLANG_SCALAR_CFG':raise AssertionError(report)
        query,unused=functional_proof(case,report['normalization']['source'])
        if query['status']!='REFUTED_FUNCTIONAL_QF_BV':raise AssertionError(query)
        witness=query['counterexample'];expected=independent_value(case,witness);native=[]
        for opt in ('-O0','-O2'):
            run=native_run(path,case,wrong64,[witness],opt,'wrong64')
            if run['exit_code'] or run['stderr'] or int(run['stdout'])==expected:raise AssertionError(run)
            native.append(run)
        controls.append({'control':'defined_but_wrong_popcount64','request':request,'source':wrong64.read_text(),
                         'source_sha256':hashlib.sha256(wrong64.read_bytes()).hexdigest(),'analysis':compact_report(report),
                         'functional':query,'independent_expected':expected,'native':native})
        # A wrong union byte offset is still defined scalar C. Independently
        # refute it rather than trusting the normalizer's output as its own spec.
        case=next(c for c in cases() if c['name']=='union_signed_compare64')
        original_row=next(r for r in rows if r['case']['name']==case['name'])
        original_normalized=original_row['analysis']['normalization']['source']
        wrong_view=path/'wrong_union_view.c';wrong_view.write_text(original_normalized.replace(' >> 32',' >> 0'))
        if wrong_view.read_text()==original_normalized:raise AssertionError('Union offset mutation did not change the source')
        request,report,unused=isolated_analyze_case(case,database,wrong_view)
        if report['status']!='PROVED_DEFINED_CLANG_CFG_CALLS':raise AssertionError(report)
        query,unused=functional_proof(case,report['normalization']['source'])
        if query['status']!='REFUTED_FUNCTIONAL_QF_BV':raise AssertionError(query)
        witness=query['counterexample'];expected=independent_value(case,witness);native=[]
        for opt in ('-O0','-O2'):
            run=native_run(path,case,wrong_view,[witness],opt,'wrong_view')
            if run['exit_code'] or run['stderr'] or int(run['stdout'])==expected:raise AssertionError(run)
            native.append(run)
        controls.append({'control':'defined_but_wrong_union_view_offset','request':request,'source':wrong_view.read_text(),
                         'original_normalized_sha256':hashlib.sha256(original_normalized.encode()).hexdigest(),
                         'source_sha256':hashlib.sha256(wrong_view.read_bytes()).hexdigest(),'analysis':compact_report(report),
                         'functional':query,'independent_expected':expected,'native':native})
        uninitialized=path/'uninitialized_union.c';uninitialized.write_text((VENDOR/case['file']).read_text().replace('x.all = a;',''))
        request,report,unused=isolated_analyze_case(case,database,uninitialized)
        if report['status']!='UNKNOWN' or report.get('c_overflow_verified') or not report.get('normalization',{}).get('union_views'):raise AssertionError(report)
        controls.append({'control':'uninitialized_union_read','request':request,'source':uninitialized.read_text(),
                         'source_sha256':hashlib.sha256(uninitialized.read_bytes()).hexdigest(),'analysis':compact_report(report),
                         'native_executed':False,'reason':'UBSan does not provide a general uninitialized-read oracle'})
        # Signed low-byte left shift overflows before conversion to the return type.
        case=copy.deepcopy(next(c for c in cases() if c['name']=='bswap32'))
        case.update(name='signed_shift_mutation',types={'u':(32,True)},bounds={'u':[0,255]})
        unsafe=path/'unsafe_bswap.c';unsafe.write_text((VENDOR/case['file']).read_text().replace('uint32_t u','int32_t u'))
        request,report,elapsed=isolated_analyze_case(case,database,unsafe)
        if report['status']!='UNKNOWN' or report.get('c_overflow_verified'):raise AssertionError(report)
        normalized=path/'unsafe_bswap_normalized.c';normalized.write_text(report['normalization']['source']);native=[]
        for opt in ('-O0','-O2'):
            for tag,source in [('original',unsafe),('normalized',normalized)]:
                run=native_run(path,case,source,[{'u':128}],opt,tag)
                if run['exit_code']==0 or not any(t in run['stderr'] for t in ('left shift','cannot be represented')):raise AssertionError(run)
                native.append(run)
        controls.append({'control':'undefined_signed_shift','request':request,'source':unsafe.read_text(),
                         'source_sha256':hashlib.sha256(unsafe.read_bytes()).hexdigest(),'analysis':compact_report(report),'native':native})
        # The abort is an intended library effect, not an undefined operation.
        for case in [c for c in cases() if c['oracle'] in ('abs','negate')]:
            wide=copy.deepcopy(case);wide['bounds']={'a':[-2147483648,2147483647]}
            wide_request,wide_report,unused=isolated_analyze_case(wide,database)
            if wide_report['status']!='UNKNOWN' or wide_report.get('analysis_limit')!='external_call_frontier':raise AssertionError(wide_report)
            if int(wide_report.get('counterexample',{}).get('a',0))!=-2147483648:raise AssertionError(wide_report)
            native=[]
            for opt in ('-O0','-O2'):
                run=native_run(path,case,VENDOR/case['file'],[{'a':-2147483648}],opt,'abort')
                if run['exit_code']!=-signal.SIGABRT:raise AssertionError(run)
                native.append(run)
            controls.append({'control':'intended_external_abort','case':case['name'],'input':{'a':-2147483648},
                             'wide_domain_request':wide_request,'wide_domain_analysis':compact_report(wide_report),'native':native})
        if args.compare_baseline:
            run=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--functional-baseline','--database',str(database)],capture_output=True,text=True,timeout=60)
            if run.returncode:raise AssertionError(run.stderr)
            functional_baseline.append(json.loads(run.stdout))
            for name in ('clzsi2_positive','ctzsi2_positive'):
                command=[sys.executable,str(Path(__file__).resolve()),'--baseline-case',name,'--database',str(database)]
                run=subprocess.run(command,capture_output=True,text=True,timeout=60)
                if run.returncode:raise AssertionError(run.stderr)
                old=json.loads(run.stdout)
                case=copy.deepcopy(next(c for c in cases() if c['name']==name));case['bounds']={'a':[-2147483648,2147483647]}
                request,report,elapsed=isolated_analyze_case(case,database)
                if report['status']!='PROVED_DEFINED_CLANG_SCALAR_CFG':raise AssertionError(report)
                baseline.append({'case':name,'baseline':old,'current':{'request':request,'elapsed_seconds':elapsed,'report':compact_report(report)},
                                 'solver_timeout_unchanged_ms':5000})
        if any(path.glob('*.o')) or any(path.glob('*.d')):raise AssertionError('Compiler frontend wrote compilation-database output artifacts')
    verify_vendor()
    safety_proved=sum(row['analysis']['status'].startswith('PROVED_DEFINED_') for row in rows)
    functional_proved=sum(row['functional'] is not None and row['functional']['status'].startswith('PROVED_FUNCTIONAL_') for row in rows)
    result={'passed':True,'provenance':provenance,'case_count':len(rows),'upstream_functions':len({r['case']['function'] for r in rows}),
            'safety_proved_cases':safety_proved,'safety_unknown_cases':len(rows)-safety_proved,'functional_proved_cases':functional_proved,
            'functional_unknown_cases':[r['case']['name'] for r in rows if r['functional'] is not None and r['functional']['status']=='UNKNOWN'],
            'case_optimization_correspondences':correspondences,'native_comparisons':native_comparisons,'model_comparisons':model_comparisons,
            'expected_ubsan_failures':4,'intended_abort_runs':4,'wrong_algorithm_native_refutations':6,
            'baseline':baseline,'functional_baseline':functional_baseline,'functional_methods':{name:sum(r['functional'] is not None and r['functional']['status']==name for r in rows) for name in ('PROVED_FUNCTIONAL_QF_BV','PROVED_FUNCTIONAL_BV_CUTS')},'cases':rows,'controls':controls,'compiler':subprocess.check_output(['cc','--version'],text=True).splitlines()[0],
            'source_analysis_process_isolation':True,'source_analysis_retries':0,'scope':'pinned compiler-rt integer pilot; unsupported rows retained; native LP64; not representative whole-C/library coverage'}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cases','controls','baseline','functional_baseline')},indent=2),flush=True)
    return 0


if __name__=='__main__':raise SystemExit(main())
