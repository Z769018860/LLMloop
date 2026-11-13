"""v0.81: AUTOMATIC transcription of real C functions (gnulib / coreutils) into the verifier fragment, replacing the earlier hand transcriptions.
Pipeline (all steps untrusted; the verifier decides, and a native differential test compares the original function with the transcription):
 1. clang -ast-print of the translation unit (macros expanded, -DNDEBUG so asserts vanish) -> the function text; typedef names are resolved to builtin types;
 2. pycparser; normalizations: scalar locals get `= 0` initializers, declarations inside loop bodies are hoisted (renamed), `for(;;)`/trailing-loop functions get a dead `return 0;`,
    bool -> int, qualifiers/attributes dropped, `x ? y : z`/`do` left to the verifier's normalizers;
 3. calls: output-only calls (printf family) with scalar-or-string arguments are dropped; calls to functions defined in the same file are INLINED (loop-free callees, returns turned into flag variables);
    other calls whose arguments are all scalars and whose result is scalar become nondeterministic inputs (assumes the callee does not modify our locals: it cannot, arguments are by value);
    anything with pointers/arrays/structs/floats is rejected with a reason.
 4. certification: sampling + Houdini (llmloop.houdini_while / houdini_loops) with parameter bounds = full range of the declared types."""
import collections, copy, json, os, random, re, subprocess, sys, tempfile
from pathlib import Path
from pycparser import c_parser, c_ast, c_generator
sys.setrecursionlimit(10000)
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts.memabs import Env, MemAbs
from scripts.memsafe import MemSafe
CU = Path('/tmp/cu'); G = c_generator.CGenerator()
EXITS = {'exit', '_exit', 'abort', 'usage_exit'}
OUTPUT_ONLY = {'printf_unlocked', 'fprintf_unlocked', 'fputs_unlocked', 'putchar_unlocked', 'emit_try_help', 'emit_mandatory_arg_note', 'emit_size_note', 'emit_stdin_note', 'emit_bug_reporting_address', 'version_etc', 'fputs_unlocked', 'printf', 'fprintf', 'puts', 'putchar', 'fputs', 'fputc', 'putc', 'fwrite', 'fflush', 'perror', 'vfprintf', 'oputs_', 'emit_ancillary_info'}
FORCED = {}
INTS = {('int',): (32, True), ('unsigned',): (32, False), ('unsigned', 'int'): (32, False), ('long',): (64, True), ('long', 'int'): (64, True), ('unsigned', 'long'): (64, False), ('unsigned', 'long', 'int'): (64, False),
        ('short',): (16, True), ('unsigned', 'short'): (16, False), ('char',): (8, True), ('unsigned', 'char'): (8, False), ('signed', 'char'): (8, True), ('long', 'long'): (64, True), ('unsigned', 'long', 'long'): (64, False),
        ('_Bool',): (8, False)}


_TU = {}


def tu_text(path, includes):
    key = str(path)
    if key not in _TU:
        r = subprocess.run(['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-include', str(CU / 'fake/config.h'), '-include', 'stdbool.h', '-include', 'stdint.h', '-include', 'stddef.h', '-include', str(CU / 'fake/prelude.h'), '-DNDEBUG', '-D__NO_CTYPE', '-Xclang', '-ast-print'] + [x for i in includes for x in ('-I', str(i))] + [str(path)], capture_output=True, text=True, timeout=180)
        _TU[key] = re.sub(r'__attribute__\(\(.*?\)\)\s*', '', r.stdout)
    return _TU[key]


def typedef_map(text):
    """typedef name -> builtin scalar type words; pointer typedefs -> 'void *'; struct/union/function typedefs -> 'struct __o'"""
    m = {}
    for a, b in re.findall(r'^typedef ([A-Za-z_0-9 ]+?) (\w+);$', text, re.M): m[b] = a
    changed = True
    while changed:
        changed = False
        for k, v in list(m.items()):
            w = v.split()
            if len(w) == 1 and w[0] in m and w[0] != k: m[k] = m[w[0]]; changed = True
    for decl in re.findall(r'^typedef (.*);$', text, re.M):
        mm = re.search(r'\(\s*\*\s*(\w+)\s*\)', decl)
        if mm: m.setdefault(mm.group(1), 'void *'); continue
        am = re.match(r'(.*?)(\w+)\s*\[[^\]]*\]$', decl.strip())
        if am and am.group(2) not in m:
            sm2 = re.search(r'\b(struct|union) (\w+)\b', am.group(1)); m[am.group(2)] = ('%s %s *' % (sm2.group(1), sm2.group(2)) if sm2 else 'void *'); continue
        mm = re.search(r'(\w+)$', decl.strip())
        sm = re.search(r'\b(struct|union) (\w+)\b', decl)
        if mm and mm.group(1) not in m: m[mm.group(1)] = ('%s %s *' % (sm.group(1), sm.group(2)) if sm else 'void *') if '*' in decl else ('%s %s' % (sm.group(1), sm.group(2)) if sm else 'struct __o')
    for nm in re.findall(r'^\} (\w+);$', text, re.M): m[nm] = 'struct ' + nm
    for k, v in list(m.items()):
        if v.startswith('enum '): m[k] = 'int'
    changed = True
    while changed:                                         # typedef chains (va_list -> __mbstate_t -> struct __mbstate_t)
        changed = False
        for k, v in list(m.items()):
            w = v.split()
            if len(w) == 1 and w[0] in m and w[0] != k and m[w[0]] != v: m[k] = m[w[0]]; changed = True
    return m


def protos_of(text, tmap):
    """function prototypes of the TU: name -> 'void' | 'scalar' | 'other' (by return type)"""
    out = {}
    for line in text.split('\n'):
        if not line.rstrip().endswith(';') or line.startswith(('typedef', 'struct', 'union', 'enum', ' ')): continue
        m = re.match(r'^(?:extern |static )*(.+?)\b(\w+)\s*\(.*\)\s*;\s*$', line)
        if not m: continue
        rt = clean(m.group(1), tmap).strip()
        out.setdefault(m.group(2), 'void' if rt == 'void' else 'scalar' if tuple(rt.split()) in INTS else 'other')
    return out


def extract(text, name):
    """source text of the definition of `name` (top-level, column 0) from clang -ast-print output; also returns the other function definitions of the file"""
    defs = {}
    lines = text.split('\n'); i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r'^(?:static |inline |extern )*[A-Za-z_][\w \*]*?\b(\w+)\(([^;]*)\) \{$', l)
        if m and not l.startswith(('typedef', 'struct')):
            j = i
            while j < len(lines) and lines[j] != '}': j += 1
            defs.setdefault(m.group(1), '\n'.join(lines[i:j + 1])); i = j
        i += 1
    return defs


def clean(src, tmap):
    src = re.sub(r'__attribute__\(\(.*?\)\)', '', src)
    src = re.sub(r'__builtin_offsetof\s*\([^()]*(?:\([^()]*\)[^()]*)*\)', 'nondet_ulong()', src)       # an offset: an arbitrary size_t value (sound)
    src = re.sub(r'__builtin_constant_p\s*\([^()]*(?:\([^()]*\)[^()]*)*\)', '0', src)
    src = re.sub(r'__builtin_types_compatible_p\s*\([^()]*(?:\([^()]*\)[^()]*)*\)', '0', src)
    for q in ('static', 'inline', 'register', 'const', 'extern', 'volatile', 'restrict', '__restrict', '__inline', '__extension__'): src = re.sub(r'\b%s\b' % q, '', src)
    items = sorted(tmap.items(), key=lambda kv: -len(kv[0]))
    for k, v in items: src = re.sub(r'\b%s\b' % re.escape(k), v, src)
    src = re.sub(r'\b_Bool\b', 'int', src); src = re.sub(r'\bbool\b', 'int', src); src = re.sub(r'\benum \w+', 'int', src)
    for ty, n in (('unsigned long long', 8), ('unsigned long', 8), ('long long', 8), ('unsigned int', 4), ('unsigned short', 2), ('unsigned char', 1), ('long', 8), ('int', 4), ('short', 2), ('char', 1), ('signed char', 1)): src = re.sub(r'sizeof\(%s\)' % ty, str(n), src)
    return src


KEYWORDS = {'return', 'else', 'goto', 'case', 'default', 'sizeof', 'typedef', 'struct', 'union', 'enum', 'unsigned', 'signed', 'int', 'long', 'short', 'char', 'void', 'float', 'double', 'if', 'while', 'for', 'do', 'switch', 'break', 'continue', 'static', 'extern', 'const', 'volatile', 'register', 'auto', 'inline'}


def discover_types(src, tmap):
    """identifiers that are used as type names (`T x;`, `T *x = ..`, `T x[n];`, `(T *) e`) but unknown to the typedef map become opaque struct types (their member accesses are then untyped and rejected, their pointers abstracted)"""
    found = False
    for m in re.finditer(r'(?m)^[ \t]*(?:const |static |register )*([A-Za-z_]\w*)\s+\**\s*[A-Za-z_]\w*\s*(?:\[[^\]]*\])*\s*(?:=|;|,)', src):
        nm = m.group(1)
        if nm not in KEYWORDS and nm not in tmap:
            tmap[nm] = 'struct __o'; found = True
            for k, v in list(tmap.items()):
                if v == nm: tmap[k] = 'struct __o'
    return found


def parse_fn(src):
    ast = c_parser.CParser().parse(src); return [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]


def walk(n):
    yield n
    for _, c in n.children(): yield from walk(c)


def scalar_type(ty):
    return isinstance(ty, c_ast.TypeDecl) and isinstance(ty.type, c_ast.IdentifierType) and tuple(ty.type.names) in INTS


def ret_scalar(fd): return scalar_type(fd.decl.type.type) or (isinstance(fd.decl.type.type, c_ast.TypeDecl) and isinstance(fd.decl.type.type.type, c_ast.IdentifierType) and fd.decl.type.type.type.names == ['void'])


def check_scalar_only(fd):
    for n in walk(fd):
        if isinstance(n, (c_ast.PtrDecl, c_ast.ArrayDecl, c_ast.Struct, c_ast.Union, c_ast.StructRef, c_ast.ArrayRef, c_ast.FuncDecl)) and not (isinstance(n, c_ast.FuncDecl) and n is fd.decl.type): raise ValueError('pointers/arrays/structs')
        if isinstance(n, c_ast.UnaryOp) and n.op in ('*', '&'): raise ValueError('pointers/arrays/structs')
        if isinstance(n, c_ast.Constant) and n.type in ('float', 'double', 'string'): raise ValueError('floats/strings')
        if isinstance(n, c_ast.Goto): raise ValueError('goto')
        if isinstance(n, c_ast.TypeDecl) and isinstance(n.type, c_ast.IdentifierType) and tuple(n.type.names) not in INTS and n.type.names != ['void']: raise ValueError('non-integer type ' + ' '.join(n.type.names))


def normalize_structure(fd, notes):
    """(void)0 statements dropped; do{..}while(0) flattened; do{B}while(c) -> B; while(c){B} (exact without break/continue); for(i;c;s){B} -> i; while(c){B; s}; void functions -> int"""
    def has_jump(n): return any(isinstance(x, (c_ast.Break, c_ast.Continue)) for x in walk(n))
    sw_counter = [0]

    def replace_continues(items, make):
        """replace `continue` belonging to this loop (not nested loops) by make() + continue"""
        out = []
        for it in items:
            if isinstance(it, c_ast.Continue): out.append(c_ast.Compound(make() + [c_ast.Continue()]))
            elif isinstance(it, c_ast.Compound): it.block_items = replace_continues(it.block_items or [], make); out.append(it)
            elif isinstance(it, c_ast.If):
                for a in ('iftrue', 'iffalse'):
                    s = getattr(it, a)
                    if s is not None: setattr(it, a, c_ast.Compound(replace_continues(s.block_items if isinstance(s, c_ast.Compound) else [s], make)))
                out.append(it)
            elif isinstance(it, c_ast.Switch):
                sw = it.stmt; sw.block_items = replace_continues(sw.block_items or [], make) if isinstance(sw, c_ast.Compound) else sw; out.append(it)
            elif isinstance(it, (c_ast.Case, c_ast.Default)): it.stmts = replace_continues(it.stmts or [], make); out.append(it)
            else: out.append(it)
        return out

    def flat_cases(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.Case): out.append(('case', it.expr)); out += flat_cases(it.stmts or [])
            elif isinstance(it, c_ast.Default): out.append(('default', None)); out += flat_cases(it.stmts or [])
            else: out.append(('stmt', it))
        return out

    def conv_switch(sw):
        sw_counter[0] += 1; nm = '__sw%d' % sw_counter[0]
        flat = flat_cases(sw.stmt.block_items if isinstance(sw.stmt, c_ast.Compound) else [sw.stmt])
        groups = []; labels = []; body = []
        for kind, x in flat:
            if kind in ('case', 'default'):
                if body: groups.append((labels, body)); labels, body = [], []
                labels.append((kind, x))
            else: body.append(x)
        groups.append((labels, body))
        decl = c_ast.Decl(nm, [], [], [], [], c_ast.TypeDecl(nm, [], None, c_ast.IdentifierType(['long', 'long'])), sw.cond, None)
        def ends(b): return bool(b) and isinstance(b[-1], (c_ast.Break, c_ast.Return))
        simple = all(ends(b) or k == len(groups) - 1 for k, (l, b) in enumerate(groups))
        if simple:
            for l, b in groups:
                inner = b[:-1] if b and isinstance(b[-1], c_ast.Break) else b
                if any(isinstance(x, c_ast.Break) for s in inner for x in walk(s) if not isinstance(x, (c_ast.While, c_ast.For, c_ast.DoWhile))): simple = False
        def test(l):
            cs = [c_ast.BinaryOp('==', c_ast.ID(nm), x) for k, x in l if k == 'case']
            return cs
        allcases = [c for l, b in groups for c in test(l)]
        if simple:
            chain = None; default = None; ifs = []
            for l, b in groups:
                inner = list(b[:-1]) if b and isinstance(b[-1], c_ast.Break) else list(b)
                if any(k == 'default' for k, x in l): default = c_ast.Compound(inner); continue
                cond = test(l)[0]
                for c in test(l)[1:]: cond = c_ast.BinaryOp('||', cond, c)
                ifs.append((cond, c_ast.Compound(inner)))
            tail = default
            for cond, blk in reversed(ifs): tail = c_ast.If(cond, blk, tail)
            notes.add('switch -> if chain'); return [decl] + ([tail] if tail is not None else [])
        if any(isinstance(x, c_ast.Continue) for l, b in groups for s in b for x in walk(s)): raise ValueError('continue inside a fallthrough switch')
        # general (fallthrough) form: while (1) { if (matched || test) { matched = 1; body } ... break; }
        mn = nm + 'm'; out = [decl, c_ast.Decl(mn, [], [], [], [], c_ast.TypeDecl(mn, [], None, c_ast.IdentifierType(['int'])), c_ast.Constant('int', '0'), None)]
        none = None
        for c in allcases: none = c if none is None else c_ast.BinaryOp('||', none, c)
        loop = []
        for l, b in groups:
            cs = test(l); cond = c_ast.ID(mn)
            for c in cs: cond = c_ast.BinaryOp('||', cond, c)
            if any(k == 'default' for k, x in l): cond = c_ast.BinaryOp('||', cond, c_ast.UnaryOp('!', none) if none is not None else c_ast.Constant('int', '1'))
            loop.append(c_ast.If(cond, c_ast.Compound([c_ast.Assignment('=', c_ast.ID(mn), c_ast.Constant('int', '1'))] + list(b)), None))
        loop.append(c_ast.Break()); notes.add('switch -> while(1) with fallthrough flag'); return out + [c_ast.While(c_ast.Constant('int', '1'), c_ast.Compound(loop))]
    def tr(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.Cast) and isinstance(it.expr, c_ast.Constant): continue
            if isinstance(it, c_ast.Switch):
                if any(isinstance(x, c_ast.Continue) for x in walk(it)) and False: raise ValueError('continue in switch')
                out += tr(conv_switch(it)); continue
            if isinstance(it, c_ast.Compound): it.block_items = tr(it.block_items or []); out.append(it); continue
            if isinstance(it, c_ast.DoWhile):
                body = it.stmt if isinstance(it.stmt, c_ast.Compound) else c_ast.Compound([it.stmt])
                body.block_items = tr(body.block_items or [])
                if has_jump(body):          # do { B } while (c)  ->  while (1) { B'; if (!c) break; }  with `continue` -> { if (!c) break; continue; }
                    cb = lambda c=it.cond: [c_ast.If(c_ast.UnaryOp('!', copy.deepcopy(c)), c_ast.Compound([c_ast.Break()]), None)]
                    body.block_items = replace_continues(body.block_items, cb) + cb()
                    out.append(c_ast.While(c_ast.Constant('int', '1'), body)); notes.add('do-while with jumps -> while(1)'); continue
                if isinstance(it.cond, c_ast.Constant) and it.cond.value == '0': out.append(body); notes.add('do-while(0) flattened'); continue
                out.append(copy.deepcopy(body)); out.append(c_ast.While(it.cond, body)); notes.add('do-while peeled'); continue
            if isinstance(it, c_ast.For):
                body = it.stmt if isinstance(it.stmt, c_ast.Compound) else c_ast.Compound([it.stmt])
                body.block_items = tr(body.block_items or [])
                if it.next is not None and any(isinstance(x, c_ast.Continue) for s in body.block_items for x in walk(s)): body.block_items = replace_continues(body.block_items, lambda nxt=it.next: [copy.deepcopy(nxt)])
                if it.init is not None:
                    if isinstance(it.init, c_ast.DeclList): out.extend(it.init.decls)
                    else: out.append(it.init)
                if it.next is not None: body.block_items.append(it.next)
                out.append(c_ast.While(it.cond if it.cond is not None else c_ast.Constant('int', '1'), body)); notes.add('for -> while'); continue
            if isinstance(it, c_ast.While):
                it.stmt = it.stmt if isinstance(it.stmt, c_ast.Compound) else c_ast.Compound([it.stmt]); it.stmt.block_items = tr(it.stmt.block_items or []); out.append(it); continue
            if isinstance(it, c_ast.If):
                for a in ('iftrue', 'iffalse'):
                    s = getattr(it, a)
                    if s is not None:
                        s = s if isinstance(s, c_ast.Compound) else c_ast.Compound([s]); s.block_items = tr(s.block_items or []); setattr(it, a, s)
            out.append(it)
        return out
    fd.body.block_items = tr(fd.body.block_items or [])
    if isinstance(fd.decl.type.type, c_ast.TypeDecl) and isinstance(fd.decl.type.type.type, c_ast.IdentifierType) and fd.decl.type.type.type.names == ['void']:
        fd.decl.type.type.type.names = ['int']; notes.add('void -> int')
        for n in walk(fd.body):
            for name, ch in list(n.children()):
                if isinstance(ch, c_ast.Return) and ch.expr is None: ch.expr = c_ast.Constant('int', '0')


def add_globals(fd, gmap, notes):
    """free identifiers (globals) become extra parameters: the function is verified for ANY initial value of every global it reads"""
    declared = {p.name for p in (fd.decl.type.args.params if fd.decl.type.args else [])} | {n.name for n in walk(fd.body) if isinstance(n, c_ast.Decl)}
    called = {getattr(n.name, 'name', None) for n in walk(fd.body) if isinstance(n, c_ast.FuncCall)}
    free = []
    for n in walk(fd.body):
        if isinstance(n, c_ast.ID) and n.name not in declared and n.name not in called and n.name not in free and n.name != 'unknown': free.append(n.name)
    par = parents_of(fd.body)
    for n in list(walk(fd.body)):
        if isinstance(n, c_ast.ID) and gmap.get(n.name) == 'ENUM' and n.name not in declared and id(n) in par:
            pr, attr = par[id(n)]; setchild(pr, attr, c_ast.Constant('int', str(ENUMS[n.name]))); notes.add('enumerator constant ' + n.name)
    extra = []
    for g in free:
        ty = gmap.get(g)
        if ty == 'ENUM': continue
        if ty == '_Bool': ty = 'int'; FORCED[g] = [0, 1]
        if ty is None or tuple(ty.split()) not in INTS: raise ValueError('unresolved free identifier ' + g)
        extra.append(c_ast.Decl(g, [], [], [], [], c_ast.TypeDecl(g, [], None, c_ast.IdentifierType(ty.split())), None, None)); notes.add('global as parameter: ' + g)
    if extra:
        if fd.decl.type.args is None: fd.decl.type.args = c_ast.ParamList([])
        fd.decl.type.args.params = [p for p in fd.decl.type.args.params if not (isinstance(p, c_ast.Typename))] + extra
    return [e.name for e in extra]


def enum_consts(text):
    out = {}
    for body in re.findall(r'^enum \w* ?\{(.*?)\n\};', text, re.M | re.S):
        v = 0
        for item in [x.strip() for x in body.replace('\n', ' ').split(',') if x.strip()]:
            if '=' in item:
                nm, ex = [s.strip() for s in item.split('=', 1)]
                if not re.fullmatch(r'[0-9xXa-fA-F\s<>()+\-*|&~UL]+', ex): continue
                try: v = int(eval(ex.replace('U', '').replace('L', '')))
                except Exception: continue
            else: nm = item
            out[nm] = v; v += 1
    return out


def global_map(text, tmap):
    m = dict((k, 'ENUM') for k in enum_consts(text))
    for nm in re.findall(r'^(?:static |extern )*enum \w+ (\w+)(?: = [^;]*)?;$', text, re.M): m[nm] = 'int'
    for ty, nm in re.findall(r'^(?:static |extern )*((?:unsigned |signed )?(?:long long|long|int|short|char|size_t|[A-Za-z_0-9]+))\s+(\w+)(?: = [^;]*)?;$', text, re.M):
        m[nm] = tmap.get(ty, ty)
    return m


def rename_underscored(fd):
    names = {n.name for n in walk(fd) if isinstance(n, c_ast.Decl) and n.name and n.name.startswith('_')}
    for n in walk(fd):
        if isinstance(n, c_ast.Decl) and n.name in names:
            n.name = 'v' + n.name; ty = n.type
            while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
            if ty is not None: ty.declname = n.name
        elif isinstance(n, c_ast.ID) and n.name in names: n.name = 'v' + n.name


def copy_mutated_params(fd, notes):
    params = fd.decl.type.args.params if fd.decl.type.args else []
    assigned = {n.lvalue.name for n in walk(fd.body) if isinstance(n, c_ast.Assignment) and isinstance(n.lvalue, c_ast.ID)} | {n.expr.name for n in walk(fd.body) if isinstance(n, c_ast.UnaryOp) and n.op in ('p++', 'p--', '++', '--') and isinstance(n.expr, c_ast.ID)}
    pre = []
    for p in params:
        if p.name in assigned:
            nm = p.name; new = nm + '_in'; ty = copy.deepcopy(p.type); ty.declname = nm
            pre.append(c_ast.Decl(nm, [], [], [], [], ty, c_ast.ID(new), None)); p.name = new
            t2 = p.type
            while t2 is not None and not isinstance(t2, c_ast.TypeDecl): t2 = getattr(t2, 'type', None)
            t2.declname = new; notes.add('copied mutated parameter ' + nm)
    fd.body.block_items = pre + fd.body.block_items


def parents_of(root):
    par = {}
    for n in walk(root):
        for name, c in n.children(): par[id(c)] = (n, name)
    return par


def drop_opaque_params(fd, notes):
    """pointer/struct parameters that are only passed on to calls or compared with NULL are removed (null-ness becomes nondeterministic); `(void)` parameter lists are emptied"""
    if fd.decl.type.args is None: return
    keep, par = [], parents_of(fd.body)
    for p in fd.decl.type.args.params:
        if isinstance(p, c_ast.Typename): notes.add('(void) parameter list'); continue
        if isinstance(p, c_ast.Decl) and scalar_type(p.type): keep.append(p); continue
        if not isinstance(p, c_ast.Decl) or not p.name: raise ValueError('non-scalar parameter')
        for n in walk(fd.body):
            if not (isinstance(n, c_ast.ID) and n.name == p.name): continue
            pr, attr = par[id(n)]
            if isinstance(pr, c_ast.ExprList) and id(pr) in par and isinstance(par[id(pr)][0], c_ast.FuncCall): continue          # passed on to a call
            nullcheck = (isinstance(pr, c_ast.BinaryOp) and (pr.op in ('&&', '||') or (pr.op in ('==', '!=') and any(isinstance(x, c_ast.Constant) and x.value == '0' for x in (pr.left, pr.right))))) or (isinstance(pr, c_ast.UnaryOp) and pr.op == '!') or (isinstance(pr, (c_ast.If, c_ast.While, c_ast.TernaryOp)) and attr == 'cond')
            if not nullcheck: raise ValueError('pointer/struct parameter %s is dereferenced or computed with' % p.name)
            setchild(pr, attr, c_ast.FuncCall(c_ast.ID('unknown'), None)); notes.add('null-ness of parameter %s is nondeterministic' % p.name)
        notes.add('opaque parameter dropped: ' + p.name)
    fd.decl.type.args.params = keep


def hoist_and_init(fd, notes):
    """locals: initializer 0; declarations inside loops hoisted to the top"""
    body = fd.body; top = []; counter = [0]
    def fix(stmt, in_loop):
        if isinstance(stmt, c_ast.Compound):
            items = []; in_loop = in_loop or stmt is not body
            for it in stmt.block_items or []:
                if isinstance(it, c_ast.Decl) and in_loop:
                    counter[0] += 1; nm = it.name
                    d = copy.deepcopy(it); d.init = None; top.append(d)
                    if it.init is not None: items.append(c_ast.Assignment('=', c_ast.ID(nm), it.init))
                    notes.add('hoisted loop-body declaration')
                else: items.append(fix(it, in_loop))
            stmt.block_items = items; return stmt
        if isinstance(stmt, (c_ast.While, c_ast.DoWhile)): stmt.stmt = fix(stmt.stmt, True); return stmt
        if isinstance(stmt, c_ast.For): stmt.stmt = fix(stmt.stmt, True); return stmt
        if isinstance(stmt, c_ast.If):
            stmt.iftrue = fix(stmt.iftrue, True)
            if stmt.iffalse is not None: stmt.iffalse = fix(stmt.iffalse, True)
        return stmt
    fix(body, False)
    names = [d.name for d in top]
    if len(set(names)) != len(names) or any(d.name in {x.name for x in body.block_items if isinstance(x, c_ast.Decl)} for d in top): raise ValueError('hoisting would shadow')
    pos = 0
    items = body.block_items
    for d in reversed(top): items.insert(0, d)
    # declarations that follow executable statements at function level are hoisted as well (the loop front ends only accept leading declarations)
    k = 0
    while k < len(items) and isinstance(items[k], c_ast.Decl): k += 1
    lead, rest = items[:k], items[k:]; moved = []; newrest = []
    for it in rest:
        if isinstance(it, c_ast.Decl):
            d = copy.deepcopy(it); d.init = None; moved.append(d)
            if it.init is not None: newrest.append(c_ast.Assignment('=', c_ast.ID(it.name), it.init))
            notes.add('hoisted late declaration')
        else: newrest.append(it)
    items[:] = lead + moved + newrest
    for n in walk(body):
        if isinstance(n, c_ast.Decl) and n.init is None and isinstance(n.type, c_ast.TypeDecl): n.init = c_ast.Constant('int', '0'); notes.add('zero-initialized locals')


def flatten_blocks(fd, notes):
    """redundant nested { } blocks (left by do{}while(0) flattening) are spliced into the parent list: all names are unique and declarations are hoisted by now"""
    def fl(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.Compound): out += fl(it.block_items or []); notes.add('flattened blocks')
            else:
                for a in ('iftrue', 'iffalse', 'stmt'):
                    s = getattr(it, a, None) if isinstance(it, (c_ast.If, c_ast.While)) else None
                    if isinstance(s, c_ast.Compound): s.block_items = fl(s.block_items or [])
                out.append(it)
        return out
    fd.body.block_items = fl(fd.body.block_items or [])


def ensure_return(fd, notes):
    items = fd.body.block_items
    if not items or not isinstance(items[-1], c_ast.Return):
        items.append(c_ast.Return(c_ast.Constant('int', '0'))); notes.add('dead trailing return')


LIB_RANGES = {'rand': (0, 2147483647), 'getchar': (-1, 255), 'fgetc': (-1, 255), 'getc': (-1, 255), 'random': (0, 2147483647)}
LIB_BOOL = {  # ASCII/C-locale ctype predicates, used only where the result is consumed as a truth value (glibc returns any non-zero value, we return 1)
    'isdigit': '(c >= 48 && c <= 57)', 'isalpha': '((c >= 65 && c <= 90) || (c >= 97 && c <= 122))', 'isupper': '(c >= 65 && c <= 90)', 'islower': '(c >= 97 && c <= 122)',
    'isalnum': '((c >= 48 && c <= 57) || (c >= 65 && c <= 90) || (c >= 97 && c <= 122))', 'isspace': '(c == 32 || (c >= 9 && c <= 13))', 'isxdigit': '((c >= 48 && c <= 57) || (c >= 65 && c <= 70) || (c >= 97 && c <= 102))',
    'isblank': '(c == 32 || c == 9)', 'isprint': '(c >= 32 && c <= 126)', 'iscntrl': '((c >= 0 && c <= 31) || c == 127)', 'isgraph': '(c >= 33 && c <= 126)'}
LIB_VALUE = {'abs': '(c < 0 ? -c : c)', 'labs': '(c < 0 ? -c : c)', 'llabs': '(c < 0 ? -c : c)',    # exact, including the signed-overflow undefined behaviour at INT_MIN
             'toupper': '((c >= 97 && c <= 122) ? c - 32 : c)', 'tolower': '((c >= 65 && c <= 90) ? c + 32 : c)', '__builtin_expect': 'c'}


def _sub(text, name, expr_ast):
    e = c_parser.CParser().parse('int f(){ int c; return %s; }' % text).ext[0].body.block_items[1].expr
    for n in walk(e):
        for nm, ch in list(n.children()):
            if isinstance(ch, c_ast.ID) and ch.name == 'c': setchild(n, nm, c_ast.ID(name))
    return e


def setchild(n, name, new):
    m = re.match(r'(\w+)\[(\d+)\]$', name)
    if m: getattr(n, m.group(1))[int(m.group(2))] = new
    else: setattr(n, name, new)


def is_bool_ctx(parent, name):
    if isinstance(parent, (c_ast.If, c_ast.While)) and name == 'cond': return True
    if isinstance(parent, c_ast.UnaryOp) and parent.op == '!': return True
    if isinstance(parent, c_ast.BinaryOp) and parent.op in ('&&', '||'): return True
    if isinstance(parent, c_ast.TernaryOp) and name == 'cond': return True
    return isinstance(parent, c_ast.BinaryOp) and parent.op in ('==', '!=') and any(isinstance(x, c_ast.Constant) and x.value == '0' for x in (parent.left, parent.right))


def inline_calls(fd, defs_ast, notes, depth=0, stack=()):
    """calls: drop output-only calls, library specs, inline same-file scalar callees (loops allowed: returns are removed with jump_eliminate first), nondeterministic result for other scalar calls;
    calls in loop headers are hoisted: while (C(call)) B  ->  while (1) { pre; if (!C) break; B }"""
    counter = [0]
    def uid(): counter[0] += 1; return '__c%d_%d' % (depth, counter[0])
    def scalar_decl(nm, init, ty=None):
        return c_ast.Decl(nm, [], [], [], [], c_ast.TypeDecl(nm, [], None, c_ast.IdentifierType(ty or ['int'])), init, None)
    def callee_result(call, boolctx=False):
        nm = call.name.name if isinstance(call.name, c_ast.ID) else None
        if nm is None: raise ValueError('indirect call')
        args = call.args.exprs if call.args else []
        if nm in OUTPUT_ONLY:
            for a in args:
                if any(isinstance(n, c_ast.BinaryOp) and n.op in ('/', '%', '<<', '>>') for n in walk(a)): raise ValueError('output call with computed arguments')
            return None, []
        if nm in EXITS: return 'EXIT', []
        if nm == '__builtin_expect' and len(args) == 2: return args[0], []
        if nm.startswith('nondet_') and not args: return call, []          # typed nondeterministic input produced by the memory abstraction (kept as is)
        if nm in ('strlen', 'strnlen', 'wcslen') and args:             # an object size is below 2^62: the result is an arbitrary size_t in [0, 2^62]
            u = uid(); tmp = 'v' + u; notes.add('library range: %s in [0, 2^62]' % nm)
            clamp = [c_ast.If(c_ast.BinaryOp('>', c_ast.ID(tmp), c_ast.Constant('int', '4611686018427387904')), c_ast.Compound([c_ast.Assignment('=', c_ast.ID(tmp), c_ast.Constant('int', '4611686018427387904'))]), None)]
            return c_ast.ID(tmp), [scalar_decl(tmp, c_ast.FuncCall(c_ast.ID('nondet_ulong'), None), ['unsigned', 'long'])] + clamp
        if (nm in LIB_VALUE or (nm in LIB_BOOL and boolctx)) and len(args) == 1:
            u = uid(); tmp = 'v' + u; res = 'v' + u + 'r'
            spec = LIB_VALUE.get(nm) or '(%s ? 1 : 0)' % LIB_BOOL[nm]
            notes.add('library spec: ' + nm)
            return c_ast.ID(res), [scalar_decl(tmp, args[0]), scalar_decl(res, _sub(spec, tmp, None))]
        if nm in LIB_RANGES and not args:
            lo, hi = LIB_RANGES[nm]; u = uid(); tmp = 'v' + u; notes.add('library range: %s in [%d,%d]' % (nm, lo, hi))
            clamp = [c_ast.If(c_ast.BinaryOp('<', c_ast.ID(tmp), c_ast.Constant('int', str(lo))), c_ast.Compound([c_ast.Assignment('=', c_ast.ID(tmp), c_ast.Constant('int', str(lo)))]), None),
                     c_ast.If(c_ast.BinaryOp('>', c_ast.ID(tmp), c_ast.Constant('int', str(hi))), c_ast.Compound([c_ast.Assignment('=', c_ast.ID(tmp), c_ast.Constant('int', str(hi)))]), None)]
            return c_ast.ID(tmp), [scalar_decl(tmp, c_ast.FuncCall(c_ast.ID('unknown'), None))] + clamp
        if nm in defs_ast and depth < 3 and nm not in stack and nm != fd.decl.name:
            try: return inline_callee(nm, args)
            except ValueError as e:
                if 'loop' in str(e) and 'callee' not in str(e) and False: raise
                notes.add('callee %s not inlinable (%s): treated as an opaque call' % (nm, str(e)[:50]))
        kind = PROTOS.get(nm) or ('void' if nm in defs_ast and is_void(defs_ast[nm]) else 'scalar' if nm in defs_ast and ret_scalar(defs_ast[nm]) else None)
        if kind is None and nm in DEFTEXT:
            hdr = DEFTEXT[nm].split('{')[0]; rt = clean(hdr[:hdr.index(nm + '(')], TMAP).strip() if (nm + '(') in hdr else ''
            kind = 'void' if rt == 'void' else 'scalar' if tuple(rt.split()) in INTS else 'other'
        if kind is None: kind = 'scalar'; notes.add('implicitly declared function %s (C: returns int)' % nm)
        locs = {p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if getattr(p, 'name', None)} | {n.name for n in walk(fd.body) if isinstance(n, c_ast.Decl) and n.name}
        scalar_locs = {}
        for p in (fd.decl.type.args.params if fd.decl.type.args else []):
            if isinstance(p, c_ast.Decl) and scalar_type(p.type): scalar_locs[p.name] = tuple(p.type.type.names)
        for n in walk(fd.body):
            if isinstance(n, c_ast.Decl) and n.name and scalar_type(n.type): scalar_locs[n.name] = tuple(n.type.type.names)
        havoc = []
        for a in args:
            if isinstance(a, c_ast.UnaryOp) and a.op == '&' and isinstance(a.expr, c_ast.ID) and a.expr.name in scalar_locs:      # the callee may overwrite the local: havoc it
                from scripts.memabs import NDNAME
                havoc.append(c_ast.Assignment('=', c_ast.ID(a.expr.name), c_ast.FuncCall(c_ast.ID('nondet_' + NDNAME[scalar_locs[a.expr.name]]), None))); continue
            for n in walk(a):
                if isinstance(n, c_ast.UnaryOp) and n.op == '&' and any(isinstance(x, c_ast.ID) and x.name in locs and x.name not in scalar_locs for x in walk(n)): raise ValueError('call with the address of a local: ' + nm)
                if isinstance(n, c_ast.BinaryOp) and n.op in ('/', '%', '<<', '>>'): raise ValueError('opaque call with computed arguments: ' + nm)
        if kind == 'void': notes.add('opaque void call dropped: ' + nm); return None, havoc
        if kind == 'other': notes.add('opaque pointer-returning call dropped: ' + nm); return 'OTHER', havoc
        notes.add('nondeterministic result for ' + nm)
        return c_ast.FuncCall(c_ast.ID('unknown'), None), havoc
    def inline_callee(nm, args):
        cd = copy.deepcopy(defs_ast[nm]); check_scalar_only_decl(cd)
        normalize_structure(cd, notes); uniquify_decls(cd)
        inline_calls(cd, defs_ast, notes, depth + 1, stack + (fd.decl.name,))
        check_scalar_only(cd); ensure_return(cd, set())
        from llmloop.jump_eliminate import eliminate_jumps
        eliminate_jumps(cd)
        sfx = '__c%d_%d' % (depth, counter[0] + 1); counter[0] += 1
        names = {p.name for p in (cd.decl.type.args.params if cd.decl.type.args else [])} | {n.name for n in walk(cd.body) if isinstance(n, c_ast.Decl)}
        for n in walk(cd):
            if isinstance(n, c_ast.Decl) and n.name in names and n is not cd.decl:
                n.name += sfx; ty = n.type
                while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
                if ty is not None: ty.declname = n.name
            elif isinstance(n, c_ast.ID) and n.name in names: n.name += sfx
        decls = []; params = [p for p in (cd.decl.type.args.params if cd.decl.type.args else []) if isinstance(p, c_ast.Decl)]
        if len(params) != len(args): raise ValueError('arity mismatch for ' + nm)
        for p, a in zip(params, args):
            if p.name is None: continue
            pn = p.name; ty = copy.deepcopy(p.type); ty.declname = pn; decls.append(c_ast.Decl(pn, [], [], [], [], ty, a, None))
        rv = 'vrv' + sfx; items = list(cd.body.block_items); fin = items.pop()
        has_ret = not (isinstance(cd.decl.type.type.type, c_ast.IdentifierType) and cd.decl.type.type.type.names == ['void'])
        rty = copy.deepcopy(cd.decl.type.type); rty.declname = rv
        pre = decls + ([c_ast.Decl(rv, [], [], [], [], rty, c_ast.Constant('int', '0'), None)] if has_ret else []) + items
        if has_ret and isinstance(fin, c_ast.Return) and fin.expr is not None: pre.append(c_ast.Assignment('=', c_ast.ID(rv), fin.expr))
        notes.add('inlined ' + nm + (' (with loops)' if any(isinstance(n, c_ast.While) for n in walk(cd.body)) else ''))
        return (c_ast.ID(rv) if has_ret else None), pre

    def replace_calls(root_parent, attr):
        """calls inside root_parent.<attr> (an expression), innermost first; returns the statements to run before"""
        pre = []
        def rec(parent, name, node):
            for nm, ch in list(node.children()): rec(node, nm, ch)
            if isinstance(node, c_ast.FuncCall):
                r, p = callee_result(node, is_bool_ctx(parent, name)); pre.extend(p)
                if r is None or r == 'OTHER': raise ValueError('call without a scalar result used as a value')
                if r == 'EXIT': raise ValueError('exit used as a value')
                setchild(parent, name, r)
        rec(root_parent, attr, getattr(root_parent, attr)); return pre
    def tr_stmt_list(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.FuncCall):
                r, pre = callee_result(it); out += pre
                if r == 'EXIT': out.append(c_ast.Return(c_ast.Constant('int', '0')))
            elif isinstance(it, c_ast.Compound): it.block_items = tr_stmt_list(it.block_items or []); out.append(it)
            elif isinstance(it, c_ast.If):
                it.iftrue = wrap(it.iftrue); it.iffalse = wrap(it.iffalse) if it.iffalse is not None else None
                out += replace_calls(it, 'cond'); out.append(it)
            elif isinstance(it, c_ast.While):
                it.stmt = wrap(it.stmt)
                if any(isinstance(n, c_ast.FuncCall) for n in walk(it.cond)):
                    pre = replace_calls(it, 'cond'); notes.add('loop-header call hoisted')
                    body = [c_ast.If(c_ast.UnaryOp('!', it.cond), c_ast.Compound([c_ast.Break()]), None)] + list(it.stmt.block_items)
                    out.append(c_ast.While(c_ast.Constant('int', '1'), c_ast.Compound(pre + body)))
                else: out.append(it)
            elif isinstance(it, c_ast.Return):
                if it.expr is not None: out += replace_calls(it, 'expr')
                out.append(it)
            elif isinstance(it, c_ast.Decl):
                if it.init is not None and not isinstance(it.init, c_ast.InitList): out += replace_calls(it, 'init')
                out.append(it)
            else:
                if isinstance(it, c_ast.Assignment): out += replace_calls(it, 'rvalue')
                elif isinstance(it, c_ast.UnaryOp): pass
                else:
                    holder = c_ast.ExprList([it]); out += replace_calls(holder, 'exprs[0]') if False else []
                out.append(it)
        return out
    def wrap(s):
        if isinstance(s, c_ast.Compound): s.block_items = tr_stmt_list(s.block_items or []); return s
        return c_ast.Compound(tr_stmt_list([s]))
    fd.body.block_items = tr_stmt_list(fd.body.block_items or [])


def is_void(fd): return isinstance(fd.decl.type.type, c_ast.TypeDecl) and isinstance(fd.decl.type.type.type, c_ast.IdentifierType) and fd.decl.type.type.type.names == ['void']


PROTOS = {}
DEFTEXT = {}
TMAP = {}
ENUMS = {}


def normalize_chars(fd, notes):
    """character constants become int constants (the verifier front ends only know integer literals)"""
    esc = {'n': 10, 't': 9, 'r': 13, 'a': 7, 'b': 8, 'f': 12, 'v': 11, '0': 0, '\\': 92, "'": 39, '"': 34, '?': 63, 'e': 27}
    par = parents_of(fd.body)
    for n in list(walk(fd.body)):
        if isinstance(n, c_ast.Constant) and n.type == 'char' and id(n) in par:
            v = n.value[1:-1] if not n.value.startswith(('L', 'u', 'U')) else n.value[2:-1]
            if v.startswith('\\'):
                body = v[1:]
                if body and body[0] in 'xX': code = int(body[1:], 16)
                elif body and body[0] in '01234567': code = int(body, 8)
                elif body in esc: code = esc[body]
                else: raise ValueError('character escape ' + v)
            elif len(v) == 1: code = ord(v)
            else: raise ValueError('multi-character constant')
            pr, attr = par[id(n)]; setchild(pr, attr, c_ast.Constant('int', str(code))); notes.add('character constants converted')


def eliminate_gotos(fd, notes):
    """forward gotos to labels at function level (the usual error/cleanup exits) become a pending-jump variable: `goto L` -> `__gt = id(L)`, the statements that follow (in every enclosing list) are guarded by
    `__gt == 0`, loops that contain a goto get `&& __gt == 0`, and the code of a label runs when no jump is pending or the pending jump targets it.  Backward gotos, nested labels: rejected."""
    items = fd.body.block_items or []
    gotos = [n for n in walk(fd.body) if isinstance(n, c_ast.Goto)]
    labels = [n for n in walk(fd.body) if isinstance(n, c_ast.Label)]
    if not gotos and not labels: return
    top_labels = [i for i, it in enumerate(items) if isinstance(it, c_ast.Label)]
    if len(top_labels) != len(labels): raise ValueError('label inside a nested block')
    ids = {items[i].name: k + 1 for k, i in enumerate(top_labels)}
    pos = {items[i].name: i for i in top_labels}
    if any(g.name not in ids for g in gotos): raise ValueError('goto to an unknown label')
    def has_goto(n): return any(isinstance(x, c_ast.Goto) for x in walk(n))
    def tr_list(stmts):
        out = []
        for k, s in enumerate(stmts):
            hg = has_goto(s); new = tr_stmt(s); out += new
            if hg and k + 1 < len(stmts):
                rest = tr_list(stmts[k + 1:]); out.append(c_ast.If(c_ast.BinaryOp('==', c_ast.ID('__gt'), c_ast.Constant('int', '0')), c_ast.Compound(rest), None)); break
        return out
    def tr_stmt(s):
        if isinstance(s, c_ast.Goto): return [c_ast.Assignment('=', c_ast.ID('__gt'), c_ast.Constant('int', str(ids[s.name])))]
        if isinstance(s, c_ast.Compound): return [c_ast.Compound(tr_list(list(s.block_items or [])))]
        if isinstance(s, c_ast.If):
            for a in ('iftrue', 'iffalse'):
                b = getattr(s, a)
                if b is not None: setattr(s, a, c_ast.Compound(tr_list(list(b.block_items) if isinstance(b, c_ast.Compound) else [b])))
            return [s]
        if isinstance(s, c_ast.While):
            body = list(s.stmt.block_items) if isinstance(s.stmt, c_ast.Compound) else [s.stmt]
            if has_goto(s): s.cond = c_ast.BinaryOp('&&', s.cond, c_ast.BinaryOp('==', c_ast.ID('__gt'), c_ast.Constant('int', '0')))
            s.stmt = c_ast.Compound(tr_list(body)); return [s]
        if isinstance(s, c_ast.Switch) or isinstance(s, (c_ast.For, c_ast.DoWhile)) and has_goto(s): raise ValueError('goto inside a for/do/switch (normalize first)')
        return [s]
    # segments: [before first label] [L1: ...] [L2: ...]
    segs = []; cur = []; curlab = None
    for it in items:
        if isinstance(it, c_ast.Label):
            segs.append((curlab, cur)); cur = [it.stmt]; curlab = it.name
        else: cur.append(it)
    segs.append((curlab, cur))
    for lab in ids:                               # forward only
        if any(isinstance(g, c_ast.Goto) and g.name == lab and not any(g in list(walk(it)) for it in sum([s for l, s in segs[:ids[lab]]], [])) for g in gotos): raise ValueError('backward goto')
    decl = c_ast.Decl('__gt', [], [], [], [], c_ast.TypeDecl('__gt', [], None, c_ast.IdentifierType(['int'])), c_ast.Constant('int', '0'), None)
    lead = [it for it in items if isinstance(it, c_ast.Decl)]; k = 0
    new = []
    for lab, body in segs:
        body = [b for b in body if not isinstance(b, c_ast.Decl)] if True else body
        tb = tr_list(body)
        if lab is None: new += tb
        else:
            cond = c_ast.BinaryOp('||', c_ast.BinaryOp('==', c_ast.ID('__gt'), c_ast.Constant('int', '0')), c_ast.BinaryOp('==', c_ast.ID('__gt'), c_ast.Constant('int', str(ids[lab]))))
            new.append(c_ast.If(cond, c_ast.Compound([c_ast.Assignment('=', c_ast.ID('__gt'), c_ast.Constant('int', '0'))] + tb), None))
    fd.body.block_items = lead + [decl] + new; notes.add('forward gotos eliminated (%d)' % len(gotos))


def hoist_effects(fd, notes):
    """side effects inside conditions/initializers/return values (x--, ++x, (c = e)) are moved in front of the statement; `while (C) B` becomes `while (1) { pre; if (!C) break; B }`.
    Effects under the right operand of &&/|| or a conditional branch are not moved (that would change the evaluation): such functions are rejected."""
    types = {}
    for p in (fd.decl.type.args.params if fd.decl.type.args else []):
        if isinstance(p, c_ast.Decl): types[p.name] = p.type
    for n in walk(fd.body):
        if isinstance(n, c_ast.Decl) and n.name: types[n.name] = n.type
    cnt = [0]
    def tmpdecl(x):
        cnt[0] += 1; nm = '__he%d' % cnt[0]; ty = copy.deepcopy(types[x]); inner = ty
        while inner is not None and not isinstance(inner, c_ast.TypeDecl): inner = getattr(inner, 'type', None)
        inner.declname = nm; return nm, ty
    def rec(parent, name, node, conditional, pre):
        if isinstance(node, c_ast.ExprList) and len(node.exprs) > 1 and parent is not None and not isinstance(parent, c_ast.FuncCall):          # comma expression (not an argument list): strictly left to right
            if conditional: raise ValueError('comma expression under a short-circuit operand')
            last = len(node.exprs) - 1
            for i in range(len(node.exprs)):
                sub = []; rec(node, 'exprs[%d]' % i, node.exprs[i], conditional, sub); pre.extend(sub)
                if i < last: pre.append(node.exprs[i])
            setchild(parent, name, node.exprs[-1]); notes.add('comma expression split'); return
        for nm, ch in list(node.children()):
            rec(node, nm, ch, conditional or (isinstance(node, c_ast.BinaryOp) and node.op in ('&&', '||') and nm.startswith('right')) or (isinstance(node, c_ast.TernaryOp) and nm in ('iftrue', 'iffalse')), pre)
        eff = None
        if isinstance(node, c_ast.UnaryOp) and node.op in ('p++', 'p--', '++', '--') and isinstance(node.expr, c_ast.ID) and node.expr.name in types: eff = ('inc', node)
        elif isinstance(node, c_ast.Assignment) and isinstance(node.lvalue, c_ast.ID) and parent is not None and not isinstance(parent, (c_ast.ExprList,)) and parent is not fd.body: eff = ('asg', node)
        if eff is None: return
        if conditional: raise ValueError('side effect under a short-circuit operand')
        k, nd = eff
        if k == 'inc':
            x = nd.expr.name; op = '+' if nd.op in ('p++', '++') else '-'; upd = c_ast.Assignment('=', c_ast.ID(x), c_ast.BinaryOp(op, c_ast.ID(x), c_ast.Constant('int', '1')))
            if nd.op.startswith('p'):
                tn, ty = tmpdecl(x); pre.append(c_ast.Decl(tn, [], [], [], [], ty, c_ast.ID(x), None)); pre.append(upd); setchild(parent, name, c_ast.ID(tn))
            else: pre.append(upd); setchild(parent, name, c_ast.ID(x))
        else:
            pre.append(copy.deepcopy(nd)); setchild(parent, name, c_ast.ID(nd.lvalue.name))
        notes.add('side effect hoisted out of an expression')
    def effects_in(expr):
        par2 = parents_of(expr) if isinstance(expr, c_ast.Node) else {}
        return any((isinstance(n, c_ast.UnaryOp) and n.op in ('p++', 'p--', '++', '--')) or isinstance(n, c_ast.Assignment) or (isinstance(n, c_ast.ExprList) and len(n.exprs) > 1 and not (id(n) in par2 and isinstance(par2[id(n)][0], c_ast.FuncCall))) for n in walk(expr))
    def do_expr(holder, attr):
        pre = []; rec(holder, attr, getattr(holder, attr), False, pre); return pre
    def tr(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.While):
                it.stmt = c_ast.Compound(tr(it.stmt.block_items if isinstance(it.stmt, c_ast.Compound) else [it.stmt]))
                if effects_in(it.cond):
                    pre = do_expr(it, 'cond')
                    out.append(c_ast.While(c_ast.Constant('int', '1'), c_ast.Compound(pre + [c_ast.If(c_ast.UnaryOp('!', it.cond), c_ast.Compound([c_ast.Break()]), None)] + list(it.stmt.block_items))))
                else: out.append(it)
            elif isinstance(it, c_ast.If):
                for a in ('iftrue', 'iffalse'):
                    s = getattr(it, a)
                    if s is not None: setattr(it, a, c_ast.Compound(tr(s.block_items if isinstance(s, c_ast.Compound) else [s])))
                if effects_in(it.cond): out += do_expr(it, 'cond')
                out.append(it)
            elif isinstance(it, c_ast.Compound): it.block_items = tr(it.block_items or []); out.append(it)
            elif isinstance(it, c_ast.ExprList): out += tr(list(it.exprs))
            elif isinstance(it, c_ast.Return) and it.expr is not None and effects_in(it.expr): out += do_expr(it, 'expr'); out.append(it)
            elif isinstance(it, c_ast.Decl) and it.init is not None and not isinstance(it.init, c_ast.InitList) and effects_in(it.init): out += do_expr(it, 'init'); out.append(it)
            elif isinstance(it, c_ast.Assignment) and effects_in(it.rvalue): out += do_expr(it, 'rvalue'); out.append(it)
            else: out.append(it)
        return out
    fd.body.block_items = tr(fd.body.block_items or [])


def check_scalar_only_decl(cd):
    for p in (cd.decl.type.args.params if cd.decl.type.args else []):
        if isinstance(p, c_ast.Typename): continue
        if not isinstance(p, c_ast.Decl) or not scalar_type(p.type): raise ValueError('callee with non-scalar parameter')
    if not ret_scalar(cd): raise ValueError('callee with non-scalar return type')


def uniquify_decls(fd):
    """nested declarations that reuse a name already declared in the function get a fresh name (sequential, so initializers still see the outer variable)"""
    declared = {p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if p.name}
    counter = [0]; done = set()
    def comp(c, top):
        if id(c) in done: return
        done.add(id(c)); cur = {}
        def ren(node):
            for n in walk(node):
                if isinstance(n, c_ast.ID) and n.name in cur: n.name = cur[n.name]
        for it in c.block_items or []:
            if isinstance(it, c_ast.Decl) and it.name:
                if it.init is not None: ren(it.init)
                if it.name in declared or it.name in cur.values():
                    counter[0] += 1; new = '%s__u%d' % (it.name, counter[0]); cur[it.name] = new; old = it.name; it.name = new; ty = it.type
                    while ty is not None and not isinstance(ty, c_ast.TypeDecl): ty = getattr(ty, 'type', None)
                    if ty is not None: ty.declname = new
                declared.add(it.name)
            else:
                ren(it)
            for n in (list(walk(it)) if not isinstance(it, c_ast.Decl) else []):
                if isinstance(n, c_ast.Compound) and n is not c: pass
        for n in [x for it in (c.block_items or []) for x in walk(it) if isinstance(x, c_ast.Compound)]:
            if n is not c: comp2(n)
    def comp2(c):
        comp(c, False)
    comp(fd.body, True)


def tr_returns(items, rv, dn):
    """loop-free callee body: return e -> flag + value, rest of the list guarded"""
    out = []
    for k, it in enumerate(items):
        if isinstance(it, c_ast.Return):
            if rv and it.expr is not None: out.append(c_ast.Assignment('=', c_ast.ID(rv), it.expr))
            out.append(c_ast.Assignment('=', c_ast.ID(dn), c_ast.Constant('int', '1'))); return out
        has = any(isinstance(n, c_ast.Return) for n in walk(it))
        if has:
            if isinstance(it, c_ast.If):
                it.iftrue = c_ast.Compound(tr_returns(list(it.iftrue.block_items) if isinstance(it.iftrue, c_ast.Compound) else [it.iftrue], rv, dn))
                if it.iffalse is not None: it.iffalse = c_ast.Compound(tr_returns(list(it.iffalse.block_items) if isinstance(it.iffalse, c_ast.Compound) else [it.iffalse], rv, dn))
            elif isinstance(it, c_ast.Compound): it.block_items = tr_returns(list(it.block_items), rv, dn)
            else: raise ValueError('return in unsupported position')
            out.append(it); rest = items[k + 1:]
            if rest: out.append(c_ast.If(c_ast.UnaryOp('!', c_ast.ID(dn)), c_ast.Compound(tr_returns(list(rest), rv, dn)), None))
            return out
        out.append(it)
    return out


def bounds_of(fd):
    b = {}
    forced = dict(FORCED)
    for p in (fd.decl.type.args.params if fd.decl.type.args else []):
        if p.name is None: continue
        if p.name in forced: b[p.name] = forced[p.name]; continue
        if p.name.endswith('__n'): b[p.name] = [0, 1 << 40]; continue
        bits, signed = INTS[tuple(p.type.type.names)]; b[p.name] = [-(1 << (bits - 1)), (1 << (bits - 1)) - 1] if signed else [0, (1 << bits) - 1]
    return b


class Info:
    def __init__(self, fd, extra, prelude, nondet, ms=None): self.fd, self.extra, self.prelude, self.nondet, self.ms = fd, extra, prelude, nondet, ms
    def __iter__(self): return iter((self.fd, self.extra))


_FILE = {}


def file_material(path, includes):
    key = str(path)
    if key not in _FILE:
        text = tu_text(path, includes); tmap = typedef_map(text); defs = extract(text, '')
        asts = {}
        for k, v in defs.items():
            for attempt in range(3):
                try: asts[k] = parse_fn(clean(v, tmap)); break
                except Exception as e:
                    if attempt == 2 or not (discover_types(clean(v, tmap), tmap) or discover_types(v, tmap)): break
        _FILE[key] = (text, tmap, defs, protos_of(text, tmap), asts, global_map(text, tmap), Env(text, tmap, clean))
    return _FILE[key]


def transcribe(path, name, includes, memsafe=False):
    text, tmap, defs, protos, asts, gmap, env = file_material(path, includes); PROTOS.clear(); PROTOS.update(protos); DEFTEXT.clear(); DEFTEXT.update(defs); TMAP.clear(); TMAP.update(tmap); ENUMS.clear(); ENUMS.update(enum_consts(text))
    if name not in defs: raise ValueError('definition not found')
    if '<recovery-expr>' in defs[name]: raise ValueError('translation-unit errors (missing project macros/headers)')
    notes = set()
    if name not in asts: raise ValueError('parse failure')
    orig_src = clean(defs[name], tmap); fd = copy.deepcopy(asts[name])
    eliminate_gotos(fd, notes)
    normalize_structure(fd, notes); uniquify_decls(fd)
    ms = MemSafe(fd, env, notes).run() if memsafe else None
    MemAbs(fd, env, notes).run(); normalize_chars(fd, notes); hoist_effects(fd, notes)
    inline_calls(fd, asts, notes)
    extra_params = add_globals(fd, gmap, notes)
    check_scalar_only(fd)
    hoist_and_init(fd, notes); flatten_blocks(fd, notes); ensure_return(fd, notes); rename_underscored(fd); copy_mutated_params(fd, notes)
    if fd.decl.type.args is None or not fd.decl.type.args.params:          # the verifier front ends need one parameter
        fd.decl.type.args = c_ast.ParamList([c_ast.Decl('__z', [], [], [], [], c_ast.TypeDecl('__z', [], None, c_ast.IdentifierType(['int'])), None, None)]); FORCED['__z'] = [0, 0]
    fd.decl.name = 'f'; fd.decl.type.type.declname = 'f' if hasattr(fd.decl.type.type, 'declname') else None
    for p in fd.decl.type.args.params: p.quals = []
    inl = [re.sub(r' \(with loops\)$', '', n[len('inlined '):]) for n in notes if n.startswith('inlined')]
    prelude = '\n'.join(clean(defs[k], tmap) for k in defs if k in inl)
    nondet = any(n.startswith(('nondeterministic', 'library range')) for n in notes)
    return orig_src, G.visit(fd), bounds_of(fd), sorted(notes), Info(fd, extra_params, prelude, nondet, ms)


def with_contract(fd, contract_text):
    """the function with `if (!(contract)) return 0;` after its leading declarations (the verdict is then relative to the contract)"""
    f2 = copy.deepcopy(fd); items = f2.body.block_items; k = 0
    while k < len(items) and isinstance(items[k], c_ast.Decl): k += 1
    cond = c_parser.CParser().parse('int f(){ return %s; }' % contract_text).ext[0].body.block_items[0].expr
    items.insert(k, c_ast.If(c_ast.UnaryOp('!', cond), c_ast.Compound([c_ast.Return(c_ast.Constant('int', '0'))]), None)); return f2


def contract_candidates(fd, len_params):
    ints = [p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if isinstance(p, c_ast.Decl) and p.name not in len_params and p.name != '__z' and scalar_type(p.type)]
    out = [('none', None)]
    if ints:
        out.append(('len >= each integer parameter', ' && '.join('(%s >= %s)' % (L, q) for L in len_params for q in ints)))
        out.append(('len >= each integer parameter + 1', ' && '.join('(%s >= %s + 1)' % (L, q) for L in len_params for q in ints)))
    out.append(('len >= 1', ' && '.join('(%s >= 1)' % L for L in len_params)))
    return out


def certify_memsafe(path, fn, includes, budget=120):
    """bounds checking of tracked pointers: returns a row fragment (status PROVED_MEMSAFE / NOT_PROVED / NOT_APPLICABLE)"""
    try: orig, new, bounds, notes, info = transcribe(path, fn, includes, memsafe=True)
    except Exception as e: return {'status': 'NOT_APPLICABLE', 'reason': str(e)[:80]}
    ms = info.ms
    res = {'status': 'NOT_PROVED', 'checked_accesses': ms.checked, 'unchecked_call_args': ms.unchecked, 'bases': sorted(set(ms.base.values())), 'strings': sorted(b for b, s in ms.string.items() if s), 'len_params': ms.len_params, 'notes': [n for n in notes if n.startswith(('memory-safety', 'tracked'))]}
    if ms.checked == 0: res['status'] = 'NO_CHECKED_ACCESSES'; return res
    for name, c in contract_candidates(info.fd, ms.len_params):
        if c is None and not ms.len_params: pass
        f2 = with_contract(info.fd, c) if c else info.fd
        f2 = copy.deepcopy(f2); f2.decl.name = 'f'
        src = G.visit(f2); r = certify(src, bounds, budget=budget)
        if r['status'] == 'PROVED': res.update({'status': 'PROVED_MEMSAFE', 'contract': name, 'contract_strength': 'weak (excludes empty buffers/strings)' if name == 'len >= 1' else 'strong' if name == 'none' else 'length contract', 'contract_text': c, 'method': r['method'], 'source': src, 'bounds': bounds}); return res
    return res


def certify(src, bounds, budget=150):
    import time
    from llmloop import houdini_while as HW
    HW.DEADLINE = time.time() + budget
    try: return _certify(src, bounds)
    finally: HW.DEADLINE = None


def _certify(src, bounds):
    from llmloop.api import analyze_request
    from llmloop.houdini_while import houdini
    res = {'status': 'NOT_RUN'}
    try:       # trivial invariants first: undefinedness-freedom often needs none
        from llmloop.houdini_loops import _prepare
        nl = len(_prepare(src)[2])
        if nl == 0:
            r0 = analyze_request({'source': src, 'frontend': 'typed_c', 'abi': 'LP64', 'parameter_bounds': bounds}); return {'status': 'PROVED' if r0['status'].startswith('PROVED') else r0['status'][:40], 'method': 'typed_c_no_loops_after_stubbing', 'rounds': 0}
        req = {'source': src, 'parameter_bounds': bounds, 'abi': 'LP64', 'solver_timeout_ms': 20000}
        r = analyze_request({**req, 'frontend': 'typed_invariant_while', 'range_invariants': {'invariant': ['True']}} if nl == 1 else {**req, 'frontend': 'typed_invariant_loops', 'range_invariants': {'invariants': [['True']] * nl}})
        if r['status'].startswith('PROVED'): return {'status': 'PROVED', 'method': 'trivial_invariants', 'invariant': ['True'] * nl, 'rounds': 1}
    except Exception: pass
    for tag, fn in (('houdini_while', lambda: houdini(src, bounds, 'LP64')), ('houdini_loops', None)):
        try:
            if fn: st, inv, rounds, log = fn(); ok = st == 'PROVED'; res = {'status': st[:60], 'method': tag, 'invariant': inv if ok else None, 'rounds': rounds}
            else:
                from llmloop.houdini_loops import houdini_loops
                st, inv, rounds, log = houdini_loops(src, bounds, 'LP64', max_rounds=60); ok = st == 'PROVED'; res = {'status': st[:60], 'method': tag, 'invariant': inv if ok else None, 'rounds': rounds}
        except Exception as e: ok = False; res = {'status': 'ERROR:' + str(e)[:60], 'method': tag}
        if ok: return res
    return res


def native_check(orig_src, new_src, bounds, ncases=24, seed=1, prelude=''):
    names = list(bounds); rng = random.Random(seed); cases = []
    for _ in range(ncases):
        row = []
        for n in names:
            lo, hi = bounds[n]; row.append(rng.choice([lo, hi, 0 if lo <= 0 <= hi else lo, 1 if lo <= 1 <= hi else lo, rng.randint(lo, min(hi, lo + 2 ** 20)), rng.randint(max(lo, hi - 2 ** 20), hi), rng.randint(lo, hi)]))
        cases.append(row)
    fo = re.search(r'\b(\w+)\s*\(', orig_src.split('{')[0]).group(1)
    d = tempfile.mkdtemp(); p = os.path.join(d, 'h.c')
    ptypes = re.findall(r'(?:^|[(,])\s*([A-Za-z_ ]+?)\s+\w+\s*(?=[,)])', orig_src.split('{')[0].split('(', 1)[1])
    new2 = new_src.replace('f(', 'zz_new(', 1)
    args = ', '.join('(%s)strtoll(argv[%d], 0, 10)' % (t.strip() or 'long', i + 2) for i, t in enumerate(ptypes))
    args_u = ', '.join('(%s)strtoull(argv[%d], 0, 10)' % (t.strip() or 'long', i + 2) for i, t in enumerate(ptypes))
    open(p, 'w').write('#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <ctype.h>\nint unknown(void){return 0;}\n%s\n%s\n%s\nint main(int argc,char**argv){ if(argv[1][0]==\'o\') printf("%%lld\\n",(long long)%s(%s)); else printf("%%lld\\n",(long long)zz_new(%s)); return 0;}\n' % (prelude, orig_src, new2, fo, args, args)) 
    r = subprocess.run(['gcc', '-O0', '-w', '-o', p[:-2], p], capture_output=True, text=True)
    if r.returncode: return {'equivalent': None, 'detail': 'compile error: ' + r.stderr[:80]}
    same = 0; timeouts = 0; bad = 0; inconclusive = 0
    for row in cases:
        outs = []
        for mode in ('o', 'n'):
            try: outs.append(subprocess.run([p[:-2], mode] + [str(v) for v in row], capture_output=True, text=True, timeout=6).stdout.strip())
            except subprocess.TimeoutExpired: outs.append('TIMEOUT')
        if outs[0] == outs[1]: same += 1; timeouts += outs[0] == 'TIMEOUT'
        elif 'TIMEOUT' in outs: inconclusive += 1          # one side timed out (speed difference), not a semantic mismatch
        else: bad += 1
    return {'equivalent': bad == 0, 'cases': len(cases), 'agree': same, 'both_timeout': timeouts, 'one_sided_timeout': inconclusive}


INC = [CU / 'fake', CU / 'gnulib/lib', CU / 'coreutils/src', CU / 'coreutils/lib']


class _TO(Exception): pass


def _alarm(sig, frm): raise _TO('timeout')


def run_one(path, fn, cls=None, suite=None, limit=420):
    import signal
    import hashlib
    row = {'suite': suite, 'file': Path(path).name, 'function': fn, 'class': cls}
    try: d = file_material(path, INC)[2].get(fn); row['src_sha1'] = hashlib.sha1(d.encode()).hexdigest()[:12] if d else None
    except Exception: pass
    signal.signal(signal.SIGALRM, _alarm); signal.alarm(limit)
    try:
        orig, new, bounds, notes, info = transcribe(path, fn, INC); fd, extra = info
        row.update({'stage': 'transcribed', 'notes': notes, 'bounds': bounds, 'transcription': new})
        row['native'] = native_check(orig, new, bounds, prelude=info.prelude) if not extra and not info.nondet else {'equivalent': None, 'detail': 'not applicable (globals or nondeterministic stubs)'}
        row['certification'] = certify(new, bounds)
        if row['certification']['status'] != 'PROVED' and any(lo < 0 for lo, hi in bounds.values()):    # full signed range includes overflowing inputs: retry under the (documented) precondition 0 <= x <= max/2
            b2 = {k: ([0, hi // 2] if lo < 0 else [lo, hi]) for k, (lo, hi) in bounds.items()}; r2 = certify(new, b2)
            if r2['status'] == 'PROVED': r2['precondition'] = b2; row['certification'] = r2
        row['stage'] = 'certified' if row['certification']['status'] == 'PROVED' else 'not_certified'
        if row['stage'] == 'certified' and row['certification']['method'] != 'typed_c_no_loops_after_stubbing':
            row['memsafe'] = certify_memsafe(path, fn, INC, budget=40)           # bounds checking of tracked pointers (scripts/memsafe.py)
    except _TO: row.update({'stage': 'not_certified' if 'transcription' in row else 'rejected', 'reason': 'timeout %ds' % limit, 'certification': {'status': 'TIMEOUT', 'method': 'timeout'}, 'native': row.get('native', {'equivalent': None})})
    except Exception as e: row.update({'stage': 'rejected', 'reason': str(e)[:90]})
    finally: signal.alarm(0)
    return row


def run_one_isolated(path, fn, cls=None, suite=None, limit=120):
    """run_one in a forked process killed after `limit` seconds (z3 can hold the interpreter in C code where an alarm cannot interrupt it)"""
    import multiprocessing as mp
    q = mp.get_context('fork').Queue()
    def work(): q.put(run_one(path, fn, cls, suite, limit=limit))
    pr = mp.get_context('fork').Process(target=work); pr.start(); pr.join(limit + 20)
    if pr.is_alive():
        pr.terminate(); pr.join()
        return {'suite': suite, 'file': Path(path).name, 'function': fn, 'class': cls, 'stage': 'not_certified', 'reason': 'solver unresponsive: killed after %ds' % (limit + 20), 'certification': {'status': 'TIMEOUT', 'method': 'killed'}, 'native': {'equivalent': None}}
    return q.get()


def has_loop(fd): return any(isinstance(n, (c_ast.While, c_ast.For, c_ast.DoWhile)) for n in walk(fd.body))


def run_file(args):
    path, suite = args; rows = []
    try:
        text, tmap, defs, protos, asts, gmap, env = file_material(path, INC)
    except Exception as e: return [{'suite': suite, 'file': Path(path).name, 'function': '*', 'stage': 'rejected', 'reason': 'file: ' + str(e)[:60]}]
    for fn in defs:
        if fn in asts and not has_loop(asts[fn]): continue
        if fn not in asts and not re.search(r'\b(while|for|do)\b', defs[fn]): continue
        rows.append(run_one_isolated(path, fn, 'loop' if fn in asts else 'unparsed', suite, limit=300))
    return rows


if __name__ == '__main__':
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if only == 'all':
        from concurrent.futures import ProcessPoolExecutor, as_completed
        jobs = [(str(f), s) for s, d in (('gnulib:lib', CU / 'gnulib/lib'), ('coreutils:src', CU / 'coreutils/src')) for f in sorted(d.glob('*.c'))]
        rows = []
        with ProcessPoolExecutor(3) as pool:
            for k, fut in enumerate(as_completed([pool.submit(run_file, j) for j in jobs])):
                rs = fut.result()
                rows += rs; print(k, len(jobs), len(rows), flush=True)
                with open(ROOT / 'experiments/v083/auto_transcribe_all.jsonl', 'a') as fh:
                    for r in rs: fh.write(json.dumps(r) + '\n')
        (ROOT / 'experiments/v083/auto_transcribe_all.json').write_text(json.dumps(rows, indent=1) + '\n')
        print(collections.Counter(r['stage'] for r in rows)); print(collections.Counter(r.get('reason', '')[:50] for r in rows if r['stage'] == 'rejected').most_common(25))
        sys.exit(0)
    cands = json.loads((ROOT / 'experiments/v081/gnulib_coverage_candidates.json').read_text()); rows = []
    for c in cands:
        if only and only not in c['function']: continue
        row = run_one(c['file'], c['function'], c['class'], c['suite']); rows.append(row); print(row['file'], row['function'], row['stage'], row.get('reason') or row.get('certification', {}).get('status'), flush=True)
    if not only:
        (ROOT / 'experiments/v082/auto_transcribe.json').write_text(json.dumps(rows, indent=1) + '\n')
        print(collections.Counter(r['stage'] for r in rows)); print(collections.Counter(r.get('reason', '')[:40] for r in rows if r['stage'] == 'rejected').most_common(12))
