"""Typed, fail-closed Clang normalization for existing memory/call kernels.

This is a trusted syntactic translation, never an LLVM interpreter. Pointer casts,
qualifiers and representation-sensitive records are refused rather than erased.
"""
import re
from .clang_proof import ScalarNormalizer,nodes,INTEGER
from .smt_spath import SMTGraphError

BUILTINS={'malloc','calloc','free'}
IDENT=re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def null_literal(n):
    for _ in range(16):
        if n.get('kind')=='IntegerLiteral':return n.get('value')=='0'
        if n.get('kind')=='ParenExpr' or n.get('kind') in ('CStyleCastExpr','ImplicitCastExpr') and n.get('castKind')=='NullToPointer':
            c=n.get('inner',[])
            if len(c)!=1:return False
            n=c[0]
        else:return False
    return False


class MemoryNormalizer(ScalarNormalizer):
    def __init__(self,frontend,root=None,functions=None):
        selected=frontend['functions'][0]['ast'] if root is None else root
        super().__init__({**frontend,'functions':[{'ast':selected}]})
        self.functions=functions or {};self.required_records=set();self.builtins=set()

    def type(self,t):
        text=t.get('desugaredQualType',t.get('qualType','')) if isinstance(t,dict) else t
        if not isinstance(text,str):raise SMTGraphError('Clang memory type missing')
        text=' '.join(text.split());seen=set()
        while True:
            if any(q in text.split() for q in ('volatile','_Atomic','restrict','const')):raise SMTGraphError('Qualified memory types unsupported')
            if text in INTEGER or text=='void':return text
            if text.endswith('*'):
                base=self.type(text[:-1].strip())
                if base.count('*')>=3:raise SMTGraphError('Pointer depth budget is 3')
                return base+' *'
            array=re.fullmatch(r'(.+)\[(\d+)\]',text)
            if array:
                if not 1<=int(array[2])<=8:raise SMTGraphError('Fixed array capacity must be 1..8')
                base=self.type(array[1].strip())
                if '[' in base:raise SMTGraphError('Multidimensional arrays unsupported')
                return base+'['+array[2]+']'
            record=re.fullmatch(r'struct ([A-Za-z_][A-Za-z0-9_]*)',text)
            if record:self.required_records.add(record[1]);return text
            if text in seen or text not in self.aliases or len(self.aliases[text])!=1:raise SMTGraphError('Unsupported/ambiguous Clang memory type: '+text)
            seen.add(text);text=next(iter(self.aliases[text]))

    def declarator(self,t,name):
        t=self.type(t)
        array=re.fullmatch(r'(.+)\[(\d+)\]',t)
        return array[1]+' '+name+'['+array[2]+']' if array else t+' '+name

    @staticmethod
    def reference(n):
        while n.get('kind') in ('ImplicitCastExpr','ParenExpr') and len(n.get('inner',[]))==1:n=n['inner'][0]
        return n.get('referencedDecl',{}) if n.get('kind')=='DeclRefExpr' else {}

    def expr(self,n):
        self.operations+=1
        if self.operations>8192:raise SMTGraphError('Clang memory expression budget exceeded')
        kind=n.get('kind');c=n.get('inner',[])
        if kind=='ImplicitValueInitExpr' and '*' in self.type(n['type']):return '0'
        if kind=='ImplicitCastExpr' and len(c)==1:
            cast=n.get('castKind');target=self.type(n['type'])
            if cast in ('ArrayToPointerDecay','LValueToRValue','NoOp'):
                return self.expr(c[0])
            if cast=='NullToPointer':
                # Do not erase evaluation or an implementation-dependent cast.
                child=c[0]
                if not null_literal(child):raise SMTGraphError('Only literal null-pointer conversions admitted')
                return '0'
            if cast=='PointerToBoolean':return '(!(!('+self.expr(c[0])+')))'
            if cast=='BitCast':
                child=c[0]
                # C's allocator return conversion, or argument conversion to free.
                if target=='void *' or child.get('kind')=='CallExpr' and self.reference(child['inner'][0]).get('name') in ('malloc','calloc'):
                    return self.expr(child)
                raise SMTGraphError('Pointer reinterpretation unsupported')
        if kind=='CStyleCastExpr' and len(c)==1 and '*' in self.type(n['type']):
            if n.get('castKind')=='NullToPointer' and null_literal(c[0]):return '0'
            if n.get('castKind')=='BitCast' and c[0].get('kind')=='CallExpr' and self.reference(c[0]['inner'][0]).get('name') in ('malloc','calloc'):return self.expr(c[0])
            # Other pointer casts require provenance/alignment obligations.
            raise SMTGraphError('Explicit pointer casts unsupported; use C implicit allocator conversion')
        if kind=='UnaryOperator' and len(c)==1 and n.get('opcode') in ('*','&'):
            self.type(n['type']);return '('+n['opcode']+'('+self.expr(c[0])+'))'
        if kind=='ArraySubscriptExpr' and len(c)==2:
            self.type(n['type']);return '('+self.expr(c[0])+')['+self.expr(c[1])+']'
        if kind=='MemberExpr' and len(c)==1:
            if not n.get('isArrow') or not IDENT.fullmatch(n.get('name','')):raise SMTGraphError('Only pointer-to-record member access supported')
            self.type(n['type']);return '('+self.expr(c[0])+')->'+n['name']
        if kind=='CallExpr' and c:
            ref=self.reference(c[0]);name=ref.get('name')
            if ref.get('kind')!='FunctionDecl' or name not in self.functions and name not in BUILTINS:raise SMTGraphError('Direct available calls/standard allocators only')
            if name in BUILTINS:
                if name in self.functions:raise SMTGraphError('Reserved allocator definition unsupported')
                signature=' '.join(ref.get('type',{}).get('qualType','').split())
                if name=='free':valid=signature=='void (void *)'
                else:
                    triple=self.frontend['target']['triple']
                    size_type='unsigned int' if re.match(r'i[3-6]86-',triple) else 'unsigned long long' if '-windows-' in triple else 'unsigned long'
                    valid=signature=='void *('+size_type+(', '+size_type if name=='calloc' else '')+')'
                if not valid:raise SMTGraphError('Allocator requires standard size_t/void-pointer prototype')
                self.builtins.add(name)
            self.type(n['type']);return name+'('+', '.join(self.expr(v) for v in c[1:])+')'
        if kind=='InitListExpr':
            self.type(n['type'])
            if n.get('array_filler') is not None:
                # Clang's semantic array list is filler followed by explicit slots.
                filler=n['array_filler']
                if c or not isinstance(filler,list) or not filler or filler[0].get('kind')!='ImplicitValueInitExpr':raise SMTGraphError('Unsupported Clang array filler representation')
                c=filler[1:]
            return '{'+', '.join(self.expr(v) for v in c)+'}'
        if kind=='UnaryExprOrTypeTraitExpr' and n.get('name')=='sizeof':
            t=self.type(n.get('argType') or (c[0].get('type') if len(c)==1 else None))
            if '[' in t:raise SMTGraphError('sizeof array requires an explicit scalar element count')
            return 'sizeof('+t+')'
        return super().expr(n)

    def action(self,n):
        c=n.get('inner',[])
        if n.get('kind')=='UnaryOperator' and n.get('opcode') in ('++','--') and len(c)==1:
            value=self.expr(c[0]);return value+n['opcode'] if n.get('isPostfix') else n['opcode']+value
        if n.get('kind') in ('BinaryOperator','CompoundAssignOperator') and n.get('opcode') in ('=','+=','-=','*=','/=','%=','<<=','>>=','&=','|=','^=') and len(c)==2:
            if c[0].get('kind') not in ('DeclRefExpr','ArraySubscriptExpr','MemberExpr','UnaryOperator'):raise SMTGraphError('Unsupported memory assignment target')
            if n['kind']=='CompoundAssignOperator':self.type(n['computeLHSType']);self.type(n['computeResultType'])
            return self.expr(c[0])+' '+n['opcode']+' '+self.expr(self.assignment_value(n))
        return super().action(n)

    def decl(self,n):
        if n.get('kind')!='VarDecl' or n.get('storageClass') or n.get('tls'):raise SMTGraphError('Automatic declarations only')
        c=n.get('inner',[])
        if len(c)>1 or any(v.get('kind','').endswith('Attr') for v in c):raise SMTGraphError('Declaration attributes unsupported')
        t=self.type(n['type'])
        if '*' not in t and '[' not in t and not t.startswith('struct '):return super().decl(n)
        if t.startswith('struct ') and '*' not in t:raise SMTGraphError('By-value/stack records unsupported')
        return self.declarator(n['type'],self.names[n['id']])+(' = '+self.expr(c[0]) if c else '')

    def stmt(self,n):
        if n.get('kind')=='CallExpr':return self.expr(n)+';'
        if n.get('kind')=='ReturnStmt' and not n.get('inner'):return 'return;'
        return super().stmt(n)

    def source(self):
        # Reuse all structural body checks, but pointer returns/parameters need
        # C declarators; array parameters have already decayed in Clang's type.
        return super().source()


def normalize_program(frontend,with_calls=False):
    root=frontend['functions'][0]['ast'];entry=root['name']
    definitions=frontend.get('dependencies',{}).get('functions',[])
    funcs={}
    for n in definitions:
        if n['name'] in funcs:raise SMTGraphError('Duplicate Clang function definitions')
        funcs[n['name']]=n
    funcs.setdefault(entry,root)
    chosen={};pending=[entry]
    while pending:
        name=pending.pop()
        if name in chosen:continue
        if name not in funcs:raise SMTGraphError('Missing call definition')
        chosen[name]=funcs[name]
        if len(chosen)>16:raise SMTGraphError('Call closure budget is 16 functions')
        for node in nodes(funcs[name]):
            if node.get('kind')!='CallExpr':continue
            ref=MemoryNormalizer.reference(node['inner'][0]);callee=ref.get('name')
            if callee in BUILTINS:continue
            if not with_calls:raise SMTGraphError('User calls require calls backend')
            if callee not in funcs:raise SMTGraphError('External/indirect calls unsupported')
            pending.append(callee)
    normalizers=[];sources=[];required=set();builtins=set()
    for name,root in chosen.items():
        n=MemoryNormalizer(frontend,root,funcs);sources.append(n.source());normalizers.append(n);required.update(n.required_records);builtins.update(n.builtins)
    available={}
    for record in frontend.get('dependencies',{}).get('records',[]):available.setdefault(record.get('name'),[]).append(record)
    emitted={}
    while required-set(emitted):
        name=next(iter(required-set(emitted)))
        if len(available.get(name,[]))!=1:raise SMTGraphError('Unique complete named record definition required: '+name)
        r=available[name][0]
        if r.get('tagUsed')!='struct':raise SMTGraphError('Union proof unsupported')
        fields=[];n=normalizers[0]
        for member in r.get('inner',[]):
            if member.get('kind')!='FieldDecl' or member.get('isBitfield') or member.get('inner') or not IDENT.fullmatch(member.get('name','')):raise SMTGraphError('Only natural unqualified non-bitfield records supported')
            fields.append(n.declarator(member['type'],member['name'])+';')
        emitted[name]='struct '+name+' {'+' '.join(fields)+'};'
        required.update(n.required_records)
        if len(required)>8:raise SMTGraphError('Record budget is 8')
    digest_roots=[chosen[name] for name in chosen]
    prototypes=[text.split('{',1)[0].strip()+';' for text in sources] if with_calls else []
    return '\n'.join(list(emitted.values())+prototypes+sources),normalizers,digest_roots
