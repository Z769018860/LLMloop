"""Compare original eager-call C with certified expression expansion."""
import ctypes
from pathlib import Path
import subprocess
import tempfile
from llmloop.typed_cfg_calls import TypedCFGCalls
from build_eager_call_cases import FACT,CONTROL,NARROW,BAD

def main():
    specs=[('recursive',FACT,'recursive_expression',range(5),{'allow_recursion':True,'max_call_depth':4}),
           ('control',CONTROL,'entry',range(4),{}),('narrow',NARROW,'entry',range(254,258),{})]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,source,root,values,opts in specs:
            e=TypedCFGCalls(source,function=root,parameter_bounds={'n':[min(values),max(values)]},max_steps=512,**opts)
            assert e.report()['status']=='PROVED_DEFINED_TYPED_C_CFG_CALLS',e.report()
            for optimization in ['-O0','-O2']:
                code=path/(name+optimization+'.c');code.write_text(source)
                so=code.with_suffix('.so')
                subprocess.run(['cc','-std=c11',optimization,'-shared','-fPIC','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(code),'-o',str(so)],check=True,capture_output=True)
                fn=getattr(ctypes.CDLL(str(so)),root);fn.argtypes=[ctypes.c_int];fn.restype=ctypes.c_int
                for n in values:assert fn(n)==e.evaluate_return({'n':n}).as_long(),(name,n)
                print(f'{name} original C UBSan {optimization}: {len(values)}/{len(values)} matched',flush=True)
        assert TypedCFGCalls(BAD,function='entry').report()['status']=='UNKNOWN'
        code=path/'overflow.c';code.write_text(BAD+'\nint main(void){return entry();}')
        binary=path/'overflow'
        subprocess.run(['cc','-std=c11','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(code),'-o',str(binary)],check=True,capture_output=True)
        outcome=subprocess.run([str(binary)],capture_output=True,text=True)
        assert outcome.returncode!=0 and 'signed integer overflow' in outcome.stderr,outcome.stderr
        print('Intentional eager-call UBSan fault correspondence: 1/1 matched')

if __name__=='__main__':main()
