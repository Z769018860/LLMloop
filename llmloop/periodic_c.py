"""Canonical scalar for/if C adapter for inductively proved periodic branches.

Source execution order is lowered into simultaneous affine updates. This
frontend uses mathematical integers; C machine arithmetic is not certified.
"""
import sympy as s
from pycparser import c_ast, c_parser
from .c_validation import validate_automatic_locals
from .cfg_frontend import _is_int_decl
from .memory_frontend import _lit
from .periodic_recurrence import periodic_summary
from .smt_spath import SMTGraphError


def analyze_periodic_c(source, function=None, parameter_bounds=None, invariants=None):
    if parameter_bounds is not None and not isinstance(parameter_bounds, dict):
        raise SMTGraphError('parameter_bounds must be an object')
    try:
        unit = c_parser.CParser().parse(source)
    except Exception as exc:
        raise SMTGraphError('C parsing failed: ' + str(exc)) from exc
    functions = [f for f in unit.ext if isinstance(f, c_ast.FuncDef)
                 and (function is None or f.decl.name == function)]
    if len(functions) != 1 or not _is_int_decl(functions[0].decl):
        raise SMTGraphError('Expected one selected int-returning function')
    func = functions[0]
    validate_automatic_locals(func, SMTGraphError)
    raw = func.decl.type.args.params if func.decl.type.args else []
    if len(raw) == 1 and isinstance(raw[0], c_ast.Typename) and isinstance(raw[0].type, c_ast.TypeDecl) and isinstance(raw[0].type.type, c_ast.IdentifierType) and raw[0].type.type.names == ['void']:
        raw = []
    class LiteralTypes(c_ast.NodeVisitor):
        def visit_Constant(self, node):
            if node.type != 'int':
                raise SMTGraphError('Only int literals in periodic scalar C')
    LiteralTypes().visit(func)
    params = []
    for param in raw:
        if not isinstance(param, c_ast.Decl) or not _is_int_decl(param) or not param.name or param.name in params:
            raise SMTGraphError('Unique scalar int parameters required')
        params.append(param.name)
    names = {p: s.Symbol(p, integer=True) for p in params}
    state, initial, index = {}, {}, None

    def arithmetic(node, env):
        if isinstance(node, c_ast.ID) and node.name in env:
            return env[node.name]
        literal = _lit(node)
        if literal is not None:
            # Reject wide or unsigned C literal types rather than pretending to
            # verify their promotions through this mathematical int adapter.
            if not -(1 << 31) <= literal < (1 << 31):
                raise SMTGraphError('Wide literals unsupported in periodic scalar C')
            if isinstance(node, c_ast.Constant) and node.type != 'int':
                raise SMTGraphError('Only int literals in periodic scalar C')
            return s.Integer(literal)
        if isinstance(node, c_ast.UnaryOp) and node.op in ('+', '-'):
            term = arithmetic(node.expr, env)
            return term if node.op == '+' else -term
        if isinstance(node, c_ast.BinaryOp) and node.op in ('+', '-', '*'):
            a, b = arithmetic(node.left, env), arithmetic(node.right, env)
            return {'+': lambda: a+b, '-': lambda: a-b, '*': lambda: a*b}[node.op]()
        raise SMTGraphError('Unsupported periodic C arithmetic: ' + type(node).__name__)

    items = func.body.block_items or []
    position = 0
    while position < len(items) and isinstance(items[position], c_ast.Decl):
        node = items[position]
        if not _is_int_decl(node) or node.init is None or node.name in names:
            raise SMTGraphError('Unique initialized scalar int locals required')
        value = arithmetic(node.init, {**names, **initial})
        state[node.name] = str(value)
        initial[node.name] = value
        names[node.name] = s.Symbol(node.name, integer=True)
        position += 1
    if position + 2 != len(items) or not isinstance(items[position], c_ast.For) or not isinstance(items[-1], c_ast.Return):
        raise SMTGraphError('Expected initialized locals, one counted for loop, and final return')
    loop = items[position]
    init = loop.init
    if not isinstance(init, c_ast.DeclList) or len(init.decls) != 1:
        raise SMTGraphError('Loop needs a fresh int index declaration')
    declaration = init.decls[0]
    if not _is_int_decl(declaration) or declaration.name in names or _lit(declaration.init) != 0:
        raise SMTGraphError('Loop index must be fresh and initialized to zero')
    index = declaration.name
    if not state:
        raise SMTGraphError('At least one mutable scalar local required')
    cond = loop.cond
    if not isinstance(cond, c_ast.BinaryOp) or cond.op != '<' or not isinstance(cond.left, c_ast.ID) or cond.left.name != index:
        raise SMTGraphError('For guard must be index < immutable expression')
    stop = arithmetic(cond.right, {p: names[p] for p in params})
    nxt = loop.next
    increment = isinstance(nxt, c_ast.UnaryOp) and nxt.op in ('++', 'p++') and isinstance(nxt.expr, c_ast.ID) and nxt.expr.name == index
    if isinstance(nxt, c_ast.Assignment) and isinstance(nxt.lvalue, c_ast.ID) and nxt.lvalue.name == index:
        increment = nxt.op == '+=' and _lit(nxt.rvalue) == 1
        if nxt.op == '=':
            rhs = nxt.rvalue
            increment = isinstance(rhs, c_ast.BinaryOp) and rhs.op == '+' and isinstance(rhs.left, c_ast.ID) and rhs.left.name == index and _lit(rhs.right) == 1
    if not increment:
        raise SMTGraphError('Loop index must advance by one')
    counter = index
    guardenv = {**names, index: s.Symbol(index, integer=True)}

    def guard_arithmetic(node):
        # Validate with the same pure-arithmetic parser, then retain an AST-shaped
        # spelling so x*x does not become an unsupported textual x**2 guard.
        arithmetic(node, guardenv)
        if isinstance(node, c_ast.ID):
            return node.name
        literal = _lit(node)
        if literal is not None:
            return str(literal)
        if isinstance(node, c_ast.UnaryOp):
            return '(' + node.op + guard_arithmetic(node.expr) + ')'
        return '(' + guard_arithmetic(node.left) + node.op + guard_arithmetic(node.right) + ')'

    def predicate(node):
        if isinstance(node, c_ast.UnaryOp) and node.op == '!':
            return '(not (' + predicate(node.expr) + '))'
        if isinstance(node, c_ast.BinaryOp):
            if node.op in ('&&', '||'):
                return '(' + predicate(node.left) + (' and ' if node.op == '&&' else ' or ') + predicate(node.right) + ')'
            if node.op in ('==', '!=', '<', '<=', '>', '>='):
                return f'({guard_arithmetic(node.left)} {node.op} {guard_arithmetic(node.right)})'
        # C uses integer truth, including scalar IDs.
        return '(' + guard_arithmetic(node) + ' != 0)'

    def branch_updates(node):
        env = dict(names)
        def lower(statement):
            if isinstance(statement, c_ast.Compound):
                for child in statement.block_items or []:
                    lower(child)
                return
            if isinstance(statement, c_ast.EmptyStatement):
                return
            if isinstance(statement, c_ast.Assignment) and isinstance(statement.lvalue, c_ast.ID) and statement.lvalue.name in state:
                dest = statement.lvalue.name
                value = arithmetic(statement.rvalue, env)
                if statement.op == '=':
                    env[dest] = value
                elif statement.op in ('+=', '-=', '*='):
                    old = env[dest]
                    env[dest] = {'+=': lambda: old+value, '-=': lambda: old-value, '*=': lambda: old*value}[statement.op]()
                else:
                    raise SMTGraphError('Unsupported periodic assignment operator')
                return
            raise SMTGraphError('Branches require scalar assignments without nested control flow')
        lower(node)
        return {v: str(env[v]) for v in state}

    body = loop.stmt.block_items if isinstance(loop.stmt, c_ast.Compound) else [loop.stmt]
    if not body or len(body) != 1 or not isinstance(body[0], c_ast.If):
        raise SMTGraphError('For body requires exactly one if/else chain')
    phases = []
    path = 'True'
    node = body[0]
    while isinstance(node, c_ast.If):
        guard = predicate(node.cond)
        phases.append({'guard': f'({path} and {guard})', 'updates': branch_updates(node.iftrue)})
        path = f'({path} and not {guard})'
        node = node.iffalse
    if node is None:
        raise SMTGraphError('A final else branch is required')
    phases.append({'guard': path, 'updates': branch_updates(node)})
    obj = {'kind': 'periodic_recurrence', 'name': func.decl.name, 'state': state,
           'parameters': params, 'counter': counter, 'phases': phases}
    if invariants is not None:
        obj['phase_invariants'] = invariants
        obj['parameter_bounds'] = parameter_bounds or {}
    elif parameter_bounds:
        raise SMTGraphError('Parameter bounds require phase invariants')
    report, forms = periodic_summary(obj)
    count = s.Max(0, stop)
    count_symbol = s.Symbol(counter, integer=True, nonnegative=True)
    post = {names[v]: expression.subs(count_symbol, count) for v, expression in forms.items()}
    returned = arithmetic(items[-1].expr, names).subs(post, simultaneous=True)
    return {**report, 'source_function': func.decl.name, 'ir': obj,
            'iteration_count': str(count), 'return_expr': str(s.simplify(returned)),
            'termination_proved': True,
            'termination_scope': 'mathematical integer counted-for semantics; machine integer safety not proved',
            'frontend': 'canonical scalar for/if C; sequential assignments lowered exactly; mathematical integers'}
