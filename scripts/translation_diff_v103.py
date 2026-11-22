"""v1.03: differential tests for the two translations the paper leans on.

A. Integer semantics. `llmloop.c_integers.IntegerABI` is a hand-written model of C integer arithmetic
   (promotions, usual conversions, literals, casts, wrapping, the undefined set). This part generates
   typed expressions, evaluates each with the model *and* with the host compiler under
   `-fsanitize=undefined`, and compares value and definedness. A disagreement in either direction is a
   translation bug: too permissive means the verifier reasons about a program C does not have, too
   strict means it rejects programs C accepts.

B. Loop translation. `llmloop.c_frontend.translate_c` turns a single-`while` C function into the
   periodic IR the analyser proves things about. This part generates programs in exactly that
   fragment, compiles them natively, and compares the tool's concrete replay
   (`exact_trip_count` + `after_steps`) with the value the compiled program returns. Inputs where the
   native run trips a sanitizer are reported separately: those are outside the no-overflow domain the
   certificates already condition on, not translation errors.

usage:
  translation_diff_v103.py integers --n 400 --seed 1 [--emit-only]
  translation_diff_v103.py loops    --n 40 --inputs 8 --seed 1 [--emit-only]
  translation_diff_v103.py all      --n 400 --loops 40 --inputs 8 --seed 1
"""

import argparse
import collections
import json
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / 'experiments' / 'v103' / 'translation_diff'

SAN = ['-O0', '-std=c99', '-w', '-fsanitize=undefined', '-fno-sanitize-recover=undefined',
       '-fno-sanitize=alignment']

TYPES = ['char', 'unsigned char', 'short', 'unsigned short', 'int', 'unsigned int',
         'long', 'unsigned long', 'long long', 'unsigned long long', '_Bool']
BIN = ['+', '-', '*', '/', '%', '&', '|', '^', '<<', '>>', '<', '<=', '>', '>=', '==', '!=', '&&', '||']
UN = ['-', '~', '!']
CMP = {'<', '<=', '>', '>=', '==', '!='}


def cc_version(cc):
    try:
        return subprocess.run([cc, '--version'], capture_output=True, text=True).stdout.splitlines()[0]
    except OSError:
        return None


def emit_expr(node):
    """C text for an expression node; every operator is parenthesised, so precedence cannot bite."""
    if 'literal' in node:
        return node['literal']
    if 'value' in node:
        return '((%s)%d)' % (node['type'], node['value'])
    if 'cast' in node:
        return '((%s)(%s))' % (node['cast'], emit_expr(node['expr']))
    op, args = node['op'], node['args']
    if op == '?:':
        return '((%s) ? (%s) : (%s))' % tuple(emit_expr(a) for a in args)
    if len(args) == 1:
        return '(%s(%s))' % (op, emit_expr(args[0]))
    return '((%s) %s (%s))' % (emit_expr(args[0]), op, emit_expr(args[1]))


def gen_expr(rng, depth=0):
    if depth >= 3 or rng.random() < 0.25:
        kind = rng.random()
        if kind < 0.5:
            return {'value': rng.choice([0, 1, 2, 3, 7, 127, 128, 255, 256, 32767, 32768, 65535,
                                         2147483647, -1, -2, -128, -32768, -2147483648]),
                    'type': rng.choice(TYPES)}
        return {'literal': rng.choice(['0', '1', '2', '7', '10', '255', '0x7f', '0x8000', '0xffff',
                                       '0x7fffffff', '0xffffffff', '1u', '1ul', '1ll']) }
    kind = rng.random()
    if kind < 0.15:
        return {'cast': rng.choice(TYPES), 'expr': gen_expr(rng, depth + 1)}
    if kind < 0.3:
        return {'op': rng.choice(UN), 'args': [gen_expr(rng, depth + 1)]}
    if kind < 0.4:
        return {'op': '?:', 'args': [gen_expr(rng, depth + 1), gen_expr(rng, depth + 1),
                                     gen_expr(rng, depth + 1)]}
    return {'op': rng.choice(BIN), 'args': [gen_expr(rng, depth + 1), gen_expr(rng, depth + 1)]}


def eval_model(node):
    from llmloop.c_integers import evaluate_integer_request
    return evaluate_integer_request({'abi': 'LP64', 'char_signed': True, 'expression': node})


def fmt_of(model_result):
    if model_result.get('status') == 'DEFINED_INTEGER_EXPRESSION' and not model_result['signed']:
        return '%llu', '(unsigned long long)'
    return '%lld', '(long long)'


def collect_leaves(node, out, idx):
    """Every leaf becomes a function parameter, so no operand is a compile-time constant.

    This matters: with all-constant operands the compiler folds the whole expression during
    front-end constant evaluation and no sanitizer check is emitted, so an overflow would go
    unnoticed and the case would silently "agree"."""
    if 'literal' in node or 'value' in node:
        if id(node) not in idx:
            idx[id(node)] = len(out)
            out.append(node)
        return
    if 'cast' in node:
        collect_leaves(node['expr'], out, idx)
        return
    for a in node['args']:
        collect_leaves(a, out, idx)


def emit_parameterised(node, idx):
    if 'literal' in node:
        return 'v%d' % idx[id(node)]
    if 'value' in node:
        return '((%s)v%d)' % (node['type'], idx[id(node)])
    if 'cast' in node:
        return '((%s)(%s))' % (node['cast'], emit_parameterised(node['expr'], idx))
    op, args = node['op'], node['args']
    if op == '?:':
        return '((%s) ? (%s) : (%s))' % tuple(emit_parameterised(a, idx) for a in args)
    if len(args) == 1:
        return '(%s(%s))' % (op, emit_parameterised(args[0], idx))
    return '((%s) %s (%s))' % (emit_parameterised(args[0], idx), op, emit_parameterised(args[1], idx))


def integers(n, seed, cc, emit_only):
    from llmloop.c_integers import IntegerABI
    abi = IntegerABI('LP64', True)
    rng = random.Random(seed)
    cases, lines = [], ['#include <stdio.h>', '#include <stdlib.h>', '']
    calls = []
    for i in range(n):
        node = gen_expr(rng)
        model = eval_model(node)
        leaves, idx = [], {}
        collect_leaves(node, leaves, idx)
        ptypes = [abi.literal(leaf['literal']).type.name if 'literal' in leaf else leaf['type']
                  for leaf in leaves]
        sig = ', '.join('%s v%d' % (t, k) for k, t in enumerate(ptypes)) or 'void'
        fmt, cast = fmt_of(model)
        cases.append({'index': i, 'expression': node, 'model': model})
        lines.append('static int case_%d(%s){ printf("%s\\n", %s(%s)); return 0; }'
                     % (i, sig, fmt, cast, emit_parameterised(node, idx)))
        args = [leaf['literal'] if 'literal' in leaf else '((%s)%d)' % (leaf['type'], leaf['value'])
                for leaf in leaves]
        calls.append('  case %d: return case_%d(%s);' % (i, i, ', '.join(args)))
    lines.append('int main(int argc, char **argv){')
    lines.append('  int k = argc > 1 ? atoi(argv[1]) : 0;')
    lines.append('  switch (k) {')
    lines += calls
    lines.append('  }')
    lines.append('  return 2;')
    lines.append('}')
    src_text = '\n'.join(lines) + '\n'

    OUT.mkdir(parents=True, exist_ok=True)
    src = OUT / ('integers_seed%d.c' % seed)
    src.write_text(src_text, encoding='utf-8')
    # the same leaves, so a reader can audit one case without reading the generated TU
    (OUT / ('integers_seed%d.jsonl' % seed)).write_text(
        '\n'.join(json.dumps({'index': c['index'], 'expression': c['expression'],
                              'model': c['model']}) for c in cases) + '\n', encoding='utf-8')

    rows, counts = [], collections.Counter()
    if emit_only:
        for c in cases:
            rows.append({'index': c['index'], 'model_status': c['model'].get('status')})
            counts['emitted'] += 1
    else:
        with tempfile.TemporaryDirectory() as td:
            wd = Path(td)
            # one TU for all cases; a case that traps under UBSan only kills its own process
            built = subprocess.run([cc] + SAN + ['-o', str(wd / 'a.out'), str(src)],
                                   capture_output=True, text=True)
            if built.returncode != 0:
                raise SystemExit('integer batch failed to compile://n' + built.stderr[-2000:])
            for c in cases:
                run = subprocess.run([str(wd / 'a.out'), str(c['index'])], capture_output=True, text=True)
                native = {'exit': run.returncode, 'stdout': run.stdout.strip(),
                          'ub': 'runtime error' in run.stderr,
                          'ub_message': (run.stderr.strip().splitlines() or [''])[0][:160]}
                model = c['model']
                defined = model.get('status') == 'DEFINED_INTEGER_EXPRESSION'
                if defined and native['exit'] == 0:
                    verdict = 'agree' if native['stdout'] == str(model['value']) else 'value mismatch'
                elif not defined and native['ub']:
                    verdict = 'agree'                      # both call it undefined
                elif defined and native['ub']:
                    verdict = 'model too permissive'        # model says defined, C says UB
                elif not defined and not native['ub']:
                    verdict = 'model too strict'            # model rejects, C is fine
                else:
                    verdict = 'inconclusive'
                counts[verdict] += 1
                rows.append({'index': c['index'], 'expression': c['expression'],
                             'model_status': model.get('status'),
                             'model_value': model.get('value'), 'model_type': model.get('type'),
                             'native': native, 'verdict': verdict})

    payload = {'part': 'integers', 'seed': seed, 'cases': n, 'compiler': cc_version(cc),
               'flags': SAN, 'counts': dict(counts), 'rows': rows}
    (OUT / ('integers_seed%d.json' % seed)).write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({'part': 'integers', 'counts': dict(counts)}, ensure_ascii=False, indent=1))
    return payload


# ----------------------------------------------------------------------------- part B: loops

def gen_loop(rng, pid):
    """A program in translate_c's fragment.

    Deliberately narrow: `%` and other operators are outside `c_frontend._expr`, and the analyser
    needs the per-cycle map to be linear and unipotent, so an update may add a constant, a parameter
    or a parameter multiple to a state variable but must not multiply state by state.
    """
    nparams = rng.randint(1, 3)
    params = ['p%d' % i for i in range(nparams)]
    extra = rng.choice([0, 0, 1, 2])
    states = ['i', 's'] + ['t%d' % k for k in range(extra)]
    step = rng.choice([1, 1, 2, 3])
    limit = rng.choice(['6', '8', '10', '4 + %s' % params[-1], '%s + 2' % params[0], params[-1]])
    # translate_c's `if (ph == 0) ... else ...` branch does not reach a certified closed form
    # (LoopAnalyzer rejects the composed cycle), so only the single-phase form is generated here
    two_phase = False

    def delta():
        return rng.choice(['1', '2', '3', params[0], params[0] + ' * 2', '1 + ' + params[-1]])

    decls = ['int i = 0;', 'int s = %s;' % rng.choice(params + ['0', '1'])]
    for t in states[2:]:
        decls.append('int %s = %s;' % (t, rng.choice(params + ['0', '2'])))
    if two_phase:
        decls.append('int ph = 0;')
        body = ('if (ph == 0) { i = i + %d; s = s + %s; ph = 1; %s} '
                'else { i = i + %d; s = s + %s; ph = 0; %s}'
                % (step, delta(), ''.join('%s = %s + %s; ' % (t, t, delta()) for t in states[2:]),
                   step, delta(), ''.join('%s = %s + %s; ' % (t, t, delta()) for t in states[2:])))
    else:
        stmts = ['i = i + %d;' % step, 's = s + %s;' % delta()]
        for t in states[2:]:
            stmts.append('%s = %s + %s;' % (t, t, delta()))
        body = ' '.join(stmts)
    ret = rng.choice(states)
    src = ('int f(%s) {\n  %s\n  while (i < %s) { %s }\n  return %s;\n}\n'
           % (', '.join('int ' + p for p in params), '\n  '.join(decls), limit, body, ret))
    return {'name': 'loop_%04d' % pid, 'source': src, 'params': params, 'states': states, 'ret': ret}


def inputs_for(rng, params, count):
    return [{p: rng.randint(0, 9) for p in params} for _ in range(count)]


def build_model(source):
    """Translate once, then reuse the analyser for every input of that program."""
    from llmloop.c_frontend import translate_c
    from llmloop.core import PeriodicSystem, LoopAnalyzer
    ir = translate_c(source)
    return ir, LoopAnalyzer(PeriodicSystem.load(ir))


def model_run(analyzer, ir, inputs, ret):
    """The tool's own concrete replay: trip count from the guard, then k steps of the phases."""
    from llmloop.expressions import integer_value
    k = integer_value(analyzer.exact_trip_count(ir['guard']), inputs)
    final = analyzer.after_steps(k, inputs)
    return {'trip_count': int(k), 'predicted': int(final[ret])}


def compile_native(cc, source, params, workdir):
    """One TU per program: the program text plus a driver that calls f with argv values."""
    (workdir / 'prog.c').write_text(source, encoding='utf-8')
    driver = ('#include <stdio.h>\n#include <stdlib.h>\n#include "prog.c"\n'
              'int main(int argc, char **argv){ int a[%d]; int i;\n'
              '  for (i = 0; i < %d; i++) a[i] = atoi(argv[i + 1]);\n'
              '  printf("%%d\\n", f(%s)); return 0; }\n'
              % (max(1, len(params)), len(params), ', '.join('a[%d]' % i for i in range(len(params)))))
    (workdir / 'driver.c').write_text(driver, encoding='utf-8')
    built = subprocess.run([cc] + SAN + ['-o', str(workdir / 'p'), str(workdir / 'driver.c')],
                           capture_output=True, text=True)
    if built.returncode != 0:
        return None, (built.stderr.strip().splitlines() or ['unknown'])[-1][:200]
    return workdir / 'p', None


def run_native(binary, params, inputs):
    run = subprocess.run([str(binary)] + [str(inputs[p]) for p in params], capture_output=True, text=True)
    return {'exit': run.returncode, 'stdout': run.stdout.strip(),
            'ub': 'runtime error' in run.stderr,
            'ub_message': (run.stderr.strip().splitlines() or [''])[0][:160]}


def loops(n, inputs, seed, cc, emit_only):
    rng = random.Random(seed)
    (OUT / 'loops').mkdir(parents=True, exist_ok=True)
    rows, counts, rejected = [], collections.Counter(), []
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        for pid in range(n):
            prog = gen_loop(rng, pid)
            (OUT / 'loops' / (prog['name'] + '.c')).write_text(prog['source'], encoding='utf-8')
            row = {'name': prog['name'], 'source': prog['source'], 'params': prog['params'], 'ret': prog['ret']}
            try:
                ir, analyzer = build_model(prog['source'])
            except Exception as exc:
                row['model_error'] = type(exc).__name__ + ': ' + str(exc)[:160]
                rejected.append(row['model_error'])
                counts['not in fragment'] += 1
                rows.append(row)
                continue
            if emit_only:
                counts['emitted'] += 1
                rows.append(row)
                continue
            binary, err = compile_native(cc, prog['source'], prog['params'], wd)
            if binary is None:
                row['compile_error'] = err
                counts['native compile error'] += 1
                rows.append(row)
                continue
            for env in inputs_for(rng, prog['params'], inputs):
                try:
                    model = model_run(analyzer, ir, env, prog['ret'])
                except Exception as exc:
                    row.setdefault('model_errors', []).append(
                        {'inputs': env, 'error': type(exc).__name__ + ': ' + str(exc)[:120]})
                    counts['model error on input'] += 1
                    continue
                native = run_native(binary, prog['params'], env)
                if native['ub']:
                    verdict = 'outside no-overflow domain'
                elif native['exit'] != 0:
                    verdict = 'native failed'
                elif native['stdout'] == str(model['predicted']):
                    verdict = 'agree'
                else:
                    verdict = 'value mismatch'
                counts[verdict] += 1
                row.setdefault('trials', []).append({'inputs': env, 'verdict': verdict,
                                                     'model': model['predicted'],
                                                     'native': native['stdout'],
                                                     'trip_count': model['trip_count']})
            rows.append(row)
    payload = {'part': 'loops', 'seed': seed, 'programs': n, 'inputs_per_program': inputs,
               'compiler': cc_version(cc), 'flags': SAN, 'counts': dict(counts),
               'not_in_fragment': rejected[:20], 'rows': rows}
    (OUT / ('loops_seed%d.json' % seed)).write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({'part': 'loops', 'counts': dict(counts)}, ensure_ascii=False, indent=1))
    return payload


def summarise(payloads):
    md = ['# 翻译差分测试 / Translation differential tests', '']
    for p in payloads:
        if p['part'] == 'integers':
            md += ['## A. 整数语义（`IntegerABI` vs 原生 C + UBSan）', '',
                   '- 用例 / cases: %d，种子 / seed: %d' % (p['cases'], p['seed']),
                   '- 编译器 / compiler: `%s`' % p['compiler'],
                   '- 参数 / flags: `%s`' % ' '.join(p['flags']), '',
                   '| 结论 | 例数 |', '|---|---|']
            for k, v in p['counts'].items():
                md.append('| %s | %d |' % (k, v))
            bad = [r for r in p['rows'] if r.get('verdict') not in ('agree', None)]
            if bad:
                md += ['', '不一致的例子（最多 10 个）:', '']
                for r in bad[:10]:
                    md.append('- `%s` → 模型 %s / 原生 exit=%s out=%r ub=%s'
                              % (emit_expr(r['expression'])[:110], r['model_value'], r['native']['exit'],
                                 r['native']['stdout'], r['native']['ub']))
            md.append('')
        else:
            md += ['## B. 循环翻译（`translate_c` + 重放 vs 原生 C）', '',
                   '- 程序 / programs: %d，每程序输入 / inputs each: %d，种子 / seed: %d'
                   % (p['programs'], p['inputs_per_program'], p['seed']),
                   '- 编译器 / compiler: `%s`' % p['compiler'], '',
                   '| 结论 | 例数 |', '|---|---|']
            for k, v in p['counts'].items():
                md.append('| %s | %d |' % (k, v))
            if p['not_in_fragment']:
                md += ['', '生成器产出但前端不接受的形状（最多 5 条）:', '']
                for e in p['not_in_fragment'][:5]:
                    md.append('- `%s`' % e)
            bad = [r for r in p['rows'] for t in r.get('trials', []) if t['verdict'] == 'value mismatch']
            if bad:
                md += ['', '不一致的例子:', '']
                for r in bad[:10]:
                    t = [x for x in r['trials'] if x['verdict'] == 'value mismatch'][0]
                    md.append('- `%s` 输入 %s → 模型 %s / 原生 %s'
                              % (r['name'], t['inputs'], t['model'], t['native']))
            md.append('')
    (OUT / 'summary.md').write_text('\n'.join(md) + '\n')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['integers', 'loops', 'all'])
    ap.add_argument('--n', type=int, default=400)
    ap.add_argument('--loops', type=int, default=40)
    ap.add_argument('--inputs', type=int, default=8)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--cc', default=os.environ.get('CC', 'gcc'))
    ap.add_argument('--emit-only', action='store_true')
    a = ap.parse_args(argv)
    payloads = []
    if a.action in ('integers', 'all'):
        payloads.append(integers(a.n, a.seed, a.cc, a.emit_only))
    if a.action in ('loops', 'all'):
        payloads.append(loops(a.loops, a.inputs, a.seed + 1, a.cc, a.emit_only))
    summarise(payloads)


if __name__ == '__main__':
    main()
