"""Fail-closed scalar Clang AST normalization into existing typed proof engines.

Clang and this structural normalizer are trusted frontend components, not a
machine-checked compiler equivalence theorem. Every emitted operation is retained;
unsupported source constructs are refused, never replaced by a sample result.
"""
from collections import Counter
import hashlib
import json
import re
from .clang_adapter import ClangAdapter
from .smt_spath import SMTGraphError


INTEGER={'_Bool','char','signed char','unsigned char','short','short int','signed short','signed short int','unsigned short','unsigned short int','int','signed','signed int','unsigned','unsigned int','long','long int','signed long','signed long int','unsigned long','unsigned long int','long long','long long int','signed long long','signed long long int','unsigned long long','unsigned long long int'}


def nodes(root):
    pending=[root]
    while pending:
        n=pending.pop();yield n;pending.extend(reversed(n.get('inner',[])))


class ScalarNormalizer:
    def __init__(self,frontend):
        if len(frontend['functions'])!=1 or 'ast' not in frontend['functions'][0]:raise SMTGraphError('Clang proof requires one selected function and include_ast=true')
        self.frontend=frontend;self.root=frontend['functions'][0]['ast'];self.names={};self.labels={};self.renamed=[];self.operations=0
        declarations=[n for n in nodes(self.root) if n.get('kind') in ('ParmVarDecl','VarDecl')]
        counts=Counter(n.get('name') for n in declarations);self.used={n.get('name') for n in nodes(self.root) if n.get('name')};self.serial=0
        for n in declarations:
            name=n.get('name')
            if not name or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name):raise SMTGraphError('Named ASCII scalar variables required')
            emitted=name if n['kind']=='ParmVarDecl' or counts[name]==1 else self.fresh('local')
            self.names[n['id']]=emitted
            if emitted!=name:self.renamed.append({'source':name,'normalized':emitted})
        for n in nodes(self.root):
            if n.get('kind')=='LabelStmt':self.labels[n['declId']]=self.fresh('label')
        self.aliases={}
        for n in frontend.get('typedefs',[]):self.aliases.setdefault(n['name'],set()).add(n['type'].get('desugaredQualType',n['type'].get('qualType','')))

    def fresh(self,tag):
        while True:
            self.serial+=1;name='__clang_'+tag+'_'+str(self.serial)
            if name not in self.used:self.used.add(name);return name

    def type(self,t):
        text=t.get('desugaredQualType',t.get('qualType','')) if isinstance(t,dict) else t
        if not isinstance(text,str):raise SMTGraphError('Clang scalar type missing')
        text=' '.join(text.split());seen=set()
        while text not in INTEGER:
            if text.startswith('const '):text=text[6:];continue
            if text in seen or text not in self.aliases or len(self.aliases[text])!=1:raise SMTGraphError('Unsupported/ambiguous Clang scalar type: '+text)
            seen.add(text);text=next(iter(self.aliases[text]))
        return text

    def expr(self,n):
        self.operations+=1
        if self.operations>4096:raise SMTGraphError('Clang normalization expression budget exceeded')
        kind=n.get('kind');children=n.get('inner',[])
        if kind in ('ParenExpr','ConstantExpr') and len(children)==1:return '('+self.expr(children[0])+')'
        if kind in ('ImplicitCastExpr','CStyleCastExpr') and len(children)==1:
            if kind=='ImplicitCastExpr' and n.get('castKind') not in ('LValueToRValue','NoOp','IntegralCast','IntegralToBoolean'):raise SMTGraphError('Unsupported Clang implicit cast: '+str(n.get('castKind')))
            target=self.type(n['type'])
            if kind=='ImplicitCastExpr' and n.get('castKind') in ('LValueToRValue','NoOp'):return self.expr(children[0])
            return '(('+target+')('+self.expr(children[0])+'))'
        if kind=='DeclRefExpr':
            ref=n.get('referencedDecl',{});key=ref.get('id')
            if key not in self.names:raise SMTGraphError('Clang proof rejects globals, functions and external references')
            self.type(n['type']);return self.names[key]
        if kind in ('IntegerLiteral','CharacterLiteral'):
            t=self.type(n['type']);value=str(n['value'])
            if not re.fullmatch(r'\d+',value):raise SMTGraphError('Unsupported Clang integer literal')
            suffix='ULL' if 'unsigned' in t and t.count('long')==2 else 'UL' if 'unsigned' in t and 'long' in t else 'U' if 'unsigned' in t else 'LL' if t.count('long')==2 else 'L' if 'long' in t else ''
            return value+suffix if t in ('int','long','long long','unsigned int','unsigned long','unsigned long long') else '(('+t+')'+value+suffix+')'
        if kind=='ImplicitValueInitExpr':return '(('+self.type(n['type'])+')0)'
        if kind=='InitListExpr' and len(children)==1:self.type(n['type']);return self.expr(children[0])
        if kind=='UnaryOperator' and len(children)==1 and n.get('opcode') in ('+','-','!','~'):
            self.type(n['type']);return '('+n['opcode']+'('+self.expr(children[0])+'))'
        if kind=='BinaryOperator' and len(children)==2 and n.get('opcode') in ('+','-','*','/','%','<<','>>','&','|','^','<','<=','>','>=','==','!=','&&','||'):
            self.type(n['type']);return '('+self.expr(children[0])+' '+n['opcode']+' '+self.expr(children[1])+')'
        if kind=='ConditionalOperator' and len(children)==3:
            self.type(n['type']);return '('+self.expr(children[0])+' ? '+self.expr(children[1])+' : '+self.expr(children[2])+')'
        if kind=='UnaryExprOrTypeTraitExpr' and n.get('name')=='sizeof':
            t=n.get('argType') or (children[0].get('type') if len(children)==1 else None)
            return 'sizeof('+self.type(t)+')'
        raise SMTGraphError('Unsupported Clang proof expression: '+str(kind))

    def action(self,n):
        kind=n.get('kind');children=n.get('inner',[])
        if kind in ('BinaryOperator','CompoundAssignOperator') and n.get('opcode') in ('=','+=','-=','*=','/=','%=','<<=','>>=','&=','|=','^=') and len(children)==2:
            if children[0].get('kind')!='DeclRefExpr':raise SMTGraphError('Clang scalar assignment requires a local identifier')
            if kind=='CompoundAssignOperator':
                self.type(n['computeLHSType']);self.type(n['computeResultType'])
            return self.expr(children[0])+' '+n['opcode']+' '+self.expr(children[1])
        if kind=='UnaryOperator' and n.get('opcode') in ('++','--') and len(children)==1 and children[0].get('kind')=='DeclRefExpr':
            value=self.expr(children[0]);return value+n['opcode'] if n.get('isPostfix') else n['opcode']+value
        # No nested assignment/increment, comma side effects, calls or memory reads.
        return self.expr(n)

    def decl(self,n):
        if n.get('kind')!='VarDecl' or n.get('storageClass') or n.get('tls'):raise SMTGraphError('Only automatic Clang scalar declarations supported')
        children=n.get('inner',[])
        if len(children)!=1:raise SMTGraphError('Clang scalar declarations require one initializer and no attributes')
        if 'volatile' in n['type'].get('qualType','') or '_Atomic' in n['type'].get('qualType',''):raise SMTGraphError('Volatile/atomic scalar storage unsupported')
        qualifier='const ' if n['type'].get('qualType','').startswith('const ') else ''
        initializer=children[0]
        # The typed declaration performs this assignment conversion itself.
        if initializer.get('kind')=='ImplicitCastExpr' and initializer.get('castKind') in ('IntegralCast','IntegralToBoolean') and self.type(initializer['type'])==self.type(n['type']) and len(initializer.get('inner',[]))==1:initializer=initializer['inner'][0]
        return qualifier+self.type(n['type'])+' '+self.names[n['id']]+' = '+self.expr(initializer)

    def stmt(self,n):
        kind=n.get('kind');c=n.get('inner',[])
        if kind=='CompoundStmt':return '{\n'+'\n'.join(self.stmt(v) for v in c)+'\n}'
        if kind=='DeclStmt':
            return '\n'.join(self.decl(v)+';' if v.get('kind')=='VarDecl' else '' if v.get('kind')=='TypedefDecl' else self.unsupported(v) for v in c)
        if kind=='ReturnStmt' and len(c)==1:return 'return '+self.expr(c[0])+';'
        if kind=='IfStmt' and len(c) in (2,3):return 'if ('+self.expr(c[0])+') '+self.stmt(c[1])+(' else '+self.stmt(c[2]) if len(c)==3 else '')
        if kind=='WhileStmt' and len(c)==2:return 'while ('+self.expr(c[0])+') '+self.stmt(c[1])
        if kind=='DoStmt' and len(c)==2:return 'do '+self.stmt(c[0])+' while ('+self.expr(c[1])+');'
        if kind=='ForStmt' and len(c)==5 and not c[1]:
            init=c[0]
            if init.get('kind')=='DeclStmt':
                if len(init.get('inner',[]))!=1:raise SMTGraphError('One for initializer declaration required')
                start=self.decl(init['inner'][0])
            else:start=self.action(init) if init else ''
            return 'for ('+start+'; '+(self.expr(c[2]) if c[2] else '')+'; '+(self.action(c[3]) if c[3] else '')+') '+self.stmt(c[4])
        if kind=='SwitchStmt' and len(c)==2:return 'switch ('+self.expr(c[0])+') '+self.stmt(c[1])
        if kind=='CaseStmt' and len(c)==2:return 'case '+self.expr(c[0])+': '+self.stmt(c[1])
        if kind=='DefaultStmt' and len(c)==1:return 'default: '+self.stmt(c[0])
        if kind=='BreakStmt':return 'break;'
        if kind=='ContinueStmt':return 'continue;'
        if kind=='NullStmt':return ';'
        if kind=='LabelStmt' and len(c)==1:return self.labels[n['declId']]+': '+self.stmt(c[0])
        if kind=='GotoStmt' and n.get('targetLabelDeclId') in self.labels:return 'goto '+self.labels[n['targetLabelDeclId']]+';'
        if kind in ('BinaryOperator','CompoundAssignOperator','UnaryOperator'):return self.action(n)+';'
        return self.unsupported(n)

    @staticmethod
    def unsupported(n):raise SMTGraphError('Unsupported Clang proof statement: '+str(n.get('kind')))

    def source(self):
        children=self.root.get('inner',[])
        if any(n.get('kind') not in ('ParmVarDecl','CompoundStmt','FullComment') for n in children):raise SMTGraphError('Unsupported Clang function attributes/declarations')
        bodies=[n for n in children if n.get('kind')=='CompoundStmt']
        if len(bodies)!=1:raise SMTGraphError('One Clang function body required')
        signature=self.root['type'].get('desugaredQualType',self.root['type']['qualType'])
        if '...' in signature:raise SMTGraphError('Variadic Clang proof entry unsupported')
        result=self.type(signature.split('(',1)[0].strip())
        params=[n for n in children if n.get('kind')=='ParmVarDecl']
        declarations=', '.join(self.type(n['type'])+' '+self.names[n['id']] for n in params) or 'void'
        return result+' '+self.root['name']+'('+declarations+') '+self.stmt(bodies[0])+'\n'


def prove_clang(source=None,source_file=None,function=None,clang=None,proof=None):
    if proof is None:proof={}
    if not isinstance(proof,dict) or set(proof)-{'backend','parameter_bounds','inputs','max_steps','max_paths','closed_forms','loop_summaries','allocation_failure','max_call_depth','allow_recursion','allocation_count','functional'}:return {'status':'UNKNOWN','reason':'Invalid Clang proof options'}
    options={} if clang is None else dict(clang) if isinstance(clang,dict) else clang
    if isinstance(options,dict) and options.get('include_ast') is False:return {'status':'UNKNOWN','reason':'Clang proof requires include_ast=true'}
    backend=proof.get('backend','cfg')
    front=ClangAdapter(source,source_file,None if backend in ('calls','list_calls','bv_calls') else function,options).report()
    if front['status']!='CLANG_FRONTEND_READY':return front
    failure={'status':'UNKNOWN','frontend':'clang_proof','c_overflow_verified':False,'memory_safety_verified':False,'termination_proved':False,'clang_frontend':front}
    try:
        if backend not in ('cfg','nested','recurrence','memory','calls','list','list_calls','bv_cfg','bv_calls'):raise SMTGraphError('Clang proof backend must be cfg/nested/recurrence/memory/calls/list/list_calls/bv_cfg/bv_calls')
        triple=front['target']['triple']
        linux=triple.endswith(('linux-gnu','linux-musl'))
        windows='-windows-gnu' in triple or '-windows-msvc' in triple
        if triple.startswith('x86_64-') and (linux or windows):abi='LLP64' if windows else 'LP64'
        elif re.match(r'i[3-6]86-',triple) and linux:abi='ILP32'
        else:raise SMTGraphError('Clang proof target not covered by the current x86 ABI contract (including x32)')
        if backend in ('calls','list_calls','bv_calls'):
            from .clang_memory_proof import normalize_calls
            normalized,normalizers,entry=normalize_calls(front,function)
        else:
            if backend in ('memory','list'):
                from .clang_memory_proof import MemoryNormalizer
                normalizer=MemoryNormalizer(front)
            else:
                from .clang_union_views import UnionViewNormalizer
                normalizer=UnionViewNormalizer(front)
            normalized=normalizer.source();normalizers=[normalizer];entry=front['functions'][0]['name']
        renamed=[item for normalizer in normalizers for item in normalizer.renamed]
        if backend in ('nested','recurrence','memory') and renamed:raise SMTGraphError('Summary backends require unambiguous source scalar names')
        record_tags=set();layout_correspondence={}
        if backend in ('memory','calls','list','list_calls','bv_calls'):
            from .clang_memory_proof import record_source
            records,record_tags=record_source(normalizers)
            if record_tags:normalized=records+'\n'+normalized
        char_signed=True
        for flag in front['effective_flags']:
            if flag in ('-funsigned-char','-fsigned-char'):char_signed=flag=='-fsigned-char'
        if backend in ('list','list_calls'):
            if set(proof)-{'backend','parameter_bounds','inputs','max_paths','loop_summaries','allocation_count'}:raise SMTGraphError('List proof accepts bounds, inputs, allocation_count, max_paths and optional fold summaries only')
            if backend=='list_calls':
                from .list_heap_calls import ListHeapCallsProgram as ListProgram
            else:
                from .list_heap import ListHeapProgram as ListProgram
            program=ListProgram(normalized,function=entry,parameter_bounds=proof.get('parameter_bounds'),abi=abi,char_signed=char_signed,max_paths=proof.get('max_paths',48),loop_summaries=proof.get('loop_summaries','auto'))
            result=program.report(proof.get('inputs'),proof.get('allocation_count'))
        else:
            request={'source':normalized,'function':entry,'frontend':{'cfg':'typed_cfg_heap','nested':'typed_nested','recurrence':'typed_recurrence','memory':'typed_memory','calls':'typed_cfg_calls','bv_cfg':'typed_bv_cfg','bv_calls':'typed_bv_calls'}[backend],'abi':abi,'char_signed':char_signed}
            for key,value in proof.items():
                if key!='backend':request[key]=value
            if backend in ('nested','memory') and 'loop_summaries' not in proof:request['loop_summaries']='auto'
            from .api import analyze_request
            result=analyze_request(request)
        success=result['status'].startswith('PROVED_DEFINED_TYPED_C_')
        if success and record_tags:
            from .clang_memory_proof import check_record_layouts
            layout_correspondence=check_record_layouts(front,result,record_tags)
        statuses={'cfg':'PROVED_DEFINED_CLANG_SCALAR_CFG','nested':'PROVED_DEFINED_CLANG_SCALAR_NESTED','recurrence':'PROVED_DEFINED_CLANG_SCALAR_RECURRENCE','memory':'PROVED_DEFINED_CLANG_FINITE_MEMORY','calls':'PROVED_DEFINED_CLANG_CFG_CALLS','list':'PROVED_DEFINED_CLANG_LIST_HEAP','list_calls':'PROVED_DEFINED_CLANG_LIST_CALLS','bv_cfg':'PROVED_DEFINED_CLANG_BV_CFG','bv_calls':'PROVED_DEFINED_CLANG_BV_CALLS'}
        if success:result['status']=statuses[backend]
        return {**result,'frontend':'clang_proof','clang_frontend':front,'normalization':{'method':'structural admitted Clang AST to typed C; Clang + normalizer are trusted frontend components','source':normalized,'source_sha256':hashlib.sha256(normalized.encode()).hexdigest(),'ast_sha256':hashlib.sha256(json.dumps([n.root for n in normalizers],sort_keys=True).encode()).hexdigest(),'type_environment_sha256':hashlib.sha256(json.dumps({key:front.get(key,[]) for key in ('typedefs','record_definitions','modeled_function_declarations','function_parameter_declarations','external_function_declarations')},sort_keys=True).encode()).hexdigest(),'alpha_renamed':renamed,'functions':[n.root['name'] for n in normalizers],'backend':backend,'external_call_frontiers':[f for n in normalizers for f in getattr(n,'external_frontiers',[])],'external_call_semantics_assumed':False,'bit_builtin_calls':[v for n in normalizers for v in getattr(n,'bit_builtin_calls',[])],'bit_builtin_models':list(next((n.bit_models.models for n in normalizers if getattr(n,'bit_models',None) is not None),{}).values()),'union_views':[v for n in normalizers for v in n.union_views],'abi':abi,'char_signed':char_signed,'record_layout_correspondence':layout_correspondence,'compiler_equivalence_machine_proved':False,'unsupported_constructs_rejected':True},'scope':'declared scalar input domain and selected typed backend contract; allocation assumptions and the selected shape/CFG proof boundary remain explicit; no general LLVM semantics or KLEE execution'}
    except (SMTGraphError,ValueError,TypeError,KeyError,RecursionError) as exc:return {**failure,'reason':str(exc)}
