"""v0.83: MEMORY-SAFETY pass (bounds) for the automatic transcriber, run BEFORE the memory abstraction (scripts/memabs.py), which still handles everything this pass leaves alone.
Tracked pointers: pointer PARAMETERS of scalar element type, LOCAL ARRAYS of constant size and pointer LOCALS whose every assignment derives from one such base (`p = s`, `p = s + k`, `p = &s[k]`, `p++`, `p -= k`, ...).
  * a tracked pointer variable p becomes the integer OFFSET variable p__o of its base (exact: p++ is p__o++, `q - p` is a difference of offsets, p < q compares offsets);
  * every access `*p`, `p[i]` (read, write, compound assignment, ++/--) is CHECKED: 0 <= offset+i < size(base)   (size = constant for arrays, a fresh parameter `<base>__n` for pointer parameters);
    the check is `0*(1/cond)` so the unchanged verifier's definedness proof covers it (division by zero <=> out of bounds);
  * reads return an arbitrary value of the element type; a base used as a NUL-terminated STRING (it is only passed to read-only string functions and never written) obeys the C string semantics:
    size = strlen, offset == size reads 0, smaller offsets read a NON-ZERO character, and the valid offsets are 0..strlen (the terminator may be read);
  * pointer parameters are assumed NON-NULL and not to overlap; the lengths `<base>__n` are free parameters: the verdict is relative to a LENGTH CONTRACT (e.g. n_buf >= count) that is inferred
    from a small candidate set and reported with the result.  Accesses made by CALLED functions (memcpy, ...) and accesses through untracked pointers (malloc results, struct members, pointers of other
    provenance) are NOT checked; the number of checked/unchecked accesses is reported.
Rejected (ValueError -> the caller falls back to the plain memory abstraction): pointers with several bases, ordered comparisons across bases, pointer-to-integer casts, address of a tracked variable."""
import copy, re
from pycparser import c_ast, c_parser
from scripts.memabs import desc, walk, num, setchild, NDNAME, INTS, _gen, _P, SIZES

SUMMARY_FN = None      # callable(name) -> {'params': [(name, tracked?)], 'contract': text or None} | None   (set by scripts/auto_transcribe.certify_memsafe)
READONLY_STR = {'strlen', 'strcmp', 'strncmp', 'strchr', 'strrchr', 'strstr', 'strspn', 'strcspn', 'strpbrk', 'strcasecmp', 'strncasecmp', 'memcmp', 'strnlen', 'strcoll', 'atoi', 'atol', 'strtol', 'strtoul', 'puts', 'fputs'}
STR_USERS = {'strlen', 'strcmp', 'strncmp', 'strchr', 'strrchr', 'strstr', 'strspn', 'strcspn', 'strpbrk', 'strcasecmp', 'strncasecmp', 'strnlen', 'strcoll'}


def idn(n): return c_ast.ID(n)


def bin_(op, a, b): return c_ast.BinaryOp(op, a, b)


class MemSafe:
    def __init__(self, fd, env, notes):
        self.fd, self.env, self.notes = fd, env, notes
        self.base = {}            # tracked pointer variable -> base name
        self.size = {}            # base -> size expression (AST factory)
        self.string = {}          # base -> bool
        self.elem = {}            # base -> scalar word tuple
        self.checked = 0; self.unchecked = 0; self.k = 0; self.pre = []
        self.heap = {}; self.orig_params = []; self.callee_checks = 0; self.pos_bases = set(); self.disjoint = []; self.len_params = []; self.null_params = []; self.nullable = set(); self.voidbase = set(); self.freeable = set(); self.libchecks = 0

    # ------------------------------------------------------------------ analysis
    def analyse(self):
        fd = self.fd; params = [p for p in (fd.decl.type.args.params if fd.decl.type.args else []) if isinstance(p, c_ast.Decl)]
        called = {}                # base -> set of callees it is passed to
        self.types = {}
        for p in params: self.types[p.name] = desc(p.type)
        for n in walk(fd.body):
            if isinstance(n, c_ast.Decl) and n.name: self.types[n.name] = desc(n.type)
        for p in params:
            d = desc(p.type)
            if d and d[0] == 'p' and d[1] and d[1][0] == 's' and isinstance(p.type, c_ast.PtrDecl): self.base[p.name] = p.name; self.size[p.name] = ('param', p.name + '__n'); self.elem[p.name] = d[1][1]; self.nullable.add(p.name)
            elif d and d[0] == 'p' and d[1] and d[1][0] == 'p' and d[1][1] and d[1][1][0] == 's' and isinstance(p.type, c_ast.PtrDecl):          # char **argv: base of POINTER elements
                self.base[p.name] = p.name; self.size[p.name] = ('param', p.name + '__n'); self.elem[p.name] = ('ptr', d[1][1][1]); self.nullable.add(p.name)
            elif d and d[0] == 'p' and d[1] and d[1][0] == 'st' and isinstance(p.type, c_ast.PtrDecl) and d[1][1] in self.env.fields:          # struct pointer: base of struct ELEMENTS
                self.base[p.name] = p.name; self.size[p.name] = ('param', p.name + '__n'); self.elem[p.name] = ('struct', d[1][1]); self.nullable.add(p.name)
            elif d and d[0] == 'p' and d[1] and d[1][0] == 'v' and isinstance(p.type, c_ast.PtrDecl) and self.void_as_bytes(p.name):              # void *: a byte buffer when it is only cast to char pointers
                self.base[p.name] = p.name; self.size[p.name] = ('param', p.name + '__n'); self.elem[p.name] = ('unsigned', 'char'); self.nullable.add(p.name); self.voidbase.add(p.name)
        for n in walk(fd.body):
            if isinstance(n, c_ast.Decl) and isinstance(n.type, c_ast.ArrayDecl) and isinstance(n.type.dim, c_ast.Constant) and isinstance(n.type.type, c_ast.TypeDecl):
                d = desc(n.type.type)
                if d and d[0] == 's':
                    try: N = int(n.type.dim.value.rstrip('uUlL'), 0)
                    except Exception: continue
                    self.base[n.name] = n.name; self.size[n.name] = ('const', N); self.elem[n.name] = d[1]
        # pointer locals: fixpoint over the assignments
        locs = {n.name for n in walk(fd.body) if isinstance(n, c_ast.Decl) and n.name and isinstance(n.type, c_ast.PtrDecl) and desc(n.type) and desc(n.type)[1] and desc(n.type)[1][0] == 's'}
        assigns = collections_defaultdict()
        for n in walk(fd.body):
            if isinstance(n, c_ast.Decl) and n.name in locs and n.init is not None: assigns[n.name].append(n.init)
            if isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name in locs and n.op == '=': assigns[n.lvalue.name].append(n.rvalue)
            if isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID) and n.lvalue.name in locs and n.op != '=': assigns[n.lvalue.name].append(None)      # p += k: keeps the base
        for p in params:       # parameters that are reassigned stay tracked with their own base
            pass
        changed = True; bad = set()
        while changed:
            changed = False
            for v in sorted(locs - bad):
                bs = set()
                for rv in assigns.get(v, []):
                    if rv is None: continue
                    b = self.heap_base(v, rv) or self.base_of(rv)
                    bs.add(b)
                if not assigns.get(v) or None in bs or len(bs) != 1 or list(bs)[0] is None and True:
                    if not assigns.get(v) or None in bs or len(bs) != 1: bad.add(v); changed = True; continue
                b = list(bs)[0]
                if self.base.get(v) != b: self.base[v] = b; changed = True
        for v in bad: self.base.pop(v, None)
        for v, (hb, w) in list(self.heap.items()):
            if v not in self.base or self.base[v] != hb: self.heap.pop(v)
            else: self.size[hb] = ('local', hb + '__n'); self.elem[hb] = w; self.nullable.add(hb)
        # which bases are strings: only passed to read-only string functions (at least one of the STR_USERS) and never written
        passed = collections_defaultdict(); written = set()
        for n in walk(fd.body):
            if isinstance(n, c_ast.FuncCall) and n.args:
                nm = n.name.name if isinstance(n.name, c_ast.ID) else None
                for a in n.args.exprs:
                    b = self.base_of(a) if self.is_tracked_expr(a) else None
                    if b: passed[b].append(nm)
            if isinstance(n, c_ast.Assignment) and not (isinstance(n.lvalue, c_ast.ID)):
                for x in walk(n.lvalue):
                    if isinstance(x, c_ast.ID) and x.name in self.base: written.add(self.base[x.name])
            if isinstance(n, c_ast.UnaryOp) and n.op in ('p++', 'p--', '++', '--') and not isinstance(n.expr, c_ast.ID):
                for x in walk(n.expr):
                    if isinstance(x, c_ast.ID) and x.name in self.base: written.add(self.base[x.name])
        for b in set(self.base.values()):
            callees = passed.get(b, [])
            if self.elem[b][0] in ('struct', 'ptr'): self.string[b] = False; continue
            self.string[b] = (self.size[b][0] == 'param' and self.elem[b] in (('char',), ('unsigned', 'char'), ('signed', 'char')) and b not in written and bool(callees) and all(c in READONLY_STR for c in callees) and any(c in STR_USERS for c in callees)) or \
                             (self.size[b][0] == 'param' and self.elem[b] in (('char',), ('unsigned', 'char')) and b not in written and not callees and self.reads_until_nul(b))
        for n in walk(fd.body):
            if isinstance(n, c_ast.FuncCall) and isinstance(n.name, c_ast.ID) and n.name.name == 'free' and n.args:
                b = self.base_of(n.args.exprs[0])
                if b and b in self.nullable: self.freeable.add(b)
        if not self.base: raise ValueError('no trackable pointer')

    def alloc_call(self, rv):
        while isinstance(rv, c_ast.Cast): rv = rv.expr
        return rv if isinstance(rv, c_ast.FuncCall) and isinstance(rv.name, c_ast.ID) and rv.name.name in ('malloc', 'calloc') and rv.args and len(rv.args.exprs) == (1 if rv.name.name == 'malloc' else 2) else None

    def heap_base(self, v, rv):
        """`v = malloc(n)` / `calloc(a, b)`: v points to the heap object (v + '__h') whose size (in elements) is recorded at the allocation"""
        call = self.alloc_call(rv)
        if call is None: return None
        d = self.types.get(v); w = d[1][1] if d and d[0] == 'p' and d[1] and d[1][0] == 's' else None
        if w is None or NDNAME.get(w) not in ('char', 'uchar', 'short', 'ushort', 'int', 'uint', 'long', 'ulong', 'longlong', 'ulonglong'): return None
        self.heap[v] = (v + '__h', w); return v + '__h'

    def void_as_bytes(self, name):
        par = {}
        for n in walk(self.fd.body):
            for nm, c in n.children(): par[id(c)] = (n, nm)
        ok = False
        for n in walk(self.fd.body):
            if isinstance(n, c_ast.ID) and n.name == name:
                pr, attr = par[id(n)]
                if isinstance(pr, c_ast.Cast):
                    d = desc(pr.to_type)
                    if d and d[0] == 'p' and d[1] and d[1][0] == 's' and d[1][1] in (('char',), ('unsigned', 'char'), ('signed', 'char')): ok = True; continue
                    return False
                if isinstance(pr, c_ast.ExprList) or isinstance(pr, c_ast.BinaryOp) and pr.op in ('==', '!=') or isinstance(pr, c_ast.UnaryOp) and pr.op == '!' or isinstance(pr, (c_ast.If, c_ast.While)):
                    continue
                if isinstance(pr, c_ast.Decl): return False
                return False
        return ok

    def reads_until_nul(self, b):
        """a char base whose reads sit in a loop condition `*p` / `p[i]` (NUL-terminated walking)"""
        for n in walk(self.fd.body):
            if isinstance(n, c_ast.While):
                for x in walk(n.cond):
                    if isinstance(x, (c_ast.UnaryOp, c_ast.ArrayRef)) and (getattr(x, 'op', '*') == '*') and any(isinstance(y, c_ast.ID) and self.base.get(y.name) == b for y in walk(x)): return True
        return False

    def is_tracked_expr(self, e): return self.base_of(e) is not None

    def base_of(self, e):
        if isinstance(e, c_ast.ID):
            if e.name in self.base: return self.base[e.name]
            return None
        if isinstance(e, c_ast.Cast): return self.base_of(e.expr)
        if isinstance(e, c_ast.BinaryOp) and e.op in ('+', '-'):
            lb = self.base_of(e.left); rb = self.base_of(e.right)
            if lb and not rb and not self.ptrlike(e.right): return lb
            if rb and e.op == '+' and not lb and not self.ptrlike(e.left): return rb
            return None
        if isinstance(e, c_ast.UnaryOp) and e.op == '&' and isinstance(e.expr, c_ast.ArrayRef): return self.base_of(e.expr.name)
        if isinstance(e, c_ast.UnaryOp) and e.op in ('p++', 'p--', '++', '--') and isinstance(e.expr, c_ast.ID): return self.base_of(e.expr)
        return None

    def ptrlike(self, e):
        d = self.types.get(e.name) if isinstance(e, c_ast.ID) else None
        return bool(d and d[0] == 'p')

    # ------------------------------------------------------------------ offsets
    def off(self, e):
        """offset (AST, in elements) of the tracked pointer expression e relative to its base"""
        if isinstance(e, c_ast.ID):
            if e.name in self.base and self.base[e.name] != e.name: return idn(e.name + '__o')
            if e.name in self.base: return idn(e.name + '__o') if e.name in self.pvars else num(0)
        if isinstance(e, c_ast.Cast): return self.off(e.expr)
        if isinstance(e, c_ast.BinaryOp) and e.op in ('+', '-'):
            if self.base_of(e.left): return bin_(e.op, self.off(e.left), self.ex(e.right))
            return bin_('+', self.ex(e.left), self.off(e.right))
        if isinstance(e, c_ast.UnaryOp) and e.op == '&' and isinstance(e.expr, c_ast.ArrayRef): return bin_('+', self.off(e.expr.name), self.ex(e.expr.subscript))
        raise ValueError('untracked pointer expression')

    def nonnull_cond(self, b): return bin_('==', idn(self.nullvar(b)), num(0)) if b in self.nullable else num(1)

    def sizeast(self, b):
        k, v = self.size[b]; return num(v) if k == 'const' else idn(v)

    def nullvar(self, b): return b + '__null'

    def freevar(self, b): return b + '__fr'

    def guard(self, b, E, count=None):
        """0*(1/cond): cond = in bounds (the access of `count` elements starting at E, default one element) AND the base is not NULL AND not freed"""
        N = self.sizeast(b); hi = '<=' if self.string.get(b) else '<'
        end = bin_('+', copy.deepcopy(E), num(0) if count is None else count)
        cond = bin_('&&', bin_('>=', copy.deepcopy(E), num(0)), bin_(hi, end, N) if count is None else bin_('<=', end, N))
        if count is not None: cond = bin_('||', bin_('==', copy.deepcopy(count), num(0)), cond)
        if b in self.nullable: cond = bin_('&&', bin_('==', idn(self.nullvar(b)), num(0)), cond) if count is None else bin_('||', bin_('==', copy.deepcopy(count), num(0)), bin_('&&', bin_('==', idn(self.nullvar(b)), num(0)), cond))
        if b in self.freeable: cond = bin_('&&', bin_('==', idn(self.freevar(b)), num(0)), cond)
        return bin_('*', num(0), bin_('/', num(1), cond))

    def nd(self, words): return c_ast.FuncCall(idn('nondet_' + NDNAME[words]), None)

    def read_value(self, b, E):
        if self.elem[b][0] == 'struct': raise ValueError('struct element accessed as a value')
        self.checked += 1; g = self.guard(b, E); w = self.elem[b]
        if self.string.get(b):
            self.k += 1; t = '__s%d' % self.k
            self.pre += [c_ast.Decl(t, [], [], [], [], c_ast.TypeDecl(t, [], None, c_ast.IdentifierType(list(w))), self.nd(w), None),
                         c_ast.If(bin_('==', idn(t), num(0)), c_ast.Compound([c_ast.Assignment('=', idn(t), num(1))]), None)]
            v = c_ast.TernaryOp(bin_('==', copy.deepcopy(E), self.sizeast(b)), num(0), idn(t))
            return bin_('+', v, g)
        return bin_('+', self.nd(w), g)

    # ------------------------------------------------------------------ expressions
    def sacc(self, e):
        """access path rooted at a tracked struct base: `p->f`, `p[i].f`, `(*p).f`, then any chain of `.g` / `[k]` (array fields are bounds-checked against their declared dimensions).
        Returns (base, element offset AST, final desc, extra guard conditions) or None when the expression is not such a path."""
        if isinstance(e, c_ast.StructRef):
            root = e.name
            if e.type == '->':
                b = self.base_of(root)
                if not (b and self.elem[b][0] == 'struct'): return None
                off = self.off(root); tag = self.elem[b][1]; guards = []
            else:
                if isinstance(root, c_ast.ArrayRef) and self.base_of(root.name) and self.elem[self.base_of(root.name)][0] == 'struct':
                    b = self.base_of(root.name); off = bin_('+', self.off(root.name), self.ex(root.subscript)); tag = self.elem[b][1]; guards = []
                elif isinstance(root, c_ast.UnaryOp) and root.op == '*' and self.base_of(root.expr) and self.elem[self.base_of(root.expr)][0] == 'struct':
                    b = self.base_of(root.expr); off = self.off(root.expr); tag = self.elem[b][1]; guards = []
                else:
                    inner = self.sacc(root)
                    if inner is None: return None
                    b, off, cur, guards = inner
                    if not (cur and cur[0] == 'st' and cur[1] in self.env.fields): raise ValueError('field access on a non-struct field')
                    tag = cur[1]
            fd_ = self.env.fields.get(tag, {}).get(e.field.name)
            self.dims_pending = list(self.env.fdims.get((tag, e.field.name), []))
            return b, off, fd_, guards
        if isinstance(e, c_ast.ArrayRef):
            inner = self.sacc(e.name)
            if inner is None: return None
            b, off, cur, guards = inner
            dims = getattr(self, 'dims_pending', [])
            if not (cur and cur[0] == 'p' and dims): raise ValueError('index into a field without a known array dimension')
            idx = self.ex(e.subscript)
            guards = guards + [bin_('&&', bin_('>=', copy.deepcopy(idx), num(0)), bin_('<', copy.deepcopy(idx), num(dims[0])))]
            self.dims_pending = dims[1:]
            return b, off, (('p', cur[1]) if len(dims) > 1 else cur[1]), guards
        return None

    def pacc(self, e):
        """e dereferences a POINTER ELEMENT of a tracked base: `argv[i][j]`, `*argv[i]`, `argv[i][j]` writes -> (base, offset of the pointer element) else None"""
        op = e.name if isinstance(e, c_ast.ArrayRef) else e.expr if isinstance(e, c_ast.UnaryOp) and e.op == '*' else None
        if op is None: return None
        inner = self.acc(op) if isinstance(op, (c_ast.ArrayRef, c_ast.UnaryOp)) else None
        if inner and self.elem[inner[0]][0] == 'ptr': return inner
        return None

    def acc(self, e):
        """(base, offset) if e is `*q` / `q[i]` with a tracked q, else None"""
        if isinstance(e, c_ast.UnaryOp) and e.op == '*' and self.base_of(e.expr): return self.base_of(e.expr), self.off(e.expr)
        if isinstance(e, c_ast.ArrayRef) and self.base_of(e.name): return self.base_of(e.name), bin_('+', self.off(e.name), self.ex(e.subscript))
        return None

    def ex(self, e):
        if e is None: return None
        sa = self.sacc(e)
        if sa is not None:
            b, off, fdsc, gs = sa; self.checked += 1; g = self.guard(b, off)
            for c in gs: self.checked += 1; g = bin_('+', g, bin_('*', num(0), bin_('/', num(1), c)))
            if fdsc is None or fdsc[0] != 's': raise ValueError('struct field of non-scalar or unknown type')
            return bin_('+', self.nd(fdsc[1]), g)
        pa = self.pacc(e)
        if pa is not None:                                          # `argv[i][j]`: the pointer element is checked, the inner access has no size information
            self.checked += 1; self.unchecked += 1; g = self.guard(pa[0], pa[1]); idx = self.ex(e.subscript) if isinstance(e, c_ast.ArrayRef) else num(0)
            return bin_('+', bin_('+', self.nd(self.elem[pa[0]][1]), g), bin_('*', num(0), idx))
        a = self.acc(e)
        if a is not None and self.elem[a[0]][0] == 'ptr': raise ValueError('pointer element read as a value')
        if a is not None: return self.read_value(a[0], a[1])
        if isinstance(e, c_ast.ID):
            if e.name in self.base and e.name not in self.arrays: raise ValueError('tracked pointer used as a value')
            return e
        if isinstance(e, c_ast.BinaryOp):
            lb, rb = self.base_of(e.left), self.base_of(e.right)
            if e.op in ('==', '!=', '<', '<=', '>', '>=') and (lb or rb):
                if lb and rb:
                    if lb != rb: raise ValueError('comparison of pointers with different bases')
                    return bin_(e.op, self.off(e.left), self.off(e.right))
                other = e.right if lb else e.left
                if isinstance(other, c_ast.Constant) and other.value == '0':
                    if e.op not in ('==', '!='): raise ValueError('ordered comparison with NULL')
                    b = lb or rb
                    if b in self.nullable: return bin_('!=' if e.op == '==' else '==', idn(self.nullvar(b)), num(0))       # q == NULL  <=>  the base parameter is NULL
                    return num(1 if e.op == '!=' else 0)
                raise ValueError('comparison of a tracked pointer with an unknown pointer')
            if e.op == '-' and lb and rb:
                if lb != rb: raise ValueError('difference of pointers with different bases')
                return bin_('-', self.off(e.left), self.off(e.right))
            if e.op in ('+', '-') and (lb or rb): raise ValueError('pointer arithmetic as a value')
            e.left = self.ex(e.left); e.right = self.ex(e.right); return e
        if isinstance(e, c_ast.UnaryOp):
            if e.op == '!' and self.base_of(e.expr):
                b = self.base_of(e.expr); return bin_('!=', idn(self.nullvar(b)), num(0)) if b in self.nullable else num(0)
            if e.op in ('p++', 'p--', '++', '--') and self.base_of(e.expr) and isinstance(e.expr, c_ast.ID): raise ValueError('pointer increment as a value')
            if e.op in ('p++', 'p--', '++', '--') and self.acc(e.expr): raise ValueError('increment of a memory cell as a value')
            if e.op == '&': return e
            if e.op == 'sizeof': return e
            e.expr = self.ex(e.expr); return e
        if isinstance(e, c_ast.Cast):
            if self.base_of(e.expr): raise ValueError('pointer cast in scalar context')
            e.expr = self.ex(e.expr); return e
        if isinstance(e, c_ast.TernaryOp):
            if self.base_of(e.cond): e.cond = self.nonnull_cond(self.base_of(e.cond))
            else: e.cond = self.ex(e.cond)
            e.iftrue = self.ex(e.iftrue); e.iffalse = self.ex(e.iffalse); return e
        if isinstance(e, c_ast.Assignment):
            if isinstance(e.lvalue, c_ast.ID) and e.lvalue.name in self.base: raise ValueError('pointer assignment as a value')
            if self.acc(e.lvalue): raise ValueError('memory write as a value')
            e.rvalue = self.ex(e.rvalue); return e
        if isinstance(e, c_ast.FuncCall):
            self.libcall(e); self.callee_contract(e)
            if e.args:
                for i, a in enumerate(e.args.exprs):
                    pe = self.acc(a) if isinstance(a, (c_ast.ArrayRef, c_ast.UnaryOp)) else None
                    if pe is not None and self.elem[pe[0]][0] == 'ptr':
                        self.checked += 1; self.pre.append(c_ast.Assignment('=', idn('__ms_w'), self.guard(pe[0], pe[1]))); e.args.exprs[i] = num(0); self.unchecked += 1; continue
                    if self.base_of(a): self.unchecked += 1               # the callee's accesses are not checked (unless modelled by libcall)
                    else: e.args.exprs[i] = self.ex(a)
            return e
        for name, ch in list(e.children()):
            if isinstance(ch, c_ast.Node): setchild(e, name, self.ex(ch)) if isinstance(ch, (c_ast.ID, c_ast.BinaryOp, c_ast.UnaryOp, c_ast.Cast, c_ast.TernaryOp, c_ast.ArrayRef, c_ast.Assignment, c_ast.FuncCall, c_ast.Constant)) else None
        return e

    def callee_contract(self, call):
        """a call of a function of the same file whose bounds were verified UNDER A CONTRACT: the contract is checked at the call site (callee-internal accesses are covered compositionally)"""
        nm = call.name.name if isinstance(call.name, c_ast.ID) else None
        if SUMMARY_FN is None or nm is None: return
        s = SUMMARY_FN(nm)
        if not s or not call.args or len(call.args.exprs) != len(s['params']): return
        if s['contract'] is None: self.callee_checks += 1; self.notes.add('callee verified without a contract: ' + nm); return
        sub = {}
        for (pn, tracked), a in zip(s['params'], call.args.exprs):
            if tracked:
                b = self.base_of(a)
                if not b: return                                                        # an untracked pointer is passed: nothing can be checked
                sub[pn + '__n'] = bin_('-', self.sizeast(b), self.off(a))               # elements left behind the pointer
                sub[pn + '__null'] = idn(self.nullvar(b)) if b in self.nullable else num(0)
            else: sub[pn] = self.ex(copy.deepcopy(a))
        cond = c_parser.CParser().parse('int f(){ return %s; }' % s['contract']).ext[0].body.block_items[0].expr
        for n in list(walk(cond)):
            for name, ch in list(n.children()):
                if isinstance(ch, c_ast.ID) and ch.name in sub: setchild(n, name, copy.deepcopy(sub[ch.name]))
        if any(isinstance(n, c_ast.ID) and (n.name.endswith(('__pos', '__fr')) ) for n in walk(cond)): return      # overlap/UAF contracts of the callee are not instantiated
        self.pre.append(c_ast.Assignment('=', idn('__ms_w'), bin_('*', num(0), bin_('/', num(1), cond)))); self.checked += 1; self.callee_checks += 1; self.notes.add('callee contract checked at the call: ' + nm)

    def libcall(self, call):
        """accesses made by well-known library functions on tracked pointers are checked as range accesses (+ memcpy overlap, free of a tracked base)"""
        nm = call.name.name if isinstance(call.name, c_ast.ID) else None
        args = call.args.exprs if call.args else []
        def rng(a, n):
            b = self.base_of(a)
            if not b or self.elem[b][0] == 'struct': return None
            self.libchecks += 1; self.checked += 1
            return (b, self.off(a), self.guard(b, self.off(a), self.ex(copy.deepcopy(n))))
        w = lambda g: self.pre.append(c_ast.Assignment('=', idn('__ms_w'), g))
        if nm in ('memcpy', 'memmove', 'memcmp') and len(args) == 3:
            r1, r2 = rng(args[0], args[2]), rng(args[1], args[2])
            for r in (r1, r2):
                if r: w(r[2])
            if nm in ('memcpy',) and r1 and r2 and r1[0] != r2[0] and self.size[r1[0]][0] == 'param' and self.size[r2[0]][0] == 'param':     # two pointer parameters: they must not overlap (a contract on the caller)
                n = self.ex(copy.deepcopy(args[2])); pd, ps = idn(r1[0] + '__pos'), idn(r2[0] + '__pos'); self.pos_bases |= {r1[0], r2[0]}
                ad, as_ = bin_('+', pd, copy.deepcopy(r1[1])), bin_('+', ps, copy.deepcopy(r2[1]))
                ov = bin_('||', bin_('==', copy.deepcopy(n), num(0)), bin_('||', bin_('<=', bin_('+', copy.deepcopy(ad), copy.deepcopy(n)), copy.deepcopy(as_)), bin_('<=', bin_('+', copy.deepcopy(as_), copy.deepcopy(n)), copy.deepcopy(ad))))
                w(bin_('*', num(0), bin_('/', num(1), ov))); self.notes.add('memcpy overlap of two parameters checked (contract: disjoint objects)')
                atom = '((%s__pos + %s__n <= %s__pos) || (%s__pos + %s__n <= %s__pos))' % (r1[0], r1[0], r2[0], r2[0], r2[0], r1[0])
                if atom not in self.disjoint: self.disjoint.append(atom)
            if nm == 'memcpy' and r1 and r2 and r1[0] == r2[0]:                     # overlap of the two ranges is undefined
                n = self.ex(copy.deepcopy(args[2]))
                ov = bin_('||', bin_('==', copy.deepcopy(n), num(0)), bin_('||', bin_('<=', bin_('+', copy.deepcopy(r1[1]), copy.deepcopy(n)), copy.deepcopy(r2[1])), bin_('<=', bin_('+', copy.deepcopy(r2[1]), copy.deepcopy(n)), copy.deepcopy(r1[1]))))
                w(bin_('*', num(0), bin_('/', num(1), ov))); self.notes.add('memcpy overlap checked')
        elif nm == 'memset' and len(args) == 3:
            r = rng(args[0], args[2])
            if r: w(r[2])
        elif nm in ('strncpy',) and len(args) == 3:
            r = rng(args[0], args[2])
            if r: w(r[2])
        elif nm == 'strcpy' and len(args) == 2:
            d, s = self.base_of(args[0]), self.base_of(args[1])
            if d and s and self.string.get(s) and self.elem[d][0] != 'struct':          # copies strlen(s)+1 elements
                n = bin_('+', bin_('-', self.sizeast(s), self.off(args[1])), num(1))
                w(self.guard(d, self.off(args[0]), n)); self.libchecks += 1; self.checked += 1
        elif nm == 'free' and len(args) == 1:
            b = self.base_of(args[0])
            if b and b in self.freeable:
                o = self.off(args[0]); self.checked += 1; self.libchecks += 1
                ok = bin_('||', bin_('!=', idn(self.nullvar(b)), num(0)), bin_('&&', bin_('==', copy.deepcopy(o), num(0)), bin_('==', idn(self.freevar(b)), num(0))))    # free(NULL) is fine; else offset 0 and not yet freed
                w(bin_('*', num(0), bin_('/', num(1), ok)))
                self.pre.append(c_ast.If(bin_('==', idn(self.nullvar(b)), num(0)), c_ast.Compound([c_ast.Assignment('=', idn(self.freevar(b)), num(1))]), None))

    # ------------------------------------------------------------------ statements
    def alloc_stmts(self, v, rv, decl):
        hb, w = self.heap[v]; call = self.alloc_call(rv); a = call.args.exprs
        bytes_ = self.ex(a[0]) if call.name.name == 'malloc' else bin_('*', self.ex(a[0]), self.ex(a[1]))
        esz = SIZES[NDNAME[w]]
        out = []
        if decl: out.append(c_ast.Decl(v + '__o', [], [], [], [], c_ast.TypeDecl(v + '__o', [], None, c_ast.IdentifierType(['long'])), num(0), None)); self.pvars.add(v)
        out += [c_ast.Assignment('=', idn(hb + '__n'), bin_('/', bin_('+', bytes_, num(0)), num(esz))), c_ast.Assignment('=', idn(hb + '__fr'), num(0)),
                c_ast.Assignment('=', idn(hb + '__null'), bin_('!=', self.nd(('unsigned', 'char')), num(0))), c_ast.Assignment('=', idn(v + '__o'), num(0))]
        self.notes.add('heap object tracked: ' + hb); return out

    def flush(self, out): r = self.pre; self.pre = []; return r + out

    def stmt(self, s):
        if isinstance(s, c_ast.Compound): s.block_items = self.stmts(s.block_items or []); return [s]
        if isinstance(s, c_ast.Decl):
            if s.name in self.base and s.name not in self.arrays and s.name in self.heap and s.init is not None and self.alloc_call(s.init) is not None:
                return self.flush(self.alloc_stmts(s.name, s.init, True))
            if s.name in self.base and s.name not in self.arrays:        # tracked pointer local
                out = [c_ast.Decl(s.name + '__o', [], [], [], [], c_ast.TypeDecl(s.name + '__o', [], None, c_ast.IdentifierType(['long'])), num(0), None)]
                if s.init is not None: out.append(c_ast.Assignment('=', idn(s.name + '__o'), self.off(s.init)))
                self.pvars.add(s.name); return self.flush(out)
            if s.name in self.arrays: return [s]
            pe = self.acc(s.init) if s.init is not None and isinstance(s.init, (c_ast.ArrayRef, c_ast.UnaryOp)) and isinstance(s.type, c_ast.PtrDecl) else None
            if pe is not None and self.elem[pe[0]][0] == 'ptr':
                self.checked += 1; s.init = num(0); return self.flush([c_ast.Assignment('=', idn('__ms_w'), self.guard(pe[0], pe[1])), s])
            if s.init is not None and not isinstance(s.init, c_ast.InitList): s.init = self.ex(s.init)
            return self.flush([s])
        if isinstance(s, c_ast.Assignment):
            lv = s.lvalue
            if isinstance(lv, c_ast.ID) and lv.name in self.heap and s.op == '=' and self.alloc_call(s.rvalue) is not None: return self.flush(self.alloc_stmts(lv.name, s.rvalue, False))
            if isinstance(lv, c_ast.ID) and lv.name in self.base and lv.name not in self.arrays:
                o = idn(lv.name + '__o')
                if s.op == '=': return self.flush([c_ast.Assignment('=', o, self.off(s.rvalue))])
                return self.flush([c_ast.Assignment('=', o, bin_(s.op[:-1], o, self.ex(s.rvalue)))])
            pw = self.pacc(lv)
            if pw is not None:
                self.checked += 1; self.unchecked += 1; out = [c_ast.Assignment('=', idn('__ms_w'), self.guard(pw[0], pw[1]))]
                if isinstance(lv, c_ast.ArrayRef): out.append(c_ast.Assignment('=', idn('__ms_w'), self.ex(lv.subscript)))
                out.append(c_ast.Assignment('=', idn('__ms_w'), self.ex(s.rvalue))); return self.flush(out)
            sw = self.sacc(lv)
            if sw is not None:
                b, off, fdsc, gs = sw
                if fdsc is None or fdsc[0] != 's': raise ValueError('write to a struct field of non-scalar or unknown type')
                self.checked += 1; out = [c_ast.Assignment('=', idn('__ms_w'), self.guard(b, off))] + [c_ast.Assignment('=', idn('__ms_w'), bin_('*', num(0), bin_('/', num(1), c))) for c in gs]; rhs = self.ex(s.rvalue)
                if s.op != '=': rhs = bin_(s.op[:-1], self.nd(fdsc[1]), rhs)
                out.append(c_ast.Assignment('=', idn('__ms_w'), rhs)); return self.flush(out)
            a = self.acc(lv)
            if a is not None:
                if self.elem[a[0]][0] == 'struct': raise ValueError('struct element assignment')
                self.checked += 1; g = self.guard(a[0], a[1]); out = [c_ast.Assignment('=', idn('__ms_w'), g)]
                rhs = self.ex(s.rvalue)
                if s.op != '=': rhs = bin_(s.op[:-1], self.nd(self.elem[a[0]]), rhs)
                out.append(c_ast.Assignment('=', idn('__ms_w'), rhs)); return self.flush(out)
            s.rvalue = self.ex(s.rvalue); return self.flush([s])
        if isinstance(s, c_ast.UnaryOp) and s.op in ('p++', 'p--', '++', '--'):
            if isinstance(s.expr, c_ast.ID) and s.expr.name in self.base and s.expr.name not in self.arrays:
                o = idn(s.expr.name + '__o'); return [c_ast.Assignment('=', o, bin_('+' if s.op in ('p++', '++') else '-', o, num(1)))]
            a = self.acc(s.expr)
            if a is not None:
                self.checked += 1; return self.flush([c_ast.Assignment('=', idn('__ms_w'), self.guard(a[0], a[1])), c_ast.Assignment('=', idn('__ms_w'), bin_('+', self.nd(self.elem[a[0]]), num(1)))])
        if isinstance(s, c_ast.If):
            s.cond = self.ex(s.cond) if not self.base_of(s.cond) else self.nonnull_cond(self.base_of(s.cond)); pre = self.pre; self.pre = []
            for x in ('iftrue', 'iffalse'):
                b = getattr(s, x)
                if b is not None: setattr(s, x, c_ast.Compound(self.stmts(b.block_items) if isinstance(b, c_ast.Compound) else self.stmt(b)))
            return pre + [s]
        if isinstance(s, c_ast.While):
            s.cond = self.ex(s.cond) if not self.base_of(s.cond) else self.nonnull_cond(self.base_of(s.cond)); pre = self.pre; self.pre = []
            b = s.stmt; body = self.stmts(b.block_items) if isinstance(b, c_ast.Compound) else self.stmt(b)
            if pre: return [c_ast.While(num(1), c_ast.Compound(pre + [c_ast.If(c_ast.UnaryOp('!', s.cond), c_ast.Compound([c_ast.Break()]), None)] + body))]
            s.stmt = c_ast.Compound(body); return [s]
        if isinstance(s, c_ast.Return):
            if s.expr is not None:
                if self.base_of(s.expr): raise ValueError('returning a tracked pointer')
                s.expr = self.ex(s.expr)
            return self.flush([s])
        if isinstance(s, c_ast.FuncCall): return self.flush([self.ex(s)])
        if isinstance(s, (c_ast.Break, c_ast.Continue, c_ast.EmptyStatement)): return [s]
        return self.flush([self.ex(s)])

    def stmts(self, ss):
        out = []
        for s in ss: out += self.stmt(s)
        return out

    def run(self):
        self.analyse(); fd = self.fd
        self.orig_params = [(p.name, p.name in self.base) for p in (fd.decl.type.args.params if fd.decl.type.args else []) if isinstance(p, c_ast.Decl)]
        self.arrays = {n.name for n in walk(fd.body) if isinstance(n, c_ast.Decl) and isinstance(n.type, c_ast.ArrayDecl) and n.name in self.base}
        self.pvars = set(p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if isinstance(p, c_ast.Decl) and p.name in self.base)
        pre = []
        for p in sorted(self.pvars):         # pointer parameters: offset variable, initially 0
            pre.append(c_ast.Decl(p + '__o', [], [], [], [], c_ast.TypeDecl(p + '__o', [], None, c_ast.IdentifierType(['long'])), num(0), None))
        body = self.stmts(fd.body.block_items or [])
        # length parameters
        params = list(fd.decl.type.args.params if fd.decl.type.args else [])
        for b in sorted({b for b in self.base.values() if self.size[b][0] == 'param'}):
            nm = b + '__n'; params.append(c_ast.Decl(nm, [], [], [], [], c_ast.TypeDecl(nm, [], None, c_ast.IdentifierType(['unsigned', 'long'])), None, None)); self.len_params.append(nm)
        for b in sorted(self.pos_bases):
            nm = b + '__pos'; params.append(c_ast.Decl(nm, [], [], [], [], c_ast.TypeDecl(nm, [], None, c_ast.IdentifierType(['unsigned', 'long'])), None, None))
        for b in sorted(x for x in self.nullable & set(self.base.values()) if self.size[x][0] == 'param'):
            nm = b + '__null'; params.append(c_ast.Decl(nm, [], [], [], [], c_ast.TypeDecl(nm, [], None, c_ast.IdentifierType(['int'])), None, None)); self.null_params.append(nm)
        fd.decl.type.args = c_ast.ParamList(params)
        for v, (hb, w) in sorted(self.heap.items()):
            pre.append(c_ast.Decl(hb + '__n', [], [], [], [], c_ast.TypeDecl(hb + '__n', [], None, c_ast.IdentifierType(['unsigned', 'long'])), num(0), None))
            pre.append(c_ast.Decl(hb + '__null', [], [], [], [], c_ast.TypeDecl(hb + '__null', [], None, c_ast.IdentifierType(['int'])), num(1), None))
        for b in sorted(self.freeable | {hb for hb, w in self.heap.values()}):
            pre.append(c_ast.Decl(self.freevar(b), [], [], [], [], c_ast.TypeDecl(self.freevar(b), [], None, c_ast.IdentifierType(['int'])), num(0), None))
        keep_params = []
        decl_w = c_ast.Decl('__ms_w', [], [], [], [], c_ast.TypeDecl('__ms_w', [], None, c_ast.IdentifierType(['long', 'long'])), num(0), None)
        fd.body.block_items = [decl_w] + pre + body
        self.notes.add('memory-safety pass: %d checked accesses, %d unchecked (calls)' % (self.checked, self.unchecked))
        self.notes.add('tracked bases: ' + ', '.join('%s%s' % (b, ' (string)' if self.string.get(b) else '') for b in sorted(set(self.base.values()))))
        return self


def collections_defaultdict():
    import collections
    return collections.defaultdict(list)
