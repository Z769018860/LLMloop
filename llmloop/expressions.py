"""Safe, deliberately small integer expression language (no Python eval)."""
from __future__ import annotations
import ast
import sympy as s
_ALLOWED = {"floor":s.floor, "ceiling":s.ceiling, "Mod":s.Mod, "Min":s.Min,
            "Max":s.Max, "binomial":s.binomial, "Abs":s.Abs}
class ExpressionError(ValueError):
    pass
def parse(source:object, names:dict[str,s.Symbol])->s.Expr:
    if isinstance(source,bool): raise ExpressionError("Boolean is not an integer")
    if isinstance(source,int): return s.Integer(source)
    if not isinstance(source,str) or len(source)>1000:
        raise ExpressionError("Expected expression string, up to 1000 chars")
    try: tree=ast.parse(source,mode="eval")
    except SyntaxError as exc: raise ExpressionError(str(exc)) from exc
    def visit(node):
        if isinstance(node,ast.Constant) and type(node.value) is int: return s.Integer(node.value)
        if isinstance(node,ast.Name) and node.id in names: return names[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            x=visit(node.operand)
            return x if isinstance(node.op,ast.UAdd) else -x
        if isinstance(node,ast.BinOp):
            a,b=visit(node.left),visit(node.right)
            if isinstance(node.op,ast.Add): return a+b
            if isinstance(node.op,ast.Sub): return a-b
            if isinstance(node.op,ast.Mult): return a*b
            if isinstance(node.op,ast.FloorDiv): return s.floor(a/b)
            if isinstance(node.op,ast.Mod): return s.Mod(a,b)
            if isinstance(node.op,ast.Pow):
                if b.is_Integer and 0<=int(b)<=8: return a**b
                raise ExpressionError("Exponent must be integer in [0,8]")
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            if node.func.id in _ALLOWED and not node.keywords and len(node.args)<=3:
                return _ALLOWED[node.func.id](*(visit(x) for x in node.args))
        raise ExpressionError("Unsupported syntax: "+ast.dump(node)[:150])
    return s.simplify(visit(tree.body))
def parse_equality(source:str, names:dict[str,s.Symbol])->tuple[s.Expr,s.Expr]:
    if not isinstance(source,str) or source.count("==")!=1:
        raise ExpressionError("Phase guard must contain one '=='")
    a,b=source.split("==",1)
    return parse(a.strip(),names),parse(b.strip(),names)
def exact_zero(expr:s.Expr)->bool:
    return s.simplify(s.expand(expr))==0
def integer_value(expr:s.Expr, values:dict[str,int])->int:
    syms={str(x):x for x in expr.free_symbols}
    if set(syms)-set(values): raise ExpressionError("Unbound parameters: "+str(set(syms)-set(values)))
    result=s.simplify(expr.subs({symbol:s.Integer(values[name]) for name,symbol in syms.items()}))
    if result.is_Integer is not True: raise ExpressionError("Not a concrete integer: "+str(result))
    return int(result)
