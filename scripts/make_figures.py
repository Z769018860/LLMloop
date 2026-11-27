"""Draw the paper's two figures as standalone SVG, from the committed data.

Why a script and not a drawing program: a figure is an argument, and every number in it has to be
re-derivable from a file that is already in the repository. Fig. 2 is built from four summaries —

    experiments/v107/e6c/summary.json   the 8-rung ladder of the cheap arm (panel a, row 1 of b)
    experiments/v108/e6d/summary.json   the second price point
    experiments/v106/e6b/summary.json   the 16k arm, after the void was filled
    experiments/v107/e6c/breakdown.json the wide arm paired against the same control

— plus, for Fig. 1, the witness summary and the ledger. No number is typed into this file except
the prose. Fig. 1 is mostly layout: it encodes the trust boundary and theorem T2. The four counters
under its re-check band and the bill in its footer are read from
`experiments/v104/witness/full165/` and `scripts/llm_ledger.py`, so the one figure that could have
been pure decoration still cannot disagree with the data.

Output is plain SVG with no external references (no <image>, no web fonts), so the same file can be
dropped into a LaTeX `\\includegraphics`, opened in a browser, or diffed in git. Running this script
twice produces byte-identical files: no timestamps, no random ids.

    python scripts/make_figures.py            # writes paper/figures/*.svg
    python scripts/make_figures.py --check     # exit 1 if the files on disk differ
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIGDIR = ROOT / 'paper' / 'figures'

# Palette. Muted enough to print in greyscale, distinct enough to survive a projector.
INK = '#1F2328'
MUTED = '#57606A'
RULE = '#D0D7DE'
PANEL = '#F6F8FA'
AMBER_S, AMBER_F = '#B45309', '#FFF7ED'          # untrusted: proposals
BLUE_S, BLUE_F = '#1D4ED8', '#EFF6FF'            # trusted: the fixed trust base
GREEN_S, GREEN_F = '#047857', '#ECFDF5'          # independent: shares no code
PROVED_S, PROVED_F = '#15803D', '#DCFCE7'
UNKNOWN_S, UNKNOWN_F = '#6B7280', '#F3F4F6'
RED = '#B91C1C'
MODEL = '#2563EB'                                 # only-model bar
CONTROL = '#EA580C'                               # only-control bar

FONT = "'Helvetica Neue', Helvetica, Arial, sans-serif"


def esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def num(x: float) -> str:
    """Coordinates: two decimals, no trailing zeros, no exponents."""
    s = '%.2f' % x
    return s.rstrip('0').rstrip('.') if '.' in s else s


class SVG:
    def __init__(self, w: int, h: int, title: str):
        self.w, self.h, self.title = w, h, title
        self.body: list[str] = []

    # -- primitives ---------------------------------------------------------------------------
    def add(self, s: str) -> None:
        self.body.append('  ' + s)

    def rect(self, x, y, w, h, *, fill='none', stroke='none', sw=1.4, rx=8, dash=None, op=None):
        d = '' if dash is None else ' stroke-dasharray="%s"' % dash
        o = '' if op is None else ' opacity="%s"' % op
        self.add('<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" stroke="%s" '
                 'stroke-width="%s"%s%s/>' % (num(x), num(y), num(w), num(h), num(rx), fill,
                                              stroke, num(sw), d, o))

    def text(self, x, y, s, *, size=12, anchor='start', fill=INK, weight='normal',
             style='normal', spacing=None):
        sp = '' if spacing is None else ' letter-spacing="%s"' % spacing
        self.add('<text x="%s" y="%s" font-family="%s" font-size="%s" font-weight="%s" '
                 'font-style="%s" fill="%s" text-anchor="%s"%s>%s</text>'
                 % (num(x), num(y), FONT, num(size), weight, style, fill, anchor, sp, esc(s)))

    def runs(self, x, y, runs, *, size=12, fill=INK, dx='7'):
        """One line, several weights: <text> with tspans, so a bold lead-in cannot drift into the
        sentence after it (the first version hard-coded an x offset and they overlapped)."""
        out = []
        for i, (s, weight, col) in enumerate(runs):
            d = '' if i == 0 else ' dx="%s"' % dx
            out.append('<tspan font-weight="%s" fill="%s"%s>%s</tspan>' % (weight, col, d, esc(s)))
        self.add('<text x="%s" y="%s" font-family="%s" font-size="%s" fill="%s">%s</text>'
                 % (num(x), num(y), FONT, num(size), fill, ''.join(out)))

    def line(self, x1, y1, x2, y2, *, stroke=INK, sw=1.4, dash=None, marker=False):
        d = '' if dash is None else ' stroke-dasharray="%s"' % dash
        m = ' marker-end="url(#ah-%s)"' % _marker_key(stroke) if marker else ''
        self.add('<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"%s%s/>'
                 % (num(x1), num(y1), num(x2), num(y2), stroke, num(sw), d, m))

    def path(self, d, *, stroke=INK, sw=1.4, fill='none', dash=None, marker=False, marker_start=False):
        ds = '' if dash is None else ' stroke-dasharray="%s"' % dash
        m = ' marker-end="url(#ah-%s)"' % _marker_key(stroke) if marker else ''
        ms = ' marker-start="url(#ah-%s)"' % _marker_key(stroke) if marker_start else ''
        self.add('<path d="%s" fill="%s" stroke="%s" stroke-width="%s"%s%s%s/>'
                 % (d, fill, stroke, num(sw), ds, m, ms))

    def cross(self, x, y, r=5, *, stroke=RED, sw=1.8):
        self.line(x - r, y - r, x + r, y + r, stroke=stroke, sw=sw)
        self.line(x - r, y + r, x + r, y - r, stroke=stroke, sw=sw)

    # -- composite ----------------------------------------------------------------------------
    def box(self, x, y, w, h, title, lines, *, stroke=INK, fill='#FFFFFF', title_size=13.5,
            dashed=False, tag=None):
        self.rect(x, y, w, h, fill=fill, stroke=stroke, sw=1.6, rx=9,
                  dash='5 4' if dashed else None)
        cx = x + w / 2
        cy = y + 26
        self.text(cx, cy, title, size=title_size, anchor='middle', weight='bold')
        ty = cy + 20
        if tag:
            self.text(cx, cy + 16, tag, size=9.8, anchor='middle', fill=MUTED, style='italic')
            ty = cy + 36
        for i, ln in enumerate(lines):
            self.text(cx, ty + i * 17, ln, size=11.6, anchor='middle', fill=MUTED)

    def render(self) -> str:
        head = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                'viewBox="0 0 %d %d" role="img" aria-label="%s">\n'
                '<title>%s</title>\n' % (self.w, self.h, self.w, self.h,
                                         esc(self.title), esc(self.title)))
        return head + _defs() + '\n' + '\n'.join(self.body) + '\n</svg>\n'


def _marker_key(color: str) -> str:
    return {INK: 'ink', MUTED: 'muted', RED: 'red', MODEL: 'blue', CONTROL: 'orange',
            GREEN_S: 'green'}.get(color, 'ink')


def _defs() -> str:
    out = ['<defs>']
    for key, color in [('ink', INK), ('muted', MUTED), ('red', RED), ('blue', MODEL),
                       ('orange', CONTROL), ('green', GREEN_S)]:
        out.append(
            '<marker id="ah-%s" viewBox="0 0 10 10" refX="9.5" refY="5" markerWidth="6.5" '
            'markerHeight="6.5" orient="auto-start-reverse">'
            '<path d="M0,0 L10,5 L0,10 z" fill="%s"/></marker>' % (key, color))
    out.append('</defs>')
    return '\n'.join(out)


def _load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding='utf-8'))


def _witness() -> dict:
    """The counters Fig. 1 puts under the re-check band, from the run that produced them.

    `verdicts.ultimate.TRUE` is 90 *cases*, not 121 invariants: one case carries several loops, and
    the per-invariant number lives in the shards as `loops` per row. Reading the case count and
    printing it over the invariant count is exactly the kind of quiet unit error this paper is
    about, so the loop totals are summed here instead of assumed.
    """
    d = _load('experiments/v104/witness/full165/summary.json')
    ex, v = d['exporter'], d['verdicts']
    rejected = sum(x.get('FALSE', 0) for x in v.values())   # a key that is absent means zero
    loops = {}
    for val in ('ultimate', 'cpachecker'):
        ok = tot = 0
        for f in sorted((ROOT / 'experiments/v104/witness/full165').glob(
                'shard*/validation-%s.json' % val)):
            for r in json.loads(f.read_text(encoding='utf-8'))['rows']:
                n = r.get('loops') or 0
                tot += n
                if r['result'] == 'TRUE':
                    ok += n
        loops[val] = (ok, tot)
    return {'considered': d['considered'], 'exported': ex['exported_cases'],
            'invariants': ex['invariants_exported'], 'rejected': rejected,
            'ult_inv': loops['ultimate'], 'cpac_inv': loops['cpachecker']}


def _bill() -> dict:
    """Calls, tokens and dollars, computed by the same module the appendix trusts."""
    sys.path.insert(0, str(ROOT))
    from scripts import llm_ledger
    arms = llm_ledger.collect()
    usd = llm_ledger.money(arms)
    calls = sum(m['calls'] for a in arms for m in a['models'].values())
    tokens = sum(m['prompt'] + m['completion'] for a in arms for m in a['models'].values())
    return {'calls': calls, 'tokens': tokens, 'usd': usd}


# ==================================================================================================
# Figure 1 -- the pipeline and the trust boundary. It encodes a theorem, and reads the four counters
# of the re-check band plus the bill from the files that produced them; the layout is the only
# thing here that is a decision rather than a number.
# ==================================================================================================
def fig1_pipeline() -> str:
    wit, bill = _witness(), _bill()
    s = SVG(1160, 412, 'Figure 1. Proposals are strings; acceptance is decided by an unchanged '
                       'verifier; the certificate is checked by code that shares nothing with it.')

    # Bands ------------------------------------------------------------------------------------
    # The descriptor sits at the band's right edge, not after the title: the title's rendered width
    # is not the character count times a constant, and estimating it put the two on top of each other.
    bands = [
        (18, 216, AMBER_S, AMBER_F, 'UNTRUSTED', ''),
        (246, 548, BLUE_S, BLUE_F, 'TRUSTED', 'fixed for every arm'),
        (806, 336, GREEN_S, GREEN_F, 'INDEPENDENT', 'shares no code'),
    ]
    for x, w, stroke, fill, title, sub in bands:
        s.rect(x, 56, w, 196, fill=fill, stroke=stroke, sw=1.3, rx=10, dash='6 4')
        s.text(x + 12, 70, title, size=9.6, fill=stroke, weight='bold', spacing='0.9')
        if sub:
            s.text(x + w - 12, 246, sub, size=9.6, fill=MUTED, style='italic', anchor='end')

    # Boxes ------------------------------------------------------------------------------------
    y, h = 80, 144
    s.box(28, y, 172, h, 'Proposers',
          ['any source, untrusted', 'LLM — six models', 'trajectory fitter', 'sampling + Houdini',
           'contract writer'],
          stroke=AMBER_S, fill='#FFFFFF')
    s.box(262, y, 140, h, 'Normalisation',
          ['C89 index rebasing', 'while → for', 'UBSan differential'],
          stroke=BLUE_S, fill='#FFFFFF')
    s.box(418, y, 232, h, 'Unchanged verifier',
          ['Z3 + typed C integer semantics', 'O1 entry · O2 preservation',
           'O3–O6 exit & definedness', 'O7 path coverage · O8 shape',
           'one code path for every arm'],
          stroke=BLUE_S, fill='#FFFFFF', title_size=14)

    # Verdict pills, inside the trusted band because the verifier produces them.
    s.rect(664, 88, 118, 38, fill=PROVED_F, stroke=PROVED_S, sw=1.5, rx=7)
    s.text(723, 104, 'PROVED', size=11.6, anchor='middle', weight='bold', fill=PROVED_S)
    s.text(723, 118, '%d cases' % wit['exported'], size=10, anchor='middle', fill=MUTED)

    s.rect(664, 140, 118, 38, fill=UNKNOWN_F, stroke=UNKNOWN_S, sw=1.4, rx=7)
    s.text(723, 156, 'UNKNOWN', size=11.6, anchor='middle', weight='bold', fill='#4B5563')
    s.text(723, 170, 'incl. timeouts', size=10, anchor='middle', fill=MUTED)

    s.box(818, y, 312, h, 'Independent re-check',
          ['%d witnesses, %d invariants' % (wit['exported'], wit['invariants']),
           'invariant_set 2.0, one set per loop',
           'CPAchecker 4.2.2 — %d rejected' % wit['rejected'],
           'Ultimate 0.3.2 — %d/%d invariants' % wit['ult_inv']],
          stroke=GREEN_S, fill='#FFFFFF', title_size=14,
          tag='re-runs the property from the witness alone')

    # Flow ------------------------------------------------------------------------------------
    s.line(200, 150, 258, 150, marker=True)
    s.line(402, 150, 414, 150, marker=True)
    s.line(650, 107, 660, 107, marker=True)
    s.line(650, 159, 660, 159, marker=True)
    s.line(782, 107, 814, 107, marker=True)

    # The edge that does not exist -------------------------------------------------------------
    s.path('M114 80 C 114 24, 723 24, 723 84', stroke=RED, sw=1.5, dash='3 4', marker=True)
    s.cross(418, 42, 5.5)
    s.text(418, 20, 'no edge from a proposal to PROVED', size=10.6, anchor='middle',
           fill=RED, weight='bold')

    # Repair loop ------------------------------------------------------------------------------
    s.path('M 470 224 L 470 280 L 114 280 L 114 228', stroke=MUTED, sw=1.3, dash='4 4', marker=True)
    s.text(302, 266, 'UNKNOWN → counterexample → repair (untrusted again)',
           size=10.2, anchor='middle', fill=MUTED, style='italic')

    # T2 ---------------------------------------------------------------------------------------
    s.rect(28, 292, 1102, 66, fill=PANEL, stroke=RULE, sw=1.2, rx=8)
    s.runs(44, 314, [('T2 — proposer independence.', 'bold', INK),
                     ('PROVED is decided only by whether the obligations of I hold, never by where '
                      'I came from.', 'normal', INK)], size=12)
    s.runs(44, 334, [('What crosses the dashed boundary is a string, I₁…Iₙ', 'italic', MUTED),
                     ('A proposer can change what is found; it cannot change what is accepted — '
                      'which is why the red arc never reaches an accepted proof.', 'normal', MUTED)],
           size=11.4)

    # Footer -----------------------------------------------------------------------------------
    s.line(28, 376, 1130, 376, stroke=RULE, sw=1)
    foot = ['%d of %d witnesses rejected by either validator'
            % (wit['rejected'], wit['exported']),
            '{:,} calls · {:.2f} M tokens · ${:.2f} — every arm'
            .format(bill['calls'], bill['tokens'] / 1e6, bill['usd']),
            'T1–T2 are paper proofs (§1b), not machine-checked']
    xs = [28, 300, 620]
    for x, t in zip(xs, foot):
        s.text(x, 394, t, size=10.6, fill=MUTED)
    return s.render()


# ==================================================================================================
# Figure 2 -- the ladder, and the four arms. Every number below is read from a summary on disk.
# ==================================================================================================
MODEL_SHORT = re.compile(r'-\d{8}$')


def _arm(study: str, protocol: str, summary: str) -> dict:
    plan, summ = _load(protocol), _load(summary)
    top = summ['ladder'][0]
    reps = plan.get('repeats', 1)
    model = MODEL_SHORT.sub('', plan['model'])
    return {
        'label': 'E6%s' % study,
        'model': model,
        'cap': plan['max_tokens'],
        'draws': reps,
        'only_s': top['only_s'],
        'only_b': top['only_b'],
        'both': top['both'],
        'p': top['p'],
        'proved': top['only_s'] + top['both'],
    }


def _fmt_p(p: float) -> str:
    if p >= 0.1:
        return '%.3f' % p
    if p >= 0.01:
        return '%.4f' % p
    return '%.2g' % p


def _cap(n: int) -> str:
    return '{:,}'.format(n)


def fig2_ladder() -> str:
    e6c = _arm('c', 'experiments/v107/e6c/protocol.json', 'experiments/v107/e6c/summary.json')
    e6d = _arm('d', 'experiments/v108/e6d/protocol.json', 'experiments/v108/e6d/summary.json')
    e6b = _arm('b', 'experiments/v106/e6b/protocol.json', 'experiments/v106/e6b/summary.json')
    wide_json = _load('experiments/v107/e6c/breakdown.json')
    wide_top = wide_json['ladder'][0]
    wide = {
        'label': 'E6', 'model': '3 models × 3 draws', 'cap': 1500, 'draws': 3,
        'only_s': wide_top['only_s'], 'only_b': wide_top['only_b'],
        'both': wide_top['both'], 'p': wide_top['p'],
        'proved': wide_top['only_s'] + wide_top['both'],
    }
    control = _load('experiments/v107/e6c/summary.json')['ladder'][0]
    ctrl_both = control['both']
    ctrl_proved = wide_json['control_proved']

    s = SVG(1060, 420, 'Figure 2. (a) One arm over eight retained-domain floors: only-control cases '
                       'outnumber only-model cases at every floor. (b) The same 17/83 control '
                       'against four model arms: at a 2,048 cap the gap is significant, at 16,384 '
                       'it is not.')

    # ---- panel (a) ---------------------------------------------------------------------------
    a_cx, scale = 252, 11.0
    s.text(300, 26, '(a)  One arm, eight floors', size=13.5, anchor='middle', weight='bold')
    s.text(300, 45, 'E6c: %s, cap %s, %d draw. The control is 17/83 before any floor is applied.'
           % (e6c['model'], _cap(e6c['cap']), e6c['draws']),
           size=10.4, anchor='middle', fill=MUTED)

    s.text(a_cx - 10, 74, '← only model', size=10.6, anchor='end', fill=MODEL, weight='bold')
    s.text(a_cx + 10, 74, 'only control →', size=10.6, fill=CONTROL, weight='bold')
    s.text(536, 74, 'exact McNemar p', size=10.6, anchor='end', fill=MUTED)
    s.text(60, 74, 'retained domain ≥ t', size=10.2, fill=MUTED, style='italic')

    rows_a = _load('experiments/v107/e6c/summary.json')['ladder']
    y0, dy = 100, 33
    s.line(a_cx, 84, a_cx, y0 + dy * (len(rows_a) - 1) + 12, stroke=RULE, sw=1)
    for i, r in enumerate(rows_a):
        yc = y0 + i * dy
        s.text(208, yc + 4, 't = ' + (('%g' % r['t']) if r['t'] else '0'), size=10.8,
               anchor='end', fill=INK)
        if r['only_s']:
            w = r['only_s'] * scale
            s.rect(a_cx - w, yc - 7.5, w, 15, fill=MODEL, stroke=MODEL, sw=1, rx=2)
            s.text(a_cx - w - 6, yc + 4, str(r['only_s']), size=10.6, anchor='end', fill=MODEL,
                   weight='bold')
        else:
            s.text(a_cx - 6, yc + 4, '0', size=10.6, anchor='end', fill='#9CA3AF')
        w = r['only_b'] * scale
        s.rect(a_cx, yc - 7.5, w, 15, fill=CONTROL, stroke=CONTROL, sw=1, rx=2)
        s.text(a_cx + w + 6, yc + 4, str(r['only_b']), size=10.6, fill=CONTROL, weight='bold')
        sig = r['p'] < 0.05
        s.text(536, yc + 4, _fmt_p(r['p']), size=10.8, anchor='end',
               fill=RED if sig else MUTED, weight='bold' if sig else 'normal')

    s.text(300, 356, 'every one of the eight floors fails the pre-registered rule', size=11.4,
           anchor='middle', fill=INK)
    s.text(300, 374, 'verdict: no net contribution  ("breaks", claim = false)', size=11.4,
           anchor='middle', fill=RED, weight='bold')

    # ---- panel (b) ---------------------------------------------------------------------------
    b_cx, b_scale = 820, 10.0
    s.line(566, 18, 566, 348, stroke=RULE, sw=1)
    s.text(815, 26, '(b)  One control, four arms', size=13.5, anchor='middle', weight='bold')
    s.text(815, 45, 'only the model and its cap change — p moves with the cap, not with the price',
           size=10.4, anchor='middle', fill=MUTED)

    s.text(b_cx - 10, 76, '← only model', size=10.6, anchor='end', fill=MODEL, weight='bold')
    s.text(b_cx + 10, 76, 'only control →', size=10.6, fill=CONTROL, weight='bold')
    s.text(1036, 76, 'exact McNemar p', size=10.6, anchor='end', fill=MUTED)

    rows_b = [e6c, e6d, e6b, wide]
    yb0, dyb = 112, 46
    s.line(b_cx, 86, b_cx, yb0 + dyb * (len(rows_b) - 1) + 16, stroke=RULE, sw=1)
    for i, a in enumerate(rows_b):
        yc = yb0 + i * dyb
        s.text(758, yc - 2, '%s · %s' % (a['label'], a['model']), size=10.8, anchor='end',
               weight='bold')
        s.text(758, yc + 11, 'cap %s · %d draw%s' % (_cap(a['cap']), a['draws'],
                                                     '' if a['draws'] == 1 else 's'),
               size=10, anchor='end', fill=MUTED)
        if a['only_s']:
            w = a['only_s'] * b_scale
            s.rect(b_cx - w, yc - 4, w, 15, fill=MODEL, stroke=MODEL, sw=1, rx=2)
            s.text(b_cx - w - 6, yc + 8, str(a['only_s']), size=10.6, anchor='end', fill=MODEL,
                   weight='bold')
        w = a['only_b'] * b_scale
        s.rect(b_cx, yc - 4, w, 15, fill=CONTROL, stroke=CONTROL, sw=1, rx=2)
        s.text(b_cx + w + 6, yc + 8, str(a['only_b']), size=10.6, fill=CONTROL, weight='bold')
        sig = a['p'] < 0.05
        s.text(1036, yc + 8, _fmt_p(a['p']), size=10.8, anchor='end',
               fill=RED if sig else MUTED, weight='bold' if sig else 'normal')

    # The reading, spelled out from the rows above rather than asserted: two arms at one cap, one at
    # another, same control. Each number here is the corresponding row's own only_s / only_b / p.
    pairs_2048 = ';  '.join('%d vs %d (p = %s)' % (a['only_s'], a['only_b'], _fmt_p(a['p']))
                            for a in rows_b if a['cap'] == 2048)
    p16 = [a['p'] for a in rows_b if a['cap'] == 16384][0]

    s.rect(580, 298, 456, 60, fill=PANEL, stroke=RULE, sw=1.1, rx=7)
    s.text(592, 316, 'cap 2,048, two vendors:', size=10.4, fill=MUTED)
    s.text(592, 331, pairs_2048, size=10.4, fill=INK)
    s.text(592, 348, 'cap 16,384: %d vs %d, p = %s — behind, not significantly'
           % (e6b['only_s'], e6b['only_b'], _fmt_p(p16)), size=10.4, fill=INK)

    # ---- shared footer -----------------------------------------------------------------------
    s.text(530, 396, 'Bars count cases proved by one side only ("both" omitted, %d cases in panel a). '
                     'p: exact McNemar over the same 83 paired cases; the control proves %d/83 and '
                     'was not re-run.' % (ctrl_both, ctrl_proved),
           size=10.2, anchor='middle', fill=MUTED)
    s.text(530, 411, 'Counts are not exact: three draws of one arm move 5 verdicts, so read them as '
                     '±5 cases (E6e).', size=10.2, anchor='middle', fill='#9CA3AF')
    return s.render()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--check', action='store_true',
                    help='do not write; exit 1 if the committed files differ')
    args = ap.parse_args(argv)

    FIGDIR.mkdir(parents=True, exist_ok=True)
    figures = {'fig1_pipeline.svg': fig1_pipeline(), 'fig2_ladder.svg': fig2_ladder()}

    rc = 0
    for name, body in figures.items():
        path = FIGDIR / name
        old = path.read_text(encoding='utf-8') if path.exists() else None
        if args.check:
            if old != body:
                print('DRIFT %s' % path.relative_to(ROOT))
                rc = 1
            else:
                print('ok    %s' % path.relative_to(ROOT))
            continue
        path.write_text(body, encoding='utf-8')
        print('%-18s %6d bytes%s' % (name, len(body.encode('utf-8')),
                                     '' if old is None else ' (unchanged)' if old == body else ' (rewritten)'))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
