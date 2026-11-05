"""Type-only C sizeof inference for a closed non-VM expression fragment.

No environment values, pointer targets, indexes or arithmetic results are
executed. Ill-typed operations are rejected even in unevaluated operands.
"""
from dataclasses import dataclass,replace
from pycparser import c_ast

from .c_integers import IntType
from .smt_spath import SMTGraphError
from .typed_c import c_type


BINARY={'+','-','*','/','%','<<','>>','&','|','^','<','<=','>','>=','==','!=','&&','||'}
UNARY={'+','-','~','!','*','&','++','p++','--','p--'}
ASSIGN={'=','+=','-=','*=','/=','%=','<<=','>>=','&=','|=','^='}


def void_cast_type(node):
    return (isinstance(node,c_ast.TypeDecl) and not node.quals
            and isinstance(node.type,c_ast.IdentifierType) and node.type.names==['void'])


def sizeof_type_supported(node):
    depth=0
    while isinstance(node,c_ast.PtrDecl):
        if node.quals:return False
        depth+=1;node=node.type
    if depth>3 or not isinstance(node,c_ast.TypeDecl) or set(node.quals or [])-{'const'}:return False
    if not isinstance(node.type,c_ast.IdentifierType):return False
    names=node.type.names
    if names==['_Bool'] or depth>0 and names==['void']:return True
    allowed={'char','short','int','long','signed','unsigned'}
    return (bool(names) and set(names)<=allowed and all(names.count(n)<=1 for n in allowed-{'long'})
            and names.count('long')<=2 and not ('signed' in names and 'unsigned' in names)
            and not ('char' in names and set(names)&{'short','long','int'})
            and not ('short' in names and 'long' in names))


def unevaluated_syntax(node,start_depth=0):
    """Return identifier names and node count, without visiting type effects."""
    pending=[(node,start_depth)];names=set();count=0
    while pending:
        n,depth=pending.pop();count+=1
        if count>256 or depth>32:raise SMTGraphError('sizeof operand expression budget exceeded')
        if isinstance(n,c_ast.ID):names.add(n.name);continue
        if isinstance(n,c_ast.Constant) and (n.type=='char' and n.value.startswith("'") or set(n.type.split())<={'int','long','signed','unsigned'}):continue
        if isinstance(n,c_ast.UnaryOp) and n.op=='sizeof':
            if isinstance(n.expr,c_ast.Typename):
                if not sizeof_type_supported(n.expr.type):raise SMTGraphError('VM/general sizeof type names unsupported')
                continue
            children=[n.expr]
        elif isinstance(n,c_ast.UnaryOp) and n.op in UNARY:children=[n.expr]
        elif isinstance(n,c_ast.BinaryOp) and n.op in BINARY:children=[n.left,n.right]
        elif isinstance(n,c_ast.Assignment) and n.op in ASSIGN:children=[n.lvalue,n.rvalue]
        elif isinstance(n,c_ast.ArrayRef):children=[n.name,n.subscript]
        elif isinstance(n,c_ast.TernaryOp) and n.iftrue is not None:children=[n.cond,n.iftrue,n.iffalse]
        elif isinstance(n,c_ast.Cast) and (sizeof_type_supported(n.to_type.type) or void_cast_type(n.to_type.type)):children=[n.expr]
        elif isinstance(n,c_ast.ExprList) and len(n.exprs)>=2:children=n.exprs
        else:raise SMTGraphError('Unsupported unevaluated sizeof operand: '+type(n).__name__)
        pending.extend((child,depth+1) for child in children)
    return sorted(names),count


@dataclass(frozen=True)
class ExprType:
    kind: str
    integer: object=None
    target: object=None
    readonly: bool=False
    lvalue: bool=False

    def value(self):return replace(self,readonly=False,lvalue=False)


def pointer(target):
    t=ExprType('pointer',target=target);depth=0;cursor=t
    while cursor.kind=='pointer':depth+=1;cursor=cursor.target
    if depth>3:raise SMTGraphError('sizeof pointer type depth exceeds three')
    return t


def from_type(node,abi,under_pointer=False):
    if isinstance(node,c_ast.PtrDecl):
        if not sizeof_type_supported(node):raise SMTGraphError('Unsupported sizeof pointer type')
        return pointer(from_type(node.type,abi,True))
    if not isinstance(node,c_ast.TypeDecl) or not isinstance(node.type,c_ast.IdentifierType):raise SMTGraphError('Unsupported sizeof operand declaration type')
    if node.type.names==['void'] and under_pointer:return ExprType('void',readonly='const' in node.quals)
    if not sizeof_type_supported(node):raise SMTGraphError('Unsupported sizeof integer type')
    return ExprType('integer',integer=c_type(node,abi),readonly='const' in node.quals)


def from_declaration(decl,abi,parameter=False):
    if decl.storage or set(decl.quals or [])-{'const'}:raise SMTGraphError('sizeof operand storage/qualification unsupported')
    node=decl.type
    if isinstance(node,c_ast.ArrayDecl):
        if not isinstance(node.type,c_ast.TypeDecl) or not sizeof_type_supported(node.type):raise SMTGraphError('sizeof operands require one-dimensional integer arrays')
        element=from_type(node.type,abi)
        return replace(pointer(element) if parameter else ExprType('array',target=element),lvalue=True)
    return replace(from_type(node,abi),lvalue=True)


def from_model_type(t):
    if isinstance(t,IntType):return ExprType('integer',integer=t)
    if hasattr(t,'target'):return pointer(from_model_type(t.target))
    raise SMTGraphError('sizeof expression requires an integer/data-pointer type')


def size_t(abi):return abi.types['unsigned long' if abi.model=='LP64' else 'unsigned int' if abi.model=='ILP32' else 'unsigned long long']


def size_bytes(t,abi):
    if t.kind=='integer':return max(1,t.integer.bits//8)
    if t.kind=='pointer':return 4 if abi.model=='ILP32' else 8
    raise SMTGraphError('Complex sizeof operands must have non-VM integer/pointer result type')


def infer_sizeof_operand(root,lookup,abi):
    """Infer a C result type, checking constraints without evaluating values."""
    unevaluated_syntax(root);visits=0
    def fail():raise SMTGraphError('Ill-typed or unsupported unevaluated sizeof expression')
    def decay(t):return pointer(t.target) if t.kind=='array' else t.value()
    def integer(t):
        if t.kind!='integer':fail()
        return t.integer
    def scalar(t):
        if t.kind not in ('integer','pointer'):fail()
    def promoted(t):return ExprType('integer',integer=abi.promote(abi.value(0,integer(t).name)).type)
    def common(a,b):
        at,bt=integer(a),integer(b)
        return ExprType('integer',integer=abi.common(abi.value(0,at.name),abi.value(0,bt.name))[0].type)
    def compatible(a,b,ignore_readonly=True):
        if a.kind!=b.kind:return False
        if not ignore_readonly and a.readonly!=b.readonly:return False
        if a.kind=='integer':return a.integer==b.integer
        if a.kind=='void':return True
        return compatible(a.target,b.target,False)
    def composite(a,b):
        return replace(a,readonly=a.readonly or b.readonly,target=composite(a.target,b.target) if a.target else None,lvalue=False)
    def null(n):
        if not isinstance(n,c_ast.Constant) or n.type=='char':return False
        try:return abi.literal(n.value).value==0
        except ValueError:return False
    def modifiable(t):
        if not t.lvalue or t.readonly or t.kind not in ('integer','pointer'):fail()
    def assignable(left,right,node):
        if left.kind==right.kind=='integer':return
        if left.kind=='pointer' and right.kind=='integer' and null(node):return
        if left.kind==right.kind=='pointer' and (compatible(left.target,right.target) or left.target.kind=='void' or right.target.kind=='void'):
            if right.target.readonly and not left.target.readonly:fail()
            return
        fail()
    def visit(n,depth=0):
        nonlocal visits
        visits+=1
        if visits>256 or depth>32:raise SMTGraphError('sizeof type inference budget exceeded')
        if isinstance(n,c_ast.ID):return lookup(n.name)
        if isinstance(n,c_ast.Constant):
            if n.type=='char':return ExprType('integer',integer=abi.types['int'])
            try:return ExprType('integer',integer=abi.literal(n.value).type)
            except ValueError as exc:raise SMTGraphError(str(exc)) from exc
        if isinstance(n,c_ast.Cast):
            operand=decay(visit(n.expr,depth+1))
            if void_cast_type(n.to_type.type):
                if operand.kind not in ('integer','pointer','void'):fail()
                return ExprType('void')
            t=from_type(n.to_type.type,abi);scalar(operand);return t.value()
        if isinstance(n,c_ast.ExprList):
            # Check every operand's constraints; discard all values. Comma
            # converts arrays to pointers and never yields a C lvalue, while
            # leaving a narrow integer's type unpromoted.
            result=None
            for expression in n.exprs:result=decay(visit(expression,depth+1))
            return result.value()
        if isinstance(n,c_ast.UnaryOp):
            if n.op=='sizeof':
                if isinstance(n.expr,c_ast.Typename):from_type(n.expr.type,abi)
                else:
                    t=visit(n.expr,depth+1)
                    if t.kind not in ('integer','pointer','array'):fail()
                return ExprType('integer',integer=size_t(abi))
            t=visit(n.expr,depth+1)
            if n.op in ('++','p++','--','p--'):
                modifiable(t)
                if t.kind=='pointer' and t.target.kind=='void':fail()
                return t.value()
            if n.op=='&':
                if not t.lvalue or t.kind=='array':fail()
                return pointer(replace(t,lvalue=False))
            t=decay(t)
            if n.op=='*':
                if t.kind!='pointer' or t.target.kind=='void':fail()
                return replace(t.target,lvalue=True)
            if n.op=='!':scalar(t);return ExprType('integer',integer=abi.types['int'])
            return promoted(t)
        if isinstance(n,c_ast.ArrayRef):
            a,b=decay(visit(n.name,depth+1)),decay(visit(n.subscript,depth+1))
            if a.kind=='integer' and b.kind=='pointer':a,b=b,a
            if a.kind!='pointer' or a.target.kind=='void':fail()
            integer(b);return replace(a.target,lvalue=True)
        if isinstance(n,c_ast.Assignment):
            left=visit(n.lvalue,depth+1);right=decay(visit(n.rvalue,depth+1));modifiable(left)
            if n.op=='=':assignable(left,right,n.rvalue)
            elif left.kind=='pointer':
                if n.op not in ('+=','-=') or left.target.kind=='void':fail()
                integer(right)
            else:integer(left);integer(right)
            return left.value()
        if isinstance(n,c_ast.BinaryOp):
            a,b=decay(visit(n.left,depth+1)),decay(visit(n.right,depth+1))
            if n.op in ('&&','||'):scalar(a);scalar(b);return ExprType('integer',integer=abi.types['int'])
            if n.op in ('==','!=','<','<=','>','>='):
                if a.kind==b.kind=='integer':pass
                elif a.kind==b.kind=='pointer' and ((compatible(a.target,b.target) and (n.op in ('==','!=') or a.target.kind!='void')) or n.op in ('==','!=') and (a.target.kind=='void' or b.target.kind=='void')):pass
                elif n.op in ('==','!=') and (a.kind=='pointer' and b.kind=='integer' and null(n.right) or b.kind=='pointer' and a.kind=='integer' and null(n.left)):pass
                else:fail()
                return ExprType('integer',integer=abi.types['int'])
            if n.op in ('+','-') and (a.kind=='pointer' or b.kind=='pointer'):
                if n.op=='+' and a.kind=='integer':a,b=b,a
                if a.kind=='pointer' and b.kind=='integer' and a.target.kind!='void':return a
                if n.op=='-' and a.kind==b.kind=='pointer' and a.target.kind!='void' and compatible(a.target,b.target):
                    return ExprType('integer',integer=abi.types['long' if abi.model=='LP64' else 'int' if abi.model=='ILP32' else 'long long'])
                fail()
            if n.op in ('<<','>>'):integer(b);return promoted(a)
            return common(a,b)
        if isinstance(n,c_ast.TernaryOp):
            scalar(decay(visit(n.cond,depth+1)));a,b=decay(visit(n.iftrue,depth+1)),decay(visit(n.iffalse,depth+1))
            if a.kind==b.kind=='void':return ExprType('void')
            if a.kind==b.kind=='integer':return common(a,b)
            if a.kind==b.kind=='pointer' and compatible(a.target,b.target):return pointer(composite(a.target,b.target))
            if a.kind=='pointer' and b.kind=='integer' and null(n.iffalse):return a
            if b.kind=='pointer' and a.kind=='integer' and null(n.iftrue):return b
            fail()
        fail()
    result=visit(root);size_bytes(result,abi);return result
