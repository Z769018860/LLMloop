"""Admitted Clang array/pointer and direct-call AST normalization.

This is a trusted structural frontend, not an LLVM interpreter. The receiving
typed kernels retain their finite memory, alias, lifetime and call budgets.
"""
import re

from .clang_proof import ScalarNormalizer, nodes
from .smt_spath import SMTGraphError


BUILTINS = {'malloc', 'calloc', 'free'}


class MemoryNormalizer(ScalarNormalizer):
    def __init__(self, frontend, callables=()):
        super().__init__(frontend)
        self.callables = set(callables)
        self.memory_used = False
        self.builtins = {n['id']: n for n in frontend.get('modeled_function_declarations', [])}
        self.record_defs = {}
        self.used_records = set()
        for record in frontend.get('record_definitions', []):
            self.record_defs.setdefault(record.get('name'), []).append(record)

    def check_builtin(self, ref):
        declaration = self.builtins.get(ref.get('id'))
        if declaration is None:
            raise SMTGraphError('Modeled allocator declaration missing from Clang AST')
        allowed = {'ParmVarDecl', 'BuiltinAttr', 'AllocSizeAttr', 'RestrictAttr', 'NoThrowAttr', 'WarnUnusedResultAttr', 'ReturnsNonNullAttr'}
        if any(child.get('kind') not in allowed for child in declaration.get('inner', [])):
            raise SMTGraphError('Unsupported attributes/body on modeled allocator declaration')
        triple = self.frontend['target']['triple']
        size_type = 'unsigned long long' if triple.startswith('x86_64-') and '-windows-' in triple else 'unsigned long' if triple.startswith('x86_64-') else 'unsigned int'
        signature = ref['type'].get('desugaredQualType', ref['type']['qualType'])
        for alias, values in self.aliases.items():
            if len(values) == 1 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', alias):
                signature = re.sub(r'\b' + re.escape(alias) + r'\b', next(iter(values)), signature)
        expected = {'malloc': 'void *(' + size_type + ')', 'calloc': 'void *(' + size_type + ', ' + size_type + ')', 'free': 'void (void *)'}[ref['name']]
        if re.sub(r'\s+', '', signature) != re.sub(r'\s+', '', expected):
            raise SMTGraphError('Modeled allocator signature does not match target C library contract')

    def memory_type(self, value, seen=()):
        text = value.get('desugaredQualType', value.get('qualType', '')) if isinstance(value, dict) else value
        if not isinstance(text, str):
            raise SMTGraphError('Clang memory type missing')
        text = ' '.join(text.split())
        if re.search(r'\b(const|volatile|restrict|_Atomic)\b', text):
            raise SMTGraphError('Qualified Clang memory types unsupported')
        base = text.rstrip('* ').strip()
        suffix = text[len(base):]
        stars = suffix.count('*')
        if suffix.replace('*', '').strip() or stars > 3:
            raise SMTGraphError('Unsupported Clang pointer declarator')
        if base in self.aliases and len(self.aliases[base]) == 1:
            if base in seen:
                raise SMTGraphError('Cyclic Clang type alias')
            scalar = self.memory_type(next(iter(self.aliases[base])), seen + (base,))
        elif re.fullmatch(r'struct [A-Za-z_][A-Za-z0-9_]*', base):
            tag = base.split()[1]
            if len(self.record_defs.get(tag, [])) != 1:
                raise SMTGraphError('Unique named Clang struct definition required')
            self.used_records.add(tag)
            scalar = base
        else:
            scalar = super().type(base)
        result = scalar + ' *' * stars
        if result.count('*') > 3:
            raise SMTGraphError('Clang pointer indirection budget is 3')
        return result

    def array_type(self, value):
        text = value.get('desugaredQualType', value.get('qualType', ''))
        match = re.fullmatch(r'(.+?)\s*\[(\d+)\]', text)
        if not match or not 1 <= int(match[2]) <= 8:
            raise SMTGraphError('Clang arrays require one constant dimension of 1..8 cells')
        return self.memory_type(match[1]), int(match[2])

    def expr(self, node):
        kind = node.get('kind')
        children = node.get('inner', [])
        if kind == 'ImplicitValueInitExpr' and '*' in node.get('type', {}).get('qualType', ''):
            return '0'
        if kind == 'DeclRefExpr':
            ref = node.get('referencedDecl', {})
            if ref.get('kind') == 'FunctionDecl' and ref.get('name') in self.callables | BUILTINS:
                return ref['name']
            if ref.get('id') in self.names:
                # Only declarations validated by decl/source may introduce these names.
                return self.names[ref['id']]
        if kind == 'ImplicitCastExpr' and len(children) == 1:
            cast = node.get('castKind')
            if cast in ('LValueToRValue', 'ArrayToPointerDecay', 'FunctionToPointerDecay'):
                return self.expr(children[0])
            if cast == 'NullToPointer':
                child = children[0]
                while child.get('kind') in ('ParenExpr', 'ConstantExpr') and len(child.get('inner', [])) == 1:
                    child = child['inner'][0]
                if child.get('kind') == 'IntegerLiteral' and int(child.get('value', -1)) == 0:
                    return '0'
                raise SMTGraphError('Only literal-zero Clang null pointer conversion supported')
            if cast == 'PointerToBoolean':
                return '(' + self.expr(children[0]) + ' != 0)'
            if cast == 'BitCast':
                # Allocators have void* result; the memory kernel binds them to the
                # destination type. All other reinterpretation is refused.
                self.memory_type(node['type'])
                if self.allocator(children[0]):
                    return self.expr(children[0])
                raise SMTGraphError('Clang pointer reinterpretation unsupported')
        if kind == 'CStyleCastExpr' and len(children) == 1 and '*' in node['type']['qualType']:
            pointer_text = node['type'].get('desugaredQualType', node['type']['qualType'])
            target = 'void *' if pointer_text == 'void *' else self.memory_type(node['type'])
            if children[0].get('kind') == 'IntegerLiteral' and children[0].get('value') == '0':
                return '0'
            if self.allocator(children[0]):
                return self.expr(children[0])
            if target == self.memory_type(children[0]['type']):
                return self.expr(children[0])
            raise SMTGraphError('Clang pointer casts require identical types or allocator results')
        if kind == 'CStyleCastExpr' and node.get('castKind') in ('PointerToIntegral', 'PointerToBoolean'):
            raise SMTGraphError('Explicit Clang pointer-to-integer casts unsupported')
        if kind == 'ArraySubscriptExpr' and len(children) == 2:
            self.memory_used = True
            return '(' + self.expr(children[0]) + ')[' + self.expr(children[1]) + ']'
        if kind == 'MemberExpr' and node.get('isArrow') and len(children) == 1:
            name = node.get('name', '')
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                raise SMTGraphError('Named Clang struct member required')
            self.memory_type(children[0]['type'])
            self.memory_used = True
            return '(' + self.expr(children[0]) + ')->' + name
        if kind == 'UnaryOperator' and len(children) == 1 and node.get('opcode') in ('*', '&'):
            self.memory_used = True
            return '(' + node['opcode'] + '(' + self.expr(children[0]) + '))'
        if kind == 'BinaryOperator' and len(children) == 2:
            pointer_operands = ['*' in child.get('type', {}).get('qualType', '') for child in children]
            if any(pointer_operands) and node.get('opcode') in ('<', '<=', '>', '>='):
                raise SMTGraphError('Clang pointer ordering unsupported')
            if all(pointer_operands) and node.get('opcode') == '-':
                raise SMTGraphError('Clang pointer difference unsupported')
        if kind == 'BinaryOperator' and len(children) == 2 and '*' in node.get('type', {}).get('qualType', ''):
            if node.get('opcode') not in ('+', '-'):
                raise SMTGraphError('Unsupported Clang pointer operator')
            self.memory_type(node['type'])
            base = children[0]
            while base.get('kind') in ('ParenExpr', 'ImplicitCastExpr') and len(base.get('inner', [])) == 1:
                if base.get('kind') == 'ImplicitCastExpr' and base.get('castKind') not in ('NoOp', 'LValueToRValue', 'ArrayToPointerDecay'):
                    raise SMTGraphError('Clang pointer arithmetic requires a represented pointer base')
                base = base['inner'][0]
            if base.get('kind') not in ('DeclRefExpr', 'MemberExpr', 'ArraySubscriptExpr', 'UnaryOperator', 'BinaryOperator'):
                raise SMTGraphError('Clang pointer arithmetic requires a represented pointer base')
            return '(' + self.expr(children[0]) + node['opcode'] + self.expr(children[1]) + ')'
        if kind == 'CallExpr' and children:
            callee = children[0]
            while callee.get('kind') in ('ImplicitCastExpr', 'ParenExpr') and len(callee.get('inner', [])) == 1:
                callee = callee['inner'][0]
            ref = callee.get('referencedDecl', {})
            if callee.get('kind') != 'DeclRefExpr' or ref.get('kind') != 'FunctionDecl' or ref.get('name') not in self.callables | BUILTINS:
                raise SMTGraphError('Clang proof requires an available direct function call')
            if ref['name'] in BUILTINS:
                self.check_builtin(ref)
            args = children[1:]
            if ref['name'] == 'free' and len(args) == 1 and args[0].get('kind') == 'ImplicitCastExpr' and args[0].get('castKind') == 'BitCast' and args[0].get('type', {}).get('qualType') == 'void *':
                args = args[0]['inner']
            return ref['name'] + '(' + ', '.join(self.expr(child) for child in args) + ')'
        if kind == 'UnaryExprOrTypeTraitExpr' and node.get('name') == 'sizeof':
            value = node.get('argType') or (children[0].get('type') if len(children) == 1 else None)
            if value and ('*' in value.get('qualType', '') or 'struct ' in value.get('desugaredQualType', value.get('qualType', ''))):
                return 'sizeof(' + self.memory_type(value) + ')'
        return super().expr(node)

    @staticmethod
    def allocator(node):
        while node.get('kind') in ('ParenExpr',) and len(node.get('inner', [])) == 1:
            node = node['inner'][0]
        if node.get('kind') != 'CallExpr' or not node.get('inner'):
            return False
        return any(n.get('kind') == 'DeclRefExpr' and n.get('referencedDecl', {}).get('name') in ('malloc', 'calloc') for n in nodes(node['inner'][0]))

    def action(self, node):
        children = node.get('inner', [])
        if node.get('kind') in ('BinaryOperator', 'CompoundAssignOperator') and node.get('opcode') in ('=', '+=', '-=', '*=', '/=', '%=', '<<=', '>>=', '&=', '|=', '^=') and len(children) == 2:
            if children[0].get('kind') not in ('DeclRefExpr', 'ArraySubscriptExpr', 'UnaryOperator', 'MemberExpr'):
                raise SMTGraphError('Unsupported Clang memory lvalue')
            if children[0].get('kind') == 'UnaryOperator' and children[0].get('opcode') != '*':
                raise SMTGraphError('Unsupported Clang unary lvalue')
            return self.expr(children[0]) + ' ' + node['opcode'] + ' ' + self.expr(children[1])
        if node.get('kind') == 'UnaryOperator' and node.get('opcode') in ('++', '--') and len(children) == 1:
            return self.expr(children[0]) + node['opcode']
        return super().action(node)

    def decl(self, node):
        text = node.get('type', {}).get('desugaredQualType', node.get('type', {}).get('qualType', ''))
        if '*' not in text and '[' not in text:
            return super().decl(node)
        if node.get('storageClass') or node.get('tls'):
            raise SMTGraphError('Only automatic Clang memory declarations supported')
        self.memory_used = True
        children = node.get('inner', [])
        if '[' in text:
            element, length = self.array_type(node['type'])
            if not children:
                initializer = ''
            elif len(children) == 1 and children[0].get('kind') == 'InitListExpr':
                init = children[0]
                values = init.get('inner', [])
                if init.get('array_filler'):
                    # Clang's semantic filler array starts with the default value,
                    # followed by explicit elements in array-index order.
                    values = init['array_filler'][1:]
                if len(values) > length:
                    raise SMTGraphError('Excess Clang array initializers')
                initializer = ' = {' + ', '.join(self.expr(value) for value in values) + '}'
            else:
                raise SMTGraphError('Unsupported Clang array initializer/attributes')
            return element + ' ' + self.names[node['id']] + '[' + str(length) + ']' + initializer
        if len(children) != 1:
            raise SMTGraphError('Clang pointers require one initializer and no attributes')
        return self.memory_type(node['type']) + ' ' + self.names[node['id']] + ' = ' + self.expr(children[0])

    def stmt(self, node):
        if node.get('kind') == 'ReturnStmt' and not node.get('inner'):
            return 'return;'
        if node.get('kind') == 'CallExpr':
            return self.expr(node) + ';'
        return super().stmt(node)

    def source(self):
        children = self.root.get('inner', [])
        if any(n.get('kind') not in ('ParmVarDecl', 'CompoundStmt', 'FullComment') for n in children):
            raise SMTGraphError('Unsupported Clang function attributes/declarations')
        bodies = [n for n in children if n.get('kind') == 'CompoundStmt']
        if len(bodies) != 1:
            raise SMTGraphError('One Clang function body required')
        signature = self.root['type'].get('desugaredQualType', self.root['type']['qualType'])
        if '...' in signature:
            raise SMTGraphError('Variadic Clang proof entry unsupported')
        result = signature.split('(', 1)[0].strip()
        result = 'void' if result == 'void' else self.memory_type(result)
        params = [n for n in children if n.get('kind') == 'ParmVarDecl']
        declarations_to_check = [declaration for declaration in self.frontend.get('function_parameter_declarations', []) if declaration['name'] == self.root['name']]
        if not declarations_to_check:
            raise SMTGraphError('Clang original parameter declaration metadata required')
        for declaration in declarations_to_check:
            spellings = declaration['parameter_spellings']
            for param in declaration['parameters']:
                resolved = self.memory_type(param['type'])
                if '*' not in resolved:
                    continue
                raw = spellings.get(param['id'], '')
                if param.get('name'):
                    match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_\s*]*?)\s*\b' + re.escape(param['name']) + r'\s*', raw)
                    prefix = match[1].strip() if match else ''
                else:
                    prefix = raw if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_\s*]*', raw) else ''
                if not prefix or self.memory_type(prefix) != resolved:
                    raise SMTGraphError('Clang pointer parameters require literal pointer declarators in every original declaration; adjusted arrays/VLAs and macro/header spellings unsupported')
        declarations = ', '.join(self.memory_type(n['type']) + ' ' + self.names[n['id']] for n in params) or 'void'
        return result + ' ' + self.root['name'] + '(' + declarations + ') ' + self.stmt(bodies[0]) + '\n'


def normalize_calls(frontend, function):
    functions = {fn['name']: fn for fn in frontend['functions']}
    if function is None:
        if len(functions) != 1:
            raise SMTGraphError('Select the Clang proof entry function')
        function = next(iter(functions))
    if function not in functions:
        raise SMTGraphError('Clang call entry function unavailable')
    if set(functions) & BUILTINS:
        raise SMTGraphError('User-defined allocator/free semantics unsupported')
    selected = set()
    pending = [function]
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        if len(selected) > 16:
            raise SMTGraphError('Clang call proof supports at most 16 reachable functions')
        for node in nodes(functions[name]['ast']):
            if node.get('kind') == 'DeclRefExpr' and node.get('referencedDecl', {}).get('kind') == 'FunctionDecl':
                callee = node['referencedDecl']['name']
                if callee in functions:
                    pending.append(callee)
                elif callee not in BUILTINS:
                    raise SMTGraphError('External Clang call lacks a verified definition: ' + callee)
    normalizers = [MemoryNormalizer({**frontend, 'functions': [functions[name]]}, selected) for name in sorted(selected)]
    sources = [normalizer.source() for normalizer in normalizers]
    prototypes = [source.split('{', 1)[0].strip() + ';' for source in sources]
    return '\n'.join(prototypes + sources), normalizers, function


def record_source(normalizers):
    """Emit only reachable, naturally laid-out named record definitions."""
    emitted = {}
    for normalizer in normalizers:
        pending = list(normalizer.used_records)
        while pending:
            tag = pending.pop()
            if tag in emitted:
                continue
            record = normalizer.record_defs[tag][0]
            fields = record.get('inner', [])
            if record.get('tagUsed') != 'struct' or not 1 <= len(fields) <= 8:
                raise SMTGraphError('Clang records require 1..8 named struct fields')
            declarations = []
            for field in fields:
                name = field.get('name', '')
                if field.get('kind') != 'FieldDecl' or field.get('isBitfield') or field.get('inner') or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
                    raise SMTGraphError('Clang packed/attributed/anonymous/bitfield records unsupported')
                value_type = normalizer.memory_type(field['type'])
                if '[' in value_type or value_type.startswith('struct ') and '*' not in value_type:
                    raise SMTGraphError('Clang by-value/array record members unsupported')
                declarations.append(value_type + ' ' + name + ';')
            emitted[tag] = 'struct ' + tag + ' {' + ' '.join(declarations) + '};'
            pending.extend(normalizer.used_records - set(emitted))
    if len(emitted) > 8:
        raise SMTGraphError('Clang record budget is 8')
    return '\n'.join(emitted.values()), set(emitted)


def check_record_layouts(frontend, result, tags):
    layouts = result.get('memory_model', {}).get('struct_layouts', {})
    correspondence = {}
    for tag in sorted(tags):
        candidates = [layout for layout in frontend.get('record_layouts', []) if layout['name'] == 'struct ' + tag]
        if len(candidates) != 1 or tag not in layouts:
            raise SMTGraphError('Clang record layout correspondence missing: ' + tag)
        clang = candidates[0]
        model = layouts[tag]
        expected = [(member['field'], member['offset']) for member in model['members']]
        actual = [(member['declaration'].split()[-1].lstrip('*'), member['offset_bytes']) for member in clang['members']]
        if model['size'] != clang['size_bytes'] or model['alignment'] != clang['alignment_bytes'] or expected != actual:
            raise SMTGraphError('Clang record layout differs from proof model: ' + tag)
        correspondence[tag] = {'size_bytes': model['size'], 'alignment_bytes': model['alignment'], 'member_offsets': expected}
    return correspondence
