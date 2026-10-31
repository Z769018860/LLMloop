"""Declaration-checked Clang clz/ctz lowering for the direct-call backend.

Models are ordinary typed C helpers, not assumed pure/safe external contracts.
Their argument is bound once by call expansion; zero remains undefined through
an explicit divide-by-zero obligation. Compiler/normalizer trust is unchanged.
"""
import hashlib
import re

from .c_integers import IntegerABI
from .smt_spath import SMTGraphError


BIT_BUILTINS = {
    '__builtin_' + operation + suffix: (operation, ctype)
    for operation in ('clz', 'ctz')
    for suffix, ctype in (('', 'unsigned int'), ('l', 'unsigned long'), ('ll', 'unsigned long long'))
}


def bit_count_helper(name, operation, ctype, width):
    """Balanced sums keep the existing expression/AST depth limits unchanged."""
    if operation not in ('clz', 'ctz') or width not in (32, 64) or ctype not in ('unsigned int', 'unsigned long', 'unsigned long long'):
        raise SMTGraphError('Unsupported bit-count helper contract')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise SMTGraphError('Invalid bit-count helper identifier')
    suffix = {'unsigned int': 'U', 'unsigned long': 'UL', 'unsigned long long': 'ULL'}[ctype]
    # For nonzero x: clz counts thresholds above x, ctz counts zero low prefixes.
    terms = ['(x < ' + str(1 << bit) + suffix + ')' for bit in range(1, width)] if operation == 'clz' else [
        '((x % ' + str(1 << bit) + suffix + ') == 0)' for bit in range(1, width)]
    def balanced(values):
        while len(values) > 1:
            values = ['(' + values[i] + ' + ' + values[i + 1] + ')' if i + 1 < len(values) else values[i] for i in range(0, len(values), 2)]
        return values[0]
    # Separate small expressions also respect the typed kernel's 256-node limit.
    parts = [terms[i:i + 16] for i in range(0, len(terms), 16)]
    declarations = ' '.join('int count' + str(i) + ' = ' + balanced(part) + ';' for i, part in enumerate(parts))
    result = balanced(['count' + str(i) for i in range(len(parts))])
    return 'int ' + name + '(' + ctype + ' x) { ' + declarations + ' return ' + result + ' / (x != 0); }\n'


class BitBuiltinModels:
    def __init__(self, frontend, used):
        self.declarations = {n['id']: n for n in frontend.get('external_function_declarations', [])}
        self.used = set(used)
        self.models = {}
        triple = frontend['target']['triple']
        if triple.startswith('x86_64-') and (triple.endswith(('linux-gnu', 'linux-musl')) or '-windows-' in triple):
            abi = 'LLP64' if '-windows-' in triple else 'LP64'
        elif re.match(r'i[3-6]86-', triple) and triple.endswith(('linux-gnu', 'linux-musl')):
            abi = 'ILP32'
        else:
            raise SMTGraphError('Bit builtins require an admitted x86 ABI')
        self.abi = IntegerABI(abi)

    def model(self, ref, node):
        name = ref.get('name')
        if name not in BIT_BUILTINS:
            raise SMTGraphError('Unsupported Clang bit builtin')
        operation, ctype = BIT_BUILTINS[name]
        declaration = self.declarations.get(ref.get('id'))
        if declaration is None or declaration.get('name') != name:
            raise SMTGraphError('Clang bit builtin declaration identity missing')
        children = declaration.get('inner', [])
        attrs = [n for n in children if n.get('kind') != 'ParmVarDecl']
        if any(n.get('kind') not in ('BuiltinAttr', 'NoThrowAttr', 'ConstAttr', 'FullComment') for n in attrs) or not any(n.get('kind') == 'BuiltinAttr' and n.get('implicit') is True for n in attrs):
            raise SMTGraphError('Clang bit builtin requires compiler-owned BuiltinAttr and no body/extra attributes')
        expected = 'int (' + ctype + ')'
        compact = lambda value: re.sub(r'\s+', '', value.get('desugaredQualType', value.get('qualType', '')))
        params = [n for n in children if n.get('kind') == 'ParmVarDecl']
        args = node.get('inner', [])[1:]
        if compact(declaration.get('type', {})) != expected.replace(' ', '') or compact(ref.get('type', {})) != expected.replace(' ', '') or len(params) != 1 or compact(params[0].get('type', {})) != ctype.replace(' ', '') or len(args) != 1 or compact(args[0].get('type', {})) != ctype.replace(' ', '') or compact(node.get('type', {})) != 'int':
            raise SMTGraphError('Clang bit builtin signature/converted argument/result differs from target contract')
        if name not in self.models:
            width = self.abi.types[ctype].bits
            serial = 1
            while '__clang_bit_' + operation + '_' + str(serial) in self.used:
                serial += 1
            helper = '__clang_bit_' + operation + '_' + str(serial)
            self.used.add(helper)
            source = bit_count_helper(helper, operation, ctype, width)
            # The call kernel conservatively forbids locals shadowing function
            # names. Freshen helper parameters/subtotals as well as its symbol.
            bindings = {}
            for original, tag in [('x', 'argument')] + [('count' + str(i), 'count') for i in range((width - 2) // 16 + 1)]:
                serial = 1
                while '__clang_bit_' + tag + '_' + str(serial) in self.used:
                    serial += 1
                emitted = '__clang_bit_' + tag + '_' + str(serial)
                self.used.add(emitted); bindings[original] = emitted
            source = re.sub(r'\b(?:x|count[0-3])\b', lambda match: bindings[match[0]], source)
            self.models[name] = {'builtin': name, 'operation': operation, 'argument_type': ctype, 'width': width,
                                 'result_type': 'int', 'helper': helper, 'argument_name': bindings['x'],
                                 'partial_names': [bindings['count' + str(i)] for i in range((width - 2) // 16 + 1)], 'source': source,
                                 'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                                 'zero_input': 'undefined; explicit division guard retained',
                                 'semantics': 'typed scalar helper body, not an external assumption'}
        return self.models[name]
