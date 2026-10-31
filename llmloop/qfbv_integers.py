"""Pure QF_BV typed expressions with explicit C undefinedness predicates.

The concrete ABI/type rules are shared with SymbolicIntegers. Overflow uses
exact double-width arithmetic rather than BV2Int; no safety predicate is dropped.
"""
import z3

from .c_integers import IntegerABI, IntType
from .smt_spath import SMTGraphError
from .symbolic_integers import SymbolicIntegers, TypedTerm


class QFBVIntegers(SymbolicIntegers):
    def __init__(self, variables, abi='LP64', char_signed=True):
        self.abi = IntegerABI(abi, char_signed); self.nodes = 0; self.variables = {}; self.bounds = {}
        if not isinstance(variables, dict) or len(variables) > 16:
            raise SMTGraphError('At most 16 QF_BV scalar parameters')
        conditions = []
        for name, spec in variables.items():
            if not isinstance(name, str) or not name.isidentifier() or not isinstance(spec, dict) or set(spec) - {'type', 'bounds'}:
                raise SMTGraphError('Invalid QF_BV parameter')
            t = self.abi.types[spec['type']]
            limits = spec.get('bounds', [t.minimum, t.maximum])
            if not isinstance(limits, list) or len(limits) != 2 or any(type(v) is not int or not t.minimum <= v <= t.maximum for v in limits) or limits[0] > limits[1]:
                raise SMTGraphError('Bounds must be an ordered pair of representable integers')
            value = z3.BitVec('bv_cfg_' + name, t.bits)
            self.variables[name] = TypedTerm(value, t, z3.BoolVal(True)); self.bounds[name] = limits
            lo, hi = (z3.BitVecVal(v, t.bits) for v in limits)
            conditions.extend([value >= lo, value <= hi] if t.signed else [z3.UGE(value, lo), z3.ULE(value, hi)])
        self.pre = z3.simplify(z3.And(*conditions))

    def lower(self, node, depth=0):
        self.nodes += 1
        if self.nodes > 256 or depth > 32 or not isinstance(node, dict):
            raise SMTGraphError('QF_BV integer expression budget exceeded or malformed node')
        if set(node) == {'var'}:
            if node['var'] not in self.variables: raise SMTGraphError('Unknown QF_BV scalar variable')
            return self.variables[node['var']]
        if set(node) == {'literal'}: literal = self.abi.literal(node['literal'])
        elif set(node) == {'value', 'type'}: literal = self.abi.value(node['value'], node['type'])
        elif set(node) == {'cast', 'expr'}: return self.convert(self.lower(node['expr'], depth + 1), self.abi.types[node['cast']])
        else: literal = None
        if literal is not None: return TypedTerm(z3.BitVecVal(literal.value, literal.type.bits), literal.type, z3.BoolVal(True))
        if set(node) != {'op', 'args'} or not isinstance(node['args'], list): raise SMTGraphError('Malformed QF_BV integer operation')
        op = node['op']; args = [self.lower(child, depth + 1) for child in node['args']]
        if op == '?:' and len(args) == 3:
            condition, yes, no = args; yes, no = self.common(yes, no); choose = self.truth(condition)
            return TypedTerm(z3.If(choose, yes.value, no.value), yes.type,
                             z3.And(condition.safe, z3.Implies(choose, yes.safe), z3.Implies(z3.Not(choose), no.safe)))
        if len(args) == 1 and op in ('+', '-', '~', '!'):
            a = args[0]
            if op == '!': return self.boolean(z3.Not(self.truth(a)), a.safe)
            a = self.promoted(a); safe = a.safe; value = a.value
            if op == '-':
                if a.type.signed: safe = z3.And(safe, value != z3.BitVecVal(a.type.minimum, a.type.bits))
                value = -value
            elif op == '~': value = ~value
            return TypedTerm(value, a.type, safe)
        if len(args) != 2: raise SMTGraphError('Unsupported QF_BV operator arity')
        a, b = args
        if op in ('&&', '||'):
            left, right = self.truth(a), self.truth(b); needed = left if op == '&&' else z3.Not(left)
            return self.boolean(z3.And(left, right) if op == '&&' else z3.Or(left, right),
                                z3.And(a.safe, z3.Implies(needed, b.safe)))
        if op in ('<<', '>>'):
            a, b = self.promoted(a), self.promoted(b)
            # Check the original promoted amount BEFORE conversion to lhs width.
            safe = z3.And(a.safe, b.safe, z3.ULT(b.value, z3.BitVecVal(a.type.bits, b.type.bits)))
            if b.type.signed: safe = z3.And(safe, b.value >= 0)
            shift = self.convert(b, IntType('_shift', a.type.bits, False, b.type.rank)).value
            if op == '>>': value = a.value >> shift if a.type.signed else z3.LShR(a.value, shift)
            else:
                value = a.value << shift
                if a.type.signed:
                    wide = z3.ZeroExt(a.type.bits, a.value) << z3.ZeroExt(a.type.bits, shift)
                    safe = z3.And(safe, a.value >= 0, z3.ULE(wide, z3.BitVecVal(a.type.maximum, 2 * a.type.bits)))
            return TypedTerm(value, a.type, safe)
        a, b = self.common(a, b); x, y, t = a.value, b.value, a.type; safe = z3.And(a.safe, b.safe)
        if op in ('+', '-', '*'):
            value = x + y if op == '+' else x - y if op == '-' else x * y
            if t.signed:
                left, right = z3.SignExt(t.bits, x), z3.SignExt(t.bits, y)
                exact = left + right if op == '+' else left - right if op == '-' else left * right
                safe = z3.And(safe, exact == z3.SignExt(t.bits, value))
            return TypedTerm(value, t, safe)
        if op in ('/', '%'):
            safe = z3.And(safe, y != 0)
            if t.signed: safe = z3.And(safe, z3.Not(z3.And(x == z3.BitVecVal(t.minimum, t.bits), y == z3.BitVecVal(-1, t.bits))))
            value = (x / y if op == '/' else z3.SRem(x, y)) if t.signed else (z3.UDiv(x, y) if op == '/' else z3.URem(x, y))
            return TypedTerm(value, t, safe)
        if op in ('&', '|', '^'): return TypedTerm(x & y if op == '&' else x | y if op == '|' else x ^ y, t, safe)
        if op in ('==', '!=', '<', '<=', '>', '>='):
            if op == '==': claim = x == y
            elif op == '!=': claim = x != y
            elif op == '<': claim = x < y if t.signed else z3.ULT(x, y)
            elif op == '<=': claim = x <= y if t.signed else z3.ULE(x, y)
            elif op == '>': claim = x > y if t.signed else z3.UGT(x, y)
            else: claim = x >= y if t.signed else z3.UGE(x, y)
            return self.boolean(claim, safe)
        raise SMTGraphError('Unsupported QF_BV integer operator')
