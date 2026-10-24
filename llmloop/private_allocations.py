"""Fold balanced nonescaping private calloc/free lifetimes inside counted loops.

Private objects are replaced by resettable cells only after syntactic lifetime,
no-escape and per-loop balance checks. Counted memory then proves the unbounded
value summary. Allocation success is assumed for every dynamic instance.
"""
import copy
from pycparser import c_ast,c_parser,c_generator
from .memory_frontend import _base_int,_lit,_calloc_len
from .cfg_frontend import _is_int_decl
from .counted_c import translate_counted_memory_c
from .unbounded_memory import UnboundedMemory
from .smt_spath import SMTGraphError


class PrivateAllocations:
    def __init__(self,source,function=None,parameter_mins=None):
        try:unit=c_parser.CParser().parse(source)
        except Exception as exc:raise SMTGraphError('C parse failed: '+str(exc)) from exc
        funcs=[f for f in unit.ext if isinstance(f,c_ast.FuncDef) and (function is None or f.decl.name==function)]
        if len(funcs)!=1 or not _is_int_decl(funcs[0].decl):raise SMTGraphError('Expected one int-returning function')
        func=funcs[0]
        from .c_validation import validate_automatic_locals
        validate_automatic_locals(func,SMTGraphError)
        self.hoisted=[];self.owners={};self.aliases={};self.sites=[];self.names=set();self.loop_count=0
        raw=func.decl.type.args.params if func.decl.type.args else []
        for param in raw:
            if isinstance(param,c_ast.Typename):continue
            if not _is_int_decl(param) or not param.name:raise SMTGraphError('Private allocation fold permits only scalar int parameters')
            self.names.add(param.name)
        def check_expr(node,visible,live):
            if node is None:return
            if isinstance(node,c_ast.ArrayRef):
                if not isinstance(node.name,c_ast.ID) or node.name.name not in visible:raise SMTGraphError('Private memory access requires a visible local pointer')
                owner=self.aliases[node.name.name];index=_lit(node.subscript)
                if owner not in live:raise SMTGraphError('Use after free of private object')
                if index is None or not 0<=index<self.owners[owner]:raise SMTGraphError('Private memory access needs an in-range static cell')
                return
            if isinstance(node,c_ast.UnaryOp) and node.op=='*':
                if not isinstance(node.expr,c_ast.ID) or node.expr.name not in visible or self.aliases[node.expr.name] not in live:raise SMTGraphError('Invalid private dereference or use after free')
                return
            if isinstance(node,c_ast.ID) and node.name in self.aliases:raise SMTGraphError('Private pointer escape or unsupported pointer-value use')
            for _,child in node.children():check_expr(child,visible,live)
        def hoist_scalar(decl):
            if not _is_int_decl(decl) or decl.init is None:raise SMTGraphError('Initialized scalar int locals required')
            item=copy.deepcopy(decl);item.init=c_ast.Constant(type='int',value='0');self.hoisted.append(item)
        def reset_cells(owner):
            return [c_ast.Assignment(op='=',lvalue=c_ast.ArrayRef(name=c_ast.ID(name=owner),subscript=c_ast.Constant(type='int',value=str(i))),rvalue=c_ast.Constant(type='int',value='0')) for i in range(self.owners[owner])]
        def process(node,visible,live,depth):
            visible=set(visible);live=set(live)
            if node is None:return [],visible,live
            if isinstance(node,c_ast.Compound):
                entry_visible=set(visible);entry_live=set(live);out=[];created=set()
                for child in node.block_items or []:
                    before=set(self.owners)
                    lowered,visible,live=process(child,visible,live,depth);out.extend(lowered)
                    created.update(set(self.owners)-before)
                if live & created:raise SMTGraphError('Private allocation must be freed before its declaring block exits')
                return [c_ast.Compound(block_items=out)],entry_visible,live & entry_live
            if isinstance(node,c_ast.Decl):
                if not node.name or node.name in self.names or not _base_int(node) or node.init is None:raise SMTGraphError('Globally unique initialized int local names required')
                self.names.add(node.name)
                if isinstance(node.type,c_ast.PtrDecl):
                    if not isinstance(node.type.type,c_ast.TypeDecl):raise SMTGraphError('Only single-level private int pointers')
                    if isinstance(node.init,c_ast.FuncCall):
                        length=_calloc_len(node.init)
                        if length>15:raise SMTGraphError('Private cell budget exceeded')
                        owner=node.name;self.owners[owner]=length;self.aliases[node.name]=owner
                        self.hoisted.append(copy.deepcopy(node));visible.add(node.name);live.add(owner)
                        self.sites.append({'pointer':node.name,'cells':length,'loop_depth':depth,'balanced':True,'nonescaping':True})
                        resets=[c_ast.Assignment(op='=',lvalue=c_ast.ArrayRef(name=c_ast.ID(name=node.name),subscript=c_ast.Constant(type='int',value=str(i))),rvalue=c_ast.Constant(type='int',value='0')) for i in range(length)]
                        return resets,visible,live
                    if not isinstance(node.init,c_ast.ID) or node.init.name not in visible or self.aliases[node.init.name] not in live:raise SMTGraphError('Private alias initializer requires a live pointer copy')
                    self.aliases[node.name]=self.aliases[node.init.name];self.hoisted.append(copy.deepcopy(node));visible.add(node.name)
                    return [],visible,live
                check_expr(node.init,visible,live);hoist_scalar(node)
                return [c_ast.Assignment(op='=',lvalue=c_ast.ID(name=node.name),rvalue=copy.deepcopy(node.init))],visible,live
            if isinstance(node,c_ast.FuncCall):
                if not isinstance(node.name,c_ast.ID) or node.name.name!='free':raise SMTGraphError('Only private calloc/free calls supported')
                args=node.args.exprs if node.args else []
                if len(args)!=1 or not isinstance(args[0],c_ast.ID) or args[0].name not in visible:raise SMTGraphError('free requires a visible private pointer')
                owner=self.aliases[args[0].name]
                if owner not in live:raise SMTGraphError('Double free of private object')
                live.remove(owner);return reset_cells(owner),visible,live
            if isinstance(node,c_ast.For):
                self.loop_count+=1;new=copy.deepcopy(node)
                # Declarations in the for-init are handled by the counted frontend.
                if isinstance(node.init,c_ast.DeclList):
                    for decl in node.init.decls:
                        if not _is_int_decl(decl) or decl.name in self.names:raise SMTGraphError('Fresh scalar for index required')
                        self.names.add(decl.name)
                else:check_expr(node.init,visible,live)
                check_expr(node.cond,visible,live);check_expr(node.next,visible,live)
                before_owners=set(self.owners)
                lowered,_,after=process(node.stmt,visible,live,depth+1)
                if after!=live:raise SMTGraphError('A counted loop cannot free an object allocated outside that loop')
                new.stmt=lowered[0] if len(lowered)==1 and isinstance(lowered[0],c_ast.Compound) else c_ast.Compound(block_items=lowered)
                # Project dead private cells out of the loop boundary even for
                # zero iterations. They are inaccessible after their scope exits.
                dead=set(self.owners)-before_owners
                return [new]+[reset for owner in sorted(dead) for reset in reset_cells(owner)],visible,live
            if isinstance(node,c_ast.Assignment):
                if isinstance(node.lvalue,c_ast.ID) and node.lvalue.name in self.aliases:raise SMTGraphError('Pointer rebinding/escape is unsupported in the private allocation fold')
                check_expr(node.lvalue,visible,live);check_expr(node.rvalue,visible,live)
                return [copy.deepcopy(node)],visible,live
            if isinstance(node,c_ast.Return):
                check_expr(node.expr,visible,live)
                if live:raise SMTGraphError('Private allocations must be freed before return')
                return [copy.deepcopy(node)],visible,live
            if isinstance(node,c_ast.UnaryOp) and node.op in ('++','p++','--','p--'):
                check_expr(node.expr,visible,live);return [copy.deepcopy(node)],visible,live
            if isinstance(node,c_ast.EmptyStatement):return [],visible,live
            raise SMTGraphError('Unsupported private-allocation statement: '+type(node).__name__)
        # Process the function's top level directly to keep its final return last.
        visible=set();live=set();body=[]
        for statement in func.body.block_items or []:
            lowered,visible,live=process(statement,visible,live,0);body.extend(lowered)
        if live or not any(site['loop_depth']>0 for site in self.sites):raise SMTGraphError('Expected balanced private allocations inside at least one counted loop')
        transformed=copy.deepcopy(func);transformed.body=c_ast.Compound(block_items=self.hoisted+body)
        self.lowered_source=c_generator.CGenerator().visit(transformed)
        self.ir=translate_counted_memory_c(self.lowered_source,function=func.decl.name,parameter_mins=parameter_mins)
        self.summary=UnboundedMemory(self.ir)

    def report(self,inputs=None):
        result=self.summary.report(inputs)
        result.update(status='CERTIFIED_PRIVATE_ALLOCATION_FOLD',allocation_sites=self.sites,
                      allocation_certificate={'fresh_instance_each_site_execution':True,'zero_reset_equivalent':True,
                                              'no_pointer_identity_observation':True,'no_escape':True,'balanced_free':True,'private_cells_not_observable':True,
                                              'success_assumed_for_every_instance':True},
                      source_frontend='private allocation/free fold followed by counted memory',
                      scope='balanced nonescaping fixed-size calloc objects inside canonical counted loops; mathematical integer values',
                      c_overflow_verified=False)
        return result
