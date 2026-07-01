# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for the shared agent-API auth token helpers.

Uses a real in-process HTTP server (no mocks, per repo test policy) to emulate the
host's POST /token mint endpoint.
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from conductor.ai.agents._internal.token_utils import (
    _TOKEN_CACHE,
    agent_api_auth_headers,
    decode_jwt_exp,
    resolve_agent_api_token,
)


def _jwt(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{header}.{payload}.sig"


class _TokenHandler(BaseHTTPRequestHandler):
    mint_count = 0
    token = _jwt(4102444800)  # far future

    def do_POST(self):  # noqa: N802
        if self.path != "/token":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        if body.get("keyId") != "kid" or body.get("keySecret") != "ksec":
            self.send_response(401)
            self.end_headers()
            return
        type(self).mint_count += 1
        data = json.dumps({"token": self.token}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):  # silence
        pass


@pytest.fixture()
def token_server():
    _TokenHandler.mint_count = 0
    srv = HTTPServer(("127.0.0.1", 0), _TokenHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    yield url
    srv.shutdown()
    _TOKEN_CACHE.clear()


def test_decode_jwt_exp():
    assert decode_jwt_exp(_jwt(1700000000)) == 1700000000.0
    assert decode_jwt_exp("opaque-token") == 0.0
    assert decode_jwt_exp("") == 0.0


def test_api_key_passthrough():
    # An explicit api_key is already a token — no mint, returned as-is.
    assert resolve_agent_api_token("http://unused", api_key="tok-123") == "tok-123"
    assert agent_api_auth_headers("http://unused", api_key="tok-123") == {
        "X-Authorization": "tok-123"
    }


def test_anonymous_returns_none():
    assert resolve_agent_api_token("http://unused") is None
    assert agent_api_auth_headers("http://unused") == {}


def test_mint_and_cache(token_server):
    tok = resolve_agent_api_token(token_server, auth_key="kid", auth_secret="ksec")
    assert tok == _TokenHandler.token
    # Second call must hit the cache (no second mint).
    tok2 = resolve_agent_api_token(token_server, auth_key="kid", auth_secret="ksec")
    assert tok2 == tok
    assert _TokenHandler.mint_count == 1
    assert agent_api_auth_headers(token_server, auth_key="kid", auth_secret="ksec") == {
        "X-Authorization": tok
    }


def test_expired_cache_reminted(token_server):
    _TOKEN_CACHE[(token_server, "kid")] = (_jwt(100), 100.0)  # long expired
    tok = resolve_agent_api_token(token_server, auth_key="kid", auth_secret="ksec")
    assert tok == _TokenHandler.token
    assert _TokenHandler.mint_count == 1  # re-minted exactly once


def test_bad_credentials_none(token_server):
    assert resolve_agent_api_token(token_server, auth_key="kid", auth_secret="WRONG") is None