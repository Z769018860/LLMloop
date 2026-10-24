"""Safe piecewise integer closed-form expression parser (no eval/sympify)."""
import ast
import sympy as s
from .expressions import _ALLOWED
from .smt_spath import SMTGraphError


def parse_closed(source, names):
    if type(source) is int:
        return s.Integer(source)
    if not isinstance(source, str) or len(source) > 2000:
        raise SMTGraphError('Closed form requires an integer or expression of at most 2000 characters')
    tree = ast.parse(source, mode='eval')
    if sum(1 for _ in ast.walk(tree)) > 256:
        raise SMTGraphError('Closed form syntax budget exceeded')

    def arithmetic(term):
        if not isinstance(term, s.Expr):
            raise SMTGraphError('Expected integer-valued closed-form arithmetic')
        return term

    def boolean(term):
        if term not in (s.true,s.false) and term.func not in (s.And,s.Or,s.Not) and not isinstance(term,s.core.relational.Relational):
            raise SMTGraphError('Expected closed-form Boolean condition')
        return term

    def visit(node):
        if isinstance(node, ast.Constant):
            if type(node.value) is int:
                return s.Integer(node.value)
            if type(node.value) is bool:
                return s.true if node.value else s.false
        if isinstance(node, ast.Name) and node.id in names:
            return names[node.id]
        if isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.Not):
                return s.Not(boolean(value))
            value = arithmetic(value)
            if isinstance(node.op, ast.USub):
                return -value
            if isinstance(node.op, ast.UAdd):
                return value
        if isinstance(node, ast.BinOp):
            a, b = arithmetic(visit(node.left)), arithmetic(visit(node.right))
            if isinstance(node.op, ast.Add):
                return a+b
            if isinstance(node.op, ast.Sub):
                return a-b
            if isinstance(node.op, ast.Mult):
                return a*b
            if isinstance(node.op, (ast.FloorDiv, ast.Mod)):
                try:
                    divisor = ast.literal_eval(node.right)
                except (TypeError, ValueError):
                    divisor = None
                if type(divisor) is not int or divisor == 0:
                    raise SMTGraphError('Closed-form division/modulo needs a nonzero literal divisor')
                return s.floor(a/b) if isinstance(node.op, ast.FloorDiv) else s.Mod(a,b)
            if isinstance(node.op, ast.Pow) and b.is_Integer and 0 <= b <= 8:
                return a**b
        if isinstance(node, ast.IfExp):
            test = boolean(visit(node.test))
            yes, no = arithmetic(visit(node.body)), arithmetic(visit(node.orelse))
            return s.Piecewise((yes,test),(no,True))
        if isinstance(node, ast.BoolOp):
            terms = [boolean(visit(x)) for x in node.values]
            if isinstance(node.op, ast.And):
                return s.And(*terms)
            if isinstance(node.op, ast.Or):
                return s.Or(*terms)
        if isinstance(node, ast.Compare):
            a, claims = arithmetic(visit(node.left)), []
            for operation, right in zip(node.ops, node.comparators):
                b = arithmetic(visit(right))
                constructors = {ast.Eq:s.Eq, ast.NotEq:s.Ne, ast.Lt:s.Lt, ast.LtE:s.Le, ast.Gt:s.Gt, ast.GtE:s.Ge}
                if type(operation) not in constructors:
                    raise SMTGraphError('Unsupported closed-form comparison')
                claims.append(constructors[type(operation)](a,b))
                a = b
            return s.And(*claims)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords and len(node.args) <= 3:
            if node.func.id in _ALLOWED:
                if node.func.id == 'Mod':
                    if len(node.args) != 2:
                        raise SMTGraphError('Mod requires two arguments')
                    try:
                        divisor = ast.literal_eval(node.args[1])
                    except (TypeError, ValueError):
                        divisor = None
                    if type(divisor) is not int or divisor == 0:
                        raise SMTGraphError('Mod requires a nonzero literal divisor')
                return _ALLOWED[node.func.id](*(arithmetic(visit(x)) for x in node.args))
        raise SMTGraphError('Unsupported closed-form syntax: ' + type(node).__name__)

    return arithmetic(visit(tree.body))
