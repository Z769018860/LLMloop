"""Checked composition of a fresh-list builder and its unique owner.

This is a source-contract composition rule, not general inlining. Scalar
arguments must be unchanged identifiers of exactly matching integer types.
The returned footprint has one owner, permits a local nonescaping map cursor,
and is forwarded or consumed by the list fold contract, locally or in a helper.
"""
import copy
import hashlib

from pycparser import c_ast, c_generator, c_parser

from .c_integers import IntegerABI
from .c_validation import validate_automatic_locals
from .list_heap import ListHeapProgram, check_list_map, check_list_reversal, identifier, items, pointer_tag
from .smt_spath import SMTGraphError
from .typed_c import c_type


def walk(node):
    yield node
    for _, child in node.children():
        yield from walk(child)


def rename(node, names):
    """Rename value declarations/references, preserving record tags/fields."""
    result = copy.deepcopy(node)
    if isinstance(result, c_ast.ID):
        result.name = names.get(result.name, result.name)
        return result
    if isinstance(result, c_ast.StructRef):
        result.name = rename(result.name, names)
        return result
    if isinstance(result, c_ast.Decl):
        result.name = names.get(result.name, result.name)
    if isinstance(result, c_ast.TypeDecl):
        result.declname = names.get(result.declname, result.declname)
    for slot in result.__slots__:
        if slot in ('coord', '__weakref__'):
            continue
        value = getattr(result, slot)
        if isinstance(value, c_ast.Node):
            setattr(result, slot, rename(value, names))
        elif isinstance(value, list):
            setattr(result, slot, [rename(v, names) if isinstance(v, c_ast.Node) else v for v in value])
    return result


class ListHeapCallsProgram:
    def __init__(self, source, function=None, parameter_bounds=None, abi='LP64',
                 char_signed=True, max_paths=48, loop_summaries='auto'):
        if not isinstance(source, str) or len(source) > 200000:
            raise SMTGraphError('List call normal form must be at most 200000 characters')
        try:
            unit = c_parser.CParser().parse(source)
        except Exception as exc:
            raise SMTGraphError('List call normal-form parse failed: ' + str(exc)) from exc
        self.generator = c_generator.CGenerator()
        self.model = IntegerABI(abi, char_signed)
        self.bounds = {} if parameter_bounds is None else parameter_bounds
        if not isinstance(self.bounds, dict):
            raise SMTGraphError('List call parameter bounds must be an object')
        functions = [n for n in unit.ext if isinstance(n, c_ast.FuncDef)]
        records = [n for n in unit.ext if isinstance(n, c_ast.Decl) and n.name is None and isinstance(n.type, c_ast.Struct)]
        prototypes = [n for n in unit.ext if isinstance(n, c_ast.Decl) and isinstance(n.type, c_ast.FuncDecl)]
        self.functions = {n.decl.name: n for n in functions}
        if not 2 <= len(functions) <= 11 or len(self.functions) != len(functions) or len(records) != 1 or len(unit.ext) != len(functions)+1+len(prototypes):
            raise SMTGraphError('List calls need one record, entry, builder, optional reversal/map helpers and consumer, without globals')
        if function not in self.functions or set(self.functions) & {'calloc', 'malloc', 'free'}:
            raise SMTGraphError('Select an available list call entry with distinct non-builtin function names')
        for prototype in prototypes:
            if prototype.name not in self.functions or self.generator.visit(prototype) != self.generator.visit(self.functions[prototype.name].decl):
                raise SMTGraphError('List call prototypes must match their normalized definitions exactly')
        self.used = {n.name for n in walk(unit) if isinstance(n, c_ast.Decl) and n.name}
        self.function = function
        entry = self.functions[function]
        for fn in functions:
            self.validate_function(fn)
        params = entry.decl.type.args.params if entry.decl.type.args else []
        if not params or not all(isinstance(p, c_ast.Decl) and p.name for p in params):
            raise SMTGraphError('List call entry needs named scalar parameters')
        parameter_types = {p.name: c_type(p, self.model) for p in params}
        if set(self.bounds)-set(parameter_types):
            raise SMTGraphError('Unknown list call entry parameter bound')
        body = entry.body.block_items or []
        if len(body) < 2:
            raise SMTGraphError('List call entry must bind one builder result, optionally reverse, then return or consume it')
        head = body[0]
        if not isinstance(head, c_ast.Decl) or not isinstance(head.init, c_ast.FuncCall) or not isinstance(head.init.name, c_ast.ID):
            raise SMTGraphError('List call entry needs a pointer initialized by a direct builder call')
        builder_name = head.init.name.name
        if builder_name == function or builder_name not in self.functions:
            raise SMTGraphError('List builder must be a separate available direct helper')
        builder = self.functions[builder_name]
        builder_params = builder.decl.type.args.params if builder.decl.type.args else []
        actuals = head.init.args.exprs if head.init.args else []
        if len(actuals) != len(builder_params):
            raise SMTGraphError('List builder call arity mismatch')
        arguments = {}
        for formal, actual in zip(builder_params, actuals):
            if not isinstance(formal, c_ast.Decl) or not formal.name or not isinstance(actual, c_ast.ID) or actual.name not in parameter_types or c_type(formal, self.model) != parameter_types[actual.name]:
                raise SMTGraphError('List builder arguments require unchanged scalar identifiers with identical parameter types')
            arguments[formal.name] = actual.name
        record_source = self.generator.visit(records[0])+';\n'
        builder_source = record_source+self.generator.visit(builder)
        builder_bounds = {formal:self.bounds[actual] for formal, actual in arguments.items() if actual in self.bounds}
        self.builder = ListHeapProgram(builder_source, function=builder_name,
            parameter_bounds=builder_bounds, abi=abi, char_signed=char_signed, max_paths=max_paths)
        if self.builder.mode != 'escape' or pointer_tag(head) != self.builder.tag:
            raise SMTGraphError('Builder must transfer a live same-record list head to its unique caller owner')
        self.arguments = arguments
        self.builder_name = builder_name
        self.consumer_name = None
        suffix = copy.deepcopy(body[1:])
        used_functions = {function, builder_name}
        pipeline=[];self.reversal_helpers=[];self.map_helpers=[];self.heap_helpers=[]
        while suffix:
            first=suffix[0]
            if isinstance(first,c_ast.Decl) and pointer_tag(first)==self.builder.tag:
                if len(self.heap_helpers)>=8:raise SMTGraphError('At most eight source heap stages are supported')
                if identifier(first.init,head.name):
                    stage=suffix[:2]
                    contract=check_list_map(stage,head.name,self.builder.tag,self.builder.link,self.builder.value,parameter_types)
                    contract.pop('expression')
                    metadata={'callee':None,'source_contract':contract,'unique_owned_chain_precondition':True,'kind':'payload_map'}
                    pipeline.extend(stage);suffix=suffix[2:]
                    self.map_helpers.append(metadata);self.heap_helpers.append(metadata)
                    continue
                stage=suffix[:3]
                contract=check_list_reversal(stage,head.name,self.builder.tag,self.builder.link)
                pipeline.extend(stage);suffix=suffix[3:]
                metadata={'callee':None,'source_contract':contract,'unique_owned_chain_precondition':True,'kind':'reversal'}
                self.reversal_helpers.append(metadata);self.heap_helpers.append(metadata)
                continue
            if isinstance(first,c_ast.FuncCall):
                if len(self.heap_helpers)>=8:raise SMTGraphError('At most eight source heap stages are supported')
                name=first.name.name if isinstance(first.name,c_ast.ID) else None
                if name in (function,builder_name) or name not in self.functions:
                    raise SMTGraphError('Payload map must call a separate available borrowed-chain helper')
                helper=self.functions[name]
                returned=helper.decl.type.type
                formals=helper.decl.type.args.params if helper.decl.type.args else []
                actuals=first.args.exprs if first.args else []
                if not isinstance(returned,c_ast.TypeDecl) or not isinstance(returned.type,c_ast.IdentifierType) or returned.type.names!=['void'] or not formals or len(actuals)!=len(formals) or not isinstance(formals[0],c_ast.Decl) or pointer_tag(formals[0])!=self.builder.tag or not identifier(actuals[0],head.name):
                    raise SMTGraphError('Payload map helper must return void and borrow the same-record owned head')
                mapping=self.local_names(helper)
                cursor='__list_call_cursor'
                while cursor in self.used:cursor+='_'
                self.used.add(cursor);mapping[formals[0].name]=cursor
                for formal,actual in zip(formals[1:],actuals[1:]):
                    if not isinstance(formal,c_ast.Decl) or not isinstance(actual,c_ast.ID) or actual.name not in parameter_types or c_type(formal,self.model)!=parameter_types[actual.name]:
                        raise SMTGraphError('Payload map scalar arguments require immutable identifiers with identical types')
                    mapping[formal.name]=actual.name
                borrowed=rename(formals[0],mapping);borrowed.init=c_ast.ID(head.name)
                borrowed.storage=[]
                stage=[borrowed]+(rename(helper.body,mapping).block_items or [])
                contract=check_list_map(stage,head.name,self.builder.tag,self.builder.link,self.builder.value,parameter_types)
                contract.pop('expression')
                metadata={'kind':'payload_map','callee':name,'source_contract':contract,
                          'source_sha256':hashlib.sha256(self.generator.visit(helper).encode()).hexdigest(),
                          'unique_owned_chain_precondition':True,'borrowed_cursor_does_not_escape':True,
                          'same_footprint_head_and_links_preserved':True}
                pipeline.extend(stage);suffix=suffix[1:];used_functions.add(name)
                self.map_helpers.append(metadata);self.heap_helpers.append(metadata)
                continue
            if not isinstance(first,c_ast.Assignment) or first.op!='=' or not identifier(first.lvalue,head.name) or not isinstance(first.rvalue,c_ast.FuncCall):break
            if len(self.heap_helpers)>=8:raise SMTGraphError('At most eight source heap stages are supported')
            call=first.rvalue
            name=call.name.name if isinstance(call.name,c_ast.ID) else None
            if name in (function,builder_name) or name not in self.functions:
                raise SMTGraphError('Reversal must call a separate available owned-chain helper')
            helper=self.functions[name]
            formals=helper.decl.type.args.params if helper.decl.type.args else []
            actuals=call.args.exprs if call.args else []
            if pointer_tag(helper.decl.type)!=self.builder.tag or len(formals)!=1 or not isinstance(formals[0],c_ast.Decl) or pointer_tag(formals[0])!=self.builder.tag or len(actuals)!=1 or not identifier(actuals[0],head.name):
                raise SMTGraphError('Reversal helper must take and return exactly the unique owned same-record head')
            mapping=self.local_names(helper);mapping[formals[0].name]=head.name
            stage=rename(helper.body,mapping).block_items or []
            if len(stage)!=3 or not isinstance(stage[-1],c_ast.Return):
                raise SMTGraphError('Reversal helper must return its complete reversed prefix')
            stage[-1]=c_ast.Assignment('=',c_ast.ID(head.name),stage[-1].expr)
            contract=check_list_reversal(stage,head.name,self.builder.tag,self.builder.link)
            pipeline.extend(stage);suffix=suffix[1:];used_functions.add(name)
            metadata={'kind':'reversal','callee':name,'source_contract':contract,
                'source_sha256':hashlib.sha256(self.generator.visit(helper).encode()).hexdigest(),
                'unique_owned_chain_precondition':True,'same_footprint_and_payloads_returned':True}
            self.reversal_helpers.append(metadata);self.heap_helpers.append(metadata)
        if len(suffix) not in (1,3):raise SMTGraphError('List ownership pipeline must end in head return or checked fold/free')
        if len(suffix) == 1 and isinstance(suffix[0], c_ast.Return):
            caller_return=copy.deepcopy(suffix[0].expr)
            value = caller_return
            while isinstance(value, c_ast.Cast):
                c_type(value.to_type, self.model)
                value = value.expr
            if isinstance(value, c_ast.FuncCall):
                consumer_name = value.name.name if isinstance(value.name, c_ast.ID) else None
                if consumer_name in used_functions or consumer_name not in self.functions:
                    raise SMTGraphError('List consumer must be a separate available direct helper')
                consumer = self.functions[consumer_name]
                consumer_params = consumer.decl.type.args.params if consumer.decl.type.args else []
                consumer_args = value.args.exprs if value.args else []
                if len(consumer_params) != 1 or not isinstance(consumer_params[0], c_ast.Decl) or pointer_tag(consumer_params[0]) != self.builder.tag or len(consumer_args) != 1 or not identifier(consumer_args[0], head.name):
                    raise SMTGraphError('List consumer must take exactly the unique owned list head')
                return_type = c_type(consumer.decl, self.model)
                mapping = self.local_names(consumer)
                mapping[consumer_params[0].name] = head.name
                suffix = rename(consumer.body, mapping).block_items or []
                if len(suffix) != 3 or not isinstance(suffix[-1], c_ast.Return):
                    raise SMTGraphError('List consumer must have the checked accumulator, fold/free and return suffix')
                # Reify the callee's return conversion before any caller casts
                # and the caller's own return conversion. Neither may be erased.
                converted = c_parser.CParser().parse('int x(void){return ('+return_type.name+')0;}').ext[0].body.block_items[0].expr
                converted.expr = suffix[-1].expr
                def replace_call(node):
                    if isinstance(node, c_ast.Cast):
                        result = copy.deepcopy(node)
                        result.expr = replace_call(node.expr)
                        return result
                    return copy.deepcopy(converted)
                suffix[-1].expr = replace_call(caller_return)
                self.consumer_name = consumer_name
                used_functions.add(consumer_name)
        if used_functions != set(self.functions):
            raise SMTGraphError('Every normalized list call helper must participate in the checked ownership chain')
        mapping = self.local_names(builder)
        mapping.update(arguments)
        mapping[self.builder.head] = head.name
        builder_head = rename(builder.body.block_items[0], mapping)
        builder_loop = rename(self.builder.loop, mapping)
        builder_middle=rename(c_ast.Compound(builder.body.block_items[2:-1]),mapping).block_items or []
        # The validated builder has only `return head` after its loop. A null
        # failure return therefore transfers the same prefix as a loop break.
        failure = items(builder_loop.stmt)[1]
        failure_return = isinstance(items(failure.iftrue)[0], c_ast.Return)
        if failure_return:
            failure.iftrue = c_ast.Compound([c_ast.Break()])
        composed = copy.deepcopy(entry)
        composed.body.block_items = [builder_head, builder_loop]+builder_middle+pipeline+suffix
        self.composed_source = record_source+self.generator.visit(composed)
        self.program = ListHeapProgram(self.composed_source, function=function,
            parameter_bounds=self.bounds, abi=abi, char_signed=char_signed,
            max_paths=max_paths, loop_summaries=loop_summaries)
        self.contract = {'method':'checked fresh-list ownership transfer and scalar-preserving source-contract composition',
            'builder':builder_name, 'consumer':self.consumer_name or 'entry suffix',
            'argument_bindings':arguments, 'argument_conversions':'identity only; exact integer types checked',
            'builder_return_contract_checked':True, 'unique_owner_no_external_aliases':True,
            'allocation_failure_prefix_transferred':True, 'builder_failure_return_becomes_loop_exit':failure_return,
            'callee_then_caller_return_conversions_preserved':self.consumer_name is not None,
            'helper_locals_alpha_renamed':True, 'composed_source':self.composed_source,
            'reversal_helpers':self.reversal_helpers,'builder_reversal_stages':len(self.builder.reversals),
            'payload_map_helpers':self.map_helpers,'heap_helpers_in_source_order':self.heap_helpers,
            'builder_payload_map_stages':len(self.builder.maps),
            'composed_source_sha256':hashlib.sha256(self.composed_source.encode()).hexdigest(),
            'general_interprocedural_heap_analysis':False}

    def validate_function(self, function):
        if function.decl.funcspec or function.decl.quals:
            raise SMTGraphError('Attributed/qualified list call functions unsupported')
        names = set()
        for node in walk(function):
            if isinstance(node, c_ast.Decl) and not isinstance(node.type, c_ast.FuncDecl):
                if not node.name or node.name in names or node.name in set(self.functions) | {'calloc','malloc','free'}:
                    raise SMTGraphError('List call declarations need unique names that do not shadow callable names')
                names.add(node.name)
            if getattr(node, 'quals', None):
                raise SMTGraphError('Qualified list call declarators unsupported')
        validate_automatic_locals(function, SMTGraphError)

    def local_names(self, function):
        result = {}
        for node in walk(function.body):
            if isinstance(node, c_ast.Decl) and node.name:
                fresh = '__list_call_'+node.name
                while fresh in self.used:
                    fresh += '_'
                self.used.add(fresh)
                result[node.name] = fresh
        return result

    def report(self, inputs=None, allocation_count=None):
        builder_inputs = None if inputs is None else {formal:inputs[actual] for formal, actual in self.arguments.items() if actual in inputs}
        # Validate the full entry domain before selecting a helper's arguments.
        result = self.program.report(inputs, allocation_count)
        builder = self.builder.report(builder_inputs, allocation_count)
        if builder['status'] != 'PROVED_DEFINED_TYPED_C_LIST_HEAP':
            return {'status':'UNKNOWN','reason':'List builder contract failed',
                'c_overflow_verified':False,'memory_safety_verified':False,'termination_proved':False,
                'source_proof':builder}
        if result['status'] != 'PROVED_DEFINED_TYPED_C_LIST_HEAP':
            return result
        result['status'] = 'PROVED_DEFINED_TYPED_C_LIST_CALLS'
        result['interprocedural_heap_summary'] = True
        result['certificate']['composition'] = {**self.contract,'builder_proof':builder}
        result['scope'] = 'one fresh prepend builder transfers its footprint through checked reversal and nonescaping borrowed pointwise-map stages to one caller/consumer; forwarding or additive fold/free; no arbitrary aliases, calls, recursion or shapes'
        return result
