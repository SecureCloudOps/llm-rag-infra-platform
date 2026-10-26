"""Ephemeral RSA issuer and real HTTP JWKS fixture; never ships in the image."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from os import getenv
from time import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.security import JWTVerifier


@pytest.fixture
def identity_provider(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", use="sig", alg="RS256")
    state = {"keys": [jwk], "requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.path == "/jwks"
            state["requests"] += 1
            body = json.dumps({"keys": state["keys"]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("NO_PROXY", getenv("NO_PROXY", "") + ",localhost,127.0.0.1")
    monkeypatch.setenv("no_proxy", getenv("no_proxy", "") + ",localhost,127.0.0.1")
    verifier = JWTVerifier(
        origin + "/realms/rag", "rag-api", origin + "/jwks", allow_loopback_http=True
    )

    def token(tenant="tenant-a", subject="alice", roles=("reader",), **changes):
        claims = dict(
            iss=origin + "/realms/rag",
            aud="rag-api",
            sub=subject,
            tenant_id=tenant,
            iat=int(time()) - 1,
            exp=int(time()) + 300,
            typ="Bearer",
            realm_access={"roles": list(roles)},
        )
        claims.update(changes)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})

    yield SimpleNamespace(
        key=key, jwk=jwk, state=state, verifier=verifier, token=token, origin=origin
    )
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)
