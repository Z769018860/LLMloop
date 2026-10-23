"""Independent entrypoint for supported single-while C source files."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .c_frontend import translate_file
from .core import AnalysisError
from .cli import main as json_main
def main(argv:list[str]|None=None)->int:
    p=argparse.ArgumentParser(prog="llmloop-c")
    p.add_argument("file",type=Path)
    p.add_argument("--function")
    p.add_argument("--dump-ir",type=Path)
    p.add_argument("--input",action="append",default=[])
    p.add_argument("--check-range")
    p.add_argument("--output",type=Path)
    args=p.parse_args(argv)
    try:
        ir=translate_file(args.file,args.function)
        path=args.dump_ir or args.file.with_suffix(".llmloop.json")
        path.write_text(json.dumps(ir,indent=2)+"\n",encoding="utf-8")
        argv2=["analyze",str(path)]
        for inp in args.input: argv2.extend(["--input",inp])
        if args.check_range: argv2.extend(["--check-range",args.check_range])
        if args.output: argv2.extend(["--output",str(args.output)])
        return json_main(argv2)
    except (OSError,AnalysisError,ValueError) as exc:
        print(json.dumps({"status":"UNKNOWN","error":str(exc)}),file=sys.stderr)
        return 2
if __name__=="__main__": raise SystemExit(main())
