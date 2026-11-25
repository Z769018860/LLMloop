"""Tests for the streaming client: does it read a stream, stop when told, and never pay twice.

The server is a real one on 127.0.0.1 -- a fake object would test the fake. What is asserted is the
three properties the driver depends on:

  * the SSE frames become `content` / `reasoning` / `usage` exactly as a non-streamed body would;
  * a reply is cached under the request hash, and the second identical call makes no request;
  * a call that was cut off -- by budget, by the account, by a missing usage block -- is *marked*,
    and an aborted reply is never cached, because a cached partial answer would be served forever
    as if the model had answered.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts import llm_stream


class _Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    hits = []
    mode = 'ok'

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        self.rfile.read(n)
        _Handler.hits.append(self.path)
        mode = self.path.split('/')[1]
        if mode == 'quota':
            body = json.dumps({'error': {'message': 'Insufficient user quota'}}).encode()
            self.send_response(403)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        for frame in self._frames(mode):
            self.wfile.write(('data: ' + json.dumps(frame) + '\n\n').encode())
            self.wfile.flush()
        self.wfile.write(b'data: [DONE]\n\n')

    def _frames(self, mode):
        if mode == 'long':
            for i in range(200):
                yield {'choices': [{'delta': {'content': 'x%d ' % i}}]}
            yield {'choices': [{'delta': {}, 'finish_reason': 'stop'}],
                   'usage': {'prompt_tokens': 5, 'completion_tokens': 400}}
            return
        yield {'model': 'fake-1', 'choices': [{'delta': {'reasoning_content': 'think '}}]}
        yield {'choices': [{'delta': {'content': '{"pre":'}}]}
        yield {'choices': [{'delta': {'content': ' {}}'}, 'finish_reason': 'stop'}]}
        if mode != 'nousage':
            yield {'choices': [], 'usage': {'prompt_tokens': 11, 'completion_tokens': 7,
                                            'total_tokens': 18,
                                            'completion_tokens_details': {'reasoning_tokens': 3}}}


@pytest.fixture()
def server(tmp_path, monkeypatch):
    _Handler.hits = []
    srv = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    monkeypatch.setattr(llm_stream, 'CACHE', tmp_path / 'cache')
    yield 'http://127.0.0.1:%d' % srv.server_address[1]
    srv.shutdown()


MSG = [{'role': 'user', 'content': 'hi'}]


def test_a_stream_becomes_the_same_reply_a_single_body_would_have(server):
    rec = llm_stream.stream_chat('m', MSG, 'k', server + '/ok', max_tokens=64)
    assert rec['content'] == '{"pre": {}}'
    assert rec['reasoning_content'] == 'think '
    assert rec['finish_reason'] == 'stop'
    assert rec['usage']['prompt_tokens'] == 11
    assert rec['chunks'] == 4
    assert rec['ttft'] is not None and rec['aborted'] is None
    assert rec['cached'] is False


def test_the_second_identical_call_makes_no_request(server):
    a = llm_stream.stream_chat('m', MSG, 'k', server + '/ok', max_tokens=64)
    n = len(_Handler.hits)
    b = llm_stream.stream_chat('m', MSG, 'k', server + '/ok', max_tokens=64)
    assert len(_Handler.hits) == n, 'a cached call still hit the network'
    assert b['cached'] is True and b['seconds'] == 0.0
    assert b['content'] == a['content']


def test_a_different_body_is_a_different_key(server):
    assert llm_stream.key_for('m', MSG, 0.7, 64) != llm_stream.key_for('m', MSG, 0.7, 128)
    assert llm_stream.key_for('m', MSG, 0.7, 64) != llm_stream.key_for('m2', MSG, 0.7, 64)


def test_a_budget_stop_is_marked_and_not_cached(server):
    rec = llm_stream.stream_chat('m', MSG, 'k', server + '/long', max_tokens=4096,
                                 budget_tokens=20)
    assert rec['aborted'] == 'budget'
    assert rec.get('finish_reason') is None, 'the cap ended this, the model did not'
    assert len(rec['content']) > 0
    assert llm_stream.cache_get(rec['cache_key']) is None


def test_a_refused_account_is_not_a_malformed_reply(server):
    rec = llm_stream.stream_chat('m', MSG, 'k', server + '/quota', max_tokens=64)
    assert rec['quota_exhausted'] is True
    assert 'quota' in rec['transport_error']
    assert rec['content'] == ''
    assert llm_stream.cache_get(rec['cache_key']) is None


def test_missing_usage_is_estimated_and_says_so(server):
    rec = llm_stream.stream_chat('m', MSG, 'k', server + '/nousage', max_tokens=64)
    assert rec['tokens_estimated'] is True
    assert rec['usage']['prompt_tokens'] >= 0
    assert rec['content'] == '{"pre": {}}'


def test_a_dead_connection_is_a_transport_error_not_a_hang(server):
    rec = llm_stream.stream_chat('m', MSG, 'k', 'http://127.0.0.1:9', max_tokens=64,
                                 stall=5.0)
    assert rec['transport_error']
    assert rec['content'] == ''


def test_the_same_body_against_a_different_endpoint_is_a_different_key(server):
    """The key omitted the endpoint once, and a fake server's reply became the real answer."""
    a = llm_stream.key_for('m', MSG, 0.7, 64, 'https://api.example/v1')
    b = llm_stream.key_for('m', MSG, 0.7, 64, 'http://127.0.0.1:9')
    assert a != b
    assert a == llm_stream.key_for('m', MSG, 0.7, 64, 'https://api.example/v1')
