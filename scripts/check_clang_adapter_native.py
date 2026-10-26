"""Clang-exported LLVM IR versus original C; readiness is not safety proof."""
from pathlib import Path
import os
import subprocess
import tempfile
from llmloop.clang_adapter import ClangAdapter,compiler_path
from build_clang_cases import ROOT,SOURCES,FAULTS


def main():
    clang=compiler_path();print(subprocess.run([clang,'--version'],capture_output=True,text=True,check=True).stdout.splitlines()[0],flush=True)
    specs=[(name,source,'entry',list(range(254,258)) if name=='narrow' else list(range(6)) if name=='scalar' else list(range(5)),{}) for name,source in SOURCES.items()]
    specs.append(('project',None,'clang_demo',list(range(5)),{'compilation_database':str(ROOT/'examples/clang_project/compile_commands.json')}))
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,source,root,values,options in specs:
            project=ROOT/'examples/clang_project/demo.c'
            adapter=ClangAdapter(source=source,source_file=str(project) if source is None else None,function=root,options={'executable':clang,'include_ast':False,**options})
            r=adapter.report();assert r['status']=='CLANG_FRONTEND_READY',r
            assert not r['c_overflow_verified'] and r['analysis_status']=='NOT_PROVED'
            ir=path/(name+'.ll');ir.write_text(r['llvm_ir']);obj=path/(name+'.o')
            subprocess.run([clang,'-c',str(ir),'-o',str(obj)],check=True,capture_output=True)
            harness='\n#include <stdio.h>\nint '+root+'(int);int main(void){'+''.join(f'printf("%d\\n",{root}({v}));' for v in values)+'return 0;}'
            main_c=path/(name+'_main.c');main_c.write_text(harness);ir_exe=path/(name+'_ir')
            subprocess.run(['cc','-fsanitize=undefined',str(obj),str(main_c),'-o',str(ir_exe)],check=True,capture_output=True)
            ir_values=subprocess.run([str(ir_exe)],check=True,capture_output=True,text=True).stdout
            original=path/(name+'.c');original.write_text((source if source is not None else project.read_text())+harness)
            for opt in ['-O0','-O2']:
                native=path/(name+opt);extra=['-DBASE=7','-I'+str(project.parent)] if source is None else []
                subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',*extra,str(original),'-o',str(native)],check=True,capture_output=True)
                original_values=subprocess.run([str(native)],check=True,capture_output=True,text=True).stdout
                assert original_values==ir_values,(name,opt,original_values,ir_values)
                print(f'{name} original C {opt} vs Clang LLVM IR UBSan: {len(values)}/{len(values)} matched',flush=True)
        env=dict(os.environ);env['UBSAN_OPTIONS']='halt_on_error=1'
        for name,source,value,diagnostic in FAULTS:
            r=ClangAdapter(source=source,function='entry',options={'executable':clang,'include_ast':False}).report()
            assert r['status']=='CLANG_FRONTEND_READY' and not r['c_overflow_verified'],r
            ir=path/(name+'.ll');ir.write_text(r['llvm_ir']);obj=path/(name+'.o');main=path/(name+'_main.c');main.write_text(f'int entry(int);int main(void){{return entry({value});}}');exe=path/name
            subprocess.run([clang,'-c',str(ir),'-o',str(obj)],check=True,capture_output=True)
            subprocess.run(['cc','-fsanitize=undefined',str(obj),str(main),'-o',str(exe)],check=True,capture_output=True)
            result=subprocess.run([str(exe)],capture_output=True,text=True,env=env)
            assert result.returncode!=0 and diagnostic in result.stderr,(name,result.stderr)
        print(f'Clang IR intentional UBSan fault correspondences (ingestion never certified safe): {len(FAULTS)}/{len(FAULTS)} matched')


if __name__=='__main__':main()
