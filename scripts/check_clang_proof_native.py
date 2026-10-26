"""Original C versus normalized C versus independently checked scalar model."""
import subprocess
import tempfile
from pathlib import Path
from llmloop.api import analyze_request
from llmloop.clang_adapter import compiler_path
from llmloop.typed_cfg_heap import TypedCFGHeap
from llmloop.typed_nested import TypedCNested
from build_clang_proof_cases import ROOT,NARROW,CONTROL,SUM,MOD,NEST,SHADOW,LAZY,FAULTS


def main():
    clang=compiler_path();print(subprocess.run([clang,'--version'],check=True,capture_output=True,text=True).stdout.splitlines()[0],flush=True)
    specs=[('narrow',NARROW,'entry',{'n':[254,257]},[{'n':v} for v in range(254,258)],'cfg',{},{}),
           ('control',CONTROL,'entry',{'n':[0,4]},[{'n':v} for v in range(5)],'cfg',{'max_steps':256},{}),
           ('shadow',SHADOW,'entry',{'n':[0,3]},[{'n':v} for v in range(4)],'cfg',{},{}),
           ('lazy',LAZY,'entry',{'n':[0,4]},[{'n':v} for v in range(5)],'cfg',{},{}),
           ('million',SUM,'entry',{'n':[0,1000000]},[{'n':v} for v in [0,1,7,1000000]],'nested',{},{}),
           ('modular',MOD,'entry',{'n':[0,1000000]},[{'n':v} for v in [0,255,256,1000000]],'nested',{'loop_summaries':{'i':{'x':'i%256'}}},{}),
           ('nested',NEST,'entry',{'n':[0,1000],'m':[0,1000]},[{'n':n,'m':m} for n,m in [(0,3),(3,0),(2,7),(1000,1000)]],'nested',{},{}),
           ('project',None,'clang_count',{'n':[0,1000000]},[{'n':v} for v in [0,1,7,1000000]],'nested',{}, {'compilation_database':str(ROOT/'examples/clang_proof_project')})]
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)
        for name,source,root,bounds,points,backend,extra,options in specs:
            project=ROOT/'examples/clang_proof_project/count.c'
            request={'frontend':'clang_proof','function':root,'clang':{'executable':clang,**options},'proof':{'backend':backend,'parameter_bounds':bounds,'inputs':points[-1],**extra}}
            request['source' if source is not None else 'source_file']=source if source is not None else str(project)
            r=analyze_request(request);assert r['status'].startswith('PROVED_DEFINED_CLANG_SCALAR'),r
            normalized=r['normalization']['source'];abi=r['normalization']['abi'];char_signed=r['normalization']['char_signed']
            if backend=='cfg':engine=TypedCFGHeap(normalized,function=root,parameter_bounds=bounds,abi=abi,char_signed=char_signed,max_steps=extra.get('max_steps',128))
            else:engine=TypedCNested(normalized,extra.get('loop_summaries','auto'),function=root,parameter_bounds=bounds,abi=abi,char_signed=char_signed)
            expected=[engine.report(p)['evaluation']['value'] for p in points]
            assert expected[-1]==r['evaluation']['value']
            harness='\n#include <stdio.h>\nint main(void){'+''.join('printf("%lld\\n",(long long)'+root+'('+','.join(str(p[k]) for k in bounds)+'));' for p in points)+'return 0;}'
            original=path/(name+'.c');original.write_text((source if source is not None else project.read_text())+harness)
            norm=path/(name+'_normalized.c');norm.write_text(normalized+harness)
            for opt in ['-O0','-O2']:
                values=[]
                for tag,code in [('original',original),('normalized',norm)]:
                    exe=path/(name+tag+opt);flags=['-DSTEP=5','-I'+str(project.parent)] if source is None and tag=='original' else []
                    subprocess.run(['cc','-std=c11',opt,'-fsanitize=undefined','-fno-sanitize-recover=undefined',*flags,str(code),'-o',str(exe)],check=True,capture_output=True)
                    values.append([int(v) for v in subprocess.run([str(exe)],check=True,capture_output=True,text=True).stdout.splitlines()])
                assert values[0]==values[1]==expected,(name,opt,values,expected)
                print(f'{name} original C / normalized C / proved model {opt}: {len(points)}/{len(points)} matched',flush=True)
        for name,source,bounds,diagnostic in FAULTS:
            r=analyze_request({'source':source,'frontend':'clang_proof','function':'entry','clang':{'executable':clang},'proof':{'parameter_bounds':bounds}})
            assert r['status']=='UNKNOWN',r
            code=path/(name+'.c');code.write_text(source+'\nint main(void){return entry(1);}')
            exe=path/name;subprocess.run(['cc','-std=c11','-O0','-fsanitize=undefined','-fno-sanitize-recover=undefined',str(code),'-o',str(exe)],check=True,capture_output=True)
            outcome=subprocess.run([str(exe)],capture_output=True,text=True)
            assert outcome.returncode!=0 and diagnostic in outcome.stderr,(name,outcome.stderr)
        print(f'Clang scalar proof rejection / intentional UBSan fault correspondences: {len(FAULTS)}/{len(FAULTS)} matched')


if __name__=='__main__':main()
