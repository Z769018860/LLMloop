"""v1.04 (audit E1): export the verifier's invariants as SV-COMP correctness witnesses, and have a
third-party validator decide whether they actually prove the property.

Why this exists. `docs/TOP_TIER_AUDIT.md` §4.5 records the weakest point in the evidence: the 586
certificates of v1.03 are re-checked by a script we wrote, on the same proof rule, in the same
repository. That is a second implementation, not third-party confirmation. SV-COMP's own answer to
this problem is the witness: a tool states its loop invariants as a file, and an unrelated verifier
re-verifies the program from those invariants alone. If CPAchecker returns TRUE, the invariant is
sufficient for the property and consistent with the program's reachable states, and the claim stops
depending on our code.

What is written, per case:

  <out>/program/<id>.c     the frozen translation (`svcomp_translate`, NOOVF+GHOST) plus a `main`
                           that calls `f` on nondeterministic arguments under the same parameter
                           bounds the verifier assumed. The translation has no `main` of its own, and
                           the bounds are not in the source (they came from the original program's
                           assumptions), so the harness is the only way to state the same task to
                           another tool. The witness quotes this file's hash.
  <out>/witness/<id>.yml   one YAML `loop_invariant` entry per loop, at the loop head, in C.
  <out>/records/<id>.json  what was exported and from which run.

Only cases the verifier actually proved are exported, and a case is skipped with a recorded reason
rather than exported wrongly if the loop count cannot be established (see `loop_heads`).

usage:
  witness_v104.py make --external EXT --output DIR [--cases a.c,b.c] [--limit N] [--no-solver]
  witness_v104.py validate --external EXT --output DIR [--limit N]
  witness_v104.py selftest --external EXT --output DIR
  witness_v104.py merge --output DIR

`selftest` is the non-vacuity control: it validates one true invariant (must be TRUE) and one false
one (must be FALSE) on a fixed two-line loop. A validation rate is only evidence if the validator
rejects something.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pycparser import c_ast, c_parser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CASE_SET = ROOT / 'experiments' / 'v103' / 'full165' / 'protocol.json'
SPEC_OVERFLOW = 'CHECK( init(main()), LTL(G ! overflow) )'
PRODUCER = ('llmloop', '1.04')
# Frozen into every entry instead of the wall clock, so two exports of the same case produce the
# same bytes and a reader can tell that the file was not rewritten after the results were known.
FREEZE_TIME = '2026-11-22T00:00:00+00:00'
CPA_DIR = 'CPAchecker-4.2.2-unix'
CPA_SHA256 = '183adce15ced2641784dd16dd1dda3c4d88bb463674d8adb688fb28c3656525f'

# C type -> the SV-COMP nondeterministic function of that type, as CPAchecker and CBMC both provide
NONDET = {'int': 'int', 'unsigned int': 'uint', 'short': 'short', 'unsigned short': 'ushort',
          'char': 'char', 'unsigned char': 'uchar', 'long': 'long', 'unsigned long': 'ulong',
          'long long': 'longlong', 'unsigned long long': 'ulonglong'}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def save(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def dump(p, obj):
    save(p, json.dumps(obj, indent=2, sort_keys=True) + '\n')


# --------------------------------------------------------------------------- invariants -> C

MOD_ATOM = re.compile(r'^(?P<lhs>\(?[\w\- +*]+\)?)\s*%\s*(?P<m>\d+)\s*==\s*(?P<r>-?\d+)$')


def atom_to_c(atom):
    """One sampling atom, in the syntax the verifier evaluates, as a C expression with the same meaning.

    The atoms are `eval`ed as Python (`houdini_while._holds`), so four things have to be said in C:
    `True`/`False` are `1`/`0`, `or`/`and`/`not` are `||`/`&&`/`!`, and `%` is *floor* modulo. C's
    `%` truncates towards zero, so for a negative left operand the two disagree; `((v % m) + m) % m`
    is floor modulo for every integer (C result lies in (-m, m), adding m lands in (0, 2m), and the
    outer % folds it back into [0, m)). Without that rewrite an atom like `x % 2 == 1` would be false
    in C exactly on the negative odd values for which the verifier believed it true -- which a
    validator would then report as a rejected witness, for a reason that is our transcription's.
    """
    a = atom.strip()
    if a in ('True', 'true'):
        return '1'
    if a in ('False', 'false'):
        return '0'
    a = re.sub(r'\bnot\b', '!', a)
    a = a.replace(' or ', ' || ').replace(' and ', ' && ')
    m = MOD_ATOM.match(a)
    if m:
        lhs, mod, want = m.group('lhs').strip(), m.group('m'), m.group('r')
        a = '((%s %% %s) + %s) %% %s == %s' % (lhs, mod, mod, mod, want)
    return a


def conjunction(atoms):
    """The per-loop invariant, as one C expression. `1` when there is nothing to say."""
    seen, out = set(), []
    for a in atoms:
        c = atom_to_c(a)
        if c not in seen:
            seen.add(c)
            out.append(c)
    if not out:
        return '1'
    return ' && '.join('(%s)' % a for a in out) if len(out) > 1 else out[0]


# --------------------------------------------------------------------------- the harness program

def parse_sig(code):
    """(type, name) of `f`'s parameters, in order, from the generated translation."""
    ast = c_parser.CParser().parse(code)
    fn = [n for n in ast.ext if isinstance(n, c_ast.FuncDef)][0]
    out = []
    for p in (fn.decl.type.args.params if fn.decl.type.args else []):
        t = p.type
        while not isinstance(t, c_ast.TypeDecl):
            t = t.type
        out.append((' '.join(t.type.names), p.name))
    return out


def add_entry(code, bounds):
    """Append a `main` that runs the translated function on nondeterministic inputs.

    The verifier does not prove `f` for all inputs: it assumes the range constraints that the
    original program's `__VERIFIER_assume` calls implied, and the translation moved those into
    `parameter_bounds` instead of leaving them in the source. Re-imposing exactly those constraints
    is what makes the validation a check of the same claim; without it CPAchecker would be asked
    about a strictly larger input set and could reject a correct invariant.
    """
    params = parse_sig(code)
    decls, call, assume = [], [], []
    for t, n in params:
        fn = NONDET.get(t)
        if fn is None:
            raise SystemExit('parameter %s has type %r, no nondeterministic source' % (n, t))
        d = 'extern %s __VERIFIER_nondet_%s(void);' % (t, fn)
        if d not in decls:
            decls.append(d)
        call.append('__VERIFIER_nondet_%s()' % fn)
        if n in bounds and len(bounds[n]) == 2:
            lo, hi = bounds[n]
            assume.append('__VERIFIER_assume(%s >= %s && %s <= %s);' % (n, lo, n, hi))
    if not params:                       # the translation invents a dummy parameter in this case
        call = []
    main = ['extern void __VERIFIER_assume(int);', 'int main(void){']
    main += assume + ['  return f(%s);' % ', '.join(call), '}']
    return code.rstrip('\n') + '\n' + '\n'.join(decls) + '\n' + '\n'.join(main) + '\n'


def loop_heads(code, column_base=0):
    """(line, column) of each loop head, in the order `houdini_loops` numbers its invariants.

    That order is `[x for s in middle for x in _walk(s) if isinstance(x, c_ast.While)]` over the
    statements after the leading declarations and before the trailing return, walked depth-first;
    `_desugar` turns a `for` into a `while` in place, so the k-th `for`-or-`while` in the source is
    the k-th loop the verifier numbered. The loop nodes themselves are unusable for coordinates --
    `_desugar` rebuilds them without any -- so the pattern is re-parsed here instead.

    `column` is returned zero-based, as the entries format defines it ("if column has value 0 then
    the invariant holds before the first source-code token of the line"); pycparser counts columns
    from 1, hence the subtraction.

    A `do`-`while` is counted as a loop by nobody: `_desugar` does not touch it, so it never appears
    in the verifier's numbering, and an invariant would be attached to the wrong loop. Its presence
    therefore makes the case unexportable rather than mis-exported.
    """
    ast = c_parser.CParser().parse(code)
    fn = [n for n in ast.ext if isinstance(n, c_ast.FuncDef) and n.decl.name == 'f'][0]
    items = fn.body.block_items or []
    pos = 0
    while pos < len(items) and isinstance(items[pos], c_ast.Decl):
        pos += 1
    middle = items[pos:-1]

    def walk(n):
        yield n
        for _, c in n.children():
            yield from walk(c)

    heads = []
    for s in middle:
        for x in walk(s):
            if isinstance(x, c_ast.DoWhile):
                raise ValueError('do-while: the verifier does not number this loop')
            if isinstance(x, (c_ast.While, c_ast.For)):
                if x.coord is None:
                    raise ValueError('loop without coordinates')
                heads.append((x.coord.line, x.coord.column - 1 if column_base == 0
                              else x.coord.column))
    return heads


# --------------------------------------------------------------------------- the YAML witness

def witness_yaml(program_name, program_sha, entries, data_model, created, note):
    """A file of verification entries, one `loop_invariant` per loop.

    Written by hand rather than through a YAML library so the bytes are reproducible: the UUID is
    derived from the content, and `creation_time` is the freeze time passed in, not the wall clock.
    A witness whose bytes change between two runs cannot be quoted as evidence.
    """
    out = []
    for k, (line, column, invariant) in enumerate(entries):
        out.append(
            '- entry_type: loop_invariant\n'
            '  metadata:\n'
            '    format_version: 0.1\n'
            '    uuid: %s\n'
            '    creation_time: %s\n'
            '    producer:\n'
            '      name: %s\n'
            '      version: %s\n'
            '      configuration: %s\n'
            '    task:\n'
            '      input_files:\n'
            '      - %s\n'
            '      input_file_hashes:\n'
            '        %s: %s\n'
            '      specification: %s\n'
            '      data_model: %s\n'
            '      language: C\n'
            '  location:\n'
            '    file_name: %s\n'
            '    file_hash: %s\n'
            '    line: %d\n'
            '    column: %d\n'
            '    function: f\n'
            '  loop_invariant:\n'
            '    string: %s\n'
            '    type: assertion\n'
            '    format: C\n'
            % (str(uuid.uuid5(uuid.NAMESPACE_URL, 'llmloop/v1.04/%s/%d/%s'
                              % (program_sha, k, invariant))),
               created, PRODUCER[0], PRODUCER[1], note, program_name, program_name, program_sha,
               SPEC_OVERFLOW, data_model, program_name, program_sha, line, column,
               yaml_scalar(invariant))
        )
    return ''.join(out)


def yaml_scalar(s):
    """Quote a C expression so YAML reads it back as the same string.

    Single quotes are the only safe choice: `&&`, `||` and `%` are fine plain, but an expression that
    starts with a digit-and-space or contains `: ` would be re-read as something else, and Python's
    floor-mod rewrite (`((v % 2) + 2) % 2 == 1`) is full of parentheses. A literal single quote
    inside is doubled, per YAML.
    """
    return "'" + s.replace("'", "''") + "'"


# --------------------------------------------------------------------------- one case

def build_case(name, source, bounds, invariants, abi):
    """(program text, witness text, record) for one case, or (None, None, record-with-reason)."""
    program = add_entry(source, bounds)
    try:
        heads = loop_heads(program)
    except ValueError as e:
        return None, None, {'status': 'SKIPPED', 'reason': str(e)}
    if len(heads) != len(invariants):
        return None, None, {'status': 'SKIPPED',
                            'reason': 'loop count: %d in the program, %d invariants'
                                      % (len(heads), len(invariants))}
    entries = [(heads[k][0], heads[k][1], conjunction(invariants[k])) for k in range(len(heads))]
    return program, entries, {'status': 'EXPORTED', 'loops': len(entries), 'data_model': abi}


def emit_case(out, index, name, program, entries, abi, created, note):
    """Write the program and its witness into one directory, under the names the witness quotes.

    Both files have to sit side by side: a witness names its input as `program.c`, and a validator
    that resolves that name relative to the witness (rather than to the command line) would not find
    a file in a separate `program/` tree. Keeping them together removes the question.
    """
    stem = '%04d' % index
    d = out / 'cases' / stem
    save(d / 'program.c', program)
    psha = sha(d / 'program.c')
    save(d / 'witness.yml', witness_yaml('program.c', psha, entries, abi, created, note))
    return {'index': index, 'name': name, 'dir': 'cases/%s' % stem, 'program': 'program.c',
            'program_sha256': psha, 'witness_sha256': sha(d / 'witness.yml'),
            'invariants': [{'line': l, 'column': c, 'invariant': i} for l, c, i in entries]}


# --------------------------------------------------------------------------- CPAchecker

def ultimate_validate(external, program, witness, abi, log=None, timeout=300):
    """Validate the witness with Ultimate Automizer instead of CPAchecker.

    CPAchecker 4.2.2's `--witness` reads GraphML only -- it answered a YAML witness with
    "The Witness format found for ... is currently not supported" and a parser error from its XML
    reader (probe run 45007628049). Ultimate, which is what writes YAML correctness witnesses in the
    first place, has a `--validate` mode, so it is the shorter path to a second opinion. It is no
    less independent: it shares no code, no proof rule and no invariant generator with this project.
    """
    ult = external / 'ultimate-v0.3.2' / 'UAutomizer-linux' / 'Ultimate.py'
    if not ult.exists():
        return {'result': 'NO_ULTIMATE', 'detail': str(ult)}
    work = Path(log).parent if log else Path(witness).parent
    work.mkdir(parents=True, exist_ok=True)
    prp = work / 'no-overflow.prp'
    save(prp, SPEC_OVERFLOW + '\n')
    cmd = ['python3', str(ult), '--spec', str(prp), '--file', str(program),
           '--architecture', '32bit' if abi == 'ILP32' else '64bit',
           '--validate', str(witness)]
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(work))
        o = r.stdout + r.stderr
        code = r.returncode
    except subprocess.TimeoutExpired:
        return {'result': 'TIMEOUT', 'seconds': round(time.time() - t, 1), 'cmd': cmd}
    if log:
        save(Path(log), '$ %s\n\nexit %s\n\n%s' % (' '.join(cmd), code, o))
    m = re.search(r'Result:\s*\n?\s*(TRUE|FALSE|UNKNOWN|ERROR|TIMEOUT)', o)
    return {'result': m.group(1) if m else 'NO_RESULT', 'seconds': round(time.time() - t, 1),
            'exit': code, 'tail': [x for x in o.strip().splitlines() if x.strip()][-8:],
            'log': str(log) if log else None}


def validate_with(validator, external, program, witness, abi, log=None, timeout=300):
    if validator == 'ultimate':
        return ultimate_validate(external, program, witness, abi, log, timeout)
    return cpa_validate(external, program, witness, abi, log, timeout)


def cpa_validate(external, program, witness, abi, log=None, timeout=300):
    """Run the third-party validator. TRUE means the witness proves the property for this program.

    The full output goes to `log` (and the last lines into the record) whatever the verdict: on the
    first attempt this returned NO_RESULT for both invariants, and three lines of tail were not
    enough to tell a rejected witness from a command line the tool never accepted. The command line
    is recorded for the same reason -- it is what a reader has to be able to repeat.
    """
    cpa = external / CPA_DIR
    if not (cpa / 'scripts' / 'cpa.sh').exists():
        return {'result': 'NO_CPA', 'detail': 'expected %s' % cpa}
    cfg = cpa / 'config' / 'correctness-witness-validation--overflow.properties'
    if not cfg.exists():
        return {'result': 'NO_CONFIG', 'detail': str(cfg)}
    outdir = Path(log).with_suffix('') if log else Path(witness).with_suffix('.cpa')
    # CPAchecker creates its output directory itself and refuses one that is already there, so only
    # the parent is made here.
    outdir.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(cpa / 'scripts' / 'cpa.sh'), '--config', str(cfg), '--witness', str(witness),
           '--spec', str(cpa / 'config' / 'specification' / 'sv-comp-overflow.spc'),
           '--32' if abi == 'ILP32' else '--64', '--timelimit', '%ds' % (timeout - 30),
           '--output-path', str(outdir), str(program)]
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        o = r.stdout + r.stderr
        code = r.returncode
    except subprocess.TimeoutExpired:
        return {'result': 'TIMEOUT', 'seconds': round(time.time() - t, 1), 'cmd': cmd}
    if log:
        save(Path(log), '$ %s\n\nexit %s\n\n%s' % (' '.join(cmd), code, o))
    m = re.search(r'Verification result:\s*(TRUE|FALSE|UNKNOWN)', o)
    return {'result': m.group(1) if m else 'NO_RESULT', 'seconds': round(time.time() - t, 1),
            'exit': code, 'tail': [x for x in o.strip().splitlines() if x.strip()][-8:],
            'log': str(log) if log else None}


# --------------------------------------------------------------------------- the frozen case set

def case_set(external):
    plan = json.loads(CASE_SET.read_text())
    sv = external / 'svbench'
    got = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=sv, text=True).strip()
    if got != plan['svbench_pin']:
        raise SystemExit('svbench is at %s, expected the pin %s' % (got, plan['svbench_pin']))
    return plan, sv


def prove(source, bounds, abi):
    """The verifier's own verdict and per-loop invariants, with the frozen default-then-poly order."""
    from llmloop.houdini_loops import houdini_loops
    phases = []
    for poly in (False, True):
        st, inv, rounds, log = houdini_loops(source, bounds, abi=abi, integer_model='c', runs=60,
                                             max_rounds=150, solver_timeout_ms=5000, seed=1, poly=poly)
        phases.append({'poly': poly, 'status': st, 'rounds': rounds})
        if st == 'PROVED':
            return 'PROVED', inv, phases
    return 'NOT_PROVED', [], phases


def make(external, out, only=(), limit=None, created=None):
    plan, sv = case_set(external)
    out.mkdir(parents=True, exist_ok=True)
    created = created or FREEZE_TIME
    import scripts.svcomp_translate as T
    T.NOOVF = True
    T.GHOST = True
    cases = [c for c in plan['cases'] if not only or c['name'] in only]
    if limit is not None:
        cases = cases[:limit]
    rows = []
    for i, c in enumerate(cases):
        p = sv / 'c' / c['name']
        rec = {'index': i, 'name': c['name'], 'expected': c.get('expected_nooverflow')}
        try:
            source, bounds = T.translate(p)
        except Exception as e:
            rec.update({'status': 'UNSUPPORTED', 'reason': '%s: %s' % (type(e).__name__, str(e)[:80])})
            rows.append(rec)
            dump(out / 'records' / ('record_%04d.json' % i), rec)
            continue
        status, inv, phases = prove(source, bounds, c['abi'])
        rec.update({'verdict': status, 'phases': phases, 'translation_sha256': sha_of_text(source)})
        if status != 'PROVED':
            rows.append(rec)
            dump(out / 'records' / ('record_%04d.json' % i), rec)
            continue
        program, entries, info = build_case(c['name'], source, bounds, inv, c['abi'])
        rec.update(info)
        if program is None:
            rows.append(rec)
            dump(out / 'records' / ('record_%04d.json' % i), rec)
            continue
        rec.update(emit_case(out, i, c['name'], program, entries, c['abi'], created,
                             'llmloop v1.04 deterministic pipeline, invariants exported as loop heads'))
        rows.append(rec)
        dump(out / 'records' / ('record_%04d.json' % i), rec)
        print(json.dumps({'case': c['name'], 'loops': rec['loops']}), flush=True)
    dump(out / 'plan.json', {'cases': len(cases), 'rows': rows})
    import collections
    print(json.dumps(collections.Counter(r['status'] for r in rows), indent=1))


def sha_of_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


def validate(external, out, limit=None, validator='cpachecker'):
    plan = json.loads((out / 'plan.json').read_text())
    rows = [r for r in plan['rows'] if r['status'] == 'EXPORTED']
    if limit is not None:
        rows = rows[:limit]

    def one(r):
        d = out / r['dir']
        res = validate_with(validator, external, d / r['program'], d / 'witness.yml',
                            r['data_model'],
                            log=out / 'logs' / ('%04d.out.txt' % r['index']))
        return {**{'name': r['name'], 'index': r['index']}, **res}

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(one, rows))
    dump(out / 'validation.json', {'validator': validator, 'rows': results})
    import collections
    print(json.dumps(collections.Counter(r['result'] for r in results), indent=1))


# --------------------------------------------------------------------------- non-vacuity control

SELFTEST_PROGRAM = 'int f(int n){\n  int i = 0;\n  while (i <= n) {\n    i = i + 1;\n  }\n  return i;\n}\n'
SELFTEST_BOUNDS = {'n': [0, 10]}


def selftest(external, out, validator='cpachecker', column_base=0):
    """Validate a true invariant (want TRUE) and a false one (want FALSE) on a fixed program.

    Every number this script reports is a rate of `Verification result: TRUE`. That number means
    nothing unless the same command line, on the same program, rejects an invariant that is wrong.
    The wrong one is `i <= n - 1` at the loop head, which fails on the state that enters the loop
    with `i == n`: true when the loop is skipped, false after the last iteration.
    """
    out.mkdir(parents=True, exist_ok=True)
    program = add_entry(SELFTEST_PROGRAM, SELFTEST_BOUNDS)
    d = out / 'cases' / 'selftest'
    save(d / 'program.c', program)
    psha = sha(d / 'program.c')
    heads = loop_heads(program, column_base)
    rows = []
    for label, inv, want in (('true', 'i >= 0 && i <= n + 1', 'TRUE'),
                             ('false', 'i < n', 'FALSE')):
        entries = [(heads[0][0], heads[0][1], inv)]
        w = d / ('witness_%s.yml' % label)
        save(w, witness_yaml('program.c', psha, entries, 'LP64', FREEZE_TIME, 'non-vacuity control'))
        r = validate_with(validator, external, d / 'program.c', w, 'LP64',
                          log=out / 'logs' / ('selftest_%s.out.txt' % label))
        rows.append({'label': label, 'invariant': inv, 'want': want, **r})
    dump(out / 'selftest.json', rows)
    for r in rows:
        ok = r['result'] == r['want']
        print('%-6s want %-5s got %-8s %s' % (r['label'], r['want'], r['result'],
                                              'OK' if ok else 'MISMATCH'))
        if not ok:
            print('  exit %s, %s s' % (r.get('exit'), r.get('seconds')))
            for x in r.get('tail') or []:
                print('  | ' + x)
    return all(r['result'] == r['want'] for r in rows)


def merge(out):
    plan = json.loads((out / 'plan.json').read_text())
    rows = plan['rows']
    val, validator = {}, 'none'
    if (out / 'validation.json').exists():
        blob = json.loads((out / 'validation.json').read_text())
        rows_v = blob['rows'] if isinstance(blob, dict) else blob
        validator = blob.get('validator', 'unknown') if isinstance(blob, dict) else 'unknown'
        val = {r['index']: r for r in rows_v}
    import collections
    exported = [r for r in rows if r['status'] == 'EXPORTED']
    verdict = collections.Counter((val.get(r['index']) or {}).get('result', 'NOT_RUN') for r in exported)
    tally = collections.Counter(r['status'] for r in rows)
    verify = [r for r in exported if (val.get(r['index']) or {}).get('result') == 'TRUE']
    lines = [
        '# v1.04 witness export and third-party validation',
        '',
        'Cases considered: **%d**; exported as witnesses: **%d**; validated TRUE by %s: **%d**.'
        % (len(rows), len(exported), validator, len(verify)),
        '',
        '| outcome of the export | n |', '|---|---|',
    ]
    for k, v in sorted(tally.items()):
        lines.append('| %s | %d |' % (k, v))
    lines += ['', '| validator verdict | n |', '|---|---|']
    for k, v in sorted(verdict.items()):
        lines.append('| %s | %d |' % (k, v))
    if exported:
        lines += ['', '| case | loops | validator |', '|---|---|---|']
        for r in exported:
            lines.append('| %s | %d | %s |' % (r['name'], r.get('loops', 0),
                                               (val.get(r['index']) or {}).get('result', 'NOT_RUN')))
    save(out / 'summary.md', '\n'.join(lines) + '\n')
    dump(out / 'summary.json', {'considered': len(rows), 'export_outcomes': dict(tally),
                                'validator_used': validator, 'verdicts': dict(verdict),
                                'validated': len(verify)})
    print('\n'.join(lines[:14]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['make', 'validate', 'selftest', 'merge'])
    ap.add_argument('--external')
    ap.add_argument('--output', required=True)
    ap.add_argument('--cases', default='')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--validator', choices=['cpachecker', 'ultimate'], default='cpachecker')
    ap.add_argument('--column-base', type=int, choices=[0, 1], default=0,
                    help='0 for the entries format definition, 1 for what pycparser reports')
    a = ap.parse_args()
    out = Path(a.output).resolve()
    if a.action == 'make':
        make(Path(a.external), out, only={x for x in a.cases.split(',') if x}, limit=a.limit)
    elif a.action == 'validate':
        validate(Path(a.external), out, limit=a.limit, validator=a.validator)
    elif a.action == 'selftest':
        sys.exit(0 if selftest(Path(a.external), out, validator=a.validator,
                               column_base=a.column_base) else 1)
    else:
        merge(out)
