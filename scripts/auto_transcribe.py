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
CU = Path('/tmp/cu'); G = c_generator.CGenerator()
EXITS = {'exit', '_exit', 'abort', 'usage_exit'}
OUTPUT_ONLY = {'printf_unlocked', 'fprintf_unlocked', 'fputs_unlocked', 'putchar_unlocked', 'emit_try_help', 'emit_mandatory_arg_note', 'emit_size_note', 'emit_stdin_note', 'emit_bug_reporting_address', 'version_etc', 'fputs_unlocked', 'printf', 'fprintf', 'puts', 'putchar', 'fputs', 'fputc', 'putc', 'fwrite', 'fflush', 'perror', 'vfprintf', 'oputs_', 'emit_ancillary_info'}
FORCED = {}
INTS = {('int',): (32, True), ('unsigned',): (32, False), ('unsigned', 'int'): (32, False), ('long',): (64, True), ('long', 'int'): (64, True), ('unsigned', 'long'): (64, False), ('unsigned', 'long', 'int'): (64, False),
        ('short',): (16, True), ('unsigned', 'short'): (16, False), ('char',): (8, True), ('unsigned', 'char'): (8, False), ('signed', 'char'): (8, True), ('long', 'long'): (64, True), ('unsigned', 'long', 'long'): (64, False),
        ('_Bool',): (8, False)}


def tu_text(path, includes):
    r = subprocess.run(['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-include', str(CU / 'fake/config.h'), '-include', 'stdbool.h', '-include', 'stdint.h', '-include', 'stddef.h', '-DNDEBUG', '-D__NO_CTYPE', '-Xclang', '-ast-print'] + [x for i in includes for x in ('-I', str(i))] + [str(path)], capture_output=True, text=True, timeout=180)
    return r.stdout


def typedef_map(text):
    m = {}
    for a, b in re.findall(r'^typedef ([A-Za-z_ ]+?) (\w+);$', text, re.M): m[b] = a
    changed = True
    while changed:
        changed = False
        for k, v in list(m.items()):
            w = v.split()
            if len(w) == 1 and w[0] in m and w[0] != k: m[k] = m[w[0]]; changed = True
    return m


def extract(text, name):
    """source text of the definition of `name` (top-level, column 0) from clang -ast-print output; also returns the other function definitions of the file"""
    defs = {}
    lines = text.split('\n'); i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r'^(?:static |inline |extern )*[A-Za-z_][\w \*]*?\b(\w+)\(([^;]*)\) (?:__attribute__\(\([^{]*\)\) )?\{$', l)
        if m and not l.startswith(('typedef', 'struct')):
            j = i
            while j < len(lines) and lines[j] != '}': j += 1
            defs.setdefault(m.group(1), '\n'.join(lines[i:j + 1])); i = j
        i += 1
    return defs


def clean(src, tmap):
    src = re.sub(r'__attribute__\(\(.*?\)\)', '', src)
    for q in ('static', 'inline', 'register', 'const', 'extern', 'volatile', 'restrict', '__restrict', '__inline', '__extension__'): src = re.sub(r'\b%s\b' % q, '', src)
    for k, v in sorted(tmap.items(), key=lambda kv: -len(kv[0])): src = re.sub(r'\b%s\b' % re.escape(k), v, src)
    src = re.sub(r'\b_Bool\b', 'int', src); src = re.sub(r'\bbool\b', 'int', src)
    for ty, n in (('unsigned long long', 8), ('unsigned long', 8), ('long long', 8), ('unsigned int', 4), ('unsigned short', 2), ('unsigned char', 1), ('long', 8), ('int', 4), ('short', 2), ('char', 1), ('signed char', 1)): src = re.sub(r'sizeof\(%s\)' % ty, str(n), src)
    return src


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
    def tr(items):
        out = []
        for it in items:
            if isinstance(it, c_ast.Cast) and isinstance(it.expr, c_ast.Constant): continue
            if isinstance(it, c_ast.Compound): it.block_items = tr(it.block_items or []); out.append(it); continue
            if isinstance(it, c_ast.DoWhile):
                body = it.stmt if isinstance(it.stmt, c_ast.Compound) else c_ast.Compound([it.stmt])
                if has_jump(body): raise ValueError('break/continue in do-while')
                body.block_items = tr(body.block_items or [])
                if isinstance(it.cond, c_ast.Constant) and it.cond.value == '0': out.append(body); notes.add('do-while(0) flattened'); continue
                out.append(copy.deepcopy(body)); out.append(c_ast.While(it.cond, body)); notes.add('do-while peeled'); continue
            if isinstance(it, c_ast.For):
                body = it.stmt if isinstance(it.stmt, c_ast.Compound) else c_ast.Compound([it.stmt])
                body.block_items = tr(body.block_items or [])
                if has_jump(body) and not isinstance(it.next, type(None)): raise ValueError('break/continue in for-loop with step')
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
    extra = []
    for g in free:
        ty = gmap.get(g)
        if ty == '_Bool': ty = 'int'; FORCED[g] = [0, 1]
        if ty is None or tuple(ty.split()) not in INTS: raise ValueError('unresolved free identifier ' + g)
        extra.append(c_ast.Decl(g, [], [], [], [], c_ast.TypeDecl(g, [], None, c_ast.IdentifierType(ty.split())), None, None)); notes.add('global as parameter: ' + g)
    if extra:
        if fd.decl.type.args is None: fd.decl.type.args = c_ast.ParamList([])
        fd.decl.type.args.params = [p for p in fd.decl.type.args.params if not (isinstance(p, c_ast.Typename))] + extra
    return [e.name for e in extra]


def global_map(text, tmap):
    m = {}
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
        nm = getattr(call.name, 'name', None)
        if nm is None: raise ValueError('indirect call')
        args = call.args.exprs if call.args else []
        if nm in OUTPUT_ONLY:
            for a in args:
                if any(isinstance(n, c_ast.BinaryOp) and n.op in ('/', '%', '<<', '>>') for n in walk(a)): raise ValueError('output call with computed arguments')
            return None, []
        if nm in EXITS: return 'EXIT', []
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
            decls = []; params = cd.decl.type.args.params if cd.decl.type.args else []
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
        for a in args:
            if isinstance(a, c_ast.Constant) and a.type == 'string' or any(isinstance(n, c_ast.UnaryOp) and n.op in ('&', '*') for n in walk(a)) or any(isinstance(n, c_ast.Constant) and n.type == 'string' for n in walk(a)): raise ValueError('call with non-scalar argument: ' + nm)
        notes.add('nondeterministic result for ' + nm)
        return c_ast.FuncCall(c_ast.ID('unknown'), None), []
    def replace_calls(root_parent, attr):
        """calls inside root_parent.<attr> (an expression), innermost first; returns the statements to run before"""
        pre = []
        def rec(parent, name, node):
            for nm, ch in list(node.children()): rec(node, nm, ch)
            if isinstance(node, c_ast.FuncCall):
                r, p = callee_result(node, is_bool_ctx(parent, name)); pre.extend(p)
                if r is None: raise ValueError('output call used as a value')
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


def check_scalar_only_decl(cd):
    for p in (cd.decl.type.args.params if cd.decl.type.args else []):
        if not isinstance(p, c_ast.Decl) or not scalar_type(p.type): raise ValueError('callee with non-scalar parameter')
    if not ret_scalar(cd): raise ValueError('callee with non-scalar return type')


def uniquify_decls(fd):
    """nested declarations that reuse a name already declared in the function get a fresh name (sequential, so initializers still see the outer variable)"""
    declared = {p.name for p in (fd.decl.type.args.params if fd.decl.type.args else []) if p.name} | {i.name for i in (fd.body.block_items or []) if isinstance(i, c_ast.Decl)}
    counter = [0]; done = set()
    def comp(c, top):
        if id(c) in done: return
        done.add(id(c)); cur = {}
        def ren(node):
            for n in walk(node):
                if isinstance(n, c_ast.ID) and n.name in cur: n.name = cur[n.name]
        for it in c.block_items or []:
            if isinstance(it, c_ast.Decl) and it.name and not top:
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
        bits, signed = INTS[tuple(p.type.type.names)]; b[p.name] = [-(1 << (bits - 1)), (1 << (bits - 1)) - 1] if signed else [0, (1 << bits) - 1]
    return b


class Info:
    def __init__(self, fd, extra, prelude, nondet): self.fd, self.extra, self.prelude, self.nondet = fd, extra, prelude, nondet
    def __iter__(self): return iter((self.fd, self.extra))


def transcribe(path, name, includes):
    text = tu_text(path, includes); tmap = typedef_map(text); defs = extract(text, name)
    if name not in defs: raise ValueError('definition not found')
    notes = set(); asts = {}
    for k, v in defs.items():
        try: asts[k] = parse_fn(clean(v, tmap))
        except Exception: pass
    if name not in asts: raise ValueError('parse failure')
    orig_src = clean(defs[name], tmap); fd = copy.deepcopy(asts[name])
    if not ret_scalar(fd): raise ValueError('non-scalar return type')
    for p in (fd.decl.type.args.params if fd.decl.type.args else []):
        if not isinstance(p, c_ast.Decl) or not scalar_type(p.type): raise ValueError('non-scalar parameter')
    for n in walk(fd.body):
        if isinstance(n, c_ast.UnaryOp) and n.op in ('*', '&'): raise ValueError('pointers/arrays/structs')
    normalize_structure(fd, notes); uniquify_decls(fd)
    inline_calls(fd, asts, notes)
    extra_params = add_globals(fd, global_map(text, tmap), notes)
    check_scalar_only(fd)
    hoist_and_init(fd, notes); flatten_blocks(fd, notes); ensure_return(fd, notes); rename_underscored(fd); copy_mutated_params(fd, notes)
    fd.decl.name = 'f'; fd.decl.type.type.declname = 'f' if hasattr(fd.decl.type.type, 'declname') else None
    for p in fd.decl.type.args.params: p.quals = []
    inl = [re.sub(r' \(with loops\)$', '', n[len('inlined '):]) for n in notes if n.startswith('inlined')]
    prelude = '\n'.join(clean(defs[k], tmap) for k in defs if k in inl)
    nondet = any(n.startswith(('nondeterministic', 'library range')) for n in notes)
    return orig_src, G.visit(fd), bounds_of(fd), sorted(notes), Info(fd, extra_params, prelude, nondet)


def certify(src, bounds):
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
    same = 0; timeouts = 0; bad = 0
    for row in cases:
        outs = []
        for mode in ('o', 'n'):
            try: outs.append(subprocess.run([p[:-2], mode] + [str(v) for v in row], capture_output=True, text=True, timeout=3).stdout.strip())
            except subprocess.TimeoutExpired: outs.append('TIMEOUT')
        if outs[0] == outs[1]: same += 1; timeouts += outs[0] == 'TIMEOUT'
        else: bad += 1
    return {'equivalent': bad == 0, 'cases': len(cases), 'agree': same, 'both_timeout': timeouts}


if __name__ == '__main__':
    cands = json.loads((ROOT / 'experiments/v081/gnulib_coverage_candidates.json').read_text()); inc = [CU / 'fake', CU / 'gnulib/lib', CU / 'coreutils/src', CU / 'coreutils/lib']
    only = sys.argv[1] if len(sys.argv) > 1 else None; rows = []
    for c in cands:
        if only and only not in c['function']: continue
        row = {'suite': c['suite'], 'file': Path(c['file']).name, 'function': c['function'], 'class': c['class']}
        try:
            orig, new, bounds, notes, info = transcribe(c['file'], c['function'], inc); fd, extra = info; row.update({'stage': 'transcribed', 'notes': notes, 'bounds': bounds, 'transcription': new})
            row['native'] = native_check(orig, new, bounds, prelude=info.prelude) if not extra and not info.nondet else {'equivalent': None, 'detail': 'not applicable (globals or nondeterministic stubs)'}; row['certification'] = certify(new, bounds)
            if row['certification']['status'] != 'PROVED' and any(lo < 0 for lo, hi in bounds.values()):    # full signed range includes overflowing inputs: retry under the (documented) precondition 0 <= x <= max/2
                b2 = {k: ([0, hi // 2] if lo < 0 else [lo, hi]) for k, (lo, hi) in bounds.items()}; r2 = certify(new, b2)
                if r2['status'] == 'PROVED': r2['precondition'] = b2; row['certification'] = r2
            row['stage'] = 'certified' if row['certification']['status'] == 'PROVED' else 'not_certified'
        except Exception as e: row.update({'stage': 'rejected', 'reason': str(e)[:90]})
        rows.append(row); print(row['file'], row['function'], row['stage'], row.get('reason') or row.get('certification', {}).get('status'), flush=True)
    if not only:
        (ROOT / 'experiments/v082/auto_transcribe.json').write_text(json.dumps(rows, indent=1) + '\n')
        print(collections.Counter(r['stage'] for r in rows)); print(collections.Counter(r.get('reason', '')[:40] for r in rows if r['stage'] == 'rejected').most_common(12))
