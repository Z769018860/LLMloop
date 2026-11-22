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
  witness_v104.py make --external EXT --output DIR [--cases a.c,b.c] [--limit N] [--shard I/N]
  witness_v104.py validate --external EXT --output DIR [--limit N] [--timeout S] [--workers W]
  witness_v104.py selftest --external EXT --output DIR [--column-base 0|1]
  witness_v104.py merge --output DIR [--inputs DIR,DIR,...]

`selftest` is the non-vacuity control: it validates one true invariant (must be TRUE) and one false
one (must be FALSE) on a fixed two-line loop. A validation rate is only evidence if the validator
rejects something. It passes on CPAchecker 4.2.2 at both column bases (probe run 45009866409);
Ultimate 0.3.2 answers UNKNOWN to both, so it cannot serve as the control.
"""

import argparse
import collections
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
# Which shape of correctness witness to write. Ultimate writes `invariant_set` at 2.0/2.2; the
# sv-witnesses README describes `loop_invariant` at 0.1; CPAchecker 4.2.2 parses 2.0 only.
DIALECTS = {'entries-01': ('loop_invariant', '0.1'),
            'set-20': ('invariant_set', '2.0'),
            'set-22': ('invariant_set', '2.2')}
CPA_SHA256 = '183adce15ced2641784dd16dd1dda3c4d88bb463674d8adb688fb28c3656525f'
# Column convention for the witness entry. The entries format is defined zero-based, pycparser
# reports one-based, and the two validators disagree: in probe run 45009866409 both invariants were
# confirmed/rejected at column base 1 by CPAchecker 4.2.2 *and* Ultimate 0.3.2, while at column base
# 0 Ultimate reported ERROR for both (it could not match the entry) and only CPAchecker still
# answered. So 1 is the value that makes one file readable by both, and it is what gets written.
COLUMN_BASE = 1

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

    Each argument is drawn into a local of `main` first. The bounds are stated over the *parameter*
    names, which do not exist outside `f`, so assuming them directly in `main` produced a program
    CPAchecker refused to parse ("Undefined identifier n found", probe run 45009560330) -- a harness
    bug that had been hiding behind the format errors.
    """
    params = parse_sig(code)
    decls, draws, args = [], [], []
    for i, (t, n) in enumerate(params):
        fn = NONDET.get(t)
        if fn is None:
            raise SystemExit('parameter %s has type %r, no nondeterministic source' % (n, t))
        d = 'extern %s __VERIFIER_nondet_%s(void);' % (t, fn)
        if d not in decls:
            decls.append(d)
        var = 'a%d' % i
        draws.append('  %s %s = __VERIFIER_nondet_%s();' % (t, var, fn))
        if n in bounds and len(bounds[n]) == 2:
            lo, hi = bounds[n]
            draws.append('  __VERIFIER_assume(%s >= %s && %s <= %s);' % (var, lo, var, hi))
        args.append(var)
    main = ['extern void __VERIFIER_assume(int);', 'int main(void){'] + draws + \
           ['  return f(%s);' % ', '.join(args), '}']
    return code.rstrip('\n') + '\n' + '\n'.join(decls) + '\n' + '\n'.join(main) + '\n'


def loop_heads(code, column_base=1):
    """(line, column) of each loop head, in the order `houdini_loops` numbers its invariants.

    That order is `[x for s in middle for x in _walk(s) if isinstance(x, c_ast.While)]` over the
    statements after the leading declarations and before the trailing return, walked depth-first;
    `_desugar` turns a `for` into a `while` in place, so the k-th `for`-or-`while` in the source is
    the k-th loop the verifier numbered. The loop nodes themselves are unusable for coordinates --
    `_desugar` rebuilds them without any -- so the pattern is re-parsed here instead.

    `column_base` decides between the two conventions that are in play: the entries format is
    defined zero-based ("if column has value 0 then the invariant holds before the first source-code
    token of the line"), pycparser counts from 1, and the validators do not agree -- probe run
    45009866409 matched the same witness at base 1 in both CPAchecker 4.2.2 and Ultimate 0.3.2, and
    at base 0 only in CPAchecker. 1 is therefore the default (see `COLUMN_BASE`).

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

def witness_yaml(program_name, program_sha, entries, data_model, created, note,
                 entry='invariant_set', version='2.0'):
    """The witness file, one invariant entry or content item per loop.

    The shape is Ultimate's, not the one the sv-witnesses README describes. Ultimate 0.3.2 writes a
    correctness witness as `entry_type: invariant_set` with `content: [{invariant: {type:
    loop_invariant, location: {...}, value: ..., format: c_expression}}]` (probe run 45009169721
    printed one), whereas the README's older `entry_type: loop_invariant` / `format_version: 0.1`
    form is what CPAchecker 4.2.2 rejects with "The Witness format found for ... is currently not
    supported". The `version` matters separately: CPAchecker routes version 2.0 to
    `AutomatonWitnessV2d0Parser` and fails on 2.2 with a bare NoSuchElementException, so 2.0 is the
    value to try first and 2.2 is kept only to reproduce that.

    Written by hand rather than through a YAML library so the bytes are reproducible: the UUID is
    derived from the content, and `creation_time` is the freeze time passed in, not the wall clock.
    A witness whose bytes change between two runs cannot be quoted as evidence.
    """
    header = ('- entry_type: %s\n'
              '  metadata:\n'
              '    format_version: %s\n'
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
              '      language: C\n')

    def uid_of(prefix):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, 'llmloop/v1.04/%s/%s/%s%s'
                              % (program_sha, prefix, entry, version)))

    def spec(text, indent):
        # A block scalar keeps the LTL formula on one line without needing quotes, and its content is
        # indented to sit under whatever key it belongs to.
        return '|\n%s%s' % (indent, text)

    if entry == 'loop_invariant':
        # The README shape: one list item per invariant, location and invariant side by side. Legal
        # YAML with any number of items, and each entry stands on its own.
        out = []
        for k, (line, column, invariant) in enumerate(entries):
            out.append(header % (entry, "'%s'" % version, uid_of(str(k)), "'%s'" % created,
                                 PRODUCER[0], PRODUCER[1], note, program_name, program_name,
                                 program_sha, spec(SPEC_OVERFLOW, '        '), data_model)
                       + '  location:\n'
                         '    file_name: %s\n'
                         '    file_hash: %s\n'
                         '    line: %d\n'
                         '    column: %d\n'
                         '    function: f\n'
                         '  loop_invariant:\n'
                         '    string: %s\n'
                         '    type: assertion\n'
                         '    format: C\n'
                         % (program_name, program_sha, line, column, yaml_scalar(invariant)))
        return ''.join(out)

    # Ultimate's shape, and the one CPAchecker 4.2.2 can read: a *single* `invariant_set` whose
    # `content` is the list of all loop invariants. Emitting one set per loop instead would put a
    # second `- entry_type:` item beside a `content:` key that only the first item opened, which is
    # not YAML at all -- a multi-loop case would have been handed to the validator as a syntax error
    # and counted as a rejected witness.
    out = [header % (entry, "'%s'" % version, uid_of('+'.join(inv for _, _, inv in entries)),
                     "'%s'" % created, PRODUCER[0], PRODUCER[1], note, program_name, program_name,
                     program_sha, spec(SPEC_OVERFLOW, '        '), data_model),
           '  content:\n']
    for line, column, invariant in entries:
        out.append('  - invariant:\n'
                   '      type: loop_invariant\n'
                   '      location:\n'
                   '        file_name: %s\n'
                   '        line: %d\n'
                   '        column: %d\n'
                   '        function: f\n'
                   '      value: %s\n'
                   '      format: c_expression\n'
                   % (program_name, line, column, yaml_scalar(invariant)))
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

def build_case(name, source, bounds, invariants, abi, column_base=COLUMN_BASE):
    """(program text, witness text, record) for one case, or (None, None, record-with-reason)."""
    program = add_entry(source, bounds)
    try:
        heads = loop_heads(program, column_base)
    except ValueError as e:
        return None, None, {'status': 'SKIPPED', 'reason': str(e)}
    if len(heads) != len(invariants):
        return None, None, {'status': 'SKIPPED',
                            'reason': 'loop count: %d in the program, %d invariants'
                                      % (len(heads), len(invariants))}
    entries = [(heads[k][0], heads[k][1], conjunction(invariants[k])) for k in range(len(heads))]
    return program, entries, {'status': 'EXPORTED', 'loops': len(entries), 'data_model': abi}


def emit_case(out, index, name, program, entries, abi, created, note, dialect='set-20'):
    """Write the program and its witness into one directory, under the names the witness quotes.

    Both files have to sit side by side: a witness names its input as `program.c`, and a validator
    that resolves that name relative to the witness (rather than to the command line) would not find
    a file in a separate `program/` tree. Keeping them together removes the question.
    """
    stem = '%04d' % index
    d = out / 'cases' / stem
    save(d / 'program.c', program)
    psha = sha(d / 'program.c')
    entry, version = DIALECTS[dialect]
    save(d / 'witness.yml', witness_yaml('program.c', psha, entries, abi, created, note,
                                        entry, version))
    return {'index': index, 'name': name, 'dir': 'cases/%s' % stem, 'program': 'program.c',
            'program_sha256': psha, 'witness_sha256': sha(d / 'witness.yml'),
            'invariants': [{'line': l, 'column': c, 'invariant': i} for l, c, i in entries]}


# --------------------------------------------------------------------------- CPAchecker

def ultimate_validate(external, program, witness, abi, log=None, timeout=300):
    """Validate the witness with Ultimate Automizer instead of CPAchecker.

    Kept as the second opinion, not the primary one. Ultimate is what writes YAML correctness
    witnesses in the first place, so it is the strictest reader of the format -- but in probe run
    45008232723 it matched the entries and then answered UNKNOWN for both a true and a false
    invariant, which makes it useless as a non-vacuity control (see `cpa_validate` for the tool that
    did separate them).
    """
    ult = external / 'ultimate-v0.3.2' / 'UAutomizer-linux' / 'Ultimate.py'
    if not ult.exists():
        return {'result': 'NO_ULTIMATE', 'detail': str(ult)}
    work = Path(log).parent if log else Path(witness).parent
    work.mkdir(parents=True, exist_ok=True)
    prp = work / 'no-overflow.prp'
    save(prp, SPEC_OVERFLOW + '\n')
    cmd = ['python3', str(ult), '--spec', str(prp), '--file', Path(program).name,
           '--architecture', '32bit' if abi == 'ILP32' else '64bit',
           '--validate', str(Path(witness).name)]
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(Path(program).parent))
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

    The invocation is the one CPAchecker documents for witness validation (`--witnessValidation`,
    `--witness`, `--spec`, plus the data model), not `--config
    correctness-witness-validation--overflow.properties`: that file is the SV-COMP wrapper's entry
    point, and handing it to `--config` made CPAchecker 4.2.2 answer a YAML witness with "The
    Witness format found for ... is currently not supported" (run 45007628049 / 45007989891) even
    though version 2.0 of the format has been readable since CPAchecker 2.3.

    `--witnessValidation` also *validates the invariants themselves*: for no-overflow it runs the
    predicate analysis while checking each witness invariant in parallel, reporting a violation if an
    invariant does not hold. So a TRUE here is a positive result about the invariant, not just about
    the program.
    """
    cpa = external / CPA_DIR
    if not (cpa / 'scripts' / 'cpa.sh').exists():
        return {'result': 'NO_CPA', 'detail': 'expected %s' % cpa}
    work = Path(log).parent if log else Path(witness).parent
    work.mkdir(parents=True, exist_ok=True)
    prp = work / 'no-overflow.prp'
    save(prp, SPEC_OVERFLOW + '\n')
    # CPAchecker creates its output directory itself and refuses one that is already there, so only
    # the parent is made here. It goes under `cpa/`, not next to the log, because that directory is
    # megabytes of machine output per case and the run deletes the whole `cpa/` tree before the
    # artifact is kept -- the log is the evidence, not the tool's working files.
    outdir = (Path(log).parent.parent / 'cpa' / Path(log).stem) if log \
        else Path(witness).with_suffix('.cpa')
    outdir.parent.mkdir(parents=True, exist_ok=True)
    cmd = [str(cpa / 'scripts' / 'cpa.sh'), '--witnessValidation', '--heap', '4000M',
           '--witness', str(witness), '--spec', str(prp),
           '--32' if abi == 'ILP32' else '--64', '--timelimit', '%ds' % (timeout - 30),
           '--output-path', str(outdir), Path(program).name]
    t = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(Path(program).parent))
        o = r.stdout + r.stderr
        code = r.returncode
    except subprocess.TimeoutExpired:
        return {'result': 'TIMEOUT', 'seconds': round(time.time() - t, 1), 'cmd': cmd}
    if log:
        save(Path(log), '$ %s\n\nexit %s\n\n%s' % (' '.join(cmd), code, o))
    m = re.search(r'Verification result:\s*(TRUE|FALSE|UNKNOWN)', o)
    res = {'result': m.group(1) if m else 'NO_RESULT', 'seconds': round(time.time() - t, 1),
           'exit': code, 'tail': [x for x in o.strip().splitlines() if x.strip()][-8:],
           'log': str(log) if log else None}
    if res['result'] != 'TRUE':
        # A bare FALSE would be ambiguous: it can mean "the program violates the property" or "one of
        # the witness invariants is wrong". Under --witnessValidation the second case is reported
        # against the witness, so the reason is in the log and it is the only interesting part of a
        # rejection -- it says which invariant, at which line, did not hold. The dotted lines are
        # CPAchecker's configuration dump, which matches on the word "witness" everywhere and says
        # nothing about this case.
        hits = [x for x in o.splitlines()
                if re.search(r'(?i)(witness|invariant)', x) and x.strip()
                and not x.lstrip().startswith(('witness.', 'cpa.', 'counterexample.', 'termination.',
                                               'java.', '#'))]
        res['why'] = hits[-5:]
    return res


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


def make(external, out, only=(), limit=None, created=None, dialect='set-20', shard=None,
         column_base=COLUMN_BASE):
    plan, sv = case_set(external)
    out.mkdir(parents=True, exist_ok=True)
    created = created or FREEZE_TIME
    import scripts.svcomp_translate as T
    T.NOOVF = True
    T.GHOST = True
    cases = [c for c in plan['cases'] if not only or c['name'] in only]
    # The index has to be the position in the *whole* protocol, not in this shard, or two shards
    # write `records/record_0003.json` for different cases and the merge silently keeps one.
    pos = {c['name']: i for i, c in enumerate(plan['cases'])}
    if shard:
        k, n = shard
        cases = cases[k::n]
    if limit is not None:
        cases = cases[:limit]
    rows = []
    for c in cases:
        i = pos[c['name']]
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
        rec.update({'status': status, 'verdict': status, 'phases': phases,
                    'translation_sha256': sha_of_text(source)})
        if status != 'PROVED':
            rows.append(rec)
            dump(out / 'records' / ('record_%04d.json' % i), rec)
            continue
        program, entries, info = build_case(c['name'], source, bounds, inv, c['abi'],
                                            column_base)
        rec.update(info)
        if program is None:
            rows.append(rec)
            dump(out / 'records' / ('record_%04d.json' % i), rec)
            continue
        rec.update(emit_case(out, i, c['name'], program, entries, c['abi'], created,
                             'llmloop v1.04 deterministic pipeline, invariants exported as loop heads',
                             dialect))
        rows.append(rec)
        dump(out / 'records' / ('record_%04d.json' % i), rec)
        print(json.dumps({'case': c['name'], 'loops': rec['loops']}), flush=True)
    return finish_plan(out, len(cases), shard, rows)


def finish_plan(out, n_cases, shard, rows):
    """Write the shard's plan and summarise it.

    The status is the one field every row must have: `merge` counts on it, and a row without one is a
    case that did work and then reported nothing. Run 45010719952 is why this raises a sentence naming
    the cases instead of letting `Counter` produce a KeyError -- six of ten shards finished their
    whole export and then died on the summary line, so no shard result was kept.
    """
    missing = [r.get('name') for r in rows if 'status' not in r]
    if missing:
        raise SystemExit('rows without a status, so the export is incomplete: %s' % missing)
    dump(out / 'plan.json', {'cases': n_cases, 'shard': shard, 'rows': rows})
    print(json.dumps(collections.Counter(r['status'] for r in rows), indent=1))
    return rows


def sha_of_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


def log_name(index, validator):
    """The log of one validator's verdict on one case.

    Named per validator because both tools were writing `0030.out.txt`: the second one deleted the
    only record of what the first one said. Run 45010719952 lost CPAchecker's reasons for four
    rejected witnesses that way, and a rejection whose reason is gone cannot be argued about.
    """
    return '%04d.%s.out.txt' % (index, validator)


def validate(external, out, limit=None, validator='cpachecker', timeout=300, workers=2):
    plan = json.loads((out / 'plan.json').read_text())
    rows = [r for r in plan['rows'] if r['status'] == 'EXPORTED']
    if limit is not None:
        rows = rows[:limit]

    def one(r):
        d = out / r['dir']
        res = validate_with(validator, external, d / r['program'], d / 'witness.yml',
                            r['data_model'],
                            log=out / 'logs' / log_name(r['index'], validator), timeout=timeout)
        return {**{'name': r['name'], 'index': r['index'], 'loops': r.get('loops')}, **res}

    with ThreadPoolExecutor(workers) as pool:
        results = list(pool.map(one, rows))
    # One file per validator instead of one file: the same witness then gets two independent
    # verdicts, and `merge` can report whether the two tools agree. A second opinion that is allowed
    # to overwrite the first is not a second opinion.
    dump(out / ('validation-%s.json' % validator),
         {'validator': validator, 'timeout': timeout, 'rows': results})
    print(json.dumps(collections.Counter(r['result'] for r in results), indent=1))


# --------------------------------------------------------------------------- non-vacuity control

SELFTEST_PROGRAM = 'int f(int n){\n  int i = 0;\n  while (i <= n) {\n    i = i + 1;\n  }\n  return i;\n}\n'
SELFTEST_BOUNDS = {'n': [0, 10]}


def selftest(external, out, validator='cpachecker', column_base=1, dialect='set-20'):
    """Validate a true invariant (want TRUE) and a false one (want FALSE) on a fixed program.

    Every number this script reports is a rate of `Verification result: TRUE`. That number means
    nothing unless the same command line, on the same program, rejects an invariant that is wrong.
    The wrong one is `i < n` at the loop head, which is false as soon as the loop has run to its
    end (`i == n + 1`) and false immediately when `n == 0`.
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
        entry, version = DIALECTS[dialect]
        save(w, witness_yaml('program.c', psha, entries, 'LP64', FREEZE_TIME,
                             'non-vacuity control', entry, version))
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


def merge(outs, out=None):
    """Fold any number of shard directories into one summary.

    The batch runs as N independent jobs, so each one writes its own `plan.json` and
    `validation.json`. They are keyed by the case's position in the frozen protocol (not by its
    position in the shard), which is what makes folding them back together safe: a duplicated or
    missing index is visible rather than silently averaged away.
    """
    out = out or outs[0]
    rows, shards = [], []
    vals = collections.defaultdict(dict)   # validator -> index -> row
    for d in outs:
        p = d / 'plan.json'
        if p.exists():
            blob = json.loads(p.read_text())
            rows.extend(blob['rows'])
            shards.append({'dir': d.name, 'cases': blob.get('cases'), 'shard': blob.get('shard')})
        for v in sorted(d.glob('validation-*.json')):
            vb = json.loads(v.read_text())
            for r in (vb['rows'] if isinstance(vb, dict) else vb):
                vals[(vb.get('validator') if isinstance(vb, dict) else None) or v.stem.split('-')[1]][r['index']] = r
    seen = collections.Counter(r['index'] for r in rows)
    rows.sort(key=lambda r: r['index'])
    exported = [r for r in rows if r['status'] == 'EXPORTED']
    tally = collections.Counter(r['status'] for r in rows)
    loops_all = sum(r.get('loops', 0) for r in exported)
    validators = sorted(vals)
    verdict = {v: collections.Counter(vals[v].get(r['index'], {}).get('result', 'NOT_RUN')
                                      for r in exported) for v in validators}
    confirmed = {v: [r for r in exported if vals[v].get(r['index'], {}).get('result') == 'TRUE']
                 for v in validators}
    lines = [
        '# v1.04 witness export and third-party validation',
        '',
        'Cases considered: **%d**; exported as witnesses: **%d** (%d loop invariants).'
        % (len(rows), len(exported), loops_all),
        '',
    ]
    for v in validators:
        lines.append('| %s confirms | cases | invariants |' % v)
        lines.append('|---|---|---|')
        lines.append('| the witness proves the property | %d of %d | %d of %d |'
                     % (len(confirmed[v]), len(exported),
                        sum(r.get('loops', 0) for r in confirmed[v]), loops_all))
        lines.append('')
    lines += ['| outcome of the export | n |', '|---|---|']
    for k, v in sorted(tally.items()):
        lines.append('| %s | %d |' % (k, v))
    for v in validators:
        lines += ['', '| %s verdict | n |' % v, '|---|---|']
        for k, n in sorted(verdict[v].items()):
            lines.append('| %s | %d |' % (k, n))
    if len(validators) > 1:
        agree = [r for r in exported
                 if len({vals[v].get(r['index'], {}).get('result') for v in validators}) == 1]
        both = [r for r in exported
                if all(vals[v].get(r['index'], {}).get('result') == 'TRUE' for v in validators)]
        lines += ['', 'Both validators return the same verdict on **%d of %d** exported cases, and '
                  'both confirm **%d**.' % (len(agree), len(exported), len(both))]
    dupes = {i: n for i, n in seen.items() if n > 1}
    if dupes:
        lines += ['', '**Indices reported by more than one shard: %d** (the merge is not clean).'
                  % len(dupes)]
    if exported:
        head = '| case | invariants |' + ''.join(' %s |' % v for v in validators) + ' s |'
        lines += ['', head, '|---' * (len(validators) + 2) + '|']
        for r in exported:
            cell = ''.join(' %s |' % vals[v].get(r['index'], {}).get('result', 'NOT_RUN')
                           for v in validators)
            secs = max([vals[v].get(r['index'], {}).get('seconds') or 0 for v in validators] or [0])
            lines.append('| %s | %d |%s %s |' % (r['name'], r.get('loops', 0), cell, secs or '-'))
    rejected = [r for r in exported
                if any(vals[v].get(r['index'], {}).get('result') == 'FALSE' for v in validators)]
    if rejected:
        lines += ['', '## Witnesses a validator rejected', '']
        for r in rejected:
            for v in validators:
                vr = vals[v].get(r['index'], {})
                if vr.get('result') == 'FALSE':
                    lines.append('- `%s` (%s): %s' % (r['name'], v, (vr.get('why')
                                                                     or ['(no reason in the log)'])[-1]))
    save(out / 'summary.md', '\n'.join(lines) + '\n')
    dump(out / 'summary.json', {
        'considered': len(rows), 'export_outcomes': dict(tally),
        'validators': validators,
        'verdicts': {v: dict(verdict[v]) for v in validators},
        'exporter': {'exported_cases': len(exported), 'invariants_exported': loops_all,
                     **{'confirmed_%s' % v: len(confirmed[v]) for v in validators}},
        'duplicate_indices': len(dupes), 'shards': shards})
    print('\n'.join(lines[:12]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['make', 'validate', 'selftest', 'merge'])
    ap.add_argument('--external')
    ap.add_argument('--output', required=True)
    ap.add_argument('--cases', default='')
    ap.add_argument('--limit', type=int)
    ap.add_argument('--validator', choices=['cpachecker', 'ultimate'], default='cpachecker')
    ap.add_argument('--dialect', choices=sorted(DIALECTS), default='set-20')
    ap.add_argument('--column-base', type=int, choices=[0, 1], default=COLUMN_BASE,
                    help='0 per the entries format definition, 1 for what pycparser reports; %d is '
                         'the only value both validators accept' % COLUMN_BASE)
    ap.add_argument('--shard', default='', help='I/N: take every N-th case starting at I')
    ap.add_argument('--inputs', default='',
                    help='merge only: comma-separated shard directories (default: --output)')
    ap.add_argument('--timeout', type=int, default=300, help='seconds per validation')
    ap.add_argument('--workers', type=int, default=2, help='concurrent validations')
    a = ap.parse_args()
    out = Path(a.output).resolve()
    shard = None
    if a.shard:
        k, n = (int(x) for x in a.shard.split('/'))
        shard = (k, n)
    if a.action == 'make':
        make(Path(a.external), out, only={x for x in a.cases.split(',') if x}, limit=a.limit,
             dialect=a.dialect, shard=shard, column_base=a.column_base)
    elif a.action == 'validate':
        validate(Path(a.external), out, limit=a.limit, validator=a.validator,
                 timeout=a.timeout, workers=a.workers)
    elif a.action == 'selftest':
        sys.exit(0 if selftest(Path(a.external), out, validator=a.validator,
                               column_base=a.column_base, dialect=a.dialect) else 1)
    else:
        dirs = [Path(x).resolve() for x in a.inputs.split(',') if x] or [out]
        merge(dirs, out)
