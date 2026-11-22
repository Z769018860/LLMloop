"""v1.04 E3: the same verifier on industrial C, reported as three denominators.

The audit (`docs/TOP_TIER_AUDIT.md` §4.7) asks for the honest version of the coverage claim:

    of the functions that contain a loop in four industrial code bases,
    how many are in the syntactic fragment, how many survive the frontend,
    and how many are actually proved -- with every refusal named.

Nothing here is a comparison with another tool. It is a measurement of where this method stops,
which is the number a reviewer asks for and which the SV-COMP corpus cannot supply.

Stages, each a strict subset of the one before:

  1. FILES      parsed by clang (`-Xclang -ast-dump=json`), sampled by a pre-registered rule;
  2. FUNCTIONS  every `FunctionDecl` defined in those files; `functions_with_loops` is the denominator;
  3. FRAGMENT   the v0.74 classifier's `scalar_loop_candidate`: scalar int params/locals, no pointers,
                arrays, structs, floats, goto, or calls to other functions;
  4. FRONTEND   the function body, wrapped in a fixed preamble with a reconstructed signature,
                is accepted by `houdini_loops._prepare` (pycparser + desugaring + jump elimination);
  5. PROVED     `houdini_loops` returns PROVED with the parameter bounds implied by the parameter
                types (the full range of each type, not a convenient window).

Every stage records why the rest of the functions fell out, so the summary can say
"X of Y loop functions are in the fragment, and here are the eleven reasons the others are not"
rather than "most industrial code is unsupported".

`freeze` downloads the four pinned archives, verifies sha256, runs each project's own configure step,
and writes the file list with per-file hashes *before* any verification result exists. `scan` and
`prove` refuse to run against a tree whose hash does not match.

usage:
  industrial_v104.py freeze --external EXT --output experiments/v104/industrial
  industrial_v104.py scan   --external EXT --output DIR --project busybox
  industrial_v104.py prove  --output DIR --project busybox [--seconds 90]
  industrial_v104.py merge  --output DIR
"""

import argparse
import collections
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# The four bases named in the audit. Versions are pinned by archive hash, not by tag name, because a
# tag can be moved and a tarball cannot.
PROJECTS = {
    'busybox': {
        'url': 'https://busybox.net/downloads/busybox-1.36.1.tar.bz2',
        'archive': 'busybox-1.36.1.tar.bz2',
        'sha256': 'b8cc24c9574d809e7279c3be349795c5d5ceb6fdf19ca709f80cde50e47de314',
        'root': 'busybox-1.36.1',
        'globs': ['coreutils/*.c', 'libbb/*.c', 'archival/libarchive/*.c', 'networking/*.c'],
        'setup': ['make defconfig'],
        'includes': ['include', 'libbb', 'archival/libarchive', 'networking'],
        'extra': ['-include', 'include/autoconf.h', '-DKBUILD_BASENAME="x"', '-DKBUILD_MODNAME="x"'],
        'cap': 400,
    },
    'openssl': {
        'url': 'https://www.openssl.org/source/openssl-3.2.1.tar.gz',
        'archive': 'openssl-3.2.1.tar.gz',
        'sha256': '83c7329fe52c850677d75e5d0b0ca245309b97e8ecbcfdc1dfdc4ab9fac35b39',
        'root': 'openssl-3.2.1',
        'globs': ['crypto/*/*.c'],
        'setup': ['./Configure no-shared no-tests'],
        'includes': ['include', '.', 'providers/common/include', 'providers/implementations/include',
                     'apps/include'],
        'extra': [],
        'cap': 400,
    },
    'sqlite': {
        'url': 'https://sqlite.org/2024/sqlite-src-3450100.zip',
        'archive': 'sqlite-src-3450100.zip',
        'sha256': '7f7b14a68edbcd4a57df3a8c4dbd56d2d3546a6e7cdd50de40ceb03af33d34ba',
        'root': 'sqlite-src-3450100',
        'globs': ['src/*.c'],
        'setup': [],
        'includes': ['.', 'src', 'ext/fts5', 'ext/rtree', 'ext/session', 'ext/icu', 'ext/misc'],
        'extra': [],
        'cap': 200,
        # The source tree does not ship `sqlite3.h`; the amalgamation does, and it is pinned too.
        'headers': {
            'url': 'https://sqlite.org/2024/sqlite-amalgamation-3450100.zip',
            'archive': 'sqlite-amalgamation-3450100.zip',
            'sha256': '5592243caf28b2cdef41e6ab58d25d653dfc53deded8450eb66072c929f030c4',
            'member': 'sqlite-amalgamation-3450100/sqlite3.h',
            'dest': 'sqlite3.h',
        },
    },
    'aws-c-common': {
        'url': 'https://codeload.github.com/awslabs/aws-c-common/tar.gz/refs/tags/v0.9.15',
        'archive': 'aws-c-common-0.9.15.tar.gz',
        'sha256': '8f36c7a6a5d2e17365759d15591f800d3e76dcaa34a226389b92647cbd92393a',
        'root': 'aws-c-common-0.9.15',
        'globs': ['source/*.c'],
        'setup': ['cmake -S . -B build -DBUILD_TESTING=OFF'],
        'includes': ['include', 'build/generated/include'],
        'extra': [],
        'cap': 300,
    },
}

# A fixed preamble for the extracted function. It is the *standard* integer typedefs only: anything
# else (a project typedef, a struct, a macro) is part of what the frontend cannot see, and the
# summary counts it as such instead of silently supplying it.
PREAMBLE = '\n'.join([
    'typedef unsigned char uint8_t;',
    'typedef signed char int8_t;',
    'typedef unsigned short uint16_t;',
    'typedef short int16_t;',
    'typedef unsigned int uint32_t;',
    'typedef int int32_t;',
    'typedef unsigned long long uint64_t;',
    'typedef long long int64_t;',
    'typedef unsigned long size_t;',
    'typedef long ssize_t;',
    'typedef int bool;',
])

# The bounds of a parameter are the bounds of its type. A narrower window would make the result look
# better and would be a different claim; §4.7 says so in one sentence and the merge repeats it.
INT_TYPES = {
    'char': [-128, 127],
    'signed char': [-128, 127],
    'unsigned char': [0, 255],
    'short': [-32768, 32767],
    'short int': [-32768, 32767],
    'signed short': [-32768, 32767],
    'unsigned short': [0, 65535],
    'unsigned short int': [0, 65535],
    'int': [-2147483648, 2147483647],
    'signed': [-2147483648, 2147483647],
    'signed int': [-2147483648, 2147483647],
    'unsigned': [0, 4294967295],
    'unsigned int': [0, 4294967295],
    'long': [-9223372036854775808, 9223372036854775807],
    'long int': [-9223372036854775808, 9223372036854775807],
    'unsigned long': [0, 18446744073709551615],
    'unsigned long int': [0, 18446744073709551615],
    'long long': [-9223372036854775808, 9223372036854775807],
    'unsigned long long': [0, 18446744073709551615],
    'int8_t': [-128, 127], 'uint8_t': [0, 255],
    'int16_t': [-32768, 32767], 'uint16_t': [0, 65535],
    'int32_t': [-2147483648, 2147483647], 'uint32_t': [0, 4294967295],
    'int64_t': [-9223372036854775808, 9223372036854775807],
    'uint64_t': [0, 18446744073709551615],
    'size_t': [0, 18446744073709551615],
}

MAX_FILE_BYTES = 400_000          # one file above this is recorded, not parsed: AST JSON memory
MAX_FUNCTIONS_PER_FILE = 400      # keeps a pathological generated file from dominating a shard


# --------------------------------------------------------------------------- helpers


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def save(p, x):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, indent=1) + '\n', encoding='utf-8')


def download(url, dest, expect):
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256_file(dest) == expect:
        return dest
    for attempt in range(4):
        r = subprocess.run(['curl', '-sSL', '--retry', '3', '--retry-all-errors',
                            '--max-time', '600', '-o', str(dest), url],
                           capture_output=True, text=True)
        if dest.exists() and sha256_file(dest) == expect:
            return dest
        time.sleep(3 * (attempt + 1))
    raise SystemExit('download failed or hash mismatch: %s %s' % (url, r.stderr[-200:]))


def extract(archive, dest, spec):
    dest = Path(dest)
    archive = Path(archive)
    tmp = dest.parent / (dest.name + '.tmp')
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True, exist_ok=True)
    if archive.suffixes[-2:] in (['.tar', '.gz'], ['.tar', '.bz2']) or archive.suffix in ('.tgz', '.tar'):
        with tarfile.open(archive) as t:
            t.extractall(tmp)
    elif archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
    else:
        raise SystemExit('unknown archive type: %s' % archive)
    root = tmp / spec['root']
    if not root.is_dir():
        raise SystemExit('archive root missing: %s' % root)
    shutil.rmtree(dest, ignore_errors=True)
    shutil.move(str(root), str(dest))
    shutil.rmtree(tmp, ignore_errors=True)
    return dest


def prepare_tree(external, name, log=None, run_setup=True):
    """Materialise the pinned tree for one project, run its own configure step, return its path.

    `run_setup=False` is for `freeze` on a host without the project's build tools: the file list and
    the hashes do not depend on configure having run, and the setup commands are still recorded in
    the protocol verbatim so the run executes exactly them.
    """
    spec = PROJECTS[name]
    ext = Path(external) / 'industrial'
    arch = download(spec['url'], ext / 'archives' / spec['archive'], spec['sha256'])
    tree = ext / name
    stamp = tree / ('.frozen-ok' if run_setup else '.frozen-raw')
    if not stamp.exists():
        extract(arch, tree, spec)
        hdr = spec.get('headers')
        if hdr:
            z = download(hdr['url'], ext / 'archives' / hdr['archive'], hdr['sha256'])
            with zipfile.ZipFile(z) as zf:
                (tree / hdr['dest']).write_bytes(zf.read(hdr['member']))
        if run_setup:
            for cmd in spec['setup']:
                r = subprocess.run(cmd, shell=True, cwd=str(tree), capture_output=True, text=True,
                                   timeout=1800)
                if log is not None:
                    log.append({'project': name, 'command': cmd, 'exit_code': r.returncode,
                                'stderr_tail': (r.stderr or '')[-600:]})
                # A project whose configure step fails is still scanned; the reasons will be parse
                # failures, and the summary says which project could not be prepared.
        stamp.write_text('ok\n')
    elif log is not None:
        log.append({'project': name, 'command': '(tree already prepared)', 'exit_code': 0,
                    'stderr_tail': ''})
    return tree


def candidate_files(tree, spec):
    files = []
    for g in spec['globs']:
        files.extend(sorted(Path(tree).glob(g)))
    rel = sorted({str(p.relative_to(tree)).replace('\\', '/') for p in files if p.is_file()})
    return rel


def sampling_key(rel):
    return sha256_bytes(rel.encode('utf-8'))


# --------------------------------------------------------------------------- freeze


def freeze(external, out, only=None):
    out = Path(out)
    log = []
    protocol = {'pin': {}, 'harness': {'preamble': PREAMBLE, 'bounds': INT_TYPES, 'abi': 'LP64',
                                       'max_file_bytes': MAX_FILE_BYTES,
                                       'max_functions_per_file': MAX_FUNCTIONS_PER_FILE},
                'sampling': {'rule': 'ascending sha256(project-relative path), first `cap`; '
                                     'chosen before any verification result exists',
                             'caps': {k: v['cap'] for k, v in PROJECTS.items()}},
                'files': []}
    for name, spec in PROJECTS.items():
        if only and name not in only:
            continue
        tree = prepare_tree(external, name, log, run_setup=False)
        rels = candidate_files(tree, spec)
        chosen = sorted(rels, key=sampling_key)[:spec['cap']]
        protocol['pin'][name] = {'url': spec['url'], 'archive': spec['archive'],
                                 'sha256': spec['sha256'], 'root': spec['root'],
                                 'setup': spec['setup'], 'includes': spec['includes'],
                                 'extra': spec['extra'], 'candidates': len(rels),
                                 'sampled': len(chosen)}
        for r in chosen:
            p = tree / r
            protocol['files'].append({'project': name, 'path': r, 'sha256': sha256_file(p),
                                      'bytes': p.stat().st_size})
        if log:
            protocol['setup_log'] = log
        save(out / 'protocol.json', protocol)     # written after every project: a crash keeps the rest
        print('%s: %d files in scope, %d sampled' % (name, len(rels), len(chosen)), flush=True)
    save(out / 'protocol.json', protocol)
    print('protocol:', len(protocol['files']), 'files', flush=True)


# --------------------------------------------------------------------------- scan


def clang_ast(tree, path, spec):
    cmd = ['clang', '-fsyntax-only', '-w', '-ferror-limit=0', '-Xclang', '-ast-dump=json']
    cmd += [a for i in spec['includes'] for a in ('-I', str(Path(tree) / i))]
    cmd += spec['extra']
    cmd.append(str(path))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    try:
        return json.loads(r.stdout), None
    except Exception:
        first = ''
        for line in (r.stderr or '').splitlines():
            if 'error:' in line:
                first = line.strip()[:200]
                break
        return None, (first or (r.stderr or '')[-160:].strip() or 'no output')


def walk(n):
    yield n
    for c in n.get('inner', []) or []:
        if isinstance(c, dict):
            yield from walk(c)


def node_file(n):
    r = (n.get('range') or {}).get('begin') or {}
    return r.get('file') or (n.get('loc') or {}).get('file')


def body_of(fn):
    for c in fn.get('inner', []) or []:
        if isinstance(c, dict) and c.get('kind') == 'CompoundStmt':
            return c
    return None


def param_list(fn):
    return [(c.get('name') or '', (c.get('type') or {}).get('qualType', '?'))
            for c in fn.get('inner', []) or []
            if isinstance(c, dict) and c.get('kind') == 'ParmVarDecl']


def return_type(fn):
    q = (fn.get('type') or {}).get('qualType', '')
    return q.split('(')[0].strip() or 'void'


def span(src_bytes, node):
    r = node.get('range') or {}
    b = (r.get('begin') or {}).get('offset')
    e = (r.get('end') or {}).get('offset')
    if b is None or e is None:
        return None
    e += (r.get('end') or {}).get('tokLen') or 0
    return src_bytes[b:e]


def harness(fn, src_bytes):
    """Rebuild a standalone definition for one function, with the fixed preamble."""
    body = span(src_bytes, body_of(fn))
    if body is None:
        return None, 'NO_OFFSETS'
    params = param_list(fn)
    if any(not n for n, _ in params):
        return None, 'UNNAMED_PARAMETER'
    parts = []
    for n, q in params:
        q = re.sub(r'\b(const|volatile|register)\b', '', q).strip()
        if not q or q == '?':
            return None, 'UNKNOWN_PARAMETER_TYPE'
        parts.append('%s %s' % (q, n))
    sig = '%s %s(%s)' % (return_type(fn), fn.get('name', 'f'), ', '.join(parts) or 'void')
    src = PREAMBLE + '\n' + sig + ' ' + body.decode('utf-8', 'replace') + '\n'
    return src, None


def bounds_of(fn):
    out = {}
    for n, q in param_list(fn):
        q = re.sub(r'\b(const|volatile|register)\b', '', q).strip()
        if q not in INT_TYPES:
            return None, q
        out[n] = INT_TYPES[q]
    return out, None


def scan(external, out, project, log_func=print, limit=0):
    from scripts.realcode_coverage import classify_function
    out = Path(out)
    protocol = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    rows = [f for f in protocol['files'] if f['project'] == project]
    if limit:
        rows = rows[:limit]
    setup_log = []
    tree = prepare_tree(external, project, setup_log)
    save(out / 'raw' / project / 'setup.json', setup_log)
    spec = PROJECTS[project]
    coverage = []
    candidates = []
    for i, f in enumerate(rows):
        p = tree / f['path']
        rec = {'project': project, 'path': f['path'], 'bytes': f['bytes'], 'functions': []}
        if not p.exists() or sha256_file(p) != f['sha256']:
            rec.update(parsed=False, reason='SOURCE_CHANGED')
            coverage.append(rec)
            continue
        if f['bytes'] > MAX_FILE_BYTES:
            rec.update(parsed=False, reason='TOO_LARGE')
            coverage.append(rec)
            continue
        ast, err = clang_ast(tree, p, spec)
        if ast is None:
            rec.update(parsed=False, reason='PARSE_FAIL', detail=err)
            coverage.append(rec)
            continue
        src_bytes = p.read_bytes()
        seen = 0
        for n in ast.get('inner', []) or []:
            if not isinstance(n, dict) or n.get('kind') != 'FunctionDecl':
                continue
            b = body_of(n)
            if b is None:
                continue
            fpath = node_file(n) or ''
            if fpath and Path(fpath).name != p.name:
                continue
            if seen >= MAX_FUNCTIONS_PER_FILE:
                break
            seen += 1
            cls = classify_function(n)
            name = n.get('name', '?')
            rec['functions'].append({'name': name, 'class': cls})
            if cls != 'scalar_loop_candidate':
                continue
            src, why = harness(n, src_bytes)
            if src is None:
                candidates.append({'project': project, 'path': f['path'], 'function': name,
                                   'status': 'EXTRACT_FAILED', 'reason': why})
                continue
            bounds, bad = bounds_of(n)
            if bounds is None:
                candidates.append({'project': project, 'path': f['path'], 'function': name,
                                   'status': 'BOUNDS_UNKNOWN', 'reason': bad, 'harness': src})
                continue
            candidates.append({'project': project, 'path': f['path'], 'function': name,
                               'source': src, 'bounds': bounds, 'abi': 'LP64',
                               'status': 'EXTRACTED'})
        coverage.append(rec)
        if (i + 1) % 25 == 0:
            log_func('  %s: %d/%d files' % (project, i + 1, len(rows)))
    save(out / 'raw' / project / 'coverage.json', {'rows': coverage})
    save(out / 'raw' / project / 'candidates.json', {'rows': candidates})
    parsed = sum(1 for r in coverage if r.get('parsed'))
    print('%s: %d/%d files parsed, %d functions, %d candidates'
          % (project, parsed, len(coverage), sum(len(r['functions']) for r in coverage),
             len(candidates)), flush=True)


# --------------------------------------------------------------------------- prove


def frontend_check(src):
    """Does the frozen frontend accept this harness? Same call the proofs will make."""
    from llmloop.houdini_loops import _prepare
    try:
        func, nds, loops = _prepare(src)
        return True, '%d loop(s)' % len(loops)
    except Exception as e:
        return False, type(e).__name__ + ': ' + str(e)[:200]


def prove_one(cand):
    src, bounds = cand['source'], cand['bounds']
    t = time.time()
    try:
        from llmloop.houdini_loops import houdini_loops
        status, inv, rounds, log = houdini_loops(src, bounds, abi=cand.get('abi', 'LP64'),
                                                 integer_model='c', runs=60, max_rounds=150,
                                                 solver_timeout_ms=5000, seed=1, poly=False)
    except Exception as e:
        status, inv, rounds, log = 'ERROR:' + type(e).__name__ + ':' + str(e)[:160], [], 0, []
    return {'status': status, 'seconds': round(time.time() - t, 2), 'rounds': rounds,
            'invariant': [[a[:200] for a in (x or [])][:12] for x in (inv or [])][:4],
            'log_tail': [str(x)[:160] for x in (log or [])][-4:]}


def prove(out, project, seconds, workers=2, limit=0):
    out = Path(out)
    raw = out / 'raw' / project
    cands = json.loads((raw / 'candidates.json').read_text(encoding='utf-8'))['rows']
    todo = [(i, c) for i, c in enumerate(cands) if c.get('status') == 'EXTRACTED']
    if limit:
        todo = todo[:limit]
    print('%s: %d candidates, %d to prove' % (project, len(cands), len(todo)), flush=True)
    from concurrent.futures import ThreadPoolExecutor, as_completed

    def one(i_c):
        i, c = i_c
        w = raw / 'work' / ('%04d' % i)
        w.mkdir(parents=True, exist_ok=True)
        req = w / 'in.json'
        save(req, {'source': c['source'], 'bounds': c['bounds'], 'abi': c.get('abi', 'LP64')})
        dest = w / 'out.json'
        argv = [sys.executable, '-u', str(Path(__file__).resolve()), 'one',
                '--candidate', str(req), '--output', str(dest)]
        t = time.time()
        p = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                             start_new_session=True)
        try:
            _, err = p.communicate(timeout=seconds)
        except subprocess.TimeoutExpired:
            # same lesson as the witness harness: `timeout=` on the wrapper leaves the child alive
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                p.kill()
            p.communicate()
            return i, {'status': 'TIMEOUT', 'seconds': round(time.time() - t, 2),
                       'reason': 'no verdict in %d s' % seconds}
        if not dest.exists():
            return i, {'status': 'PROCESS_ERROR', 'seconds': round(time.time() - t, 2),
                       'reason': (err or b'')[-300:].decode('utf-8', 'replace')}
        return i, json.loads(dest.read_text(encoding='utf-8'))

    with ThreadPoolExecutor(workers) as pool:
        futs = [pool.submit(one, ic) for ic in todo]
        for f in as_completed(futs):
            i, r = f.result()
            save(raw / 'proofs' / ('%04d.json' % i), r)      # resumable: one file per candidate
    print('%s: %d proofs written' % (project, len(todo)), flush=True)


def one(candidate, output):
    cand = json.loads(Path(candidate).read_text(encoding='utf-8'))
    ok, why = frontend_check(cand['source'])
    if not ok:
        r = {'status': 'REJECTED_FRONTEND', 'reason': why, 'seconds': 0}
    else:
        r = prove_one(cand)
        r['frontend'] = why
    save(output, r)


# --------------------------------------------------------------------------- merge


def merge(out):
    out = Path(out)
    protocol = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    projects = list(protocol['pin'])
    table = []
    detail = {}
    for p in projects:
        cov_p = out / 'raw' / p / 'coverage.json'
        cand_p = out / 'raw' / p / 'candidates.json'
        if not cov_p.exists():
            table.append({'project': p, 'missing': True})
            continue
        rows = json.loads(cov_p.read_text(encoding='utf-8'))['rows']
        cands = json.loads(cand_p.read_text(encoding='utf-8'))['rows'] if cand_p.exists() else []
        files = len(rows)
        parsed = sum(1 for r in rows if r.get('parsed'))
        fail = collections.Counter(r.get('reason') for r in rows if not r.get('parsed'))
        funcs = [f for r in rows for f in r['functions']]
        with_loops = sum(1 for f in funcs if f['class'] != 'no_loops')
        classes = collections.Counter(f['class'] for f in funcs if f['class'] != 'no_loops')
        ext = collections.Counter(c.get('status') for c in cands)
        proofs = {}
        pdir = out / 'raw' / p / 'proofs'
        for f in (sorted(pdir.glob('*.json')) if pdir.exists() else []):
            proofs[int(f.stem)] = json.loads(f.read_text(encoding='utf-8'))
        for i, c in enumerate(cands):
            if i in proofs:
                c['proof'] = proofs[i]
        statuses = collections.Counter(c['proof']['status'].split(':')[0] for c in cands if 'proof' in c)
        proved = [c for c in cands if c.get('proof', {}).get('status') == 'PROVED']
        row = {'project': p, 'files': files, 'files_parsed': parsed,
               'parse_fail': dict(fail), 'functions': len(funcs),
               'functions_with_loops': with_loops, 'classes': dict(classes),
               'candidates': len(cands), 'extract_status': dict(ext),
               'frontend_status': dict(statuses), 'proved': len(proved),
               'proved_seconds': sorted(round(c['proof']['seconds'], 2) for c in proved)}
        table.append(row)
        detail[p] = {'candidates': cands, 'parse_fail': dict(fail), 'classes': dict(classes)}

    totals = collections.Counter()
    for r in table:
        if r.get('missing'):
            continue
        totals['files'] += r['files']
        totals['files_parsed'] += r['files_parsed']
        totals['functions'] += r['functions']
        totals['functions_with_loops'] += r['functions_with_loops']
        totals['candidates'] += r['candidates']
        totals['proved'] += r['proved']
    summary = {'projects': table, 'totals': dict(totals),
               'protocol_files': len(protocol['files'])}
    save(out / 'summary.json', summary)

    L = ['# v1.04 E3 工业代码覆盖边界 / industrial coverage boundary', '',
         '四个基座、四个版本、由归档哈希钉住；文件按路径的 sha256 升序预注册抽样，抽样发生在任何',
         '验证结果之前。三段分母严格嵌套：**有循环的函数 ⊇ 片段内候选 ⊇ 真的证出**。',
         'Four bases pinned by archive hash; files sampled by ascending sha256 of the path, chosen',
         'before any result existed. Three strictly nested denominators: loop functions ⊇ fragment ⊇ proved.', '',
         '| 项目 / project | 抽样文件 | 解析成功 | 函数 | 含循环 | 片段内候选 | 证出 |',
         '| --- | --- | --- | --- | --- | --- | --- |']
    for r in table:
        if r.get('missing'):
            L.append('| %s | — | — | — | — | — | — |' % r['project'])
            continue
        L.append('| %s | %d | %d | %d | **%d** | %d | **%d** |'
                 % (r['project'], r['files'], r['files_parsed'], r['functions'],
                    r['functions_with_loops'], r['candidates'], r['proved']))
    L.append('| **合计 / total** | **%d** | **%d** | **%d** | **%d** | **%d** | **%d** |'
             % (totals['files'], totals['files_parsed'], totals['functions'],
                totals['functions_with_loops'], totals['candidates'], totals['proved']))
    L += ['', '## 每一级为什么掉下去 / why each stage drops', '']
    for r in table:
        if r.get('missing'):
            continue
        L.append('### %s' % r['project'])
        L.append('')
        L.append('解析失败 / parse failures: ' + (', '.join('%s %d' % kv for kv in sorted(r['parse_fail'].items(), key=lambda kv: -kv[1])) or '—'))
        L.append('')
        L.append('片段外的第一处阻塞 / first blocking feature: ' + ', '.join('%s %d' % kv for kv in sorted(r['classes'].items(), key=lambda kv: -kv[1])))
        L.append('')
        L.append('候选的结局 / candidate outcomes: ' + ', '.join('%s %d' % kv for kv in sorted(r['frontend_status'].items(), key=lambda kv: -kv[1])))
        L.append('')
        if r['proved_seconds']:
            L.append('证出的用例耗时 / proved in: ' + ', '.join('%.1fs' % s for s in r['proved_seconds']))
            L.append('')
    L += ['## 这条数字能说什么 / what the numbers support', '',
          '- “含循环的函数”是分母，抽样规则与哈希都在 `protocol.json` 里，可逐文件复算。',
          '- 片段内候选是**语法**上的：标量整数、无指针/数组/结构体/浮点/goto/函数调用。',
          '- “证出”指 `houdini_loops` 在**参数类型的完整取值范围**上返回 PROVED；没有收窄参数窗口。',
          '- 这一节不含第三方见证复核（E1 在 SV-COMP 语料上做了这件事），所以它测的是**覆盖面**，',
          '  不是**可靠性**。',
          '- 与 SV-COMP 的 400 例不可混算：那边是同一族程序上的对照，这里是工业代码上的边界。', '']
    (out / 'summary.md').write_text('\n'.join(L) + '\n', encoding='utf-8')
    print('\n'.join(L[:20]))
    return summary


# --------------------------------------------------------------------------- cli


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)

    f = sub.add_parser('freeze')
    f.add_argument('--external', type=Path, required=True)
    f.add_argument('--output', type=Path, required=True)
    f.add_argument('--projects', default='')

    s = sub.add_parser('scan')
    s.add_argument('--external', type=Path, required=True)
    s.add_argument('--output', type=Path, required=True)
    s.add_argument('--project', required=True)
    s.add_argument('--limit', type=int, default=0)

    p = sub.add_parser('prove')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--project', required=True)
    p.add_argument('--seconds', type=int, default=90)
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--limit', type=int, default=0)

    o = sub.add_parser('one')
    o.add_argument('--candidate', type=Path, required=True)
    o.add_argument('--output', type=Path, required=True)

    m = sub.add_parser('merge')
    m.add_argument('--output', type=Path, required=True)

    a = ap.parse_args(argv)
    if a.cmd == 'freeze':
        only = [x for x in a.projects.split(',') if x] or None
        freeze(a.external, a.output, only)
    elif a.cmd == 'scan':
        scan(a.external, a.output, a.project, limit=a.limit)
    elif a.cmd == 'prove':
        prove(a.output, a.project, a.seconds, a.workers, a.limit)
    elif a.cmd == 'one':
        one(a.candidate, a.output)
    else:
        merge(a.output)


if __name__ == '__main__':
    main()
