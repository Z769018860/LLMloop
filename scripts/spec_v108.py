"""v1.08 / E6d: the same pairing at the expensive price, because one price point is not a trend.

v1.07 answered the question at $0.15 per million input tokens. A reviewer's first objection to that
arm is not its arithmetic but its representativeness: a single cheap model cannot separate "the model
does not help" from "this model cannot help". This arm repeats the identical 83-program pairing with
`claude-sonnet-4-5-20250929` at the same 2,048-token cap, so the two arms differ in exactly one
declared variable -- which model answered, and what that cost.

What is shared, byte for byte: the population (copied from the v1.06 protocol and hash-checked), the
control arm B2 (17/83 at 1,527 verification attempts, reused and not re-run), the prompt and the
system message (imported from v1.05, hashed), the verifier, and the decision rule (imported as code,
not restated). What differs: the model name. That is the whole point -- if the cheap arm and the
expensive arm both fail to beat the control, the finding is about the position in the market, not
about the size of the budget.

Cost: 83 calls, about $1.2 at list price. The v1.07 rows are NOT pooled with these. Two models are
two measurements, and adding them to raise n is the cross-arm error this study exists to document.
"""
import argparse
import collections
import json
import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import llm_stream                       # noqa: E402
from scripts import spec_v105 as v105                # noqa: E402
from scripts import spec_v106 as v106                # noqa: E402
from scripts import spec_v107 as v107                # noqa: E402
from scripts.heldout_v104 import mcnemar_exact       # noqa: E402

OUT = ROOT / 'experiments/v108/e6d'

# The arm is data, not configuration. One model, one cap, one sample per case, declared here and
# written into the protocol before any call.
MODEL = 'claude-sonnet-4-5-20250929'
MAXTOK = 2048
REPEATS = 1
TEMP = 0.7
STALL, WALL = 90.0, 1800.0
# Hard stops. A guard that is checked before every submission is the difference between "the run
# spent what it was supposed to" and "the run spent what it happened to".
MAX_CALLS = 83
MAX_TOKENS = 250_000          # 83 x (404 prompt + 2048 cap) = 203 k; the stop is real

MATERIAL_LADDER = v106.MATERIAL_LADDER
CONTROL_SOURCE = ROOT / 'experiments/v106/e6b/baseline.json'
CONTROL_PROTOCOL = ROOT / 'experiments/v106/e6b/protocol.json'
PRIOR_ARM = ROOT / 'experiments/v106/e6b/results.json'
V105_RESULTS = ROOT / 'experiments/v105/spec/results.json'

save, sha, shatext = v105.save, v105.sha, v105.shatext
STATUSES = v106.STATUSES + ('BUDGET_STOP',)


def load(out):
    out = Path(out)
    return (json.loads((out / 'protocol.json').read_text(encoding='utf-8')),
            json.loads((out / 'schedule.json').read_text(encoding='utf-8')))


def cases_payload(cases):
    return [{'name': c['corpus'] + '/' + c['name'], 'source': c['source'],
             'bounds': c['bounds'], 'abi': c['abi']} for c in cases]


# --------------------------------------------------------------------------------------------------
# freeze
# --------------------------------------------------------------------------------------------------

def freeze(out):
    """Write the protocol before the first call. Everything that could change the answer is in it.

    The population is *copied* from the v1.06 protocol and then checked: the same 83 programs, the
    same bounds, the same source and translation hashes. A replan that quietly re-derived its
    population would be a new study wearing the old one's name.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    prior = json.loads(CONTROL_PROTOCOL.read_text(encoding='utf-8'))
    cases = prior['cases']
    assert len(cases) == 83, len(cases)
    save(out / 'cases_payload.json', cases_payload(cases))
    assert sha(out / 'cases_payload.json') == prior['cases_payload_sha256'], \
        'the population is not the v1.06 population'

    base = {r['case']: r for r in json.loads(CONTROL_SOURCE.read_text(encoding='utf-8'))['rows']}
    b_proved = [c for c in base if base[c]['status'] == 'PROVED']
    b_timeout = [c for c in base if base[c]['status'] == 'TIMEOUT']
    attempts = sum(r.get('attempts') or 0 for r in base.values())

    files = [ROOT / 'scripts/spec_v108.py', ROOT / 'scripts/llm_stream.py',
             ROOT / 'scripts/spec_v105.py', ROOT / 'scripts/spec_v106.py',
             ROOT / 'scripts/heldout_v104.py', ROOT / 'scripts/resource_capture.py']
    plan = {
        'study': 'v1.08 / E6d',
        'purpose': 'the same 83-program pairing as v1.06 and v1.07 (contract arm vs the extended '
                   'model-free control) at a second price point, so that "one cheap model failed" is '
                   'not the whole evidence. Control and prior arms reused, not re-run.',
        'base_commit': subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                                      text=True).stdout.strip(),
        'follows': 'experiments/v107/e6c -- the same pairing at $0.15/M input. Its rows are NOT '
                   'pooled here: two models are two measurements. What is repeated is the design.',
        'deviation_from_v107': [
            {'what': 'model', 'was': v107.MODEL, 'now': MODEL,
             'why': 'v1.07 answered at $0.15/M input with one cheap model, which leaves "the model '
                    'does not help" and "this model cannot help" observationally identical. This arm '
                    'buys the difference: the same prompt, caps, population, control and verifier, '
                    'one more expensive model. It is a scope repair, not a re-test -- if both arms '
                    'land behind the control, the claim stops being about price.'},
            {'what': 'everything else', 'was': 'v1.07', 'now': 'unchanged',
             'why': 'the population is copied from v1.06 and hash-checked, the control is the same '
                    'committed baseline, the prompt and system message are imported from v1.05 and '
                    'hashed, and the decision rule is imported as code. A second price point that '
                    'also moved the design would not be a second price point.'}],
        'population': 'the 83 programs of the v1.06 protocol, copied and hash-checked '
                      '(cases_payload_sha256 equal to that protocol\'s). 14 true, 69 false.',
        'task': 'one call: the model states a box on the parameters; the frozen pipeline is re-run '
                'inside it; the outcome is conditional on the box and reported with the retained '
                'fraction. Prompt, system message, temperature and verifier imported from v1.05.',
        'control': 'NOT RUN HERE. Reused from experiments/v106/e6b/baseline.json: %d / %d proved, '
                   '%d verification attempts, %d case TIMEOUT, and the five-case 4x-budget '
                   'sensitivity in experiments/v106/e6b_sensitivity/ (0 of 5 proved at 3600 s). '
                   'Copied file hash checked at freeze time.' % (len(b_proved), len(base), attempts,
                                                                 len(b_timeout)),
        'control_sha256': sha(CONTROL_SOURCE),
        'decision_rule': 'unchanged from v1.06, and the code that applies it is imported, not '
                         'rewritten: at each floor t in %s, pair the arms on the 83 cases and '
                         'compute exact McNemar over the discordant pairs; the contract arm is '
                         'credited only if at EVERY rung where either arm claims anything, only-S '
                         'exceeds only-B with p < 0.05.' % (MATERIAL_LADDER,),
        'model': MODEL, 'max_tokens': MAXTOK, 'repeats': REPEATS, 'temperature': TEMP,
        'streaming': {'stream': True, 'include_usage': True, 'stall_seconds': STALL,
                      'wall_seconds': WALL, 'cache_dir': 'experiments/llm_cache',
                      'token_estimate_chars_per_token': llm_stream.CHARS_PER_TOKEN},
        'system_prompt_sha256': shatext(v105.SYSTEM),
        'prompt_source': 'scripts/spec_v105.py:prompt -- imported, not copied, and hashed above',
        'budgets': {'max_calls': MAX_CALLS, 'max_tokens': MAX_TOKENS,
                    'ask_wall_seconds': int(WALL) + 120, 'ask_memory_bytes': 1 << 30,
                    'verify_wall_seconds': v105.CASE_SECONDS, 'verify_memory_bytes': 2 * 1024 ** 3},
        'seeds': {'schedule': 20261125, 'houdini': v105.SEED},
        'cases': cases, 'cases_payload_sha256': sha(out / 'cases_payload.json'),
        'reuse': {
            'control_e6b': {'file': 'experiments/v106/e6b/baseline.json', 'proved': len(b_proved),
                            'cases': len(base), 'attempts': attempts, 'calls': 0},
            'control_sensitivity': {'file': 'experiments/v106/e6b_sensitivity/', 'proved': 0,
                                    'cases': 5, 'attempts': 46, 'calls': 0},
            'prior_arm_e6b': {'file': 'experiments/v106/e6b/results.json', 'rows': 249,
                              'answered': 18, 'pooled': False,
                              'why': 'different model and cap; kept as a record, not as evidence'},
            'prior_arm_v105': {'file': 'experiments/v105/spec/results.json', 'rows': 747,
                               'pooled': False,
                               'why': 'different cap (1500); used as the cap-sensitivity column, '
                                      'not as this arm'},
            'cache': {'dir': 'experiments/llm_cache',
                      'why': 'any body identical to one already paid for returns from disk at 0 calls'}},
        'frozen_source_sha256': {str(p.relative_to(ROOT).as_posix()): sha(p) for p in files},
    }
    save(out / 'protocol.json', plan)
    units = [{'case': i, 'model': MODEL, 'repeat': 0} for i in range(len(cases))]
    save(out / 'schedule.json', units)
    print(json.dumps({'cases': len(cases), 'units': len(units), 'model': MODEL, 'cap': MAXTOK,
                      'control_proved': len(b_proved), 'control_sha256': plan['control_sha256'][:12]},
                     indent=1))
    return plan


def check(out):
    """Bytes, not vibes: is the committed freeze still the freeze?"""
    out = Path(out)
    plan = json.loads((out / 'protocol.json').read_text(encoding='utf-8'))
    bad = [p for p, h in plan['frozen_source_sha256'].items()
           if not (ROOT / p).exists() or sha(ROOT / p) != h]
    assert not bad, 'code changed since freeze: %s' % bad
    assert sha(out / 'cases_payload.json') == plan['cases_payload_sha256'], 'population moved'
    assert sha(CONTROL_SOURCE) == plan['control_sha256'], 'the control it compares against moved'
    print(json.dumps({'check': 'ok', 'sources': len(plan['frozen_source_sha256']),
                      'cases': len(plan['cases']), 'control': plan['control_sha256'][:12]}))
    return 0


# --------------------------------------------------------------------------------------------------
# one unit
# --------------------------------------------------------------------------------------------------

def ask(out, index):
    out = Path(out)
    plan, units = load(out)
    unit = units[index]
    meta = plan['cases'][unit['case']]
    d = out / 'raw' / ('%04d' % index)
    d.mkdir(parents=True, exist_ok=True)
    assert plan['max_tokens'] == MAXTOK, 'frozen cap %s, this code sends %d' % (plan['max_tokens'],
                                                                               MAXTOK)
    assert plan['model'] == MODEL, 'frozen model %s, this code sends %s' % (plan['model'], MODEL)
    text = v105.prompt(meta)
    key = os.environ.get('LLM_API_KEY')
    base = os.environ.get('LLM_BASE_URL') or v105.DEFAULT_BASE
    rec = llm_stream.stream_chat(MODEL, [{'role': 'system', 'content': v105.SYSTEM},
                                         {'role': 'user', 'content': text}], key, base,
                                 temperature=TEMP, max_tokens=MAXTOK,
                                 stall=STALL, wall=WALL)
    rec['prompt_sha256'] = shatext(text)
    rec['prompt_text'] = text
    pre, err = v105.parse_spec(rec.get('content'))
    save(d / 'call.json', rec)
    out_rec = {'index': index, 'case': meta['corpus'] + '/' + meta['name'],
               'expected': meta['expected'], 'model': MODEL, 'repeat': unit['repeat'],
               'model_reply': rec.get('content'), 'served_model': rec.get('served_model'),
               'finish_reason': rec.get('finish_reason'), 'cached': bool(rec.get('cached')),
               'aborted': rec.get('aborted'), 'ttft': rec.get('ttft'),
               'tokens_estimated': bool(rec.get('tokens_estimated')),
               'seconds': rec.get('seconds'), 'tokens': v105.tokens(rec.get('usage')),
               'reasoning_tokens': v106.reasoning_tokens(rec),
               'parse_error': err, 'pre': pre}
    if pre is not None:
        bounds, info = v105.narrow(meta['bounds'], pre)
        out_rec.update({'narrowed': bounds, 'retained': v105.volume(meta['bounds'], bounds),
                        'per_dim': v105.per_dim(meta['bounds'], bounds),
                        'widened': info['widened'], 'unknown_parameters': info['unknown'],
                        'shrunk': info['shrunk'], 'empty_interval': info['empty'],
                        'aliased': info['aliased']})
    save(d / 'spec.json', out_rec)
    print(json.dumps({'index': index, 'case': out_rec['case'], 'cached': out_rec['cached'],
                      'parsed': pre is not None, 'retained': out_rec.get('retained'),
                      'ct': out_rec['tokens'].get('completion')}), flush=True)


def verify(out, index):
    out = Path(out)
    plan, units = load(out)
    unit = units[index]
    d = out / 'raw' / ('%04d' % index)
    spec = json.loads((d / 'spec.json').read_text(encoding='utf-8'))
    meta = plan['cases'][unit['case']]
    if spec['pre'] is None:
        res = {'status': 'MALFORMED', 'phases': []}
    elif spec['empty_interval']:
        res = {'status': 'VACUOUS', 'phases': []}
    else:
        status, phases = v105.prove(meta['source'], spec['narrowed'], meta['abi'])
        res = {'status': status, 'phases': phases}
    res.update({'index': index, 'case': spec['case'], 'model': MODEL,
                'repeat': unit['repeat'], 'retained': spec.get('retained'),
                'expected': meta['expected']})
    save(d / 'verify.json', res)
    print(json.dumps({'index': index, 'status': res['status']}), flush=True)


def one_unit(out, plan, units, i):
    from scripts.resource_capture import capture
    out = Path(out)
    d = out / 'raw' / ('%04d' % i)
    d.mkdir(parents=True, exist_ok=True)
    u = units[i]
    ask_run = ver_run = None
    if not (d / 'spec.json').exists():
        ask_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'ask',
                           '--output', str(out), '--index', str(i)], d / 'ask',
                          wall_seconds=plan['budgets']['ask_wall_seconds'],
                          memory_bytes=plan['budgets']['ask_memory_bytes'])
    if (d / 'spec.json').exists() and not (d / 'verify.json').exists():
        ver_run = capture([sys.executable, '-u', str(Path(__file__).resolve()), 'verify',
                           '--output', str(out), '--index', str(i)], d / 'ver',
                          wall_seconds=plan['budgets']['verify_wall_seconds'],
                          memory_bytes=plan['budgets']['verify_memory_bytes'])
    stop = (ask_run or {}).get('stop_reason') or (ver_run or {}).get('stop_reason')
    spec = json.loads((d / 'spec.json').read_text(encoding='utf-8')) \
        if (d / 'spec.json').exists() else {}
    ver = json.loads((d / 'verify.json').read_text(encoding='utf-8')) \
        if (d / 'verify.json').exists() else {}
    meta = plan['cases'][u['case']]
    tok = spec.get('tokens') or {}
    call_rec = json.loads((d / 'call.json').read_text(encoding='utf-8')) \
        if (d / 'call.json').exists() else {}
    transport = call_rec.get('transport_error')
    if not transport and call_rec and call_rec.get('aborted'):
        transport = 'aborted: ' + str(call_rec.get('aborted'))
    if stop:
        status = 'RESOURCE_STOP'
    elif transport:
        status = 'NOT_ANSWERED'
    else:
        status = ver.get('status', 'NOT_VERIFIED')
    row = {'index': i, 'case': meta['corpus'] + '/' + meta['name'], 'corpus': meta['corpus'],
           'expected': meta['expected'], 'model': MODEL, 'repeat': u['repeat'],
           'transport_error': transport, 'status': status,
           'retained': spec.get('retained'), 'pre': spec.get('pre'),
           'narrowed': spec.get('narrowed'), 'shrunk': spec.get('shrunk'),
           'empty_interval': spec.get('empty_interval'), 'parse_error': spec.get('parse_error'),
           'model_reply': spec.get('model_reply'), 'finish_reason': spec.get('finish_reason'),
           'served_model': spec.get('served_model'), 'cached': bool(spec.get('cached')),
           'aborted': spec.get('aborted'), 'ttft': spec.get('ttft'),
           'tokens_estimated': bool(spec.get('tokens_estimated')),
           'prompt_tokens': tok.get('prompt'), 'completion_tokens': tok.get('completion'),
           'reasoning_tokens': spec.get('reasoning_tokens'), 'seconds': spec.get('seconds'),
           'phases': ver.get('phases'), 'ask_stop_reason': (ask_run or {}).get('stop_reason'),
           'verify_stop_reason': (ver_run or {}).get('stop_reason')}
    save(d / 'outcome.json', row)
    return row


def _safe_unit(out, plan, units, i):
    try:
        return one_unit(out, plan, units, i)
    except Exception:
        tb = traceback.format_exc()
        meta = plan['cases'][units[i]['case']]
        row = {'index': i, 'case': meta['corpus'] + '/' + meta['name'],
               'corpus': meta['corpus'], 'expected': meta['expected'], 'model': MODEL,
               'repeat': units[i]['repeat'], 'status': 'HARNESS_ERROR', 'retained': None,
               'pre': None, 'phases': [], 'traceback': tb[-4000:], 'calls': 0}
        save(Path(out) / 'raw' / ('%04d' % i) / 'outcome.json', row)
        print(json.dumps({'index': i, 'status': 'HARNESS_ERROR',
                          'error': tb.strip().splitlines()[-1][:200]}), flush=True)
        return row


def finished(out, i):
    return (Path(out) / 'raw' / ('%04d' % i) / 'outcome.json').exists()


def budget_left(plan, calls, tokens):
    return (calls < plan['budgets']['max_calls']
            and tokens < plan['budgets']['max_tokens'])


def run(out, workers=4, limit=None):
    """Submit in batches of `workers` so the budget can be checked between submissions.

    A guard that runs after the whole list is submitted is not a guard: 83 concurrent calls cannot
    be un-placed. Batches make `max_calls` a number the run honours rather than a number it reports.
    """
    out = Path(out)
    plan, units = load(out)
    assert plan['max_tokens'] == MAXTOK and plan['model'] == MODEL
    bad = [p for p, h in plan['frozen_source_sha256'].items()
           if not (ROOT / p).exists() or sha(ROOT / p) != h]
    assert not bad, 'code changed since freeze: %s' % bad
    todo = [i for i in range(len(units)) if not finished(out, i)]
    if limit is not None:
        todo = todo[:limit]
    calls = tokens = 0
    rows = []
    stopped = None
    for start in range(0, len(todo), max(1, workers)):
        if not budget_left(plan, calls, tokens):
            stopped = 'budget'
            break
        batch = todo[start:start + max(1, workers)]
        with ThreadPoolExecutor(len(batch)) as pool:
            for f in as_completed([pool.submit(_safe_unit, out, plan, units, i) for i in batch]):
                r = f.result()
                rows.append(r)
                if not r.get('cached'):
                    calls += 1
                tokens += (r.get('prompt_tokens') or 0) + (r.get('completion_tokens') or 0)
                print(json.dumps({'done': len(rows), 'of': len(todo), 'papered_calls': calls,
                                  'tokens': tokens,
                                  'counts': dict(collections.Counter(x['status'] for x in rows))}),
                      flush=True)
                if not budget_left(plan, calls, tokens):
                    stopped = 'budget'
                    break
        if stopped:
            break
    left = [i for i in range(len(units)) if not finished(out, i)]
    print(json.dumps({'finished': len(units) - len(left), 'of': len(units), 'calls': calls,
                      'tokens': tokens, 'stopped': stopped}, indent=1))
    return 0


# --------------------------------------------------------------------------------------------------
# merge
# --------------------------------------------------------------------------------------------------

def rows_from(out):
    out = Path(out)
    rows = []
    for d in sorted((out / 'raw').glob('[0-9][0-9][0-9][0-9]')):
        f = d / 'outcome.json'
        if f.exists():
            rows.append(json.loads(f.read_text(encoding='utf-8')))
    return sorted(rows, key=lambda r: r['index'])


def ladder(rows, base, cases):
    """The v1.06 rule, applied to this arm's rows. `v106.decide` is imported, not re-implemented."""
    def s_proved(c, t):
        return any(r['status'] == 'PROVED' and (r.get('retained') or 0) >= t
                   for r in rows if r['case'] == c)

    def b_proved(c, t):
        b = base.get(c)
        return bool(b) and b['status'] == 'PROVED' and (b.get('retained') or 0) >= t

    out = []
    for t in MATERIAL_LADDER:
        S = {c for c in cases if s_proved(c, t)}
        B = {c for c in cases if b_proved(c, t)}
        only_s, only_b = len(S - B), len(B - S)
        out.append({'t': t, 'only_s': only_s, 'only_b': only_b, 'both': len(S & B),
                    'neither': len(set(cases) - S - B), 'p': mcnemar_exact(only_s, only_b),
                    'only_s_cases': sorted(S - B), 'only_b_cases': sorted(B - S)})
    return out


def merge(out):
    out = Path(out)
    plan, units = load(out)
    rows = rows_from(out)
    base = {r['case']: r for r in json.loads(CONTROL_SOURCE.read_text(encoding='utf-8'))['rows']}
    cases = [c['corpus'] + '/' + c['name'] for c in plan['cases']]
    assert sha(CONTROL_SOURCE) == plan['control_sha256'], 'the control moved under the arm'
    st = collections.Counter(r['status'] for r in rows)
    bad = sorted(set(st) - set(STATUSES))
    assert not bad, 'unnamed status: %s' % bad

    complete = len(rows) == len(units)
    not_answered = st.get('NOT_ANSWERED', 0)
    void = not_answered > 0
    lad = ladder(rows, base, cases)
    verdict = v106.decide(lad)

    paid = [r for r in rows if not r.get('cached')]
    hits = [r for r in rows if r.get('cached')]
    pt = sum((r.get('prompt_tokens') or 0) for r in paid)
    ct = sum((r.get('completion_tokens') or 0) for r in paid)
    rt = [r.get('reasoning_tokens') for r in paid if r.get('reasoning_tokens') is not None]
    live = sum((r.get('seconds') or 0) for r in paid)
    ttfts = sorted(r['ttft'] for r in rows if r.get('ttft') is not None)

    L = ['# v1.08 / E6d —— 同一个配对，换一个价位', '',
         '> 协议在任何一次真实调用之前提交。本臂 **%d 个单元**（%d 例 × 1 模型 × %d 次重复），'
         '模型 `%s`、上限 %d、流式。对照臂**未重跑**：%d/83 来自 `experiments/v106/e6b/baseline.json`'
         '（%d 次验证尝试，sha256 `%s`）。'
         % (len(units), len(cases), plan['repeats'], MODEL, MAXTOK,
            sum(1 for v in base.values() if v['status'] == 'PROVED'),
            sum(v.get('attempts') or 0 for v in base.values()), plan['control_sha256'][:12]), '']
    if void:
        L += ['> ## ⚠️ THIS RUN IS NOT A RESULT', '>',
              '> %d 个单元没有回答（传输失败或被中途取消）。判定已关闭（`verdict_applicable: false`），'
              '下面的每个比例都只在已答单元上算。' % not_answered, '']
    elif not complete:
        L += ['> ## ⚠️ 这一臂还没跑完', '>',
              '> %d / %d 个单元已有结果。下面的阶梯是在**部分样本**上算的，不构成判定。'
              % (len(rows), len(units)), '']

    L += ['## 1. 复用清单：这次没有重算什么', '',
          '| 资产 | 文件 | 规模 | 这次花的调用 |', '| --- | --- | --- | --- |',
          '| 对照臂 B2（11 级收缩 + 单参数半区间） | `experiments/v106/e6b/baseline.json` | 83 例、'
          '%d 次验证尝试、17 例证出 | **0** |' % sum(v.get('attempts') or 0 for v in base.values()),
          '| 对照预算敏感性（4× 钟） | `experiments/v106/e6b_sensitivity/` | 5 例、46 次新尝试、0 例证出 | **0** |',
          '| E6b 模型臂（deepseek 16k） | `experiments/v106/e6b/results.json` | 249 单元、18 已答 | **0**（不并入） |',
          '| v1.05 三模型 1500 上限 | `experiments/v105/spec/results.json` | 747 行 | **0**（不并入） |',
          '| 请求级缓存 | `experiments/llm_cache/` | 命中 **%d** 个单元 | **0** |' % len(hits), '',
          '两条线不是"省事"，是"同一件事不该付两次钱"：对照是确定性搜索，同一族、同一顺序、同一验证器，'
          '今天跑和上周跑得到同 17/83；模型的行换了模型或换了上限就不再是同一次测量，所以那两批**不并入**，'
          '只作为记录保留。', '']

    L += ['## 2. 单元', '',
          '| 状态 | 计数 |', '| --- | --- |']
    for k, n in sorted(st.items()):
        L.append('| %s | %d |' % (k, n))
    L += ['', '- 已答 / answered: **%d / %d**；缓存命中 **%d**（0 次调用）。'
              % (len(rows) - not_answered, len(units), len(hits)),
          '- 解析失败 / malformed: **%d**；空区间 vacuous: **%d**；验证未过 unknown: **%d**。'
          % (st.get('MALFORMED', 0), st.get('VACUOUS', 0), st.get('UNKNOWN', 0)), '']

    L += ['## 3. 阶梯', '',
          '| 保留域门槛 t | 仅 S 证出 | 仅 B 证出 | 都证出 | 都未证出 | 精确 McNemar p |',
          '| --- | --- | --- | --- | --- | --- |']
    for r in lad:
        L.append('| %s | %d | %d | %d | %d | %.3g |'
                 % ('0（非空即可）' if r['t'] == 0.0 else '%g' % r['t'], r['only_s'], r['only_b'],
                    r['both'], r['neither'], r['p']))
    L.append('')

    L += ['## 4. 判定 / verdict', '']
    if void or not complete:
        L += ['- **不适用**（%s）。阶梯上的数字描述的是这次跑了多少，不是模型能做什么。'
              % ('有单元没回答' if void else '样本不完整'), '']
        verdict = dict(verdict, claim=False, verdict_applicable=False,
                       why='void' if void else 'incomplete')
    else:
        L += ['- 判定 `%s`：%s。在最宽的一级（t = 0）上，仅 S 证出 **%d**、仅 B 证出 **%d**。'
              % ('成立' if verdict['claim'] else '不成立', verdict['why'],
                 lad[0]['only_s'], lad[0]['only_b']),
              '- 这一臂的读法只有一个方向：它测的是**这个价位的模型**，不是模型的极限。'
              '便宜模型在后，不能写成"模型不行"；它只能写成"在这个价位上，模型没有贡献"。', '']

    L += ['## 5. 成本', '',
          '| 项 | 值 |', '| --- | --- |',
          '| 真正付费的调用 | **%d** |' % len(paid),
          '| 缓存命中（0 调用） | %d |' % len(hits),
          '| prompt tokens | %d |' % pt,
          '| completion tokens | %d |' % ct,
          '| 其中 reasoning tokens | %s |' % (('%d' % sum(rt)) if rt else '—'),
          '| 生成/传输耗时 | %.0f s = %.1f min |' % (live, live / 60),
          '| 首 token 延迟 TTFT 中位 | %s |' % ('%.2f s' % v106.median(ttfts) if ttfts else '—'),
          '| 估算而非计量 token 的单元 | %d |' % sum(1 for r in rows if r.get('tokens_estimated')),
          '', '- 与 v1.07 相比：同为 83 次调用，价钱从 $0.15/M 输入、$0.60/M 输出换成 $3.00/$15.00。'
              '这一臂 **%d** 次调用、**%d** completion tokens。两个价位不是两次重复，是两次测量：'
              '它们不合并，也不相加。' % (len(paid), ct), '']

    save(out / 'results.json', {'rows': rows, 'counts': dict(st), 'complete': complete,
                                'void': void, 'paid_calls': len(paid),
                                'cache_hits': len(hits), 'prompt_tokens': pt,
                                'completion_tokens': ct, 'ladder': lad, 'verdict': verdict,
                                'protocol_sha256': sha(out / 'protocol.json')})
    save(out / 'summary.json', {'verdict': verdict, 'counts': dict(st), 'ladder': lad,
                                'paid_calls': len(paid), 'cache_hits': len(hits),
                                'prompt_tokens': pt, 'completion_tokens': ct,
                                'complete': complete, 'void': void})
    (out / 'summary.md').write_text('\n'.join(L), encoding='utf-8')
    print(json.dumps({'units': len(rows), 'of': len(units), 'paid_calls': len(paid),
                      'cache_hits': len(hits), 'tokens': pt + ct,
                      'verdict': verdict.get('claim'), 'void': void}, indent=1))
    return 0


def preflight(out):
    """One streamed call with a real prompt, at 64 tokens: is the account able, and what does it cost?

    Different from v1.06's "reply with OK": this sends the actual system message and the actual
    first prompt, so the prompt-token count it reports is the one the run will pay, and a model that
    cannot produce a JSON object at all fails here rather than in 83 rows.
    """
    out = Path(out)
    key = os.environ.get('LLM_API_KEY')
    base = os.environ.get('LLM_BASE_URL') or v105.DEFAULT_BASE
    if not key:
        print(json.dumps({'quota_ok': False, 'why': 'no LLM_API_KEY'}))
        return 2
    plan, units = load(out)
    meta = plan['cases'][0]
    text = v105.prompt(meta)
    rec = llm_stream.stream_chat(MODEL, [{'role': 'system', 'content': v105.SYSTEM},
                                         {'role': 'user', 'content': text}], key, base,
                                 temperature=TEMP, max_tokens=64, stall=STALL, wall=120.0,
                                 use_cache=False)
    ok = bool(rec.get('content')) and not rec.get('quota_exhausted') and not rec.get('transport_error')
    u = rec.get('usage') or {}
    save(out / 'preflight.json', {k: rec.get(k) for k in
                                  ('model_requested', 'served_model', 'finish_reason', 'usage',
                                   'quota_exhausted', 'transport_error', 'ttft', 'seconds',
                                   'aborted', 'chunks', 'tokens_estimated')})
    print(json.dumps({'quota_ok': ok, 'served': rec.get('served_model'),
                      'prompt_tokens': u.get('prompt_tokens'), 'ttft': rec.get('ttft'),
                      'why': rec.get('transport_error') or rec.get('parse_error')}))
    return 0 if ok else 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['freeze', 'check', 'ask', 'verify', 'run', 'merge',
                                    'preflight', 'status'])
    ap.add_argument('--output', default=str(OUT))
    ap.add_argument('--index', type=int)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, help='at most this many unfinished units this invocation')
    a = ap.parse_args()
    if a.cmd == 'freeze':
        freeze(a.output)
    elif a.cmd == 'check':
        return check(a.output)
    elif a.cmd == 'ask':
        ask(a.output, a.index)
    elif a.cmd == 'verify':
        verify(a.output, a.index)
    elif a.cmd == 'run':
        return run(a.output, workers=a.workers, limit=a.limit)
    elif a.cmd == 'merge':
        return merge(a.output)
    elif a.cmd == 'preflight':
        return preflight(a.output)
    elif a.cmd == 'status':
        plan, units = load(a.output)
        rows = rows_from(a.output)
        print(json.dumps({'units': len(units), 'done': len(rows),
                          'counts': dict(collections.Counter(r['status'] for r in rows)),
                          'cached': sum(1 for r in rows if r.get('cached'))}, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
