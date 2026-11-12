"""v0.79/0.80: pointer front end for Juliet CWE124/126/127 (+CWE839 index variants), UNTRUSTED syntactic rewrite into the bounds-only array model of scripts/juliet_eval.py.
Pointer = alias (base array, offset) where the offset is a constant OR a symbolic expression (dynamic offsets: `p = a + n`); p[e] -> a[e+off]; *p -> a[off]; pointer comparisons on one base compare offsets;
library calls become access-range checks (memset/memcpy/memmove/strcpy/strncpy and wide variants); strlen of a memset-filled NUL-terminated array is the constant fill length; large constant loops are
peeled to the first and last iteration; constant `if`/`switch`/`while(1){..break;}` (Juliet control-flow variants 02-16) are folded; a non-constant `if` splits the CONTINUATION (both paths are checked);
calls to user functions of the same testcase (Juliet 4x/5x/6x/etc.: sinks and sources, function pointers, pointer-to-pointer, globals) are INLINED with parameters bound to aliases.
Anything else raises ValueError (counted as skipped). Ground truth is the Juliet naming; the unchanged typed_c verifier decides."""
import copy, re
from pycparser import c_ast

CHECK_FUNCS = {'memset': (0,), 'wmemset': (0,), 'memcpy': (0, 1), 'memmove': (0, 1), 'wmemcpy': (0, 1), 'wmemmove': (0, 1)}
STR_FUNCS = {'strcpy': 'cpy', 'wcscpy': 'cpy', 'strncpy': 'ncpy', 'wcsncpy': 'ncpy'}
ALLOCS = ('malloc', 'ALLOCA', 'alloca')
BASIC = {'int', 'char', 'long', 'short', 'unsigned', 'signed', 'float', 'double', 'void', 'size_t', 'wchar_t', '_Bool', 'unsigned long'}
IGNORED = ('printLine', 'printWLine', 'printIntLine', 'printStructLine', 'printSizeTLine', 'exit')


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def num(v): return c_ast.Constant('int', str(v))


def setchild(n, name, new):
    m = re.match(r'(\w+)\[(\d+)\]$', name)
    if m: getattr(n, m.group(1))[int(m.group(2))] = new
    else: setattr(n, name, new)


def isnul(e): return isinstance(e, c_ast.Constant) and e.type == 'char' and e.value in ("'\\0'", "L'\\0'")
def sink_bad(): return c_ast.Assignment('=', c_ast.ID('__sink'), c_ast.BinaryOp('/', num(1), c_ast.BinaryOp('-', c_ast.ID('__sink'), c_ast.ID('__sink'))))


def add_off(off, k, sign=1):
    if isinstance(off, int) and isinstance(k, int): return off + sign * k
    a = num(off) if isinstance(off, int) else off; b = num(k) if isinstance(k, int) else k
    return c_ast.BinaryOp('+' if sign > 0 else '-', copy.deepcopy(a), copy.deepcopy(b))


class Rewriter:
    def __init__(self, funcs=None):
        self.size = {}; self.alias = {}; self.ptrs = {}; self.consts = {}; self.fill = {}; self.slen = {}; self.seen = set(); self.nsh = 0
        self.funcs = funcs or {}; self.pp = {}; self.fnptr = {}; self.ret = None; self.depth = 0; self.ptabs = set(); self.structs = set(); self.unions = set()

    # ------------------------------------------------------------------ constants
    def cexpr(self, e):
        if isinstance(e, c_ast.Constant) and e.type == 'int': return int(e.value.rstrip('uUlL'), 0)
        if isinstance(e, c_ast.Constant) and e.type == 'char': return 0 if 'x00' in e.value or '\\0' in e.value else ord(e.value.lstrip('L')[1:-1][-1])
        if isinstance(e, c_ast.ID) and e.name in self.consts: return self.consts[e.name]
        if isinstance(e, c_ast.Cast): return self.cexpr(e.expr)
        if isinstance(e, c_ast.FuncCall) and getattr(e.name, 'name', '') in ('strlen', 'wcslen'):
            p = self.pexpr(e.args.exprs[0])
            if p is None or p[0] not in self.slen or not isinstance(p[1], int): raise ValueError('unknown strlen')
            return self.slen[p[0]] - p[1]
        if isinstance(e, c_ast.UnaryOp):
            if e.op == 'sizeof': return 1          # counts are in ELEMENTS
            if e.op == '-': return -self.cexpr(e.expr)
            if e.op == '!': return int(not self.cexpr(e.expr))
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ('&&', '||'):
                a = self.cexpr(e.left)
                if e.op == '&&' and not a: return 0
                if e.op == '||' and a: return 1
                return int(bool(self.cexpr(e.right)))
            a, b = self.cexpr(e.left), self.cexpr(e.right)
            ops = {'+': a + b, '-': a - b, '*': a * b, '==': int(a == b), '!=': int(a != b), '<': int(a < b), '<=': int(a <= b), '>': int(a > b), '>=': int(a >= b)}
            if e.op in ops: return ops[e.op]
        raise ValueError('non-constant expression')

    # ------------------------------------------------------------------ pointer slots: array-of-pointer elements `a[2]` and struct fields `s.f` are tracked like pointer variables
    def slot(self, e):
        if isinstance(e, c_ast.ArrayRef) and isinstance(e.name, c_ast.ID) and e.name.name in self.ptabs:
            return '%s[%d]' % (e.name.name, self.cexpr(e.subscript))
        if isinstance(e, c_ast.StructRef) and e.type == '.' and isinstance(e.name, c_ast.ID) and e.name.name in self.structs: return '%s.%s' % (e.name.name, '*' if e.name.name in self.unions else e.field.name)
        return None

    # ------------------------------------------------------------------ pointer expressions -> (base, offset) | None (NULL)
    def pexpr(self, e):
        try: sk = self.slot(e)
        except ValueError: sk = None
        if sk is not None: return self.alias.get(sk)
        if isinstance(e, c_ast.Cast): return self.pexpr(e.expr)
        if isinstance(e, c_ast.Constant) and e.value == '0': return None
        if isinstance(e, c_ast.ID):
            if e.name in self.ptrs: return self.alias.get(e.name)
            if e.name in self.size: return (e.name, 0)
        if isinstance(e, c_ast.UnaryOp) and e.op == '*' and isinstance(e.expr, c_ast.ID) and e.expr.name in self.pp: return self.alias.get(self.pp[e.expr.name])
        if isinstance(e, c_ast.UnaryOp) and e.op == '&' and isinstance(e.expr, c_ast.ArrayRef) and isinstance(e.expr.name, c_ast.ID):
            b = self.pexpr(e.expr.name)
            if b is None: raise ValueError('null base')
            try: return (b[0], add_off(b[1], self.cexpr(e.expr.subscript)))
            except ValueError: return (b[0], add_off(b[1], copy.deepcopy(e.expr.subscript)))
        if isinstance(e, c_ast.BinaryOp) and e.op in '+-':
            b = self.pexpr(e.left)
            if b is not None:
                try: return (b[0], add_off(b[1], self.cexpr(e.right), 1 if e.op == '+' else -1))
                except ValueError: return (b[0], add_off(b[1], copy.deepcopy(e.right), 1 if e.op == '+' else -1))
        raise ValueError('unsupported pointer expression')

    def is_ptr(self, e):
        try: self.pexpr(e); return True
        except ValueError: return False

    def deref(self, name, idx):
        a = self.alias.get(name) if name in self.ptrs else ((name, 0) if name in self.size else None)
        if a is None: raise ValueError('null or unknown pointer dereference')
        e = idx if (isinstance(a[1], int) and a[1] == 0) else add_off(idx, a[1]) if isinstance(idx, int) else c_ast.BinaryOp('+', idx, num(a[1]) if isinstance(a[1], int) else copy.deepcopy(a[1]))
        return c_ast.ArrayRef(c_ast.ID(a[0]), e if not isinstance(e, int) else num(e))

    def expr(self, n):
        """rewrite pointer dereferences / pointer comparisons / strlen inside an expression tree (in place)"""
        for name, child in list(n.children()):
            self.expr(child)
            new = None
            if isinstance(child, c_ast.ArrayRef) and isinstance(child.name, c_ast.ID) and child.name.name in self.ptrs: new = self.deref(child.name.name, child.subscript)
            elif isinstance(child, c_ast.UnaryOp) and child.op == '*' and isinstance(child.expr, c_ast.ID) and child.expr.name in self.ptrs: new = self.deref(child.expr.name, num(0))
            elif isinstance(child, c_ast.UnaryOp) and child.op == '*' and isinstance(child.expr, c_ast.ID) and child.expr.name in self.pp: raise ValueError('pointer-to-pointer value in arithmetic')
            elif isinstance(child, c_ast.FuncCall) and getattr(child.name, 'name', '') in ('strlen', 'wcslen'): new = num(self.cexpr(child))
            elif isinstance(child, c_ast.BinaryOp) and child.op in ('==', '!=', '<', '<=', '>', '>=') and (self.is_ptr(child.left) and self.is_ptr(child.right)) and not (isinstance(child.left, c_ast.Constant) and isinstance(child.right, c_ast.Constant)):
                l, r = self.pexpr(child.left), self.pexpr(child.right)
                if l is None or r is None:
                    if child.op in ('==', '!='): new = num(int((l is None and r is None) == (child.op == '==')))
                    else: raise ValueError('ordered comparison with NULL')
                elif l[0] != r[0]: raise ValueError('comparison of unrelated pointers')
                else: new = c_ast.BinaryOp(child.op, num(l[1]) if isinstance(l[1], int) else copy.deepcopy(l[1]), num(r[1]) if isinstance(r[1], int) else copy.deepcopy(r[1]))
            if new is not None: setchild(n, name, new)

    # ------------------------------------------------------------------ access checks
    def access(self, p, count):
        a = self.pexpr(p)
        if a is None: raise ValueError('null pointer access')
        if count <= 0: return []
        base, off = a
        if isinstance(off, int): return [] if off >= 0 and off + count <= self.size[base] else [sink_bad()]
        cond = c_ast.BinaryOp('&&', c_ast.BinaryOp('>=', copy.deepcopy(off), num(0)), c_ast.BinaryOp('<=', c_ast.BinaryOp('+', copy.deepcopy(off), num(count)), num(self.size[base])))
        return [c_ast.Assignment('=', c_ast.ID('__sink'), c_ast.BinaryOp('*', num(0), c_ast.BinaryOp('/', num(1), cond)))]

    def call(self, s):
        nm = getattr(s.name, 'name', ''); args = s.args.exprs if s.args else []
        if nm in IGNORED: return []
        if nm in CHECK_FUNCS:
            n = self.cexpr(args[2]); out = []
            for i in CHECK_FUNCS[nm]: out += self.access(args[i], n)
            a0 = self.pexpr(args[0])
            if nm in ('memset', 'wmemset') and a0 and isinstance(a0[1], int) and a0[1] == 0 and not (isinstance(args[1], c_ast.Constant) and args[1].value in ("0", "'\\0'")): self.fill[a0[0]] = n
            return out
        if nm in STR_FUNCS:
            kind = STR_FUNCS[nm]; d = self.pexpr(args[0]); sp = self.pexpr(args[1])
            if d is None or sp is None: raise ValueError('null pointer string op')
            srcl = self.slen.get(sp[0]); srcl = None if (srcl is None or not isinstance(sp[1], int)) else srcl - sp[1]
            if kind == 'cpy':
                if srcl is None: raise ValueError('unknown string length')
                n = srcl + 1; return self.access(args[0], n) + self.access(args[1], n)
            n = self.cexpr(args[2]); m = n if srcl is None else min(n, srcl + 1)
            return self.access(args[0], n) + self.access(args[1], m)
        if nm == 'free':
            a = self.pexpr(args[0])
            if a is None: return []
            if isinstance(a[1], int): return [] if a[1] == 0 else [sink_bad()]
            return [c_ast.Assignment('=', c_ast.ID('__sink'), c_ast.BinaryOp('*', num(0), c_ast.BinaryOp('/', num(1), c_ast.BinaryOp('==', copy.deepcopy(a[1]), num(0)))))]
        target = self.fnptr.get(nm, nm)
        if target in self.funcs: return self.inline(self.funcs[target], args)[0]
        raise ValueError('call to ' + nm)

    # ------------------------------------------------------------------ inlining
    def inline(self, fd, args):
        if self.depth > 6: raise ValueError('inlining too deep')
        params = fd.decl.type.args.params if fd.decl.type.args else []
        params = [p for p in params if not (isinstance(p, c_ast.Typename) and getattr(p.type, 'type', None) is not None and isinstance(p.type.type, c_ast.IdentifierType) and p.type.type.names == ['void'])]
        if len(params) != len(args): raise ValueError('arity mismatch')
        body = copy.deepcopy(fd.body); self.nsh += 1; sfx = '__i%d' % self.nsh
        names = {p.name for p in params} | {d.name for n in walk(body) for d in [n] if isinstance(d, c_ast.Decl) and d.name}
        for n in walk(body):
            if isinstance(n, c_ast.Decl) and n.name in names:
                n.name += sfx; ty = n.type
                while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
                if ty is not None: ty.declname = n.name
            elif isinstance(n, c_ast.ID) and n.name in names: n.name += sfx
        pre = []
        for p, a in zip(params, args):
            nm = p.name + sfx
            if isinstance(p.type, c_ast.ArrayDecl) and isinstance(p.type.type, c_ast.PtrDecl) or (isinstance(p.type, c_ast.PtrDecl) and isinstance(p.type.type, c_ast.PtrDecl)):
                self.ptabs.add(nm)
                if isinstance(a, c_ast.ID) and a.name in self.ptabs:
                    for k, v in list(self.alias.items()):
                        if k.startswith(a.name + '['): self.alias[nm + k[len(a.name):]] = v; self.ptrs[nm + k[len(a.name):]] = None
                elif isinstance(a, c_ast.UnaryOp) and a.op == '&' and isinstance(a.expr, c_ast.ID) and a.expr.name in self.ptrs: self.pp[nm] = a.expr.name; self.ptabs.discard(nm)
                else: raise ValueError('pointer-to-pointer parameter')
            elif isinstance(p.type, c_ast.TypeDecl) and isinstance(p.type.type, c_ast.IdentifierType) and p.type.type.names[0] not in BASIC and isinstance(a, c_ast.ID) and a.name in self.structs:
                self.structs.add(nm)
                for k, v in list(self.alias.items()):
                    if k.startswith(a.name + '.'): self.alias[nm + k[len(a.name):]] = v; self.ptrs[nm + k[len(a.name):]] = None
            elif isinstance(p.type, c_ast.PtrDecl) and isinstance(a, c_ast.UnaryOp) and a.op == '&' and isinstance(a.expr, c_ast.ID) and a.expr.name in self.ptrs: self.pp[nm] = a.expr.name   # void * carrying &ptr
            elif isinstance(p.type, c_ast.PtrDecl):
                self.ptrs[nm] = p.type.type.type if isinstance(p.type.type, c_ast.TypeDecl) else p.type.type; self.alias[nm] = self.pexpr(a)
            else:
                d = c_ast.Decl(nm, [], [], [], [], copy.deepcopy(p.type), copy.deepcopy(a), None); d.type.declname = nm if isinstance(d.type, c_ast.TypeDecl) else None
                if isinstance(d.type, c_ast.TypeDecl): d.type.declname = nm
                pre += self.stmt(d)
        self.depth += 1; saved = self.ret; self.ret = None
        items = list(body.block_items or [])
        if items and isinstance(items[-1], c_ast.Return): rv = items.pop().expr
        else: rv = None
        out = pre + self.stmts(items)
        if rv is not None:
            try: self.ret = ('ptr', self.pexpr(rv))
            except ValueError: self.ret = ('expr', rv)
        self.depth -= 1; r = self.ret; self.ret = saved
        return out, r

    # ------------------------------------------------------------------ statements
    def stmt(self, s):
        if isinstance(s, c_ast.Compound): return [c_ast.Compound(self.stmts(self.uniquify(s.block_items or [])))]
        if isinstance(s, c_ast.Decl): return self.decl(s)
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ID) and s.lvalue.name in self.ptrs and s.op == '=': return self.passign(s.lvalue.name, s.rvalue)
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.UnaryOp) and s.lvalue.op == '*' and isinstance(s.lvalue.expr, c_ast.ID) and s.lvalue.expr.name in self.pp and s.op == '=': return self.passign(self.pp[s.lvalue.expr.name], s.rvalue)
        if isinstance(s, c_ast.Assignment) and s.op == '=' and self.slot(s.lvalue) is not None: self.ptrs.setdefault(self.slot(s.lvalue), None); return self.passign(self.slot(s.lvalue), s.rvalue)
        if isinstance(s, c_ast.FuncCall): return self.call(s)
        if isinstance(s, c_ast.For): return self.loop(s)
        if isinstance(s, c_ast.While) and self.truth(s.cond) is True:       # while(1){ ...; break; }
            items = list(s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt])
            if items and isinstance(items[-1], c_ast.Break) and not any(isinstance(x, (c_ast.Break, c_ast.Continue)) for it in items[:-1] for x in walk(it)): return self.stmt(c_ast.Compound(items[:-1]))
            raise ValueError('control flow')
        if isinstance(s, c_ast.Switch): return self.switch(s)
        if isinstance(s, c_ast.If):
            t = self.truth(s.cond)
            if t is not None:
                br = s.iftrue if t else s.iffalse
                return self.stmt(br) if br is not None else []
            if isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '==' and isinstance(s.cond.left, c_ast.ID) and s.cond.left.name in self.ptrs and isinstance(s.cond.right, c_ast.Constant) and s.cond.right.value == '0' and self.alias.get(s.cond.left.name) is not None: return []
            raise ValueError('__split__')           # handled by stmts() (continuation splitting)
        if isinstance(s, (c_ast.While, c_ast.DoWhile, c_ast.Goto, c_ast.Return, c_ast.Label, c_ast.Break, c_ast.Continue)): raise ValueError('control flow')
        if isinstance(s, c_ast.Assignment) and isinstance(s.rvalue, c_ast.FuncCall) and getattr(s.rvalue.name, 'name', '') in self.funcs.keys() | self.fnptr.keys():
            nm = getattr(s.rvalue.name, 'name', ''); out, r = self.inline(self.funcs[self.fnptr.get(nm, nm)], s.rvalue.args.exprs if s.rvalue.args else [])
            if r is None: raise ValueError('callee returns nothing')
            if isinstance(s.lvalue, c_ast.ID) and s.lvalue.name in self.ptrs and r[0] == 'ptr': self.alias[s.lvalue.name] = r[1]; return out
            if r[0] == 'expr': s.rvalue = r[1]; self.expr(s); return out + [s]
            raise ValueError('unsupported call result')
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ID) and s.op == '=':
            self.expr(s)
            try: self.consts[s.lvalue.name] = self.cexpr(s.rvalue)
            except ValueError: self.consts.pop(s.lvalue.name, None)
            return [s]
        self.expr(s)
        if isinstance(s, c_ast.Assignment) and isinstance(s.lvalue, c_ast.ArrayRef) and isnul(s.rvalue) and isinstance(s.lvalue.name, c_ast.ID):
            b = s.lvalue.name.name
            try: k = self.cexpr(s.lvalue.subscript)
            except ValueError: k = None
            if k is not None and self.fill.get(b) == k: self.slen[b] = k
        return [s]

    def truth(self, c):
        try: return bool(self.cexpr(c))
        except ValueError: pass
        if isinstance(c, c_ast.BinaryOp) and c.op in ('==', '!=', '<', '<=', '>', '>=') and self.is_ptr(c.left) and self.is_ptr(c.right):
            l, r = self.pexpr(c.left), self.pexpr(c.right)
            if c.op in ('==', '!='):
                if (l is None) != (r is None): return c.op == '!='
                if l is None: return c.op == '=='
            if l is not None and r is not None and l[0] == r[0] and isinstance(l[1], int) and isinstance(r[1], int):
                return {'==': l[1] == r[1], '!=': l[1] != r[1], '<': l[1] < r[1], '<=': l[1] <= r[1], '>': l[1] > r[1], '>=': l[1] >= r[1]}[c.op]
        return None

    def decl(self, s):
        ty = s.type
        if isinstance(ty, c_ast.ArrayDecl) and isinstance(ty.type, c_ast.PtrDecl): self.ptabs.add(s.name); return []                      # char *a[N]
        if isinstance(ty, c_ast.TypeDecl) and isinstance(ty.type, c_ast.IdentifierType) and ty.type.names[0] not in BASIC and s.init is None:
            self.structs.add(s.name)
            if 'union' in ty.type.names[0]: self.unions.add(s.name)
            return []   # struct typedef variable
        if isinstance(ty, c_ast.PtrDecl) and isinstance(ty.type, c_ast.PtrDecl):          # T **pp = &p
            init = s.init.expr if isinstance(s.init, c_ast.Cast) else s.init
            if init is not None and isinstance(init, c_ast.UnaryOp) and init.op == '&' and isinstance(init.expr, c_ast.ID) and init.expr.name in self.ptrs: self.pp[s.name] = init.expr.name; return []
            if init is not None and isinstance(init, c_ast.ID) and init.name in self.pp: self.pp[s.name] = self.pp[init.name]; return []
            raise ValueError('pointer-to-pointer')
        if isinstance(ty, c_ast.PtrDecl) and isinstance(ty.type, c_ast.FuncDecl):         # function pointer
            if s.init is not None and isinstance(s.init, c_ast.ID) and s.init.name in self.funcs: self.fnptr[s.name] = s.init.name; return []
            raise ValueError('function pointer')
        if isinstance(ty, c_ast.PtrDecl):
            self.ptrs[s.name] = ty.type.type if isinstance(ty.type, c_ast.TypeDecl) else ty.type; self.alias[s.name] = None
            return [] if s.init is None else self.passign(s.name, s.init)
        if isinstance(ty, c_ast.ArrayDecl):
            n = self.cexpr(ty.dim); self.size[s.name] = n; ty.dim = num(n); return [s]
        if s.init is not None and not isinstance(s.init, c_ast.InitList):
            self.expr(s.init)
            try: self.consts[s.name] = self.cexpr(s.init)
            except ValueError: self.consts.pop(s.name, None)
        else: self.consts.pop(s.name, None)
        return [s]

    def passign(self, name, rv):
        rv0 = rv.expr if isinstance(rv, c_ast.Cast) else rv
        if isinstance(rv0, c_ast.FuncCall) and getattr(rv0.name, 'name', '') in ALLOCS:
            n = self.cexpr(rv0.args.exprs[0]); self.nsh += 1; un = '%s__a%d' % (name, self.nsh); self.size[un] = n; self.alias[name] = (un, 0)   # one object name per allocation site/path
            return [c_ast.Decl(un, [], [], [], [], c_ast.ArrayDecl(c_ast.TypeDecl(un, [], None, self.ptrs[name]), num(n), []), None, None)]
        if isinstance(rv0, c_ast.UnaryOp) and rv0.op == '*' and isinstance(rv0.expr, c_ast.ID) and rv0.expr.name in self.pp: self.alias[name] = self.alias.get(self.pp[rv0.expr.name]); return []
        if isinstance(rv0, c_ast.FuncCall):
            nm = getattr(rv0.name, 'name', ''); nm = self.fnptr.get(nm, nm)
            if nm in self.funcs:
                out, r = self.inline(self.funcs[nm], rv0.args.exprs if rv0.args else [])
                if r is None or r[0] != 'ptr': raise ValueError('callee does not return a pointer')
                self.alias[name] = r[1]; return out
        self.alias[name] = self.pexpr(rv); return []

    def switch(self, s):
        v = self.cexpr(s.cond); body = s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt]; taken = []; on = False
        for it in body:
            if isinstance(it, c_ast.Case) and not on and self.cexpr(it.expr) == v: on = True
            if isinstance(it, c_ast.Default) and not on and not any(isinstance(x, c_ast.Case) and self.cexpr(x.expr) == v for x in body): on = True
            if on:
                for st in it.stmts:
                    if isinstance(st, c_ast.Break): return self.stmts(taken)
                    taken.append(st)
        return self.stmts(taken)

    def loop(self, s):
        if not (isinstance(s.init, c_ast.Assignment) and isinstance(s.init.lvalue, c_ast.ID) and isinstance(s.cond, c_ast.BinaryOp) and s.cond.op == '<' and isinstance(s.cond.left, c_ast.ID) and s.cond.left.name == s.init.lvalue.name): raise ValueError('loop shape')
        v = s.init.lvalue.name; a = self.cexpr(s.init.rvalue); b = self.cexpr(s.cond.right); trip = b - a
        if trip < 0: raise ValueError('negative trip')
        body = s.stmt.block_items if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
        out = []; its = list(range(a, b)) if trip <= 12 else [a, b - 1]
        for it in its:
            out.append(c_ast.Assignment('=', c_ast.ID(v), num(it))); self.consts[v] = it
            out.append(c_ast.Compound(self.stmts(copy.deepcopy(list(body)))))
        out.append(c_ast.Assignment('=', c_ast.ID(v), num(b))); self.consts[v] = b; return out

    def uniquify(self, items):
        """block-scope redeclaration (or a name used by an enclosing/earlier scope, including arrays and pointers): fresh name, because sizes/aliases are keyed by name. Renaming is sequential:
        an initializer that mentions the OUTER variable keeps referring to it (char *data = dataCopy; ... {char *data = dataCopy;})"""
        mine = {i.name for i in items if isinstance(i, c_ast.Decl) and i.name}
        clash = mine & self.seen
        if not clash: self.seen |= mine; return items
        self.nsh += 1; sfx = '__s%d' % self.nsh; cur = set()
        def ren(node):
            for n in walk(node):
                if isinstance(n, c_ast.ID) and n.name in cur: n.name += sfx
        for it in items:
            if isinstance(it, c_ast.Decl) and it.name in clash:
                if it.init is not None: ren(it.init)
                it.name += sfx; cur.add(it.name[:-len(sfx)]); ty = it.type
                while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
                if ty is not None: ty.declname = it.name
            else: ren(it)
        self.seen |= {x + sfx if x in clash else x for x in mine}; return items

    def stmts(self, ss):
        out = []; ss = list(ss)
        for k, s in enumerate(ss):
            if isinstance(s, c_ast.Goto) and k + 1 < len(ss) and isinstance(ss[k + 1], c_ast.Label) and ss[k + 1].name == s.name: continue      # goto to the next statement
            if isinstance(s, c_ast.Label): s = s.stmt
            try: out += self.stmt(s)
            except ValueError as e:
                if str(e) != '__split__': raise
                rest = ss[k + 1:]; self.expr(s.cond) if False else None
                alias, consts, fill, slen, pp = dict(self.alias), dict(self.consts), dict(self.fill), dict(self.slen), dict(self.pp); branches = []
                for br in (s.iftrue, s.iffalse):
                    self.alias, self.consts, self.fill, self.slen, self.pp = dict(alias), dict(consts), dict(fill), dict(slen), dict(pp)
                    items = self.uniquify(([br] if br is not None else []) + copy.deepcopy(rest)); branches.append(c_ast.Compound(self.stmts(items)))
                holder = c_ast.ExprList([copy.deepcopy(s.cond)]); self.expr(holder); cond = holder.exprs[0]
                out.append(c_ast.If(cond, branches[0], branches[1])); return out
        return out


def ptr_rewrite(body, funcs=None, globals_ptrs=()):
    rw = Rewriter(funcs)
    for n, elt in globals_ptrs: rw.ptrs[n] = elt; rw.alias[n] = None
    rw.seen = {i.name for i in body if isinstance(i, c_ast.Decl) and i.name} | set(rw.ptrs)
    out = rw.stmts(body); root = c_ast.Compound(out)
    for n in walk(root):
        if isinstance(n, c_ast.IdentifierType) and n.names in (['size_t'], ['wchar_t']): n.names = ['unsigned', 'long'] if n.names == ['size_t'] else ['int']
        for name, child in list(n.children()):
            if isinstance(child, c_ast.Constant) and child.type == 'char':
                v = child.value.lstrip('L'); ch = v[1:-1]; code = 0 if ch in ('\\0', '\\x00') else ord(ch[-1]); setchild(n, name, num(code))
    return root.block_items
