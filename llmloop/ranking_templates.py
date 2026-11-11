"""UNTRUSTED ranking-function candidates from the (deterministic) loop condition: for an atom `a < b` use b - a, `a <= b` -> b - a + 1, `a > b` -> a - b, `a >= b` -> a - b + 1, `a != b` -> none.
Candidates are verified by typed_invariant_while (non-negative and strictly decreasing from ANY state satisfying the invariant and the loop condition)."""
from pycparser import c_parser, c_ast, c_generator
G = c_generator.CGenerator()


def _atoms(c, out):
    if isinstance(c, c_ast.BinaryOp) and c.op == '&&': _atoms(c.left, out); _atoms(c.right, out)
    elif isinstance(c, c_ast.BinaryOp) and c.op in ('<', '<=', '>', '>='): out.append(c)


def candidates(source):
    ast = c_parser.CParser().parse(source); f = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]; out = []
    for x in f.body.block_items:
        for n in _all(x):
            if isinstance(n, (c_ast.While, c_ast.For)) and n.cond is not None:
                atoms = []; _atoms(n.cond, atoms)
                for a in atoms:
                    L, R = G.visit(a.left), G.visit(a.right)
                    out.append({'<': '(%s) - (%s)' % (R, L), '<=': '(%s) - (%s) + 1' % (R, L), '>': '(%s) - (%s)' % (L, R), '>=': '(%s) - (%s) + 1' % (L, R)}[a.op])
    return list(dict.fromkeys(out))


def _all(n):
    yield n
    for _, c in n.children(): yield from _all(c)
