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
    """Balanced literal decision trees avoid arithmetic count-sum circuits.

    Sixteen-leaf blocks preserve the existing per-expression AST budget. All
    blocks are pure and defined; a coarse tree selects the actual bit bucket.
    An explicit division guard retains undefined zero-input behavior.
    """
    if operation not in ('clz', 'ctz') or width not in (32, 64) or ctype not in ('unsigned int', 'unsigned long', 'unsigned long long'):
        raise SMTGraphError('Unsupported bit-count helper contract')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name):
        raise SMTGraphError('Invalid bit-count helper identifier')
    suffix = {'unsigned int': 'U', 'unsigned long': 'UL', 'unsigned long long': 'ULL'}[ctype]
    def choose(boundary, low, high):
        constant = str(1 << boundary) + suffix
        if operation == 'clz':
            return '(x < ' + constant + ' ? ' + low + ' : ' + high + ')'
        return '(x % ' + constant + ' == 0 ? ' + high + ' : ' + low + ')'
    def bucket(lo, hi):
        if lo == hi:return str(width - 1 - lo if operation == 'clz' else lo)
        mid = (lo + hi) // 2
        return choose(mid + 1, bucket(lo, mid), bucket(mid + 1, hi))
    blocks = width // 16
    declarations = ' '.join('int count' + str(i) + ' = ' + bucket(16*i, 16*i+15) + ';' for i in range(blocks))
    def selected(lo, hi):
        if lo == hi:return 'count' + str(lo)
        mid = (lo + hi) // 2
        return choose(16*(mid+1), selected(lo, mid), selected(mid+1, hi))
    return 'int ' + name + '(' + ctype + ' x) { ' + declarations + ' return ' + selected(0, blocks-1) + ' / (x != 0); }\n'



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
                                 'lowering': 'balanced literal decision trees in sixteen-leaf blocks',
                                 'semantics': 'typed scalar helper body, not an external assumption'}
        return self.models[name]
