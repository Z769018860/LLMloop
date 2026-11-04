"""Conservative lexical source context for once-evaluated finite local VLAs."""
from collections import Counter
from pycparser import c_ast,c_parser,c_generator

from .memory_frontend import _lit
from .smt_spath import SMTGraphError


def sizeof_type_supported(node):
    """Non-VM integer/data-pointer type names; no bound evaluation to erase."""
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
            raise SMTGraphError('VLA sizeof requires an object identifier or non-VM integer/data-pointer type name')
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


def validate_bounded_vlas(function):
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
                if node.init is not None or not isinstance(node.type.type,c_ast.TypeDecl) or not isinstance(node.type.type.type,c_ast.IdentifierType):
                    raise SMTGraphError('Bounded VLA requires uninitialized integer elements and one dimension')
            if node.name in scalar or node.name in sized:visible[node.name]=node
            return
        for _,child in node.children():visit(child,visible)
    visit(function.body,{p.name:p for p in params if isinstance(p,c_ast.Decl) and (p.name in scalar or p.name in sized)})
