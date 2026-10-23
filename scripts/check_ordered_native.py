"""Compare ordered scalar IR with native C and UBSan at 32-bit int width.

Requires POSIX cc with -fsanitize=undefined support. Finite regression evidence,
not a universal C equivalence proof. Run after installation.
"""
from pathlib import Path
import subprocess
import tempfile
from llmloop.ordered_c import translate_ordered_c
from llmloop.smt_spath import SMTPathGraph, SMTGraphError

CASES = [
    # Cancellation is unit-tested symbolically: GCC can fold (x+1)-1 before UBSan.
    ('x=x+1;x=0;',True),
    ('x*=2;',True),
    ('if(0 && x+1){x=1;}else{x=2;}',False),
    ('if(1 || x+1){x=3;}',False),
    ('x=1 ? 4 : x+1;',False),
    ('x=0 ? x+1 : 5;',False),
]


def main():
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for k,(body,overflow) in enumerate(CASES):
            source='int f(void){int x=2147483647;int i=0;while(i<1){'+body+'i++;}return x;}'
            graph=SMTPathGraph(translate_ordered_c(source))
            try:
                predicted=graph.concrete({})['final_state']['x'];ir_overflow=False
            except SMTGraphError:
                predicted=None;ir_overflow=True
            unit=path/f'case{k}.c';exe=path/f'case{k}'
            unit.write_text('#include <stdio.h>\n'+source+'\nint main(void){printf("%d",f());return 0;}\n')
            subprocess.run(['cc','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(unit),'-o',str(exe)],check=True,capture_output=True)
            native=subprocess.run([str(exe)],capture_output=True,text=True)
            native_overflow=native.returncode!=0 and 'overflow' in native.stderr
            if native_overflow!=overflow or ir_overflow!=overflow:
                raise AssertionError((k,overflow,ir_overflow,native.returncode,native.stderr))
            if not overflow and int(native.stdout)!=predicted:raise AssertionError((k,native.stdout,predicted))
    print(f'Ordered C / native UBSan checks: {len(CASES)}/{len(CASES)} passed')


if __name__=='__main__':main()
