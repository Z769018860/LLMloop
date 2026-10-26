"""Clang-owned C semantics ingestion. Frontend readiness is never a proof.

Compiler commands use argv (never a shell), private outputs, bounded time/output,
and an explicit flag subset. The host still owns filesystem/process isolation.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from .smt_spath import SMTGraphError


def digest(data):return hashlib.sha256(data).hexdigest()


def compiler_path(value=None):
    if value is not None and (not isinstance(value,str) or not value or '\0' in value):raise SMTGraphError('clang executable must be a nonempty path/name')
    candidates=[value] if value else [os.environ.get('LLMLOOP_CLANG'),'clang']+['clang-'+str(v) for v in range(22,13,-1)]
    for candidate in candidates:
        if not candidate:continue
        found=shutil.which(candidate)
        if found:return str(Path(found).resolve())
    raise SMTGraphError('Clang unavailable: install clang or set LLMLOOP_CLANG/clang.executable')


def compilation_entry(database,source,index=None):
    path=Path(database).resolve()
    if path.is_dir():path=path/'compile_commands.json'
    if not path.is_file() or path.stat().st_size>4*1024*1024:raise SMTGraphError('Compilation database missing or exceeds 4 MiB')
    try:entries=json.loads(path.read_text())
    except (OSError,ValueError) as exc:raise SMTGraphError('Invalid compilation database: '+str(exc)) from exc
    if not isinstance(entries,list):raise SMTGraphError('Compilation database must be a list')
    matches=[]
    for entry in entries:
        if not isinstance(entry,dict) or not isinstance(entry.get('directory'),str) or not isinstance(entry.get('file'),str):raise SMTGraphError('Invalid compilation command object')
        directory=Path(entry['directory'])
        if not directory.is_absolute():directory=path.parent/directory
        directory=directory.resolve()
        if (directory/entry['file']).resolve()==source:matches.append((entry,directory))
    if not matches:raise SMTGraphError('No compilation command for source_file')
    if index is None:
        if len(matches)!=1:raise SMTGraphError('Ambiguous compilation commands: select clang.command_index')
        index=0
    if type(index) is not int or not 0<=index<len(matches):raise SMTGraphError('Invalid clang.command_index')
    entry,directory=matches[index]
    if 'arguments' in entry:argv=entry['arguments']
    elif isinstance(entry.get('command'),str):
        try:argv=shlex.split(entry['command'],posix=True)
        except ValueError as exc:raise SMTGraphError('Invalid compilation command quoting') from exc
    else:raise SMTGraphError('Compilation command needs arguments or command')
    if not isinstance(argv,list) or not argv or not all(isinstance(a,str) and a and '\0' not in a for a in argv):raise SMTGraphError('Invalid compilation argv')
    return argv[1:],directory,{'path':str(path),'sha256':digest(path.read_bytes()),'command_index':index,'original_arguments':argv}


def frontend_flags(arguments,source,directory):
    """Preserve admitted semantic flags; refuse unknown flags rather than guess."""
    if not isinstance(arguments,list) or len(arguments)>256 or any(not isinstance(a,str) or not a or len(a)>8192 or '\0' in a for a in arguments):raise SMTGraphError('clang.args must be at most 256 nonempty string arguments')
    out=[];ignored=[];i=0
    paired={'-I','-isystem','-iquote','-idirafter','-include','-imacros','-isysroot','--sysroot','-D','-U','-target','--target','-std'}
    discarded={'-o','-MF','-MT','-MQ'}
    standalone={'-nostdinc','-nobuiltininc','-ffreestanding','-fno-builtin','-funsigned-char','-fsigned-char','-fshort-wchar','-fshort-enums','-m32','-m64','-mms-bitfields','-fms-extensions','-fms-compatibility','-fno-ms-extensions','-fPIC','-fpic','-fPIE','-fpie','-fomit-frame-pointer','-fno-omit-frame-pointer'}
    while i<len(arguments):
        a=arguments[i];i+=1
        if a.startswith('@') or a in ('-Xclang','-Xpreprocessor','-Xassembler','-Xlinker','-load','-plugin') or a.startswith(('-fplugin','--config','-Wp,','-Wl,','-Wa,','-save-temps')):raise SMTGraphError('Compiler action/plugin/response flag unsupported: '+a)
        if a in paired|discarded|{'-x'}:
            if i==len(arguments):raise SMTGraphError('Missing compiler option operand: '+a)
            value=arguments[i];i+=1
            if a=='-x':
                if value!='c':raise SMTGraphError('Clang adapter currently accepts C translation units only')
                ignored.extend([a,value])
            elif a in discarded:ignored.extend([a,value])
            else:out.extend([a,value])
        elif a in ('-c','-S','-emit-llvm','-fsyntax-only','-MD','-MMD','-MP','-pipe'):ignored.append(a)
        elif any(a.startswith(p) and a!=p for p in ('-MF','-MT','-MQ')):ignored.append(a)
        elif re.fullmatch(r'-O[0123sgz]|-g(?:[0123]|line-tables-only)?',a):out.append(a)
        elif a in standalone or a.startswith(('-std=','--target=','--sysroot=','-march=','-mcpu=','-mtune=','-D','-U','-I')) or a.startswith('-W'):out.append(a)
        elif not a.startswith('-') and (directory/a).resolve()==source:ignored.append(a)
        else:raise SMTGraphError('Unsupported compiler argument (not silently dropped): '+a)
    return out,ignored


def layouts_from_dump(text):
    records=[]
    for block in text.split('*** Dumping AST Record Layout')[1:]:
        header=re.search(r'^\s*0\s*\|\s*((?:struct|union) .+)\s*$',block,re.M)
        size=re.search(r'\[sizeof=(\d+), align=(\d+)\]',block)
        if not header or not size:continue
        members=[]
        for line in block[header.end():].splitlines():
            m=re.match(r'\s*(\d+)(?::(\d+)-(\d+))?\s*\|\s+(.*)',line)
            if m:members.append({'offset_bytes':int(m[1]),'declaration':m[4].strip(),**({'bit_range':[int(m[2]),int(m[3])]} if m[2] else {})})
        records.append({'name':header[1].strip(),'size_bytes':int(size[1]),'alignment_bytes':int(size[2]),'members':members})
    return records


def function_declarators(text,names):
    """Read original parameter declarators from Clang's own AST pretty-printer.

    JSON ParmVarDecl types have already lost array/static/VLA spelling and
    evaluation. Only complete top-level definition headers are admitted here.
    Strings/comments are lexically replaced before scanning braces, never parsed
    as source tokens or executed. Unrecognized headers fail closed.
    """
    clean=re.sub(r'/\*[\s\S]*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', ' ',text)
    depth=0;header=[];result={}
    for char in clean:
        if depth==0:
            if char=='{':
                prefix=''.join(header);matches=[name for name in names if re.search(r'\b'+re.escape(name)+r'\s*\(',prefix)]
                if matches:
                    if len(matches)!=1 or prefix.count('(')!=prefix.count(')'):raise SMTGraphError('Unsupported embedded function parameter declarator')
                    name=matches[0]
                    if name in result:raise SMTGraphError('Ambiguous printed function declarator')
                    result[name]=prefix.strip()
                depth=1;header=[]
            elif char==';':header=[]
            else:header.append(char)
        elif char=='{':depth+=1
        elif char=='}':depth-=1
    if set(result)!=set(names):raise SMTGraphError('Clang original function declarators missing/ambiguous')
    return result


def llvm_cfg(text):
    functions=[];current=None;block=None
    for line in text.splitlines():
        if line.startswith('define '):
            m=re.search(r'@("[^"]+"|[-\w.$]+)\(',line)
            if not m:raise SMTGraphError('Unsupported LLVM function spelling')
            current={'name':m[1].strip('"'),'blocks':[]};functions.append(current);block=None
        elif current is not None and line=='}':current=None;block=None
        elif current is not None:
            label=re.match(r'^("[^"]+"|[-\w.$]+):',line)
            if label:block={'name':label[1].strip('"'),'successors':[]};current['blocks'].append(block)
            elif line.strip() and not line.lstrip().startswith(';'):
                if block is None:block={'name':'entry','successors':[]};current['blocks'].append(block)
                block['successors']+=re.findall(r'label %((?:"[^"]+")|[-\w.$]+)',line)
    for fn in functions:
        names={b['name'] for b in fn['blocks']}
        for block in fn['blocks']:
            block['successors']=list(dict.fromkeys(v.strip('"') for v in block['successors']))
            if set(block['successors'])-names:raise SMTGraphError('LLVM CFG contains unresolved block references')
    return functions


class ClangAdapter:
    def __init__(self,source=None,source_file=None,function=None,options=None):
        self.source=source;self.source_file=source_file;self.function=function;self.options={} if options is None else options
        self.commands=[];self.compiler=None

    def run(self,argv,directory,stage,workspace,timeout):
        out=workspace/(stage+'.stdout');err=workspace/(stage+'.stderr')
        try:
            with out.open('wb') as stdout,err.open('wb') as stderr:
                result=subprocess.run(argv,cwd=directory,stdout=stdout,stderr=stderr,timeout=timeout,check=False)
        except subprocess.TimeoutExpired as exc:
            self.commands.append({'stage':stage,'argv':argv,'directory':str(directory),'exit_code':None,'timed_out':True})
            raise SMTGraphError('Clang '+stage+' timed out; no frontend/proof certificate') from exc
        except OSError as exc:raise SMTGraphError('Clang launch failed: '+str(exc)) from exc
        if out.stat().st_size>16*1024*1024 or err.stat().st_size>1024*1024:raise SMTGraphError('Clang output budget exceeded')
        output=out.read_text(errors='replace');diagnostics=err.read_text(errors='replace')
        self.commands.append({'stage':stage,'argv':argv,'directory':str(directory),'exit_code':result.returncode,'diagnostics':diagnostics,'stdout_sha256':digest(output.encode())})
        if result.returncode:raise SMTGraphError('Clang '+stage+' failed: '+diagnostics[:12000])
        return output

    def report(self):
        base={'status':'UNKNOWN','frontend':'clang','analysis_status':'NOT_PROVED','c_overflow_verified':False,'memory_safety_verified':False,'termination_proved':False,'unbounded_summary':False,'commands':self.commands}
        try:
            cfg=self.options
            allowed={'executable','args','compilation_database','command_index','working_directory','target','standard','timeout','include_ast','include_dependencies','sanitize'}
            if not isinstance(cfg,dict) or set(cfg)-allowed:raise SMTGraphError('Invalid clang options')
            timeout=cfg.get('timeout',30)
            if type(timeout) is not int or not 1<=timeout<=60:raise SMTGraphError('Clang timeout must be 1..60 seconds per stage')
            for key in ('include_ast','include_dependencies','sanitize'):
                if key in cfg and type(cfg[key]) is not bool:raise SMTGraphError('clang.'+key+' must be Boolean')
            if self.function is not None and (not isinstance(self.function,str) or not self.function):raise SMTGraphError('function must be a nonempty name')
            if (self.source is None)==(self.source_file is None):raise SMTGraphError('Provide exactly one source or source_file')
            if self.source is not None and (not isinstance(self.source,str) or len(self.source.encode())>1024*1024 or '\0' in self.source):raise SMTGraphError('Inline C source must be a string up to 1 MiB without NUL')
            for key in ('working_directory','compilation_database','target','standard'):
                if key in cfg and (not isinstance(cfg[key],str) or not cfg[key] or '\0' in cfg[key]):raise SMTGraphError('clang.'+key+' must be a nonempty string')
            executable=compiler_path(cfg.get('executable'))
            with tempfile.TemporaryDirectory(prefix='llmloop-clang-') as temp:
                workspace=Path(temp)
                if self.source_file is not None:
                    if not isinstance(self.source_file,str):raise SMTGraphError('source_file must be a path string')
                    path=Path(self.source_file).resolve()
                    if not path.is_file() or path.stat().st_size>1024*1024:raise SMTGraphError('C source_file missing or exceeds 1 MiB')
                else:path=workspace/'input.c';path.write_text(self.source)
                before=path.read_bytes();directory=Path(cfg.get('working_directory',str(path.parent if self.source_file else Path.cwd()))).resolve()
                database=None;args=[]
                if 'compilation_database' in cfg:
                    if self.source_file is None:raise SMTGraphError('Compilation database requires source_file')
                    if 'working_directory' in cfg:raise SMTGraphError('Compilation database supplies working_directory')
                    args,directory,database=compilation_entry(cfg['compilation_database'],path,cfg.get('command_index'))
                elif 'command_index' in cfg:raise SMTGraphError('command_index requires compilation_database')
                if not directory.is_dir():raise SMTGraphError('Compiler working directory missing')
                supplied=cfg.get('args',[])
                if not isinstance(supplied,list):raise SMTGraphError('clang.args must be a list')
                flags,ignored=frontend_flags(args+supplied,path,directory)
                if 'standard' in cfg:
                    if not re.fullmatch(r'(?:c|gnu)(?:89|90|99|11|17|18|2x|23)',cfg['standard']):raise SMTGraphError('Unsupported C standard name')
                    flags+=['-std='+cfg['standard']]
                elif not any(a.startswith('-std') for a in flags):flags+=['-std=c11']
                if 'target' in cfg:
                    if not re.fullmatch(r'[A-Za-z0-9_.+-]+',cfg['target']):raise SMTGraphError('Invalid target triple')
                    flags+=['--target='+cfg['target']]
                version=self.run([executable,'--version'],directory,'version',workspace,timeout)
                if not re.search(r'clang version \d+',version):raise SMTGraphError('Selected executable is not a Clang compiler')
                self.compiler={'executable':executable,'version':version.strip()}
                sanitize=cfg.get('sanitize',True)
                ir_flags=['-fsanitize=undefined','-fno-sanitize-recover=all'] if sanitize else []
                optimization=[] if any(re.fullmatch(r'-O[0123sgz]',a) for a in flags) else ['-O0']
                debug=[] if any(a.startswith('-g') for a in flags) else ['-gline-tables-only']
                quote_fallback=['-iquote',str(directory)] if self.source_file is None else []
                common=[executable,*flags,*optimization,*debug,*ir_flags,'-x','c','-fno-color-diagnostics',*quote_fallback]
                raw=self.run([*common,'-fsyntax-only','-Xclang','-ast-dump=json',str(path)],directory,'ast',workspace,timeout)
                try:ast=json.loads(raw)
                except (ValueError,RecursionError) as exc:raise SMTGraphError('Invalid/over-deep Clang JSON AST') from exc
                nodes=[ast];count=0;definitions=[];typedefs=[];records=[]
                while nodes:
                    node=nodes.pop();count+=1
                    if count>250000:raise SMTGraphError('Clang AST node budget exceeded')
                    if node.get('kind')=='TypedefDecl':typedefs.append({'name':node.get('name'),'type':node.get('type',{}),'location':node.get('loc'),'attributes':[v.get('kind') for v in node.get('inner',[]) if v.get('kind','').endswith('Attr')]})
                    if node.get('kind')=='RecordDecl' and node.get('completeDefinition'):records.append(node)
                    if node.get('kind')=='FunctionDecl' and any(child.get('kind')=='CompoundStmt' for child in node.get('inner',[])):definitions.append(node)
                    nodes.extend(reversed(node.get('inner',[])))
                selected=[n for n in definitions if self.function is None or n.get('name')==self.function]
                if self.function is not None and len(selected)!=1:raise SMTGraphError('Select one defined Clang function')
                if len(selected)>128:raise SMTGraphError('Clang function export budget is 128; select a function')
                layout_text=self.run([*common,'-fsyntax-only','-Xclang','-fdump-record-layouts-complete',str(path)],directory,'layouts',workspace,timeout)
                ir_file=workspace/'module.ll'
                self.run([*common,'-fno-discard-value-names','-S','-emit-llvm',str(path),'-o',str(ir_file)],directory,'llvm',workspace,timeout)
                if not ir_file.is_file() or ir_file.stat().st_size>16*1024*1024:raise SMTGraphError('LLVM IR missing or exceeds output budget')
                ir=ir_file.read_text();triple=re.search(r'^target triple = "([^"]+)"',ir,re.M);layout=re.search(r'^target datalayout = "([^"]+)"',ir,re.M)
                if not triple or not layout:raise SMTGraphError('LLVM target metadata missing')
                if path.read_bytes()!=before:raise SMTGraphError('Source changed during Clang ingestion')
                functions=[{'name':n.get('name'),'linkage_name':n.get('mangledName',n.get('name')),'type':n.get('type'),'location':n.get('loc'),'range':n.get('range'),**({'ast':n} if cfg.get('include_ast',True) else {})} for n in selected]
                dependencies={}
                if cfg.get('include_dependencies'):
                    if not cfg.get('include_ast',True):raise SMTGraphError('Dependency export requires include_ast=true')
                    if len(definitions)>128 or len(records)>128:raise SMTGraphError('Dependency definition export budget exceeded')
                    printed=self.run([*common,'-fsyntax-only','-Xclang','-ast-print',str(path)],directory,'declarators',workspace,timeout)
                    declarators=function_declarators(printed,[n['name'] for n in definitions])
                    if path.read_bytes()!=before:raise SMTGraphError('Source changed during Clang declaration ingestion')
                    dependencies={'dependencies':{'functions':definitions,'records':records,'function_declarators':declarators}}
                return {**base,'status':'CLANG_FRONTEND_READY','source_compiles':True,'compiler':self.compiler,'source':{'path':str(path) if self.source_file else '<inline>','sha256':digest(before)},'compilation_database':database,'effective_flags':[*flags,*optimization,*debug,*ir_flags],'ignored_build_flags':ignored,'target':{'triple':triple[1],'data_layout':layout[1]},'functions':functions,**dependencies,'typedefs':typedefs,'ast_nodes':count,'record_layouts':layouts_from_dump(layout_text),'record_layout_dump':layout_text,'llvm_ir':ir,'llvm_ir_sha256':digest(ir.encode()),'llvm_cfg':llvm_cfg(ir),'ubsan_instrumentation_requested':sanitize,'proof_boundary':'Clang semantics/AST/IR ingestion only; no LLMloop proof or KLEE execution; LLVM blocks include sanitizer branches and are not source MEMS counts','input_consistency':'main source checked unchanged; included headers/environment must remain stable across compiler stages'}
        except (SMTGraphError,OSError,ValueError,TypeError,RecursionError) as exc:return {**base,'reason':str(exc),**({'compiler':self.compiler} if self.compiler else {})}
