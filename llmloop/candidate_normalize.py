"""Host-side, UNTRUSTED syntax repair of model-proposed formulas.

Nothing here is part of the proof: every normalized candidate is handed to the unchanged verifier, which accepts or rejects it
on its own obligations, so a wrong rewrite can only cause a rejection, never a false certificate. Rewrites are deliberately
limited to forms whose intent is unambiguous. NOT rewritten: `^` (C xor vs mathematical power), `pow()`, references to state
variables inside a trajectory, comma/ternary expressions with unbalanced parentheses.
"""
import re

_CAST = re.compile(r'\(\s*(?:unsigned\s+|signed\s+)?(?:char|short|int|long(?:\s+long)?)\s*\)\s*')
_FN = {'min': 'Min', 'max': 'Max', 'abs': 'Abs'}


def _split_top(text, ch):
    depth = 0
    for i, c in enumerate(text):
        if c == '(': depth += 1
        elif c == ')': depth -= 1
        elif c == ch and depth == 0: return i
    return -1


def _ternary(text):
    """cond ? a : b  ->  (a) if (cond) else (b), recursively; returns None if unbalanced."""
    q = _split_top(text, '?')
    if q < 0: return text
    rest = text[q + 1:]
    # matching ':' for this '?' at depth 0, skipping nested '?:' pairs
    depth = 0; nest = 0; colon = -1
    for i, c in enumerate(rest):
        if c == '(': depth += 1
        elif c == ')': depth -= 1
        elif depth == 0 and c == '?': nest += 1
        elif depth == 0 and c == ':':
            if nest == 0: colon = i; break
            nest -= 1
    if colon < 0: return None
    a, b = rest[:colon], rest[colon + 1:]
    a2, b2, c2 = _ternary(a), _ternary(b), _ternary(text[:q])
    if None in (a2, b2, c2): return None
    return '((%s) if (%s) else (%s))' % (a2.strip(), c2.strip(), b2.strip())


def _convert_ternaries(text):
    """Recursively rewrite every parenthesised group first, then the top level. None if parentheses are unbalanced."""
    out = []; i = 0
    while i < len(text):
        c = text[i]
        if c == '(':
            depth = 1; j = i + 1
            while j < len(text) and depth:
                depth += (text[j] == '(') - (text[j] == ')'); j += 1
            if depth: return None
            inner = _convert_ternaries(text[i + 1:j - 1])
            if inner is None: return None
            out.append('(' + inner + ')'); i = j
        elif c == ')':
            return None
        else:
            out.append(c); i += 1
    return _ternary(''.join(out))


def normalize_formula(text):
    """Return (normalized_text, [applied rewrite names]). Unchanged text and [] when nothing applies."""
    out, applied = text, []
    t = _CAST.sub('', out)
    if t != out: applied.append('strip_c_casts'); out = t
    t = re.sub(r'entry\(\s*([A-Za-z_]\w*)\s*\)', r'entry("\1")', out)
    t = re.sub(r"entry\(\s*'([A-Za-z_]\w*)'\s*\)", r'entry("\1")', t)
    if t != out: applied.append('quote_entry_argument'); out = t
    t = re.sub(r'\b(min|max|abs)\s*\(', lambda m: _FN[m.group(1)] + '(', out)
    if t != out: applied.append('capitalize_min_max_abs'); out = t
    if '?' in out:
        r = _convert_ternaries(out)
        if r is not None and r != out: applied.append('c_ternary_to_python'); out = r
    t = out.replace('&&', ' and ').replace('||', ' or ')
    if t != out: applied.append('c_logical_ops'); out = t
    return out, applied


def normalize_summary(summary):
    """Normalize every formula string in a closed_forms / loop_summaries / range_invariants structure."""
    rewrites = []
    def walk(node):
        if isinstance(node, str):
            new, ap = normalize_formula(node); rewrites.extend(ap); return new
        if isinstance(node, dict): return {k: walk(v) for k, v in node.items()}
        return node
    return walk(summary), rewrites


def source_names(source):
    """(parameter names, loop index names) of a one-function C source; used only to drop coordinates that cannot be state."""
    m = re.search(r'\w[\w\s\*]*?\b\w+\s*\(([^)]*)\)\s*\{', source)
    params = set()
    if m:
        for part in m.group(1).split(','):
            toks = re.findall(r'[A-Za-z_]\w*', part)
            if toks and toks[-1] not in ('void',): params.add(toks[-1])
    return params, set(re.findall(r'for\s*\(\s*(?:int|long|unsigned|short|char)?\s*(\w+)\s*=', source))


def drop_non_state_coordinates(summary, source):
    """Remove coordinates named after a function parameter or a loop index (never mutable locals) from a closed_forms map
    {var: formula} or a loop_summaries map {loop: {var: formula}}. Returns (new_summary, [dropped names]). UNTRUSTED: the verifier
    still checks the remaining summary and rejects it if a real coordinate is missing."""
    params, indices = source_names(source); banned = params | indices; dropped = []
    if isinstance(summary, dict) and any(isinstance(v, dict) for v in summary.values()) and any(not isinstance(v, dict) for v in summary.values()):
        stray = [k for k, v in summary.items() if not isinstance(v, dict)]
        summary = {k: v for k, v in summary.items() if isinstance(v, dict)}; dropped += stray
    if isinstance(summary, dict) and summary and all(isinstance(v, dict) for v in summary.values()):
        out = {}
        for loop, mp in summary.items():
            out[loop] = {k: v for k, v in mp.items() if k not in banned}
            dropped += [k for k in mp if k in banned]
        return out, dropped
    if isinstance(summary, dict):
        dropped = [k for k in summary if k in banned]
        return {k: v for k, v in summary.items() if k not in banned}, dropped
    return summary, dropped
