import argparse
import asyncio
import json
import socket
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPException
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from bot.http_transport import JSONConnection, proxy_required
from bot.live import LiveExchange
from bot import live


@pytest.fixture
def server():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def handle_request(self):
            body = self.rfile.read(int(self.headers.get('Content-Length', 0)))
            requests.append({'method': self.command, 'path': self.path,
                             'port': self.client_address[1], 'body': body})
            if self.path.endswith('/drop'):
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                return
            payload = b'{"detail":"halted"}' if self.path.endswith('/error') else b'{"ok":true}'
            if self.path == '/cases/hurricane.json':
                payload = b'{"limits":{"PORT":10},"etfs":{}}'
            elif self.path == '/api/v1/competitions/time':
                payload = b'{"state":"running","competition_id":"season-1"}'
            elif self.path == '/api/v1/orders/open':
                payload = b'{"orders":[]}'
            elif self.path == '/api/v1/positions?include_zero=true':
                payload = b'{"positions":[]}'
            elif self.path == '/api/v1/trades':
                payload = b'{"trades":[]}'
            if self.path.endswith('/empty'):
                payload = b''
            status = 403 if self.path.endswith('/error') else 200
            if self.path.endswith('/redirect'):
                status = 307
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            if self.path.endswith('/redirect'):
                self.send_header('Location', '/repeated')
            if self.path.endswith('/close'):
                self.send_header('Connection', 'close')
                self.close_connection = True
            self.end_headers()
            self.wfile.write(payload)
            self.wfile.flush()

        do_GET = do_POST = handle_request

    service = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=service.serve_forever, kwargs={'poll_interval': .01}, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{service.server_port}', requests
    finally:
        service.shutdown()
        service.server_close()
        thread.join(timeout=1)


def test_fully_read_responses_reuse_one_connection(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        assert client.request('GET', '/clock') == {'ok': True}
        assert client.request('GET', '/positions') == {'ok': True}
        assert len(requests) == 2
        assert requests[0]['port'] == requests[1]['port']
    finally:
        client.close()


def test_post_with_lost_ack_is_never_retried_and_next_read_reconnects(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        with pytest.raises((OSError, HTTPException)):
            client.request('POST', '/drop', body={'symbol': 'PORT', 'quantity': 1})
        assert [r['method'] for r in requests] == ['POST']
        assert json.loads(requests[0]['body']) == {'symbol': 'PORT', 'quantity': 1}
        assert client.request('GET', '/clock') == {'ok': True}
        assert [r['method'] for r in requests] == ['POST', 'GET']
        assert requests[0]['port'] != requests[1]['port']
    finally:
        client.close()


def test_http_error_preserves_status_and_body(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        with pytest.raises(urllib.error.HTTPError) as raised:
            client.request('GET', '/error')
        assert raised.value.code == 403
        assert json.loads(raised.value.read()) == {'detail': 'halted'}
        assert client.request('GET', '/clock') == {'ok': True}
    finally:
        client.close()


def test_server_connection_close_reconnects_on_next_explicit_request(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        assert client.request('GET', '/close') == {'ok': True}
        assert client.request('GET', '/clock') == {'ok': True}
        assert requests[0]['port'] != requests[1]['port']
    finally:
        client.close()


def test_concurrent_callers_are_serialized_without_lost_responses(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        paths = [f'/clock/{i}' for i in range(8)]
        with ThreadPoolExecutor(max_workers=4) as workers:
            results = list(workers.map(lambda path: client.request('GET', path), paths))
        assert results == [{'ok': True}] * len(paths)
        assert sorted(r['path'] for r in requests) == paths
        assert len({r['port'] for r in requests}) == 1
    finally:
        client.close()


def test_redirect_does_not_resubmit_post(server):
    url, requests = server
    client = JSONConnection(url)
    try:
        with pytest.raises(urllib.error.HTTPError) as raised:
            client.request('POST', '/redirect', body={'quantity': 1})
        assert raised.value.code == 307
        assert [r['path'] for r in requests] == ['/redirect']
    finally:
        client.close()


def test_proxy_configuration_is_respected(monkeypatch):
    monkeypatch.setattr('urllib.request.getproxies', lambda: {'https': 'http://proxy.example:3128'})
    monkeypatch.setattr('urllib.request.proxy_bypass', lambda host: host == 'localhost')
    assert proxy_required('https://exchange.example')
    assert not proxy_required('https://localhost')


def test_proxy_bypass_uses_urllib_request_host_including_ipv6_and_port(monkeypatch):
    configured = {'http': 'http://proxy.example:3128', 'no': '::1'}
    monkeypatch.setattr('urllib.request.getproxies', lambda: configured)
    monkeypatch.setattr('urllib.request.proxy_bypass',
                        lambda host: urllib.request.proxy_bypass_environment(host, configured))
    url = 'http://[::1]:8000'
    expected = not urllib.request.proxy_bypass(urllib.request.Request(url).host)
    assert expected
    assert proxy_required(url) == expected


@pytest.mark.parametrize('initial_snapshot_available', [False, True])
def test_startup_failure_closes_connection(server, monkeypatch, initial_snapshot_available):
    url, requests = server
    closed = []
    original_close = LiveExchange.close

    def close(exchange):
        closed.append(exchange)
        original_close(exchange)

    def fail_strategy(**kwargs):
        raise RuntimeError('strategy startup failed')

    monkeypatch.setattr(LiveExchange, 'close', close)
    monkeypatch.setattr(live.S, 'FairValueTrader', fail_strategy)
    if not initial_snapshot_available:
        monkeypatch.setattr(LiveExchange, 'refresh', lambda exchange: None)
    args = argparse.Namespace(url=url, key='test', dry_run=True, rate=90,
                              reuse_http=True, nowcast=True, min_edge=.025, edge_full=.03)
    reason = 'strategy startup failed' if initial_snapshot_available else 'initial account snapshot'
    with pytest.raises(RuntimeError, match=reason):
        asyncio.run(live.run(args))
    assert len(requests) == (5 if initial_snapshot_available else 1)
    assert all(r['method'] == 'GET' for r in requests)
    assert len(closed) == 1
    assert closed[0]._http._connection is None


def test_live_adapter_opt_in_preserves_uncertain_post_latch(server):
    url, requests = server
    exchange = LiveExchange(url, 'test', dry_run=False, reuse_http=True)
    try:
        assert exchange.http_reuse_enabled
        assert exchange.get('/clock') == {'ok': True}
        assert requests[0]['port'] == requests[1]['port']
        exchange.state_ready = True
        assert exchange.send('POST', '/drop', {'quantity': 1}) is None
        assert not exchange.state_ready
        assert sum(r['method'] == 'POST' for r in requests) == 1
        assert exchange.get('/clock') == {'ok': True}
    finally:
        exchange.close()


def test_live_adapter_preserves_empty_send_and_http_error_handling(server):
    url, requests = server
    exchange = LiveExchange(url, 'test', dry_run=False, reuse_http=True)
    try:
        assert exchange.send('POST', '/empty', {}) == {}
        exchange.state_ready = exchange.market_open = True
        assert exchange.send('POST', '/error', {}) is None
        assert exchange.rejected == 1
        assert not exchange.state_ready
        assert not exchange.market_open
    finally:
        exchange.close()


def test_live_adapter_falls_back_to_existing_path_for_proxy(server, monkeypatch):
    url, requests = server
    monkeypatch.setattr('bot.live.proxy_required', lambda url: True)
    exchange = LiveExchange(url, 'test', dry_run=True, reuse_http=True)
    assert not exchange.http_reuse_enabled
    assert exchange.get('/clock') == {'ok': True}
    assert requests[0]['port'] != requests[1]['port']


def test_existing_transport_remains_default(server):
    url, requests = server
    exchange = LiveExchange(url, 'test', dry_run=True)
    assert not exchange.http_reuse_enabled
    assert exchange.get('/clock') == {'ok': True}
    assert requests[0]['port'] != requests[1]['port']
    exchange.close()


@pytest.mark.parametrize('url', ['https://key@example.com', 'ftp://example.com',
                                'https://example.com?key=value', 'https://example.com#fragment'])
def test_transport_rejects_ambiguous_base_urls(url):
    with pytest.raises(ValueError):
        JSONConnection(url)
