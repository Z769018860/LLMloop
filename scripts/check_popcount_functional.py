"""Prove the pinned original 64-bit popcount with an independently checked spec."""
import argparse
import json
from pathlib import Path
import tempfile

from llmloop.llvm_benchmarks import cases,verify_vendor,compilation_database,analyze_case,functional_proof


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--strategy',choices=['auto','direct'],default='auto')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args(argv);provenance=verify_vendor()
    case=next(c for c in cases() if c['name']=='popcount64')
    with tempfile.TemporaryDirectory(prefix='llmloop-popcount-proof-') as directory:
        request,report,elapsed=analyze_case(case,compilation_database(directory))
        functional=None
        if report['status']=='PROVED_DEFINED_CLANG_SCALAR_CFG':
            functional,unused=functional_proof(case,report['normalization']['source'],strategy=args.strategy)
        result={'provenance':provenance,'request':request,'source_safety_status':report['status'],
                'source_safety_elapsed_seconds':elapsed,'source_certificate':{k:v for k,v in report.items() if k!='clang_frontend'},
                'source_compiler':{k:report.get('clang_frontend',{})[k] for k in ('status','compiler','source','target','effective_flags','compilation_database') if k in report.get('clang_frontend',{})},
                'functional':functional,'proof_boundary':'typed source safety and independent functional certificate; trusted Clang/source executors/composition/translation; no complete C/LLVM claim'}
        if args.output:
            args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'source_safety_status':report['status'],'functional_status':functional['status'] if functional else None,
                          'functional_elapsed_seconds':functional.get('elapsed_seconds') if functional else None,'output':str(args.output) if args.output else None}))
        return 0 if functional and functional['status'].startswith('PROVED_FUNCTIONAL_') else 2


if __name__=='__main__':raise SystemExit(main())
