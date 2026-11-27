"""v1.03: disposition of loops that contain jumps, and of everything the front end rejects.

The paper has to say what happens to loops with `goto` / `break` / `continue` / early `return`, and
what an UNSUPPORTED row means. Two things are measured here, both on the frozen 165-case corpus:

  census    for every case, the rejection reason the frozen pipeline recorded, re-derived from the
            sources at the pinned svbench commit (and compared with the recorded row, so a reader can
            see the local re-derivation agrees with the CI run), plus a *static* classification of the
            jumps and calls each file actually contains;

  recover   for cases rejected only because a `return` sits inside a loop, apply the shipped
            normalisation (`llmloop.jump_eliminate.eliminate_jumps`, which rewrites break/continue/
            return-in-loop into flag variables and is itself checked by native differential tests) and
            translate again. This separates "the fragment cannot express it" from "the frozen
            pipeline does not run the normaliser".

Preprocessing: the frozen pipeline runs `gcc -E -nostdinc`. This script reproduces the same text in
Python (drop directives, expand object-like #define) so the census can be reproduced without a C
compiler; `--compare` shows whether the re-derived verdicts match the recorded ones.

usage:
  unsupported_jumps_v103.py census  --cases P.json --root DIR --recorded DIR [--out DIR] [--limit N]
  unsupported_jumps_v103.py recover --cases P.json --root DIR [--out DIR] [--limit N]
"""

import argparse
import collections
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pycparser import c_ast, c_generator, c_parser  # noqa: E402

OUT = ROOT / 'experiments' / 'v103' / 'unsupported_jumps'
GEN = c_generator.CGenerator()
LOOPS = (c_ast.While, c_ast.For, c_ast.DoWhile)
MACRO_RE = re.compile(r'#\s*define\s+([A-Za-z_]\w*)\s+(.+)$')


def walk(node):
    stack = [node]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(reversed([c for _, c in x.children()]))


def preprocess(path):
    """Same shape as `gcc -E -nostdinc` for this corpus: no standard headers, object-like #define."""
    text = path.read_text(encoding='utf-8', errors='replace')
    text = re.sub(r'/\*.*?\*/', ' ', text, flags=re.S)
    text = re.sub(r'//[^\n]*', '', text)
    defines, kept, dropped = {}, [], 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            m = MACRO_RE.match(stripped)
            if m:
                defines[m.group(1)] = m.group(2).strip()
            elif stripped.startswith('#define'):
                dropped += 1  # function-like macro: not modelled, and not used by this corpus
            continue
        kept.append(line)
    body = '\n'.join(kept)
    for name, value in defines.items():
        body = re.sub(r'\b%s\b' % re.escape(name), value, body)
    return 'typedef unsigned long size_t;\n' + body, {'defines': len(defines), 'unmodelled_defines': dropped}


def parse_text(text):
    return c_parser.CParser().parse(text)


def classify(ast, entry='main'):
    """What the translation unit contains, independent of whether the front end accepts it.

    Two scopes are reported, because the front end only reads `entry`, while a census of "does this
    program contain a loop with a jump" has to look at every function: several corpus cases put the
    loop in a helper and call it from `main`.
    """
    info = {'goto': 0, 'labels': 0, 'switch': 0, 'do_while': 0,
            'break_in_loop': 0, 'continue_in_loop': 0, 'return_in_loop': 0,
            'loops': 0, 'nested_loops': 0,
            'loops_in_entry': 0, 'return_in_loop_entry': 0, 'goto_entry': 0,
            'calls': sorted({getattr(n.name, 'name', '?') for n in walk(ast)
                             if isinstance(n, c_ast.FuncCall)})}

    def rec(n, loop_depth, in_entry):
        for _, c in n.children():
            here = in_entry
            if isinstance(c, c_ast.Goto):
                info['goto'] += 1
                info['goto_entry'] += int(in_entry)
            elif isinstance(c, c_ast.Label):
                info['labels'] += 1
            elif isinstance(c, c_ast.Switch):
                info['switch'] += 1
            elif isinstance(c, c_ast.DoWhile):
                info['do_while'] += 1
            if isinstance(c, LOOPS):
                info['loops'] += 1
                info['loops_in_entry'] += int(in_entry)
                info['nested_loops'] += int(loop_depth > 0)
                rec(c.stmt, loop_depth + 1, here)
            else:
                if isinstance(c, c_ast.Break) and loop_depth > 0:
                    info['break_in_loop'] += 1
                elif isinstance(c, c_ast.Continue) and loop_depth > 0:
                    info['continue_in_loop'] += 1
                elif isinstance(c, c_ast.Return) and loop_depth > 0:
                    info['return_in_loop'] += 1
                    info['return_in_loop_entry'] += int(in_entry)
                rec(c, loop_depth, here)

    for node in ast.ext:
        if isinstance(node, c_ast.FuncDef):
            rec(node.body, 0, node.decl.name == entry)
        else:
            rec(node, 0, False)
    entry_funcs = [n for n in ast.ext if isinstance(n, c_ast.FuncDef) and n.decl.name == entry]
    if entry_funcs:
        body = entry_funcs[0].body.block_items or []
        info['return_in_body_nonfinal'] = sum(
            1 for k, s in enumerate(body)
            if not (k == len(body) - 1 and isinstance(s, c_ast.Return))
            for n in walk(s) if isinstance(n, c_ast.Return))
    else:
        info['return_in_body_nonfinal'] = None
    info['has_jump'] = any(info[k] for k in ('goto', 'break_in_loop', 'continue_in_loop', 'return_in_loop'))
    info['has_jump_in_entry'] = any(info[k] for k in ('goto_entry', 'return_in_loop_entry'))
    return info


def bucket(reason):
    if not reason:
        return 'accepted'
    if 'alloca' in reason or 'malloc' in reason or 'call inside program body' in reason:
        return 'heap or external call'
    if 'pointer' in reason or 'array' in reason:
        return 'pointer or array'
    if 'early return' in reason:
        return 'return in body (not trailing)'
    if 'assumption after statements' in reason:
        return 'assumption not in prefix'
    if 'goto' in reason or 'label' in reason:
        return 'goto'
    if 'switch' in reason:
        return 'switch'
    if 'array' in reason:
        return 'pointer or array'
    return 'other'


def load_cases(protocol):
    data = json.loads(Path(protocol).read_text())
    pin = data.get('svbench_pin') or data.get('nist_pin') or data.get('tacle_pin') or 'unpinned'
    # full165 stores the corpus-relative path in `name`; the other protocols carry it separately
    return [(c['name'], c.get('path', c['name'])) for c in data['cases']], pin


def recorded_reasons(recorded):
    """case name -> (status, reason) from the frozen run, if the raw rows are present."""
    out = {}
    root = Path(recorded) / 'raw'
    if not root.is_dir():
        return out
    for d in sorted(root.iterdir()):
        try:
            req = json.loads((d / 'request.json').read_text())
            res = json.loads((d / 'result.json').read_text())
        except (OSError, ValueError):
            continue
        if req['tool'] != 'llmloop':
            continue
        out[req['case']['name']] = (res.get('status'), res.get('reason', ''))
    return out


def census(cases, root, recorded, out, limit, label=None):
    import scripts.svcomp_translate as T
    T.NOOVF = True
    T.GHOST = True
    seen = recorded_reasons(recorded) if recorded else {}
    original_parse = T.parse
    pre = {}
    rows, agree, disagree = [], 0, []

    def local_parse(path):
        text, stats = preprocess(Path(path))
        pre[str(path)] = stats
        return parse_text(text)

    T.parse = local_parse
    try:
        for name, rel in cases[:limit]:
            p = Path(root) / rel
            row = {'name': name, 'path': rel}
            try:
                row['constructs'] = classify(parse_text(preprocess(p)[0]))
            except Exception as exc:
                row['constructs'] = None
                row['parse_error'] = type(exc).__name__ + ': ' + str(exc)[:120]
            try:
                T.translate(p)
                row['status'], row['reason'] = 'TRANSLATED', ''
            except Exception as exc:
                row['status'] = 'UNSUPPORTED'
                row['reason'] = str(exc)[:200]
            row['bucket'] = bucket(row['reason']) if row['status'] == 'UNSUPPORTED' else 'accepted'
            if name in seen:
                rec_status, rec_reason = seen[name]
                row['recorded_status'], row['recorded_reason'] = rec_status, rec_reason
                # an accepted row compares as "the frozen run did not reject it either"; a rejected
                # row must agree on the reason itself
                same = ((row['status'] == 'UNSUPPORTED' and rec_status == 'UNSUPPORTED'
                         and row['reason'] == rec_reason)
                        or (row['status'] == 'TRANSLATED' and rec_status != 'UNSUPPORTED'))
                row['agrees_with_recorded'] = same
                agree += int(same)
                if not same:
                    disagree.append({'name': name, 'local': [row['status'], row['reason']],
                                     'recorded': [rec_status, rec_reason]})
            rows.append(row)
    finally:
        T.parse = original_parse

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {'cases_file': str(cases), 'corpus_root': str(root),
               'corpus_label': label or str(root), 'rows': rows,
               'unmodelled_defines': sum(s['unmodelled_defines'] for s in pre.values()),
               'compared': len([r for r in rows if 'agrees_with_recorded' in r]),
               'agree': agree, 'disagree': disagree}
    (OUT / 'census.json').write_text(json.dumps(payload, indent=1) + '\n')
    summary_md(payload)
    print(json.dumps({'cases': len(rows), 'compared': payload['compared'], 'agree': agree,
                      'disagree': len(disagree),
                      'buckets': dict(collections.Counter(r['bucket'] for r in rows))}, ensure_ascii=False, indent=1))


def summary_md(payload):
    rows = payload['rows']
    buckets = collections.Counter(r['bucket'] for r in rows)
    c = lambda k: len([r for r in rows if (r.get('constructs') or {}).get(k)])  # noqa: E731
    md = ['# v1.03 含跳转循环与 UNSUPPORTED 处置 / Loops with jumps, and what UNSUPPORTED means', '',
          '语料 / corpus: `%s`，共 %d 例。`scripts/unsupported_jumps_v103.py` 在钉住版本上重算拒绝理由，'
          '并静态统计每个翻译单元（不只 `main`）里实际出现的跳转构造。'
          % (payload['corpus_label'], len(rows)), '',
          '## 拒绝理由', '', '| 分类 | 例数 |', '|---|---|']
    for k, v in buckets.most_common():
        md.append('| %s | %d |' % (k, v))
    md += ['', '## 静态构造', '', '| 构造 | 全文件 | 仅 `main` |', '|---|---|---|',
           '| `goto` | %d | %d |' % (c('goto'), c('goto_entry')),
           '| `switch` | %d | — |' % c('switch'),
           '| 循环内 `break` | %d | — |' % c('break_in_loop'),
           '| 循环内 `continue` | %d | — |' % c('continue_in_loop'),
           '| 循环内 `return` | %d | %d |' % (c('return_in_loop'), c('return_in_loop_entry')),
           '| 任意跳转 | %d | — |' % c('has_jump'),
           '| 嵌套循环 | %d | — |' % c('nested_loops'),
           '| 无循环（主循环在被调函数里） | %d | %d |'
           % (len([r for r in rows if (r.get('constructs') or {}).get('loops') == 0]),
              len([r for r in rows if (r.get('constructs') or {}).get('loops_in_entry') == 0])),
           '', '## 跳转构造 × 判定', '',
           '| 含跳转构造 | 分布（判定: 例数） |', '|---|---|']
    for key, label in [('goto', '`goto`'), ('break_in_loop', '循环内 `break`'),
                       ('continue_in_loop', '循环内 `continue`'), ('return_in_loop', '循环内 `return`'),
                       ('has_jump', '任意跳转')]:
        dist = collections.Counter(r['bucket'] for r in rows if (r.get('constructs') or {}).get(key))
        md.append('| %s | %s |' % (label, '，'.join('%s: %d' % kv for kv in dist.most_common()) or '—'))
    md.append('')
    if payload['compared']:
        md += ['## 与冻结记录的一致性', '',
               '本地重算（无 C 编译器，改用等价的 Python 预处理）与冻结运行逐例对照：%d/%d 一致，%d 例不一致。'
               % (payload['agree'], payload['compared'], len(payload['disagree'])), '']
        for d in payload['disagree'][:20]:
            md.append('- `%s`: 本地 %s / 记录 %s' % (d['name'], d['local'], d['recorded']))
        if payload['disagree']:
            md.append('')
    (OUT / 'summary.md').write_text('\n'.join(md) + '\n')


def load_eliminate_jumps():
    """`llmloop.jump_eliminate` only needs pycparser; load it by path when the package's sympy/
    z3 imports are unavailable, so the census can be reproduced on a bare interpreter."""
    try:
        from llmloop.jump_eliminate import eliminate_jumps
        return eliminate_jumps
    except ModuleNotFoundError:
        import importlib.util
        spec = importlib.util.spec_from_file_location('_jump_eliminate', ROOT / 'llmloop' / 'jump_eliminate.py')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.eliminate_jumps


def recover(cases, root, out, limit, label=None):
    """For 'early return in body' rejections, run the shipped normaliser and translate again."""
    import scripts.svcomp_translate as T
    eliminate_jumps = load_eliminate_jumps()
    T.NOOVF = True
    T.GHOST = True
    original_parse = T.parse
    rows = []

    def local_parse(path):
        return parse_text(preprocess(Path(path))[0])

    T.parse = local_parse
    try:
        for name, rel in cases[:limit]:
            p = Path(root) / rel
            try:
                T.translate(p)
                continue  # already accepted; nothing to recover
            except Exception as exc:
                reason = str(exc)
            if 'early return' not in reason:
                continue
            row = {'name': name, 'path': rel, 'original_reason': reason[:200]}
            try:
                ast = local_parse(p)
                funcs = [n for n in ast.ext if isinstance(n, c_ast.FuncDef) and n.decl.name == 'main']
                notes = eliminate_jumps(funcs[0])
                row['notes'] = notes
                if not notes:
                    row['after'] = 'NOT_NORMALISED'
                else:
                    text = GEN.visit(ast)
                    with tempfile.NamedTemporaryFile('w', suffix='.c', delete=False, encoding='utf-8') as fh:
                        fh.write(text)
                        tmp = Path(fh.name)
                    try:
                        T.translate(tmp)
                        row['after'] = 'TRANSLATED'
                    except Exception as exc2:
                        row['after'] = 'STILL_REJECTED: ' + str(exc2)[:160]
                    finally:
                        tmp.unlink(missing_ok=True)
            except Exception as exc:
                row['after'] = 'NORMALISER_FAILED: ' + type(exc).__name__ + ': ' + str(exc)[:160]
            rows.append(row)
    finally:
        T.parse = original_parse

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {'corpus_root': str(root), 'corpus_label': label or str(root), 'rows': rows,
               'recovered': len([r for r in rows if r['after'] == 'TRANSLATED']), 'examined': len(rows)}
    (OUT / 'recover.json').write_text(json.dumps(payload, indent=1) + '\n')
    md = ['# v1.03 循环内 return 能否被归一化恢复 / Can an in-body return be recovered', '',
          '对冻结流水线判为 `early return in body` 的 %d 例（函数体里出现非末尾 `return`，包括循环内 return 与'
          ' `if (...) return 0;` 式的提前退出），先跑仓库自带的 `eliminate_jumps`（把 break/continue/循环内'
          ' return 改写成标志变量），再重新翻译。这一项区分「片段表达不了」与「冻结流水线没接归一化」。'
          % len(rows), '',
          '| 用例 | 归一化后 |', '|---|---|']
    for r in rows:
        md.append('| `%s` | %s |' % (r['name'], r['after']))
    md += ['', '恢复成功 / recovered: **%d/%d**' % (payload['recovered'], payload['examined']), '']
    (OUT / 'recover.md').write_text('\n'.join(md) + '\n')
    print(json.dumps({'examined': len(rows), 'recovered': payload['recovered']}, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=['census', 'recover'])
    ap.add_argument('--cases', required=True)
    ap.add_argument('--root', required=True)
    ap.add_argument('--recorded')
    ap.add_argument('--out')
    ap.add_argument('--limit', type=int, default=None)
    a = ap.parse_args(argv)
    global OUT
    if a.out:
        OUT = Path(a.out)
    cases, pin = load_cases(a.cases)
    label = 'svbench @ %s' % pin
    if a.action == 'census':
        census(cases, a.root, a.recorded, OUT, a.limit, label)
    else:
        recover(cases, a.root, OUT, a.limit, label)


if __name__ == '__main__':
    main()
