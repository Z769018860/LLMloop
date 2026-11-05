"""Conservative lexical source context for once-evaluated finite local VLAs."""
from collections import Counter
from pycparser import c_ast,c_parser,c_generator

from .memory_frontend import _lit
from .smt_spath import SMTGraphError
from .c_integers import IntegerABI
from .sizeof_expression import sizeof_type_supported,unevaluated_syntax,infer_sizeof_operand,from_declaration


def bound_operands(expression):
    """Separate value reads from unevaluated object/type size observations."""
    pending=[(expression,0)];values=set();sizes=set();count=0
    binary=set(('+','-','*','/','%','<<','>>','&','|','^','<','<=','>','>=','==','!=','&&','||'))
    while pending:
        node,depth=pending.pop();count+=1
        if count>256 or depth>32:raise SMTGraphError('VLA bound expression budget exceeded')
        if isinstance(node,c_ast.ID):values.add(node.name);continue
        if isinstance(node,c_ast.Constant) and node.type in ('int','unsigned int','long int','unsigned long int','long long int','unsigned long long int','char'):continue
        if isinstance(node,c_ast.UnaryOp) and node.op=='sizeof':
            if isinstance(node.expr,c_ast.ID):sizes.add(node.expr.name);continue
            if isinstance(node.expr,c_ast.Typename) and sizeof_type_supported(node.expr.type):continue
            names,extra=unevaluated_syntax(node.expr,depth+1);sizes.update(names);count+=extra
            if count>256:raise SMTGraphError('VLA bound expression budget exceeded')
            continue
        if isinstance(node,c_ast.UnaryOp) and node.op in ('+','-','~','!'):children=[node.expr]
        elif isinstance(node,c_ast.BinaryOp) and node.op in binary:children=[node.left,node.right]
        elif isinstance(node,c_ast.TernaryOp) and node.iftrue is not None:children=[node.cond,node.iftrue,node.iffalse]
        elif isinstance(node,c_ast.Cast):
            target=node.to_type.type
            if (not isinstance(target,c_ast.TypeDecl) or target.quals or node.to_type.quals
                    or not isinstance(target.type,c_ast.IdentifierType)
                    or not set(target.type.names)<=set(('_Bool','char','short','int','long','signed','unsigned'))):
                raise SMTGraphError('VLA bound casts require plain integer types')
            children=[node.expr]
        else:raise SMTGraphError('VLA bound requires pure integer operators without calls, memory reads or effects')
        pending.extend((child,depth+1) for child in children)
    return {'value':sorted(values),'sizeof':sorted(sizes)}


def bound_identifiers(expression):
    operands=bound_operands(expression)
    return sorted(set(operands['value'])|set(operands['sizeof']))


def parse_bound_expression(text):
    """Parse Clang's printed bound conservatively, then validate its grammar."""
    if len(text)>4096:raise SMTGraphError('VLA bound spelling budget exceeded')
    try:unit=c_parser.CParser().parse('int __llmloop_bound(void){return ('+text+');}')
    except Exception as exc:raise SMTGraphError('Unsupported Clang VLA bound spelling: '+str(exc)) from exc
    if len(unit.ext)!=1 or not isinstance(unit.ext[0],c_ast.FuncDef):raise SMTGraphError('Expected one VLA bound expression')
    items=unit.ext[0].body.block_items or []
    if len(items)!=1 or not isinstance(items[0],c_ast.Return):raise SMTGraphError('Expected one VLA bound expression')
    expression=items[0].expr;bound_identifiers(expression);return expression


def bound_spelling(expression):
    return c_generator.CGenerator().visit(expression)


def validate_bounded_vlas(function,abi=None):
    """Validate original scopes before call expansion creates hygienic gotos.

    Bound leaves are uniquely named, visible scalar parameters or initialized
    locals. Declarations live in explicit blocks or a for initializer. Original
    goto/labels remain refused; runtime positivity/capacity are never assumed.
    """
    declarations=[];jumps=[];pending=[(function,0)];count=0
    while pending:
        node,depth=pending.pop();count+=1
        # Receiver CFG/call AST limits remain authoritative; this preliminary
        # pass must not impose a tighter limit by counting function wrappers.
        if count>16384 or depth>128:raise SMTGraphError('Bounded VLA source context budget exceeded')
        if isinstance(node,c_ast.Decl):declarations.append(node)
        if isinstance(node,(c_ast.Goto,c_ast.Label)):jumps.append(node)
        pending.extend((child,depth+1) for _,child in node.children())
    abi=abi or IntegerABI()
    params=function.decl.type.args.params if function.decl.type.args else []
    parameter_ids={id(p) for p in params}
    dynamic={id(d):d for d in declarations if id(d) not in parameter_ids
             and isinstance(d.type,c_ast.ArrayDecl) and _lit(d.type.dim) is None}
    if not dynamic:return
    if jumps:raise SMTGraphError('Bounded VLA source goto/label unsupported')
    scalar={d.name:d for d in declarations if isinstance(d.type,c_ast.TypeDecl)
            and isinstance(d.type.type,c_ast.IdentifierType)
            and (id(d) in parameter_ids or d.init is not None)}
    sized={d.name:d for d in declarations if
           (sizeof_type_supported(d.type) and (id(d) in parameter_ids or d.init is not None))
           or isinstance(d.type,c_ast.ArrayDecl) and sizeof_type_supported(d.type.type) and isinstance(d.type.type,c_ast.TypeDecl)}
    counts=Counter(d.name for d in declarations)

    def visit(node,visible,context=None):
        if node is None:return
        if isinstance(node,c_ast.Compound):
            local=dict(visible)
            for child in node.block_items or []:visit(child,local,'block')
            return
        if isinstance(node,c_ast.For):
            local=dict(visible)
            if isinstance(node.init,c_ast.DeclList):
                for decl in node.init.decls:visit(decl,local,'for_init')
            else:visit(node.init,local)
            visit(node.cond,local);visit(node.next,local);visit(node.stmt,local)
            return
        if isinstance(node,c_ast.If):
            visit(node.cond,dict(visible));visit(node.iftrue,dict(visible));visit(node.iffalse,dict(visible));return
        if isinstance(node,(c_ast.While,c_ast.DoWhile)):
            visit(node.cond,dict(visible));visit(node.stmt,dict(visible));return
        if isinstance(node,c_ast.Decl):
            if id(node) in dynamic:
                bound=node.type.dim
                operands=bound_operands(bound);names=bound_identifiers(bound)
                if (context not in ('block','for_init')
                        or any(name not in visible or counts[name]!=1 for name in names)
                        or any(name not in scalar for name in operands['value'])
                        or any(name not in sized for name in operands['sizeof'])):
                    raise SMTGraphError('Bounded VLA requires visible unique scalar value/object-size operands and supported declaration types')
                pending_size=[bound]
                while pending_size:
                    expression=pending_size.pop()
                    if isinstance(expression,c_ast.UnaryOp) and expression.op=='sizeof' and not isinstance(expression.expr,(c_ast.ID,c_ast.Typename)):
                        infer_sizeof_operand(expression.expr,lambda name:from_declaration(visible[name],abi,id(visible[name]) in parameter_ids),abi)
                    pending_size.extend(child for _,child in expression.children())
                if node.init is not None or not isinstance(node.type.type,c_ast.TypeDecl) or not isinstance(node.type.type.type,c_ast.IdentifierType):
                    raise SMTGraphError('Bounded VLA requires uninitialized integer elements and one dimension')
            if node.name in scalar or node.name in sized:visible[node.name]=node
            return
        for _,child in node.children():visit(child,visible)
    visit(function.body,{p.name:p for p in params if isinstance(p,c_ast.Decl) and (p.name in scalar or p.name in sized)})


def split_array_type(text):
    start=text.find('[')
    if start<0:return None
    depth=0;quote=None;escaped=False
    for i in range(start,len(text)):
        char=text[i]
        if quote:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char==quote:quote=None
        elif char in ('"',"'"):quote=char
        elif char=='[':depth+=1
        elif char==']':
            depth-=1
            if depth==0:
                return (text[:start].strip(),text[start+1:i].strip()) if not text[i+1:].strip() else None
    return None
