"""v0.79: pointer-arithmetic front end for Juliet CWE124/126/127 (and CWE839 index variants). UNTRUSTED syntactic rewrite into the bounds-only array model of scripts/juliet_eval.py:
a pointer is a constant alias (base array, constant offset), `p = a - 8` / `p = a` / `p = (T*)malloc(N*sizeof(T))`; p[e] -> a[e+off]; *p -> a[off]; library calls become access-range checks
(memset/memcpy/memmove/strcpy/strncpy and wide variants: the first and last accessed element); strlen of a memset-filled, NUL-terminated array is the constant fill length; large constant loops are
PEELED to their first and last iteration (sound for an access `p[i+c]`: a monotone index leaves the object iff one of the endpoints does). Anything outside these patterns raises ValueError (counted as skipped).
Ground truth is the Juliet naming (*_bad vulnerable, good* safe); the unchanged typed_c verifier decides."""
import copy
from pycparser import c_ast

CHECK_FUNCS = {'memset': (0,), 'wmemset': (0,), 'memcpy': (0, 1), 'memmove': (0, 1), 'wmemcpy': (0, 1), 'wmemmove': (0, 1)}
STR_FUNCS = {'strcpy': 'cpy', 'wcscpy': 'cpy', 'strncpy': 'ncpy', 'wcsncpy': 'ncpy'}


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def cexpr(e, consts):
    if isinstance(e, c_ast.Constant) and e.type == 'int': return int(e.value.rstrip('uUlL'), 0)
    if isinstance(e, c_ast.ID) and e.name in consts: return consts[e.name]
    if isinstance(e, c_ast.UnaryOp) and e.op == 'sizeof': return 1          # counts are in ELEMENTS: N*sizeof(T) -> N
    if isinstance(e, c_ast.UnaryOp) and e.op == '-': return -cexpr(e.expr, consts)
    if isinstance(e, c_ast.BinaryOp) and e.op in '+-*':
        a, b = cexpr(e.left, consts), cexpr(e.right, consts); return a + b if e.op == '+' else a - b if e.op == '-' else a * b
    raise ValueError('non-constant expression')


def isnul(e): return isinstance(e, c_ast.Constant) and e.type == 'char' and e.value in ("'\\0'", "L'\\0'")
def sink_bad(): return c_ast.Assignment('=', c_ast.ID('__sink'), c_ast.BinaryOp('/', c_ast.Constant('int', '1'), c_ast.BinaryOp('-', c_ast.ID('__sink'), c_ast.ID('__sink'))))


class Rewriter:
    def __init__(self):
        self.size = {}; self.alias = {}; self.ptrs = {}; self.consts = {}; self.fill = {}; self.slen = {}; self.declared = set(); self.nsh = 0

    # ---- pointer expressions -> (base, offset) or None for NULL
    def pexpr(self, e):
        if isinstance(e, c_ast.Cast): return self.pexpr(e.expr)
        if isinstance(e, c_ast.Constant) and e.value == '0': return None
        if isinstance(e, c_ast.ID):
            if e.name in self.alias: return self.alias[e.name]
            if e.name in self.size: return (e.name, 0)
        if isinstance(e, c_ast.BinaryOp) and e.op in '+-':
            b = self.pexpr(e.left)
            if b is not None: k = cexpr(e.right, self.consts); return (b[0], b[1] + (k if e.op == '+' else -k))
        raise ValueError('unsupported pointer expression')

    def deref(self, name, idx):
        a = self.alias.get(name) if name in self.ptrs else ((name, 0) if name in self.size else None)
        if a is None: raise ValueError('null or unknown pointer dereference')
        e = idx if a[1] == 0 else c_ast.BinaryOp('+', idx, c_ast.Constant('int', str(a[1]))) if a[1] > 0 else c_ast.BinaryOp('-', idx, c_ast.Constant('int', str(-a[1])))
        return c_ast.ArrayRef(c_ast.ID(a[0]), e)

    def expr(self, n):
        """rewrite pointer dereferences inside an expression tree (in place)"""
        for name, child in list(n.children()):
            self.expr(child)
            new = None
            if isinstance(child, c_ast.ArrayRef) and isinstance(child.name, c_ast.ID) and child.name.name in self.ptrs: new = self.deref(child.name.name, child.subscript)
            elif isinstance(child, c_ast.UnaryOp) and child.op == '*' and isinstance(child.expr, c_ast.ID) and child.expr.name in self.ptrs: new = self.deref(child.expr.name, c_ast.Constant('int', '0'))
            if new is not None:
                import re; m = re.match(r'(\w+)\[(\d+)\]$', name)
                if m: getattr(n, m.group(1))[int(m.group(2))] = new
                else: setattr(n, name, new)

    def access(self, p, count):
        """emit a check that p[0..count-1] lies inside its object"""
        a = self.pexpr(p)
        if a is None: raise ValueError('null pointer access')
        if count <= 0: return []
        base, off = a
        return [] if off >= 0 and off + count <= self.size[base] else [sink_bad()]

    def call(self, s):
        nm = getattr(s.name, 'name', ''); args = s.args.exprs if s.args else []
        if nm in CHECK_FUNCS:
            n = cexpr(args[2], self.consts) if nm.endswith('set') or True else 0
            out = []
            for i in CHECK_FUNCS[nm]: out += self.access(args[i], n)
            a0 = self.pexpr(args[0])
            if nm in ('memset', 'wmemset') and a0 and a0[1] == 0 and not (isinstance(args[1], c_ast.Constant) and args[1].value in ("0", "'\\0'")): self.fill[a0[0]] = n
            return out
        if nm in STR_FUNCS:
            kind = STR_FUNCS[nm]; d = self.pexpr(args[0]); sp = self.pexpr(args[1])
            if d is None or sp is None: raise ValueError('null pointer string op')
            srcl = self.slen.get(sp[0])
            srcl = None if srcl is None else srcl - sp[1]
            if kind == 'cpy':
                if srcl is None: raise ValueError('unknown string length')
                n = srcl + 1
                return self.access(args[0], n) + self.access(args[1], n)
            n = cexpr(args[2], self.consts); m = n if srcl is None else min(n, srcl + 1)
            return self.access(args[0], n) + self.access(args[1], m)
        if nm == 'free':
            a = self.pexpr(args[0])
            return [] if a is None or a[1] == 0 else [sink_bad()]
        if nm in ('printLine', 'printWLine', 'printIntLine', 'printStructLine', 'printSizeTLine'): return []
        raise ValueError('call to ' + nm)

    def stmt(self, s):
        if isinstance(s, c_ast.Compound):
            items = s.block_items or []; mine = {i.name for i in items if isinstance(i, c_ast.Decl) and not isinstance(i.type, (c_ast.PtrDecl, c_ast.ArrayDecl))}
            clash = mine & self.declared
            if clash:                              # block-scope shadowing: give the inner declaration a fresh name (the verifier rejects shadowing)
                self.nsh += 1; sfx = '__s%d' % self.nsh; root = c_ast.Compound(items)
                for n in walk(root):
                    if isinstance(n, c_ast.Decl) and n.name in clash:
                        n.name += sfx; ty = n.type
                        while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
                        if ty is not None: ty.declname = n.name
                    elif isinstance(n, c_ast.ID) and n.name in clash: n.name += sfx
                mine = {x + sfx if x in clash else x for x in mine}
            saved = set(self.declared); self.declared |= mine; out = [c_ast.Compound(self.stmts(items))]; self.declared = saved | (set() if True else set()); return out
        # strlen / constants / plain assignments
        for n in list(walk(s)):
            for name, child in list(n.children()):
                if isinstance(child, c_ast.FuncCall) and getattr(child.name, 'name', '') in ('strlen', 'wcslen'):
                    p = self.pexpr(child.args.exprs[0])
                    if p is None or p[0] not in self.slen: raise ValueError('unknown strlen')
                    new = c_ast.Constant('int', str(self.slen[p[0]] - p[1]))
                    import re; m = re.match(r'(\w+)\[(\d+)\]$', name)
                    if m: getattr(n, m.group(1))[int(m.group(2))] = new
                    else: setattr(n, name, new)
        if isinstance(s, c_ast.If) and not (isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '==' and isinstance(s.cond.left, c_ast.ID) and s.cond.left.name in self.ptrs):
            self.expr(s); saved = (dict(self.alias), dict(self.consts))
            for a in ('iftrue', 'iffalse'):
                sub = getattr(s, a)
                if sub is not None:
                    self.alias, self.consts = dict(saved[0]), dict(saved[1]); r = self.stmt(sub); setattr(s, a, c_ast.Compound(r))
            self.alias, self.consts = saved; return [s]
        if isinstance(s, c_ast.Decl):
            ty = s.type
            if isinstance(ty, c_ast.PtrDecl):
                self.ptrs[s.name] = ty.type.type if isinstance(ty.type, c_ast.TypeDecl) else ty.type
                if s.init is None: return []
                init = s.init.expr if isinstance(s.init, c_ast.Cast) else s.init
                if isinstance(init, c_ast.FuncCall) and getattr(init.name, 'name', '') in ('malloc', 'ALLOCA', 'alloca'):
                    n = cexpr(init.args.exprs[0], self.consts); self.size[s.name] = n; self.alias[s.name] = (s.name, 0)
                    elt = ty.type.type if isinstance(ty.type, c_ast.TypeDecl) else ty.type
                    return [c_ast.Decl(s.name, [], [], [], [], c_ast.ArrayDecl(c_ast.TypeDecl(s.name, [], None, elt), c_ast.Constant('int', str(n)), []), None, None)]
                self.alias[s.name] = self.pexpr(init); return []
            if isinstance(ty, c_ast.ArrayDecl):
                n = cexpr(ty.dim, self.consts); self.size[s.name] = n; ty.dim = c_ast.Constant('int', str(n)); return [s]
            return [s]
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ID) and s.lvalue.name in self.ptrs and s.op == '=':
            rv = s.rvalue.expr if isinstance(s.rvalue, c_ast.Cast) else s.rvalue
            if isinstance(rv, c_ast.FuncCall) and getattr(rv.name, 'name', '') in ('malloc', 'ALLOCA', 'alloca'):
                n = cexpr(rv.args.exprs[0], self.consts); nm = s.lvalue.name; self.size[nm] = n; self.alias[nm] = (nm, 0)
                return [c_ast.Decl(nm, [], [], [], [], c_ast.ArrayDecl(c_ast.TypeDecl(nm, [], None, self.ptrs[nm]), c_ast.Constant('int', str(n)), []), None, None)]
            self.alias[s.lvalue.name] = self.pexpr(s.rvalue); return []
        if isinstance(s, c_ast.FuncCall): return self.call(s)
        if isinstance(s, c_ast.For): return self.loop(s)
        if isinstance(s, c_ast.If) and isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '==' and isinstance(s.cond.left, c_ast.ID) and s.cond.left.name in self.ptrs and isinstance(s.cond.right, c_ast.Constant) and s.cond.right.value == '0': return []   # malloc-failure check (malloc assumed to succeed)
        if isinstance(s, (c_ast.While, c_ast.DoWhile, c_ast.If, c_ast.Switch, c_ast.Goto, c_ast.Return)): raise ValueError('control flow')
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ID) and s.op == '=':
            try: self.consts[s.lvalue.name] = cexpr(s.rvalue, self.consts)
            except ValueError: self.consts.pop(s.lvalue.name, None)
        self.expr(s)
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ArrayRef) and isnul(s.rvalue) and isinstance(s.lvalue.name, c_ast.ID):
            b = s.lvalue.name.name
            try: k = cexpr(s.lvalue.subscript, self.consts)
            except ValueError: k = None
            if self.fill.get(b) == k: self.slen[b] = k
        return [s]

    def loop(self, s):
        if not (isinstance(s.init, c_ast.Assignment) and isinstance(s.init.lvalue, c_ast.ID) and isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '<' and isinstance(s.cond.left, c_ast.ID) and s.cond.left.name == s.init.lvalue.name): raise ValueError('loop shape')
        v = s.init.lvalue.name; a = cexpr(s.init.rvalue, self.consts); b = cexpr(s.cond.right, self.consts); trip = b - a
        if trip < 0: raise ValueError('negative trip')
        body = s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
        out = []; its = list(range(a, b)) if trip <= 12 else [a, b - 1]
        for k, it in enumerate(its):
            out.append(c_ast.Assignment('=', c_ast.ID(v), c_ast.Constant('int', str(it))))
            saved = dict(self.alias); out.append(c_ast.Compound(self.stmts(copy.deepcopy(list(body)))))
        out.append(c_ast.Assignment('=', c_ast.ID(v), c_ast.Constant('int', str(b)))); return out

    def stmts(self, ss):
        out = []
        for s in ss: out += self.stmt(s)
        return out


def ptr_rewrite(body):
    rw = Rewriter(); rw.declared = {i.name for i in body if isinstance(i, c_ast.Decl) and not isinstance(i.type, (c_ast.PtrDecl, c_ast.ArrayDecl))}
    out = rw.stmts(body); root = c_ast.Compound(out)
    for n in walk(root):
        if isinstance(n, c_ast.IdentifierType) and n.names in (['size_t'], ['wchar_t']): n.names = ['unsigned', 'long'] if n.names == ['size_t'] else ['int']
        for name, child in list(n.children()):
            if isinstance(child, c_ast.Constant) and child.type == 'char':
                v = child.value.lstrip('L'); ch = v[1:-1]; code = 0 if ch == '\\0' else ord(ch[-1]) if len(ch) == 1 or ch.startswith('\\') is False else 0
                new = c_ast.Constant('int', str(code))
                import re; m = re.match(r'(\w+)\[(\d+)\]$', name)
                if m: getattr(n, m.group(1))[int(m.group(2))] = new
                else: setattr(n, name, new)
    return root.block_items
