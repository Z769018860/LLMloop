"""v0.82: MEMORY ABSTRACTION for the automatic transcriber.  Pointers/arrays/struct accesses are abstracted so that the scalar fragment can be used:
  * every READ through a pointer / array / struct member (`*p`, `p[i]`, `p->f`, `s.f`) of scalar type T becomes an arbitrary value of type T (typed nondeterministic input nondet_T()),
    the integer sub-expressions of the address computation (indices, offsets) are still evaluated (`nondet_T() + 0*(index)`), so arithmetic undefined behaviour inside them is still checked;
  * WRITES through pointers are dropped (their right-hand side is still evaluated); pointer variables, pointer arithmetic and pointer assignments are dropped (integer parts evaluated);
  * pointer comparisons / null tests / pointer-to-integer casts / pointer differences become nondeterministic values; sizeof(struct) is an arbitrary value in [1, 65536];
  * pointer parameters and pointer-valued globals are not parameters of the scalar function.
SOUNDNESS CONTRACT (weaker than full memory safety, recorded in every result): the verdict covers undefined behaviour of the SCALAR arithmetic (overflow, division by zero, shifts) under the
assumption that all memory accesses are valid and that writes through pointers do not change the function's scalar locals (their address is never taken: `&local` is rejected).
Out-of-bounds / use-after-free / NULL dereference are NOT checked.  Struct values, floating point, function pointers, goto are rejected."""
import copy, re
from pycparser import c_parser, c_ast
INTS = {('int',): 1, ('unsigned',): 1, ('unsigned', 'int'): 1, ('long',): 1, ('long', 'int'): 1, ('unsigned', 'long'): 1, ('unsigned', 'long', 'int'): 1, ('short',): 1, ('unsigned', 'short'): 1, ('char',): 1, ('unsigned', 'char'): 1,
        ('signed', 'char'): 1, ('long', 'long'): 1, ('unsigned', 'long', 'long'): 1, ('short', 'int'): 1, ('unsigned', 'short', 'int'): 1, ('long', 'long', 'int'): 1, ('unsigned', 'long', 'long', 'int'): 1, ('signed',): 1, ('signed', 'int'): 1}
NDNAME = {('int',): 'int', ('signed',): 'int', ('signed', 'int'): 'int', ('unsigned',): 'uint', ('unsigned', 'int'): 'uint', ('long',): 'long', ('long', 'int'): 'long', ('unsigned', 'long'): 'ulong', ('unsigned', 'long', 'int'): 'ulong',
          ('short',): 'short', ('short', 'int'): 'short', ('unsigned', 'short'): 'ushort', ('unsigned', 'short', 'int'): 'ushort', ('char',): 'char', ('unsigned', 'char'): 'uchar', ('signed', 'char'): 'char', ('long', 'long'): 'longlong',
          ('long', 'long', 'int'): 'longlong', ('unsigned', 'long', 'long'): 'ulonglong', ('unsigned', 'long', 'long', 'int'): 'ulonglong'}
SIZES = {'char': 1, 'uchar': 1, 'short': 2, 'ushort': 2, 'int': 4, 'uint': 4, 'long': 8, 'ulong': 8, 'longlong': 8, 'ulonglong': 8}
from pycparser import c_generator
_gen = c_generator.CGenerator()
_P = c_parser.CParser()


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def num(v): return c_ast.Constant('int', str(v))


def setchild(n, name, new):
    m = re.match(r'(\w+)\[(\d+)\]$', name)
    if m: getattr(n, m.group(1))[int(m.group(2))] = new
    else: setattr(n, name, new)


def desc(ty):
    """type node -> ('s', words) scalar | ('p', pointee) pointer/array | ('st', tag) struct/union | ('v',) void | None"""
    if isinstance(ty, c_ast.TypeDecl):
        t = ty.type
        if isinstance(t, c_ast.IdentifierType): w = tuple(t.names); return ('s', w) if w in INTS else ('v',) if w == ('void',) else None
        if isinstance(t, (c_ast.Struct, c_ast.Union)): return ('st', t.name)
        return None
    if isinstance(ty, c_ast.PtrDecl) and isinstance(ty.type, c_ast.FuncDecl): return ('p', ('fn', desc(ty.type.type)))
    if isinstance(ty, (c_ast.PtrDecl, c_ast.ArrayDecl)): return ('p', desc(ty.type))
    if isinstance(ty, c_ast.Typename): return desc(ty.type)
    return None


def parse_decl(text):
    try:
        ast = _P.parse(text if text.rstrip().endswith(';') else text + ';')
        d = ast.ext[0]
        return d.type if isinstance(d, c_ast.Decl) else None
    except Exception: return None


class Env:
    """TU-level type information: struct fields, global variable types, prototype return types"""
    def __init__(self, text, tmap, clean):
        self.fields = {}; self.gtypes = {}; self.ret = {}
        blocks = re.findall(r'^(?:struct|union) (\w+) \{\n(.*?)\n\};', text, re.M | re.S) + [(nm, body) for body, nm in re.findall(r'^typedef (?:struct|union) \{\n(.*?)\n\} (\w+);', text, re.M | re.S)]
        for tag, body in blocks:
            f = {}
            def add_struct(st):
                for d in st.decls or []:
                    if d.name: f[d.name] = desc(d.type)
                    elif isinstance(d.type, c_ast.TypeDecl) and isinstance(d.type.type, (c_ast.Struct, c_ast.Union)) and d.type.type.decls: add_struct(d.type.type)          # anonymous member: promoted
            try: add_struct(_P.parse('struct __t { %s };' % re.sub(r'\s*:\s*\d+;', ';', clean(body, tmap))).ext[0].type)
            except Exception:
                for line in body.split('\n'):
                    line = line.strip()
                    if not line.endswith(';') or '{' in line or '}' in line: continue
                    try:
                        for d in _P.parse('struct __t { %s };' % re.sub(r'\s*:\s*\d+;$', ';', clean(line, tmap))).ext[0].type.decls: f[d.name] = desc(d.type)
                    except Exception: pass
            self.fields[tag] = f
        for line in text.split('\n'):
            m = re.match(r'^(?:static |extern )*(.+?[\s\*])(\w+)((?:\[[^\]]*\])*)(?: = .*;| = \{.*)?;?$', line)
            if m and not line.startswith(('typedef', 'struct', 'union', 'enum')) and '(' not in line:
                ty = parse_decl(clean(m.group(1), tmap) + ' ' + m.group(2) + (m.group(3) or '') + ';')
                if ty is not None: self.gtypes[m.group(2)] = desc(ty)
        for line in text.split('\n'):
            m = re.match(r'^(?:extern |static )*(.+?[\s\*])(\w+)\s*\(.*\)\s*;\s*$', line)
            if m and not line.startswith(('typedef', 'struct', 'union', 'enum', ' ')):
                ty = parse_decl(clean(m.group(1), tmap) + ' zz;')
                if ty is not None: self.ret.setdefault(m.group(2), desc(ty))


class MemAbs:
    def __init__(self, fd, env, notes, defs_ret=None):
        self.fd, self.env, self.notes, self.k = fd, env, notes, 0
        self.sym = {}
        for p in (fd.decl.type.args.params if fd.decl.type.args else []):
            if isinstance(p, c_ast.Decl): self.sym[p.name] = desc(p.type)
        for n in walk(fd.body):
            if isinstance(n, c_ast.Decl) and n.name: self.sym[n.name] = desc(n.type)
        self.retdesc = desc(fd.decl.type.type); self.defs_ret = defs_ret or {}

    # ----------------------------------------------------------------- typing
    def ety(self, e):
        if isinstance(e, c_ast.ID):
            if e.name in self.sym: return self.sym[e.name]
            if e.name in self.env.gtypes: return self.env.gtypes[e.name]
            return ('s', ('int',))
        if isinstance(e, c_ast.Constant): return ('p', ('v',)) if e.type == 'string' else ('s', ('int',))
        if isinstance(e, c_ast.Cast): return desc(e.to_type)
        if isinstance(e, c_ast.UnaryOp):
            if e.op == '*': d = self.ety(e.expr); return d[1] if d and d[0] == 'p' else None
            if e.op == '&': d = self.ety(e.expr); return ('p', d) if d else None
            if e.op in ('p++', 'p--', '++', '--'): return self.ety(e.expr)
            if e.op == 'sizeof': return ('s', ('unsigned', 'long'))
            return ('s', ('int',))
        if isinstance(e, c_ast.ArrayRef):
            d = self.ety(e.name); return d[1] if d and d[0] == 'p' else None
        if isinstance(e, c_ast.StructRef):
            d = self.ety(e.name)
            if e.type == '->':
                d = d[1] if d and d[0] == 'p' else None
            if not d or d[0] != 'st' or d[1] not in self.env.fields: return None
            return self.env.fields[d[1]].get(e.field.name)
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ('+', '-'):
                l, r = self.ety(e.left), self.ety(e.right)
                if l and l[0] == 'p' and r and r[0] == 'p': return ('s', ('long',))
                if l and l[0] == 'p': return l
                if r and r[0] == 'p' and e.op == '+': return r
                return l if l and l[0] == 's' else ('s', ('int',))
            if e.op in ('==', '!=', '<', '<=', '>', '>=', '&&', '||'): return ('s', ('int',))
            return self.ety(e.left) if self.ety(e.left) and self.ety(e.left)[0] == 's' else ('s', ('int',))
        if isinstance(e, c_ast.TernaryOp): return self.ety(e.iftrue)
        if isinstance(e, c_ast.Assignment): return self.ety(e.lvalue)
        if isinstance(e, c_ast.FuncCall):
            if not isinstance(e.name, c_ast.ID):
                d = self.ety(e.name)
                if d and d[0] == 'p' and d[1] and d[1][0] == 'fn': return d[1][1]
                return None
            nm = e.name.name
            return self.env.ret.get(nm) or self.defs_ret.get(nm) or ('s', ('int',))
        if isinstance(e, c_ast.ExprList): return self.ety(e.exprs[-1])
        return None

    def is_ptr(self, e): d = self.ety(e); return bool(d and d[0] == 'p')

    def nd(self, words):
        return c_ast.FuncCall(c_ast.ID('nondet_' + NDNAME[words]), None)

    def with_ubs(self, base, ubs):
        for u in ubs: base = c_ast.BinaryOp('+', base, c_ast.BinaryOp('*', num(0), u))
        return base

    # ----------------------------------------------------------------- integer parts of address computations (rewritten)
    def ubs(self, x):
        """integer sub-expressions that are evaluated when the pointer-valued expression x is computed"""
        if isinstance(x, (c_ast.ID, c_ast.Constant)): return []
        if isinstance(x, c_ast.Cast): return self.ubs(x.expr) if self.is_ptr(x.expr) else [self.ex(x.expr)] if self.ety(x.expr) and self.ety(x.expr)[0] == 's' else []
        if isinstance(x, c_ast.BinaryOp) and x.op in ('+', '-'):
            if self.is_ptr(x.left) and not self.is_ptr(x.right): return self.ubs(x.left) + [self.ex(x.right)]
            if self.is_ptr(x.right) and not self.is_ptr(x.left): return [self.ex(x.left)] + self.ubs(x.right)
            if self.is_ptr(x.left) and self.is_ptr(x.right): return self.ubs(x.left) + self.ubs(x.right)
        if isinstance(x, c_ast.UnaryOp) and x.op in ('p++', 'p--', '++', '--'): return self.ubs(x.expr)
        if isinstance(x, c_ast.UnaryOp) and x.op == '&': return self.lub(x.expr)
        if isinstance(x, (c_ast.UnaryOp, c_ast.ArrayRef, c_ast.StructRef)): return self.lub(x)
        if isinstance(x, c_ast.FuncCall): return []
        if isinstance(x, c_ast.Assignment): return self.ubs(x.rvalue) if self.is_ptr(x.rvalue) else [self.ex(x.rvalue)]
        if isinstance(x, c_ast.TernaryOp): return [self.ex(x.cond)]
        raise ValueError('unsupported pointer expression')

    def lub(self, lv):
        """integer parts of an lvalue's address computation"""
        if isinstance(lv, c_ast.ID): return []
        if isinstance(lv, c_ast.UnaryOp) and lv.op == '*': return self.ubs(lv.expr)
        if isinstance(lv, c_ast.ArrayRef): return self.ubs(lv.name) + [self.ex(lv.subscript)]
        if isinstance(lv, c_ast.StructRef): return self.ubs(lv.name) if lv.type == '->' else self.lub(lv.name)
        raise ValueError('unsupported lvalue')

    # ----------------------------------------------------------------- expressions
    def ex(self, e):
        """returns the abstracted expression (scalar-valued expressions only; pointer-valued ones are handled by callers)"""
        if e is None: return None
        if isinstance(e, c_ast.Constant):
            if e.type in ('float', 'double'): raise ValueError('floating point')
            return e
        if isinstance(e, c_ast.ID):
            d = self.ety(e)
            if d and d[0] in ('st',): raise ValueError('struct value')
            return e
        if isinstance(e, c_ast.UnaryOp) and e.op == 'sizeof': return self.sizeof(e)
        if isinstance(e, (c_ast.UnaryOp, c_ast.ArrayRef, c_ast.StructRef)) and (isinstance(e, (c_ast.ArrayRef, c_ast.StructRef)) or e.op == '*'):
            d = self.ety(e)
            if d is None: raise ValueError('untyped memory access: ' + _gen.visit(e)[:70])
            if d[0] == 's': return self.with_ubs(self.nd(d[1]), self.lub(e))
            if d[0] == 'p': raise ValueError('pointer value in scalar context')
            raise ValueError('struct/void value')
        if isinstance(e, c_ast.UnaryOp) and e.op == '&':
            raise ValueError('address-of in scalar context')
        if isinstance(e, c_ast.UnaryOp):
            if e.op in ('p++', 'p--', '++', '--') and self.is_ptr(e.expr): raise ValueError('pointer increment in scalar context')
            if e.op in ('p++', 'p--', '++', '--') and isinstance(e.expr, (c_ast.UnaryOp, c_ast.ArrayRef, c_ast.StructRef)):       # (*p)++ as a value
                d = self.ety(e.expr)
                if d and d[0] == 's': return self.with_ubs(self.nd(d[1]), self.lub(e.expr))
                raise ValueError('untyped memory access')
            if e.op == '!' and self.is_ptr(e.expr): return self.with_ubs(self.nd(('int',)), self.ubs(e.expr))
            e.expr = self.ex(e.expr); return e
        if isinstance(e, c_ast.Cast):
            to = desc(e.to_type)
            if to and to[0] == 's':
                if self.is_ptr(e.expr): return self.with_ubs(self.nd(to[1]), self.ubs(e.expr))
                e.expr = self.ex(e.expr); return e
            raise ValueError('cast to a non-scalar type in scalar context')
        if isinstance(e, c_ast.BinaryOp):
            if e.op in ('==', '!=', '<', '<=', '>', '>=') and (self.is_ptr(e.left) or self.is_ptr(e.right)):
                ubs = (self.ubs(e.left) if self.is_ptr(e.left) else [self.ex(e.left)]) + (self.ubs(e.right) if self.is_ptr(e.right) else [self.ex(e.right)])
                return self.with_ubs(self.nd(('int',)), ubs)
            if e.op == '-' and self.is_ptr(e.left) and self.is_ptr(e.right): return self.with_ubs(self.nd(('long',)), self.ubs(e.left) + self.ubs(e.right))
            if e.op in ('&&', '||'):
                for a in ('left', 'right'):
                    s = getattr(e, a)
                    setattr(e, a, self.with_ubs(self.nd(('int',)), self.ubs(s)) if self.is_ptr(s) else self.ex(s))
                return e
            if (e.op in ('+', '-')) and (self.is_ptr(e.left) or self.is_ptr(e.right)): raise ValueError('pointer arithmetic in scalar context')
            e.left = self.ex(e.left); e.right = self.ex(e.right); return e
        if isinstance(e, c_ast.TernaryOp):
            e.cond = self.cond(e.cond)
            if self.is_ptr(e.iftrue): raise ValueError('pointer-valued conditional in scalar context')
            e.iftrue = self.ex(e.iftrue); e.iffalse = self.ex(e.iffalse); return e
        if isinstance(e, c_ast.Assignment):
            lv = e.lvalue
            if isinstance(lv, c_ast.ID):
                d = self.ety(lv)
                if d and d[0] == 'p': raise ValueError('pointer assignment in scalar context')
                if d and d[0] == 'st': raise ValueError('struct value')
                e.rvalue = self.ex(e.rvalue); return e
            d = self.ety(lv)
            if d is None or d[0] != 's': raise ValueError('assignment through pointer of non-scalar type in scalar context')
            ubs = self.lub(lv); rhs = self.ex(e.rvalue)
            if e.op != '=': rhs = c_ast.BinaryOp(e.op[:-1], self.nd(d[1]), rhs)
            return self.with_ubs(rhs, ubs)                  # value of the assignment expression = the assigned value
        if isinstance(e, c_ast.FuncCall) and not isinstance(e.name, c_ast.ID):          # call through a function pointer: opaque, result arbitrary of the declared return type
            r = self.ety(e)
            ubs = [self.ex(a) for a in (e.args.exprs if e.args else []) if not self.is_ptr(a) and self.ety(a) and self.ety(a)[0] == 's']
            if r is None: raise ValueError('indirect call with unknown return type')
            if r[0] == 's': return self.with_ubs(self.nd(r[1]), ubs)
            if r[0] == 'v': return self.with_ubs(self.nd(('int',)), ubs)
            raise ValueError('indirect call returning a non-scalar')
        if isinstance(e, c_ast.FuncCall):
            if e.args:
                for i, a in enumerate(e.args.exprs):
                    if self.is_ptr(a): e.args.exprs[i] = a            # pointer arguments stay (the call is opaque / dropped later)
                    else: e.args.exprs[i] = self.ex(a)
            return e
        if isinstance(e, c_ast.ExprList): e.exprs = [self.ex(x) for x in e.exprs]; return e
        raise ValueError('unsupported expression ' + type(e).__name__)

    def cond(self, c):
        if self.is_ptr(c): return self.with_ubs(self.nd(('int',)), self.ubs(c))
        return self.ex(c)

    def sizeof(self, e):
        x = e.expr; self.notes.add('sizeof evaluated')
        d = desc(x) if isinstance(x, c_ast.Typename) else self.ety(x)
        if d and d[0] == 's': return num(SIZES.get(NDNAME.get(d[1], ''), 8))
        if d and d[0] == 'p':
            if isinstance(x, c_ast.ID) and x.name in getattr(self, 'arrsize', {}): return num(self.arrsize[x.name])
            return num(8)
        return c_ast.BinaryOp('+', c_ast.FuncCall(c_ast.ID('nondet_ushort'), None), _P.parse('unsigned long f(){ return (unsigned long)1; }').ext[0].body.block_items[0].expr)     # sizeof(struct): arbitrary in [1, 65536]

    # ----------------------------------------------------------------- statements
    def drop_ptr_stmt(self, rv):
        """a pointer-valued computation used for effect only: evaluate calls and integer parts"""
        out = []
        if isinstance(rv, c_ast.FuncCall): out.append(self.ex(rv))
        else:
            for u in self.ubs(rv): out.append(c_ast.Assignment('=', c_ast.ID('__w'), u))
        return out

    def stmt(self, s):
        if isinstance(s, c_ast.Compound): s.block_items = self.stmts(s.block_items or []); return [s]
        if isinstance(s, c_ast.Decl):
            if isinstance(s.type, (c_ast.Enum, c_ast.Struct, c_ast.Union)) and not s.name: return []          # type-only declaration
            if isinstance(s.type, c_ast.TypeDecl) and isinstance(s.type.type, c_ast.Enum): return [] if s.init is None else [c_ast.Decl(s.name, [], [], [], [], c_ast.TypeDecl(s.name, [], None, c_ast.IdentifierType(['int'])), self.ex(s.init), None)]
            d = desc(s.type)
            if d is None: raise ValueError('unsupported declaration type')
            if d[0] == 'st': return []          # struct local: its fields are abstracted (reads are arbitrary); address-taking is allowed only for calls
            if d[0] == 'p':
                if isinstance(s.type, c_ast.ArrayDecl):
                    try: n = int(s.type.dim.value) if isinstance(s.type.dim, c_ast.Constant) else None
                    except Exception: n = None
                    if n is not None and desc(s.type.type) and desc(s.type.type)[0] == 's': self.arrsize = getattr(self, 'arrsize', {}); self.arrsize[s.name] = n * SIZES.get(NDNAME.get(desc(s.type.type)[1], ''), 8)
                    return []
                return [] if s.init is None else self.drop_ptr_stmt(s.init)
            if s.init is not None and not isinstance(s.init, c_ast.InitList):
                if self.is_ptr(s.init): s.init = self.with_ubs(self.nd(('long',)), self.ubs(s.init))
                else: s.init = self.ex(s.init)
            elif s.init is not None: raise ValueError('initializer list')
            return [s]
        if isinstance(s, c_ast.Assignment):
            lv = s.lvalue; d = self.ety(lv)
            if isinstance(lv, c_ast.ID) and d and d[0] == 'p': return self.drop_ptr_stmt(s.rvalue) if s.op == '=' else [c_ast.Assignment('=', c_ast.ID('__w'), self.ex(s.rvalue))]
            if isinstance(lv, c_ast.ID) and d and d[0] == 'st': return []
            if not isinstance(lv, c_ast.ID):
                if d is None: raise ValueError('untyped memory access')
                if d[0] != 's': return [c_ast.Assignment('=', c_ast.ID('__w'), u) for u in self.lub(lv)] + (self.drop_ptr_stmt(s.rvalue) if self.is_ptr(s.rvalue) else [c_ast.Assignment('=', c_ast.ID('__w'), self.ex(s.rvalue))])
                out = [c_ast.Assignment('=', c_ast.ID('__w'), u) for u in self.lub(lv)]
                rhs = self.ex(s.rvalue)
                if s.op != '=': rhs = c_ast.BinaryOp(s.op[:-1], self.nd(d[1]), rhs)
                out.append(c_ast.Assignment('=', c_ast.ID('__w'), rhs)); return out
            s.rvalue = self.ex(s.rvalue) if not self.is_ptr(s.rvalue) else self.with_ubs(self.nd(('long',)), self.ubs(s.rvalue)); return [s]
        if isinstance(s, c_ast.UnaryOp) and s.op in ('p++', 'p--', '++', '--'):
            if self.is_ptr(s.expr): return [c_ast.Assignment('=', c_ast.ID('__w'), u) for u in self.ubs(s.expr)]
            if not isinstance(s.expr, c_ast.ID):
                d = self.ety(s.expr)
                if not d or d[0] != 's': raise ValueError('untyped memory access')
                return [c_ast.Assignment('=', c_ast.ID('__w'), u) for u in self.lub(s.expr)] + [c_ast.Assignment('=', c_ast.ID('__w'), c_ast.BinaryOp('+', self.nd(d[1]), num(1)))]
            return [s]
        if isinstance(s, c_ast.FuncCall):
            if not isinstance(s.name, c_ast.ID):
                r = self.ety(s)
                if r is None: raise ValueError('indirect call with unknown return type')
                return [c_ast.Assignment('=', c_ast.ID('__w'), self.ex(s))]
            return [self.ex(s)]
        if isinstance(s, c_ast.If):
            s.cond = self.cond(s.cond)
            for a in ('iftrue', 'iffalse'):
                b = getattr(s, a)
                if b is not None: setattr(s, a, c_ast.Compound(self.stmt(b) if not isinstance(b, c_ast.Compound) else self.stmts(b.block_items or [])))
            return [s]
        if isinstance(s, c_ast.While):
            s.cond = self.cond(s.cond); b = s.stmt; s.stmt = c_ast.Compound(self.stmts(b.block_items or []) if isinstance(b, c_ast.Compound) else self.stmt(b)); return [s]
        if isinstance(s, c_ast.Return):
            if s.expr is None: return [s]
            if self.retdesc and self.retdesc[0] != 's' or self.is_ptr(s.expr):
                out = self.drop_ptr_stmt(s.expr) if self.is_ptr(s.expr) or isinstance(s.expr, c_ast.FuncCall) else []
                return out + [c_ast.Return(num(0))]
            s.expr = self.ex(s.expr); return [s]
        if isinstance(s, (c_ast.Break, c_ast.Continue)): return [s]
        if isinstance(s, (c_ast.Constant, c_ast.EmptyStatement)): return []
        s2 = self.ex(s); return [s2]

    def stmts(self, ss):
        out = []
        for s in ss: out += self.stmt(s)
        return out

    def check_addresses(self):
        par = {}
        for n in walk(self.fd.body):
            for name, c in n.children(): par[id(c)] = (n, name)
        for n in walk(self.fd.body):
            if isinstance(n, c_ast.UnaryOp) and n.op == '&' and isinstance(n.expr, c_ast.ID):
                d = self.sym.get(n.expr.name) or self.env.gtypes.get(n.expr.name)
                if d and d[0] == 's':
                    pr = par.get(id(n))
                    if not (pr and isinstance(pr[0], c_ast.ExprList) and id(pr[0]) in par and isinstance(par[id(pr[0])][0], c_ast.FuncCall)): raise ValueError('address of a scalar local escapes into memory')

    def enums(self):
        consts = {}
        for n in walk(self.fd.body):
            if isinstance(n, c_ast.Enum) and n.values:
                v = 0
                for en in n.values.enumerators:
                    if en.value is not None:
                        try: v = int(en.value.value.rstrip('uUlL'), 0)
                        except Exception: raise ValueError('enumerator value is not a literal')
                    consts[en.name] = v; v += 1
        if consts:
            par = {}
            for n in walk(self.fd.body):
                for name, c in n.children(): par[id(c)] = (n, name)
            for n in list(walk(self.fd.body)):
                if isinstance(n, c_ast.ID) and n.name in consts and id(n) in par: setchild(par[id(n)][0], par[id(n)][1], num(consts[n.name]))
            self.notes.add('local enumerators substituted')

    def run(self):
        fd = self.fd
        self.enums(); self.check_addresses()
        params = [p for p in (fd.decl.type.args.params if fd.decl.type.args else [])]
        keep = []
        for p in params:
            if isinstance(p, c_ast.Typename): continue
            d = desc(p.type)
            if d and d[0] == 's': keep.append(p)
            elif d and d[0] == 'p': self.notes.add('pointer parameter abstracted: ' + p.name)
            else: raise ValueError('struct/unsupported parameter ' + p.name)
        if fd.decl.type.args is not None: fd.decl.type.args.params = keep
        fd.body.block_items = self.stmts(fd.body.block_items or [])
        if self.retdesc and self.retdesc[0] != 's' and not (self.retdesc[0] == 'v'):
            fd.decl.type.type = c_ast.TypeDecl('f', [], None, c_ast.IdentifierType(['int'])); self.notes.add('non-scalar return value dropped')
        self.notes.add('memory abstraction (memory safety assumed)')
        if any(isinstance(n, c_ast.ID) and n.name == '__w' for n in walk(fd.body)):
            fd.body.block_items.insert(0, c_ast.Decl('__w', [], [], [], [], c_ast.TypeDecl('__w', [], None, c_ast.IdentifierType(['long', 'long'])), num(0), None))
