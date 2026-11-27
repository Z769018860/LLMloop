"""One streamed chat call: a cache underneath it, a budget above it, a stall detector beside it.

This exists because the previous arm was paid for twice and answered neither time. Three
properties, each one answering a failure that has already happened in this repository:

  * **Streaming, so a slow generation is not a missing one.** The non-streaming client waits for
    one response body and dies at the socket timeout. `deepseek-v4.1-flash-ark` spent a median
    5,764 tokens of reasoning per answer; at 240 s the wall clock, not the model, decided which
    units returned. Streaming replaces one long wait with a sequence of short ones, so the only
    hard limit is `stall` -- the longest silence tolerated between chunks -- and a generation may
    take half an hour as long as it keeps talking. `ttft` is recorded because it is the number
    that tells a dead connection from a thinking model.

  * **A cache, so a paid answer is never paid for twice.** `key_for` hashes the exact request
    body, and the reply is stored under that hash in `experiments/llm_cache/`. Reuse stops being
    a policy someone has to remember and becomes what the function does; `cached` is returned so
    the caller can report `0` calls instead of inferring it.

  * **A token budget, so a runaway generation is stoppable.** `max_tokens` is enforced by the
    server, but a server-side cap produces a reply that looks like an answer until you read
    `finish_reason`. Aborting mid-stream on an estimated token count gives `aborted='budget'`
    instead, which downstream can report as "the cap ended this", not "the model said nothing".

Usage: some providers omit `usage` on streamed responses unless asked. We ask
(`stream_options.include_usage`), fall back to a body without it on HTTP 400, and when it is
missing anyway the tokens are estimated at 3.6 characters per token and flagged
`tokens_estimated: true` so no table ever divides a guess without saying so.

No retries: retry policy belongs to the caller, which knows whether the failure was transport
(retry) or the account (do not).
"""
import hashlib
import json
import os
import time
from pathlib import Path
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'experiments' / 'llm_cache'
CHARS_PER_TOKEN = 3.6


def key_for(model, messages, temperature, max_tokens, endpoint=''):
    """The identity of a call: everything that can change the answer, nothing that cannot.

    `stream` is in the key although it should not change the answer. It is in there because a
    cached reply is evidence, and evidence has to say how it was obtained.

    `endpoint` is in the key because the first version left it out, and a smoke test against a fake
    server on 127.0.0.1 wrote a reply that the real run would then have been served -- same body,
    same hash, different machine. A cache that cannot tell two endpoints apart is a cache that can
    answer with a reply nobody paid for.
    """
    body = {'model': model, 'messages': messages, 'temperature': temperature,
            'max_tokens': max_tokens, 'stream': True, 'endpoint': endpoint}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def estimate_tokens(text):
    if not text:
        return 0
    return int(round(len(text) / CHARS_PER_TOKEN))


def cache_path(key):
    return CACHE / key[:2] / (key + '.json')


def cache_get(key):
    p = cache_path(key)
    if not p.exists():
        return None
    rec = json.loads(p.read_text(encoding='utf-8'))
    rec['cached'] = True
    rec['seconds_live'] = rec.get('seconds')
    rec['seconds'] = 0.0
    return rec


def cache_put(key, rec):
    p = cache_path(key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding='utf-8')
    os.replace(tmp, p)


def stream_chat(model, messages, key, base, temperature=0.7, max_tokens=2048,
                stall=90.0, wall=1800.0, budget_tokens=None, use_cache=True):
    """POST `messages`, read the SSE stream, return a record -- never raise for a normal failure."""
    ck = key_for(model, messages, temperature, max_tokens, base)
    rec = {'model_requested': model, 'cache_key': ck, 'endpoint': base,
           'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
           'stream': True, 'chunks': 0, 'ttft': None, 'seconds': 0.0, 'aborted': None,
           'messages_sha256': hashlib.sha256(
               json.dumps(messages, sort_keys=True).encode()).hexdigest(),
           'request': {'model': model, 'temperature': temperature, 'max_tokens': max_tokens,
                       'stream': True, 'stream_options': {'include_usage': True}}}
    if use_cache:
        hit = cache_get(ck)
        if hit is not None:
            return hit
    rec['cached'] = False
    if not key:
        rec['transport_error'] = 'no LLM_API_KEY'
        return rec

    body = dict(rec['request'])
    body['messages'] = messages
    url = base.rstrip('/') + '/chat/completions'
    start = time.monotonic()
    content, reasoning = [], []
    try:
        rec['http_status'] = _consume(url, key, body, rec, content, reasoning, start, stall, wall,
                                      budget_tokens)
    except error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')[:400]
        rec['http_status'] = exc.code
        if exc.code == 400 and 'stream_options' in detail:
            # The provider does not know the field. Ask again without it rather than lose the call;
            # the missing usage is then estimated and flagged, which is the honest cost of the
            # provider's older API.
            body.pop('stream_options', None)
            rec['request'].pop('stream_options', None)
            rec['stream_options_refused'] = detail[:200]
            try:
                rec['http_status'] = _consume(url, key, body, rec, content, reasoning, start,
                                              stall, wall, budget_tokens)
            except error.HTTPError as exc2:
                rec['transport_error'] = 'HTTP %d: %s' % (
                    exc2.code, exc2.read().decode(errors='replace')[:300])
        elif exc.code == 403 and 'quota' in detail.lower():
            rec['quota_exhausted'] = True
            rec['transport_error'] = 'HTTP 403 quota: ' + detail[:300]
        else:
            rec['transport_error'] = 'HTTP %d: %s' % (exc.code, detail[:300])
    except Exception as exc:                      # socket timeout, reset, DNS, TLS
        rec['transport_error'] = type(exc).__name__ + ': ' + str(exc)[:200]

    rec['content'] = ''.join(content)
    rec['reasoning_content'] = ''.join(reasoning)
    rec['seconds'] = round(time.monotonic() - start, 3)
    if 'usage' not in rec or not rec['usage']:
        rec['usage'] = {'prompt_tokens': estimate_tokens(json.dumps(messages)),
                        'completion_tokens': estimate_tokens(rec['content'])
                        + estimate_tokens(rec['reasoning_content'])}
        rec['tokens_estimated'] = True
    if rec['content'] and 'finish_reason' not in rec and not rec.get('aborted'):
        # The stream ended without saying why. That is not a finished answer.
        rec['aborted'] = 'eof'
    # Only a clean reply is worth keeping: a partial one cached under the request hash would be
    # served forever as if it were the answer to a question the model was never asked twice.
    if use_cache and not rec.get('transport_error') and not rec.get('aborted'):
        cache_put(ck, {k: v for k, v in rec.items() if k != 'cached'})
    return rec


def _consume(url, key, body, rec, content, reasoning, start, stall, wall, budget_tokens):
    """Read the stream into `content` / `reasoning` / `rec`. Returns the HTTP status."""
    req = request.Request(url, data=json.dumps(body).encode(), method='POST',
                          headers={'Content-Type': 'application/json',
                                   'Accept': 'text/event-stream',
                                   'Authorization': 'Bearer ' + key})
    with request.urlopen(req, timeout=stall) as r:
        for raw in r:
            now = time.monotonic()
            if now - start > wall:
                rec['aborted'] = 'wall'
                break
            line = raw.decode('utf-8', 'replace').strip()
            if not line or line.startswith(':'):
                continue
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if payload == '[DONE]':
                rec['done'] = True
                break
            try:
                chunk = json.loads(payload)
            except ValueError:
                continue
            rec['chunks'] += 1
            if chunk.get('model'):
                rec['served_model'] = chunk['model']
            if chunk.get('usage'):
                rec['usage'] = chunk['usage']
            for choice in chunk.get('choices') or []:
                delta = choice.get('delta') or {}
                piece = delta.get('content')
                thought = delta.get('reasoning_content') or delta.get('reasoning')
                if piece:
                    content.append(piece)
                if thought:
                    reasoning.append(thought)
                if (piece or thought) and rec['ttft'] is None:
                    rec['ttft'] = round(now - start, 3)
                if choice.get('finish_reason'):
                    rec['finish_reason'] = choice['finish_reason']
            if budget_tokens is not None:
                used = estimate_tokens(''.join(content)) + estimate_tokens(''.join(reasoning))
                if used > budget_tokens:
                    rec['aborted'] = 'budget'
                    rec['estimated_generated'] = used
                    break
        return r.status
