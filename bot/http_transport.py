"""Optional serialized JSON HTTP transport with connection reuse and no retries."""
from __future__ import annotations

import http.client
import io
import json
import threading
import urllib.error
import urllib.parse
import urllib.request


def proxy_required(url):
    request = urllib.request.Request(url)
    return bool(urllib.request.getproxies().get(request.type)
                and not urllib.request.proxy_bypass(request.host))


class JSONConnection:
    def __init__(self, base_url, timeout=10):
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment):
            raise ValueError('an unambiguous HTTP(S) exchange URL is required')
        self.base_url = base_url.rstrip('/')
        self.scheme, self.host, self.port = parsed.scheme, parsed.hostname, parsed.port
        self.prefix, self.timeout = parsed.path.rstrip('/'), timeout
        self._connection = None
        self._lock = threading.RLock()

    def close(self):
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def request(self, method, path, body=None, headers=None, allow_empty=False):
        if not path.startswith('/') or path.startswith('//'):
            raise ValueError('a same-origin absolute request path is required')
        data = json.dumps(body).encode() if body is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers.setdefault('Content-Type', 'application/json')
        with self._lock:
            try:
                if self._connection is None:
                    cls = http.client.HTTPSConnection if self.scheme == 'https' else http.client.HTTPConnection
                    self._connection = cls(self.host, port=self.port, timeout=self.timeout)
                self._connection.request(method, self.prefix + path, body=data, headers=request_headers)
                response = self._connection.getresponse()
                payload = response.read()
                if response.status >= 300:
                    raise urllib.error.HTTPError(self.base_url + path, response.status,
                        response.reason, response.headers, io.BytesIO(payload))
                return {} if not payload and allow_empty else json.loads(payload)
            except BaseException:
                # The server may have accepted an action before the response
                # failed. Drop the socket, propagate, and never resubmit here.
                self.close()
                raise
