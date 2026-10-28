"""Inductive fresh-node list summaries without a represented-object cutoff.

Admits a checked prepend-builder normal form, optionally followed by a scalar
fold that frees every node. Abstract identities are allocation tokens, never C
addresses. Typed scalar obligations are delegated to the existing C kernel.
"""
import copy
import hashlib

from pycparser import c_ast, c_generator, c_parser
import z3

from .c_integers import IntegerABI
from .c_validation import validate_automatic_locals
from .memory_frontend import _lit
from .smt_spath import SMTGraphError
from .typed_c import c_type
from .typed_cfg_heap import TypedCFGHeap
from .typed_nested import TypedCNested


def list_shape_certificate():
    """Universally check the indexed live-prefix and consumption invariants."""
    k, j, r, m, t = z3.Ints('list_k list_node list_remaining list_length list_step')
    live = lambda size, node: z3.And(node >= 1, node <= size)
    checks = []

    def check(label, premise, claim):
        solver = z3.Solver()
        solver.set(timeout=5000)
        solver.add(premise, z3.Not(claim))
        answer = solver.check()
        if answer != z3.unsat:
            raise SMTGraphError('List shape obligation not proved: ' + label)
        checks.append({'obligation': label, 'proved': True, 'refutation_smt2': solver.to_smt2()})

    check('empty base has no live nodes', z3.BoolVal(True), z3.Not(live(0, j)))
    check('successful allocation is a fresh nonnull token', k >= 0,
          z3.And(k+1 > 0, z3.Not(live(k, k+1))))
    check('old head is null or live', k >= 0, z3.Or(k == 0, live(k, k)))
    check('prepend extends exactly the live prefix', k >= 0,
          z3.Or(live(k, j), j == k+1) == live(k+1, j))
    new_next = z3.If(j == k+1, k, j-1)
    check('new and preserved links are initialized live tails', z3.And(k >= 0, live(k+1, j)),
          z3.And(new_next == j-1, new_next >= 0, new_next < j,
                 z3.Or(new_next == 0, live(k+1, new_next))))
    check('every live payload has an initialized builder index', z3.And(m >= 0, live(m, j)),
          z3.And(j-1 >= 0, j-1 < m))
    check('head trajectory base', m >= 0, m-0 == m)
    check('head trajectory follows next at each live step', z3.And(m >= 0, t >= 0, t < m),
          z3.And(live(m, m-t), (m-t)-1 == m-(t+1)))
    check('trajectory reaches null exactly after length steps', z3.And(m >= 0, t >= 0, t <= m),
          (m-t == 0) == (t == m))
    check('every live node is on the head trajectory', z3.And(m >= 0, live(m, j)),
          z3.And(m-j >= 0, m-j < m, m-(m-j) == j))
    check('free consumes exactly the current head', r > 0,
          z3.And(live(r, j), j != r) == live(r-1, j))
    check('saved next is live or null before and after free', r > 0,
          z3.And(live(r, r), z3.Or(r-1 == 0, live(r-1, r-1))))
    check('consumption has a natural strictly decreasing rank', r > 0,
          z3.And(r-1 >= 0, r-1 < r))
    check('freed and live nodes partition all allocations', z3.And(m >= r, r >= 0),
          z3.And(z3.Or(live(r, j), z3.And(j > r, j <= m)) == live(m, j),
                 z3.Not(z3.And(live(r, j), j > r, j <= m))))
    return {'method': 'universal fresh-token/live-prefix and reverse traversal induction',
            'abstract_identities_not_addresses': True, 'represented_object_cutoff': None,
            'obligations': checks}


def items(node):
    return node.block_items or [] if isinstance(node, c_ast.Compound) else [node]


def identifier(node, name):
    return isinstance(node, c_ast.ID) and node.name == name


def pointer_tag(decl):
    node = decl.type
    if not isinstance(node, c_ast.PtrDecl) or not isinstance(node.type, c_ast.TypeDecl):
        return None
    base = node.type.type
    return base.name if isinstance(base, c_ast.Struct) and base.decls is None else None


def member(node, owner, field):
    return isinstance(node, c_ast.StructRef) and node.type == '->' and identifier(node.name, owner) and identifier(node.field, field)


def nonnull(node, name):
    return identifier(node,name) or isinstance(node,c_ast.BinaryOp) and node.op=='!=' and (
        identifier(node.left,name) and _lit(node.right)==0 or identifier(node.right,name) and _lit(node.left)==0)


def check_list_reversal(statements, head, tag, link):
    """Recognize exactly one owned-chain reversal, with no hidden effects."""
    if len(statements) != 3:
        raise SMTGraphError('Reversal requires null previous, while traversal and final head transfer')
    previous, loop, transfer = statements
    if not isinstance(previous, c_ast.Decl) or pointer_tag(previous) != tag or _lit(previous.init) != 0 or previous.name == head:
        raise SMTGraphError('Reversal previous must be a distinct null same-record pointer')
    if not isinstance(loop, c_ast.While) or not nonnull(loop.cond, head):
        raise SMTGraphError('Reversal requires while(current head)')
    body = items(loop.stmt)
    if len(body) != 4:
        raise SMTGraphError('Reversal requires saved next, link rewrite, previous update and head advance')
    saved, rewrite, publish, advance = body
    if not isinstance(saved, c_ast.Decl) or pointer_tag(saved) != tag or saved.name in (head,previous.name) or not member(saved.init,head,link):
        raise SMTGraphError('Reversal must save the old next link before overwriting it')
    if not isinstance(rewrite,c_ast.Assignment) or rewrite.op != '=' or not member(rewrite.lvalue,head,link) or not identifier(rewrite.rvalue,previous.name):
        raise SMTGraphError('Reversal must link the current node to the previous owned prefix')
    if not isinstance(publish,c_ast.Assignment) or publish.op != '=' or not identifier(publish.lvalue,previous.name) or not identifier(publish.rvalue,head):
        raise SMTGraphError('Reversal previous must become the current node after link rewrite')
    if not isinstance(advance,c_ast.Assignment) or advance.op != '=' or not identifier(advance.lvalue,head) or not identifier(advance.rvalue,saved.name):
        raise SMTGraphError('Reversal must advance to the saved unprocessed tail')
    if not isinstance(transfer,c_ast.Assignment) or transfer.op != '=' or not identifier(transfer.lvalue,head) or not identifier(transfer.rvalue,previous.name):
        raise SMTGraphError('Reversal must transfer the complete reversed prefix back to the owner')
    text=c_generator.CGenerator().visit(c_ast.Compound(statements))
    return {'head':head,'previous':previous.name,'saved_next':saved.name,
            'only_next_fields_modified':True,'no_allocation_or_free':True,
            'saved_next_before_rewrite':True,'source_sha256':hashlib.sha256(text.encode()).hexdigest()}


def list_reversal_certificate(orientation):
    """Check the disjoint reversed-prefix/unprocessed-suffix shape invariant."""
    if orientation not in ('descending','ascending'):
        raise SMTGraphError('Unknown list orientation')
    m,t,p,q,j=z3.Ints('reverse_length reverse_step reverse_position reverse_other_position reverse_token')
    valid=lambda x:z3.And(x>=0,x<m)
    processed=lambda size,x:z3.And(x>=0,x<size)
    remaining=lambda size,x:z3.And(x>=size,x<m)
    token=lambda x:m-x if orientation=='descending' else x+1
    original_next=lambda x:z3.If(x+1<m,x+1,-1)
    next_at=lambda size,x:z3.If(x<size,x-1,original_next(x))
    checks=[]
    def check(label,premise,claim):
        solver=z3.Solver();solver.set(timeout=5000);solver.add(premise,z3.Not(claim))
        if solver.check()!=z3.unsat:raise SMTGraphError('List reversal obligation not proved: '+label)
        checks.append({'obligation':label,'proved':True,'refutation_smt2':solver.to_smt2()})
    domain=z3.And(m>=0,t>=0,t<=m)
    check('incoming positions map to live allocation tokens',z3.And(m>=0,valid(p)),z3.And(token(p)>=1,token(p)<=m))
    check('incoming position identity is injective',z3.And(m>=0,valid(p),valid(q)),(token(p)==token(q))==(p==q))
    inverse=m-j if orientation=='descending' else j-1
    check('every live allocation token has an incoming position',z3.And(m>=0,j>=1,j<=m),z3.And(valid(inverse),token(inverse)==j))
    check('empty processed prefix preserves original links',z3.And(m>=0,valid(p)),next_at(0,p)==original_next(p))
    check('processed and remaining footprints exactly partition all nodes',domain,
          z3.And(z3.Or(processed(t,p),remaining(t,p))==valid(p),z3.Not(z3.And(processed(t,p),remaining(t,p)))))
    active=z3.And(domain,t<m)
    check('current node and saved old next are valid before rewrite',active,
          z3.And(remaining(t,t),z3.Or(original_next(t)==-1,remaining(t,original_next(t)))))
    check('previous is null or in disjoint processed prefix',active,
          z3.And(z3.Or(t-1==-1,processed(t,t-1)),z3.Not(remaining(t,t-1))))
    rewritten=z3.If(p==t,t-1,next_at(t,p))
    check('single source link write establishes next indexed invariant',z3.And(active,valid(p)),rewritten==next_at(t+1,p))
    check('new previous and remaining head match next phase',active,
          z3.And(processed(t+1,t),z3.Or(original_next(t)==-1,remaining(t+1,original_next(t)))))
    check('processed links descend within the reversed prefix',z3.And(domain,processed(t,p)),
          z3.And(next_at(t,p)==p-1,z3.Or(p-1==-1,processed(t,p-1))))
    check('remaining links advance within untouched suffix',z3.And(domain,remaining(t,p)),
          z3.And(next_at(t,p)==original_next(p),z3.Or(original_next(p)==-1,remaining(t,original_next(p)))))
    check('reversal rank strictly decreases without losing nodes',active,z3.And(m-(t+1)>=0,m-(t+1)<m-t))
    check('exit covers every node with reversed links',z3.And(m>=0,valid(p)),z3.And(processed(m,p),next_at(m,p)==p-1))
    step=1 if orientation=='descending' else -1
    check('final links reverse allocation-token direction',z3.And(m>=0,p>0,p<m),token(p-1)==token(p)+step)
    check('final head is the former last allocation-position node',m>0,token(m-1)==(1 if orientation=='descending' else m))
    return {'method':'universal disjoint reversed-prefix/unprocessed-suffix induction',
            'input_orientation':orientation,'output_orientation':'ascending' if orientation=='descending' else 'descending',
            'null_position':-1,'positions_are_not_C_addresses':True,
            'payload_frame_rule_checked_by_source_match':True,'represented_object_cutoff':None,'obligations':checks}


def list_traversal_certificate(orientation):
    """Check oriented traversal and exact live-footprint consumption."""
    if orientation not in ('descending','ascending'):raise SMTGraphError('Unknown list orientation')
    m,t,j=z3.Ints('traverse_length traverse_step traverse_token')
    live=lambda size,node:z3.And(node>=1,node<=m,node<=m-size if orientation=='descending' else node>size)
    head=lambda size:z3.If(size<m,m-size if orientation=='descending' else size+1,0)
    successor=lambda node:node-1 if orientation=='descending' else z3.If(node<m,node+1,0)
    checks=[]
    def check(label,premise,claim):
        solver=z3.Solver();solver.set(timeout=5000);solver.add(premise,z3.Not(claim))
        if solver.check()!=z3.unsat:raise SMTGraphError('List traversal obligation not proved: '+label)
        checks.append({'obligation':label,'proved':True,'refutation_smt2':solver.to_smt2()})
    active=z3.And(m>=0,t>=0,t<m)
    check('initial live footprint is every allocation',m>=0,live(0,j)==z3.And(j>=1,j<=m))
    check('current head is a live initialized node',active,z3.And(head(t)!=0,live(t,head(t))))
    check('stored successor follows the oriented trajectory',active,successor(head(t))==head(t+1))
    check('current free removes exactly the current head',active,z3.And(live(t,j),j!=head(t))==live(t+1,j))
    check('saved successor survives free or is null',active,z3.Or(head(t+1)==0,live(t+1,head(t+1))))
    check('every visited payload has a valid builder index',active,z3.And(head(t)-1>=0,head(t)-1<m))
    check('all nodes are consumed at exact null exit',m>=0,z3.And(head(m)==0,z3.Not(live(m,j))))
    check('oriented traversal terminates by decreasing remaining length',active,z3.And(m-t>0,m-t-1>=0,m-t-1<m-t))
    return {'method':'universal oriented traversal and exact consumption','orientation':orientation,'obligations':checks}


class ListHeapProgram:
    def __init__(self, source, function=None, parameter_bounds=None, abi='LP64', char_signed=True,
                 max_paths=48, loop_summaries='auto'):
        if not isinstance(source, str) or len(source) > 200000:
            raise SMTGraphError('List normal form must be at most 200000 characters')
        try:
            unit = c_parser.CParser().parse(source)
        except Exception as exc:
            raise SMTGraphError('List normal-form parse failed: ' + str(exc)) from exc
        self.generator = c_generator.CGenerator()
        self.model = IntegerABI(abi, char_signed)
        self.abi, self.char_signed = abi, char_signed
        self.bounds = {} if parameter_bounds is None else parameter_bounds
        if not isinstance(self.bounds, dict):
            raise SMTGraphError('List parameter bounds must be an object')
        funcs = [node for node in unit.ext if isinstance(node, c_ast.FuncDef)]
        records = [node for node in unit.ext if isinstance(node, c_ast.Decl) and node.name is None and isinstance(node.type, c_ast.Struct)]
        if len(funcs) != 1 or len(records) != 1 or len(unit.ext) != 2 or function is not None and funcs[0].decl.name != function:
            raise SMTGraphError('List normal form needs exactly one function and one named record, without globals or other declarations')
        self.func, record = funcs[0], records[0]
        if self.func.decl.funcspec or self.func.decl.quals:
            raise SMTGraphError('Qualified/attributed list function declarations unsupported')
        return_declarator = self.func.decl.type
        while return_declarator is not None:
            if getattr(return_declarator, 'quals', None):
                raise SMTGraphError('Qualified list return declarators unsupported')
            return_declarator = getattr(return_declarator, 'type', None)
        validate_automatic_locals(self.func, SMTGraphError)
        self.used = set()
        todo = [self.func]
        while todo:
            node = todo.pop()
            if isinstance(node, c_ast.Decl) and not isinstance(node.type, c_ast.FuncDecl):
                if not node.name or node.name in self.used:
                    raise SMTGraphError('List normal form requires unique named declarations')
                self.used.add(node.name)
            todo.extend(child for _, child in node.children())
        self.record_source = self.generator.visit(record) + ';\n'
        layout_name = self.fresh('layout')
        layout = TypedCFGHeap(self.record_source + 'int '+layout_name+'(void){return 0;}',
                              function=layout_name, abi=abi, char_signed=char_signed).report()
        if layout['status'] != 'PROVED_DEFINED_TYPED_C_CFG_HEAP':
            raise SMTGraphError('List record layout setup failed')
        self.memory_model = layout['memory_model']
        self.tag = record.type.name
        fields = record.type.decls or []
        if len(fields) != 2 or len({field.name for field in fields}) != 2:
            raise SMTGraphError('List record needs one integer payload and one same-record pointer')
        links = [field for field in fields if pointer_tag(field) == self.tag]
        values = [field for field in fields if isinstance(field.type, c_ast.TypeDecl) and isinstance(field.type.type, c_ast.IdentifierType)]
        if len(links) != 1 or len(values) != 1:
            raise SMTGraphError('List fields must be an integer payload and a same-record link')
        self.link, self.value = links[0].name, values[0].name
        self.payload_type = c_type(values[0], self.model)
        self.payload_type_source = self.generator.visit(values[0].type)
        raw = self.func.decl.type.args.params if self.func.decl.type.args else []
        if not raw or not all(isinstance(param, c_ast.Decl) and param.name for param in raw):
            raise SMTGraphError('List builder requires named scalar parameters including its int bound')
        self.parameters = {param.name: c_type(param, self.model) for param in raw}
        if len(self.parameters) != len(raw):
            raise SMTGraphError('Unique scalar list parameters required')
        self.parameter_source = ', '.join(self.generator.visit(param) for param in raw)
        body = self.func.body.block_items or []
        if len(body) < 3:
            raise SMTGraphError('Expected head declaration, prepend loop, optional reversals and return/fold suffix')
        head, self.loop = body[:2]
        if not isinstance(head, c_ast.Decl) or pointer_tag(head) != self.tag or _lit(head.init) != 0:
            raise SMTGraphError('List head must start as a null same-record pointer')
        self.head = head.name
        self.orientation='descending';self.reversals=[];suffix=body[2:]
        while len(suffix)>=3 and isinstance(suffix[0],c_ast.Decl) and pointer_tag(suffix[0])==self.tag:
            if len(self.reversals)>=8:raise SMTGraphError('At most eight source reversal stages are supported')
            source_contract=check_list_reversal(suffix[:3],self.head,self.tag,self.link)
            proof=list_reversal_certificate(self.orientation)
            self.reversals.append({'source_contract':source_contract,'proof':proof})
            self.orientation=proof['output_orientation'];suffix=suffix[3:]
        if len(suffix) not in (1,3):raise SMTGraphError('Expected pointer return or scalar fold/free after reversals')
        self.mode = 'escape' if len(suffix) == 1 else 'fold_free'
        if self.mode == 'escape':
            if not isinstance(suffix[0], c_ast.Return) or not identifier(suffix[0].expr, self.head) or pointer_tag(self.func.decl.type) != self.tag:
                raise SMTGraphError('Escaping builder must return its live list head')
        else:
            self.return_type = c_type(self.func.decl, self.model)
        self.parse_builder()
        build_name = self.fresh('payload_check')
        temporary, dummy = self.fresh('payload'), self.fresh('dummy')
        build = copy.deepcopy(self.loop)
        build.stmt = c_parser.CParser().parse('void x(void){'+self.payload_type_source+' '+temporary+'='+self.generator.visit(self.payload_expr)+';}').ext[0].body
        self.build_source = 'int '+build_name+'('+self.parameter_source+'){int '+dummy+'=0;'+self.generator.visit(build)+' return '+dummy+';}'
        self.build_engine = TypedCNested(self.build_source, {self.index:{dummy:'entry("'+dummy+'")'}}, function=build_name, parameter_bounds=self.bounds,
                                        abi=abi, char_signed=char_signed, max_paths=max_paths)
        self.build_report = self.build_engine.report()
        self.fold_engine = None
        self.fold_source = None
        if self.build_report['status'] == 'PROVED_DEFINED_TYPED_C_NESTED' and self.mode == 'fold_free':
            self.parse_fold(suffix)
            self.make_fold(max_paths, loop_summaries)
        self.shape = list_shape_certificate()
        self.traversal = list_traversal_certificate(self.orientation)

    def fresh(self, tag):
        name = '__list_'+tag
        while name in self.used:
            name += '_'
        self.used.add(name)
        return name

    def parse_builder(self):
        loop = self.loop
        if not isinstance(loop, c_ast.For) or not isinstance(loop.init, c_ast.DeclList) or len(loop.init.decls) != 1:
            raise SMTGraphError('List construction requires one canonical for loop')
        index = loop.init.decls[0]
        if c_type(index, self.model) != self.model.types['int'] or _lit(index.init) != 0:
            raise SMTGraphError('List index must be a fresh signed int starting at zero')
        self.index = index.name
        if not isinstance(loop.cond, c_ast.BinaryOp) or loop.cond.op != '<' or not identifier(loop.cond.left, self.index) or not isinstance(loop.cond.right, c_ast.ID):
            raise SMTGraphError('List loop condition must be index < immutable int parameter')
        self.bound = loop.cond.right.name
        if self.parameters.get(self.bound) != self.model.types['int']:
            raise SMTGraphError('List count parameter must have signed int type')
        if not isinstance(loop.next, c_ast.UnaryOp) or loop.next.op not in ('++', 'p++') or not identifier(loop.next.expr, self.index):
            raise SMTGraphError('List index must increment once per successful allocation')
        statements = items(loop.stmt)
        if len(statements) != 5 or not isinstance(statements[0], c_ast.Decl):
            raise SMTGraphError('List body requires allocation, null exit, payload, link and head writes')
        allocation, failure, payload, link, head_write = statements
        if pointer_tag(allocation) != self.tag or not isinstance(allocation.init, c_ast.FuncCall) or not identifier(allocation.init.name, 'calloc'):
            raise SMTGraphError('List allocation must be a same-record calloc declaration')
        args = allocation.init.args.exprs if allocation.init.args else []
        count = args[0] if args else None
        while isinstance(count, c_ast.Cast):
            c_type(count.to_type, self.model)
            count = count.expr
        size = args[1] if len(args) == 2 else None
        if len(args) != 2 or _lit(count) != 1 or not isinstance(size, c_ast.UnaryOp) or size.op != 'sizeof' or not isinstance(size.expr, c_ast.Typename):
            raise SMTGraphError('List allocation requires calloc(1,sizeof(record))')
        type_node = size.expr.type
        if size.expr.quals or not isinstance(type_node, c_ast.TypeDecl) or type_node.quals or not isinstance(type_node.type, c_ast.Struct) or type_node.type.name != self.tag or type_node.type.decls is not None:
            raise SMTGraphError('List calloc sizeof must match its record')
        self.node = allocation.name
        if not isinstance(failure, c_ast.If) or failure.iffalse is not None:
            raise SMTGraphError('List allocation failure needs an immediate null exit')
        condition = failure.cond
        null_test = isinstance(condition, c_ast.UnaryOp) and condition.op == '!' and identifier(condition.expr, self.node)
        if isinstance(condition, c_ast.BinaryOp) and condition.op == '==':
            null_test = identifier(condition.left, self.node) and _lit(condition.right) == 0 or identifier(condition.right, self.node) and _lit(condition.left) == 0
        exits = items(failure.iftrue)
        allowed_exit = len(exits) == 1 and (isinstance(exits[0], c_ast.Break) or self.mode == 'escape' and not self.reversals and isinstance(exits[0], c_ast.Return) and identifier(exits[0].expr, self.head))
        if not null_test or not allowed_exit:
            raise SMTGraphError('Allocation failure must break before later phases; head return is allowed only without reversal/fold')
        if not isinstance(payload, c_ast.Assignment) or payload.op != '=' or not member(payload.lvalue, self.node, self.value):
            raise SMTGraphError('Fresh list payload must be explicitly initialized')
        self.payload_expr = payload.rvalue
        allowed_names = set(self.parameters) | {self.index}
        class Pure(c_ast.NodeVisitor):
            def visit_ID(self, node):
                if node.name not in allowed_names:
                    raise SMTGraphError('List payload must depend only on immutable parameters and index')
            def visit_FuncCall(self, node):raise SMTGraphError('List payload calls unsupported')
            def visit_Assignment(self, node):raise SMTGraphError('List payload side effects unsupported')
            def visit_UnaryOp(self, node):
                if node.op in ('++','p++','--','p--','*','&'):
                    raise SMTGraphError('List payload side effects/memory unsupported')
                self.generic_visit(node)
            def visit_ArrayRef(self, node):raise SMTGraphError('List payload memory reads unsupported')
            def visit_StructRef(self, node):raise SMTGraphError('List payload memory reads unsupported')
        Pure().visit(self.payload_expr)
        if not isinstance(link, c_ast.Assignment) or link.op != '=' or not member(link.lvalue, self.node, self.link) or not identifier(link.rvalue, self.head):
            raise SMTGraphError('Fresh node must link to the previous head')
        if not isinstance(head_write, c_ast.Assignment) or head_write.op != '=' or not identifier(head_write.lvalue, self.head) or not identifier(head_write.rvalue, self.node):
            raise SMTGraphError('List construction must publish the fresh node as head')

    def parse_fold(self, suffix):
        accumulator, loop, returned = suffix
        if not isinstance(accumulator, c_ast.Decl) or _lit(accumulator.init) != 0:
            raise SMTGraphError('List fold requires a zero-initialized scalar accumulator')
        c_type(accumulator, self.model)
        self.accumulator = accumulator
        if not isinstance(loop, c_ast.While) or not nonnull(loop.cond, self.head):
            raise SMTGraphError('List consumption requires while(head)')
        statements = items(loop.stmt)
        if len(statements) != 4:
            raise SMTGraphError('List fold requires next load, payload addition, free and head advance')
        saved, addition, release, advance = statements
        if not isinstance(saved, c_ast.Decl) or pointer_tag(saved) != self.tag or not member(saved.init, self.head, self.link):
            raise SMTGraphError('Next link must be saved before free')
        value = addition.rvalue if isinstance(addition, c_ast.Assignment) else None
        while isinstance(value, c_ast.Cast):
            c_type(value.to_type, self.model)
            value = value.expr
        if not isinstance(addition, c_ast.Assignment) or addition.op != '+=' or not identifier(addition.lvalue, accumulator.name) or not member(value, self.head, self.value):
            raise SMTGraphError('List fold must add the current initialized payload')
        self.fold_addition = copy.deepcopy(addition)
        args = release.args.exprs if isinstance(release, c_ast.FuncCall) and release.args else []
        if not isinstance(release, c_ast.FuncCall) or not identifier(release.name, 'free') or len(args) != 1 or not identifier(args[0], self.head):
            raise SMTGraphError('List fold must free exactly the current head')
        if not isinstance(advance, c_ast.Assignment) or advance.op != '=' or not identifier(advance.lvalue, self.head) or not identifier(advance.rvalue, saved.name):
            raise SMTGraphError('List head must advance to the saved live tail')
        value = returned.expr if isinstance(returned, c_ast.Return) else None
        while isinstance(value, c_ast.Cast):
            c_type(value.to_type, self.model)
            value = value.expr
        if not isinstance(returned, c_ast.Return) or not identifier(value, accumulator.name):
            raise SMTGraphError('List fold must return its accumulator')
        self.fold_return = copy.deepcopy(returned.expr)

    def make_fold(self, max_paths, summaries):
        self.length_name, scan, temporary = self.fresh('length'), self.fresh('scan'), self.fresh('loaded')
        trajectory = self.length_name+'-1-'+scan if self.orientation=='descending' else scan
        reverse = c_parser.CParser().parse('int x(void){return '+trajectory+';}').ext[0].body.block_items[0].expr
        def replace(node):
            if identifier(node, self.index):
                return copy.deepcopy(reverse)
            result = copy.deepcopy(node)
            for slot in result.__slots__:
                if slot in ('coord','__weakref__'):
                    continue
                value = getattr(result, slot)
                if isinstance(value, c_ast.Node):setattr(result, slot, replace(value))
                elif isinstance(value, list):setattr(result, slot, [replace(v) if isinstance(v, c_ast.Node) else v for v in value])
            return result
        expression = self.generator.visit(replace(self.payload_expr))
        name = self.fresh('fold_check')
        addition = copy.deepcopy(self.fold_addition)
        def load(node):
            if isinstance(node, c_ast.Cast):
                node.expr = load(node.expr)
                return node
            return c_ast.ID(temporary)
        addition.rvalue = load(addition.rvalue)
        self.fold_source = self.return_type.name+' '+name+'('+self.parameter_source+', int '+self.length_name+'){'+self.generator.visit(self.accumulator)+';for(int '+scan+'=0;'+scan+'<'+self.length_name+';'+scan+'++){'+self.payload_type_source+' '+temporary+'='+expression+';'+self.generator.visit(addition)+';}return '+self.generator.visit(self.fold_return)+';}'
        limits = self.bounds.get(self.bound, [None,None])
        upper = self.model.types['int'].maximum if limits[1] is None else limits[1]
        self.max_length = max(0, upper)
        self.fold_engine = TypedCNested(self.fold_source, summaries, function=name,
            parameter_bounds={**self.bounds,self.length_name:[0,self.max_length]}, abi=self.abi,
            char_signed=self.char_signed, max_paths=max_paths)

    def report(self, inputs=None, allocation_count=None):
        failure = {'status':'UNKNOWN','c_overflow_verified':False,'memory_safety_verified':False,'termination_proved':False}
        if self.build_report['status'] != 'PROVED_DEFINED_TYPED_C_NESTED':
            return {**failure,'reason':'List payload/index source proof failed','source_proof':self.build_report}
        fold = self.fold_engine.report() if self.fold_engine is not None else None
        if fold is not None and fold['status'] != 'PROVED_DEFINED_TYPED_C_NESTED':
            return {**failure,'reason':'List fold source proof failed','source_proof':fold}
        result = {'status':'PROVED_DEFINED_TYPED_C_LIST_HEAP','abi':self.abi,'function':self.func.decl.name,
            'mode':self.mode,'c_overflow_verified':True,'memory_safety_verified':True,'termination_proved':True,
            'allocation_failure_modeled':True,'allocation_success_assumed':False,
            'unbounded_summary':True,'unbounded_heap_summary':True,'leak_freedom_proved':self.mode=='fold_free',
            'heap_summary':{'length':'m','length_domain':'0 <= m <= Max(0,'+self.bound+')',
                'all_success_case':'m == Max(0,'+self.bound+')','failure_case':'0 <= m < Max(0,'+self.bound+')',
                'abstract_head':'null if m == 0, otherwise allocation_token('+('m' if self.orientation=='descending' else '1')+')',
                'live_nodes':'allocation_token(j), 1 <= j <= m',
                'next':'allocation_token(j-1), with token(0) = null' if self.orientation=='descending' else 'allocation_token(j+1) if j < m, otherwise null',
                'orientation':self.orientation,'reversal_stages':len(self.reversals),'source_reversal_stage_budget':8,
                'traversal_builder_index':'m-1-t' if self.orientation=='descending' else 't',
                'payload_at_node':{'source_expression':self.generator.visit(self.payload_expr),'builder_index':self.index+' = j-1','assignment_type':self.payload_type.name},
                'escapes_build_loop':True,'escapes_function':self.mode=='escape',
                'live_nodes_after_return':'m' if self.mode=='escape' else '0'},
            'memory_model':{**self.memory_model,'max_object_instances':None,'max_cells_per_object':2,'max_total_cells':None,
                'model':'inductively represented fresh acyclic chain with checked in-place reversal; no per-node materialization'},
            'certificate':{'method':'checked C list normal form + universal construction/reversal/traversal induction + typed scalar loop proofs',
                'source_contract':{'record':self.tag,'payload_field':self.value,'next_field':self.link,
                    'head_initially_null':True,'fresh_allocation_before_each_publish':True,
                    'both_fields_initialized_before_publish':True,'null_failure_exits_before_memory_writes':True,
                    'no_external_aliases_or_pointer_identity_observations':True,
                    'saved_next_before_free':self.mode=='fold_free'},
                'shape':self.shape,'reversals':self.reversals,'final_traversal':self.traversal,
                'payload_source':self.build_source,'payload_proof':self.build_report,
                'fold_source':self.fold_source,'fold_proof':fold,
                'fold_domain_overapproximates_all_failure_prefix_lengths':True if fold else None},
            'scope':'fresh acyclic two-field prepend lists with failure-prefix exits; checked in-place reversals and optional additive fold/free; no external aliases or arbitrary heap updates'}
        if inputs is None:
            if allocation_count is not None:raise SMTGraphError('allocation_count requires inputs')
        else:
            self.build_engine.report(inputs)
            count = max(0, inputs[self.bound])
            selected = count if allocation_count is None else allocation_count
            if type(selected) is not int or not 0 <= selected <= count:
                raise SMTGraphError('allocation_count must be a feasible successful-allocation prefix')
            evaluation = {'allocation_count':selected,'all_success_case':selected==count,
                          'conditional_on_selected_allocation_outcome':True,'live_nodes_after_return':selected if self.mode=='escape' else 0,
                          'orientation':self.orientation}
            if self.fold_engine is not None:
                evaluation['value'] = self.fold_engine.report({**inputs,self.length_name:selected})['evaluation']['value']
            result['evaluation'] = evaluation
        return result
