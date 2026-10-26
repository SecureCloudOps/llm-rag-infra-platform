"""Opt-in, loopback-only Keycloak container with runtime-generated test credentials."""

import os
import secrets
import socket
import subprocess
import time
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest


def unused_loopback_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class DevKeycloak:
    def __init__(self, origin, admin_password):
        self.origin = origin
        self.realm = "rag-validation-" + uuid4().hex
        self.issuer = origin + "/realms/" + self.realm
        self.client_secret = secrets.token_urlsafe(32)
        self.passwords = {}
        self.users = {}
        self.admin_password = admin_password
        self.http = httpx.Client(base_url=origin, trust_env=False, timeout=15)

    def admin(self, method, path, **kwargs):
        response = self.http.post(
            "/realms/master/protocol/openid-connect/token",
            data={
                "grant_type": "password",
                "client_id": "admin-cli",
                "username": "validation-admin",
                "password": self.admin_password,
            },
        )
        response.raise_for_status()
        token = response.json()["access_token"]
        response = self.http.request(
            method, "/admin/realms" + path, headers={"Authorization": "Bearer " + token}, **kwargs
        )
        response.raise_for_status()
        return response

    def setup(self):
        self.admin(
            "POST",
            "",
            json={
                "realm": self.realm,
                "enabled": True,
                "sslRequired": "none",
                "registrationAllowed": False,
                "accessTokenLifespan": 120,
            },
        )
        for role in ("reader", "uploader", "tenant_admin"):
            self.admin("POST", f"/{self.realm}/roles", json={"name": role})
        profile = self.admin("GET", f"/{self.realm}/users/profile").json()
        profile["attributes"].append(
            {
                "name": "tenant_id",
                "displayName": "Tenant",
                "permissions": {"view": ["admin"], "edit": ["admin"]},
                "validations": {"length": {"min": 1, "max": 200}},
            }
        )
        self.admin("PUT", f"/{self.realm}/users/profile", json=profile)
        self.admin(
            "POST",
            f"/{self.realm}/clients",
            json={
                "clientId": "rag-api",
                "enabled": True,
                "protocol": "openid-connect",
                "bearerOnly": True,
            },
        )
        mappers = [
            {
                "name": "tenant",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-attribute-mapper",
                "config": {
                    "user.attribute": "tenant_id",
                    "claim.name": "tenant_id",
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                    "userinfo.token.claim": "false",
                },
            },
            {
                "name": "audience",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-audience-mapper",
                "config": {
                    "included.client.audience": "rag-api",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                },
            },
            {
                "name": "roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "config": {
                    "claim.name": "realm_access.roles",
                    "multivalued": "true",
                    "jsonType.label": "String",
                    "access.token.claim": "true",
                    "id.token.claim": "false",
                },
            },
        ]
        self.admin(
            "POST",
            f"/{self.realm}/clients",
            json={
                "clientId": "rag-validation",
                "secret": self.client_secret,
                "enabled": True,
                "protocol": "openid-connect",
                "publicClient": False,
                "directAccessGrantsEnabled": True,
                "standardFlowEnabled": False,
                "serviceAccountsEnabled": False,
                "fullScopeAllowed": True,
                # Keycloak 26 supplies the required subject claim through this scope.
                "defaultClientScopes": ["basic"],
                "protocolMappers": mappers,
            },
        )
        for username, tenant, role in [
            ("a-reader", "tenant-a", "reader"),
            ("a-owner", "tenant-a", "uploader"),
            ("a-admin", "tenant-a", "tenant_admin"),
            ("b-owner", "tenant-b", "uploader"),
            ("b-admin", "tenant-b", "tenant_admin"),
        ]:
            password = secrets.token_urlsafe(32)
            response = self.admin(
                "POST",
                f"/{self.realm}/users",
                json={
                    "username": username,
                    "enabled": True,
                    "firstName": "Validation",
                    "lastName": "User",
                    "email": username + "@example.invalid",
                    "emailVerified": True,
                    "requiredActions": [],
                    "attributes": {"tenant_id": [tenant]},
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
            )
            user_id = urlsplit(response.headers["location"]).path.rsplit("/", 1)[-1]
            role_rep = self.admin("GET", f"/{self.realm}/roles/{role}").json()
            self.admin(
                "POST", f"/{self.realm}/users/{user_id}/role-mappings/realm", json=[role_rep]
            )
            self.passwords[username], self.users[username] = password, user_id

    def token(self, username):
        response = self.http.post(
            f"/realms/{self.realm}/protocol/openid-connect/token",
            data={
                "client_id": "rag-validation",
                "client_secret": self.client_secret,
                "grant_type": "password",
                "username": username,
                "password": self.passwords[username],
            },
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def rotate(self):
        realm_id = self.admin("GET", f"/{self.realm}").json()["id"]
        self.admin(
            "POST",
            f"/{self.realm}/components",
            json={
                "name": "validation-rsa-rotation",
                "parentId": realm_id,
                "providerId": "rsa-generated",
                "providerType": "org.keycloak.keys.KeyProvider",
                "config": {
                    "priority": ["200"],
                    "enabled": ["true"],
                    "active": ["true"],
                    "algorithm": ["RS256"],
                    "keySize": ["2048"],
                },
            },
        )


# Official Quay multi-platform digest verified by Docker during the image pull.
KEYCLOAK_IMAGE = (
    "quay.io/keycloak/keycloak@sha256:"
    "044a457e04987e1fff756be3d2fa325a4ef420fa356b7034ecc9f1b693c32761"
)


@pytest.fixture
def dev_keycloak():
    """Use a cached official image; never download or substitute a synthetic issuer."""
    image = subprocess.run(
        ["docker", "image", "inspect", KEYCLOAK_IMAGE],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if image.returncode:
        pytest.fail("Pull the pinned official Quay Keycloak image before running the live test")
    name = "rag-keycloak-dev-" + uuid4().hex
    origin = f"http://127.0.0.1:{unused_loopback_port()}"
    password = secrets.token_urlsafe(32)
    server = DevKeycloak(origin, password)
    created = False
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--pull=never",
                "--rm",
                "-d",
                "--name",
                name,
                "--publish",
                f"127.0.0.1:{urlsplit(origin).port}:8080",
                "--env",
                "KC_BOOTSTRAP_ADMIN_USERNAME",
                "--env",
                "KC_BOOTSTRAP_ADMIN_PASSWORD",
                "--env",
                "JAVA_OPTS_APPEND",
                KEYCLOAK_IMAGE,
                "start-dev",
                "--db=dev-mem",
                "--http-host=0.0.0.0",
                "--http-port=8080",
                "--hostname=" + origin,
            ],
            env={
                **os.environ,
                "KC_BOOTSTRAP_ADMIN_USERNAME": "validation-admin",
                "KC_BOOTSTRAP_ADMIN_PASSWORD": password,
                "JAVA_OPTS_APPEND": os.getenv("JAVA_OPTS_APPEND", "")
                + " -Xms64m -Xmx768m -XX:ActiveProcessorCount=2",
            },
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        created = True
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            running = subprocess.check_output(
                ["docker", "inspect", "--format", "{{.State.Running}}", name], text=True
            ).strip()
            if running != "true":
                pytest.fail("Development Keycloak container exited before readiness")
            try:
                if (
                    server.http.get("/realms/master/.well-known/openid-configuration").status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.25)
        else:
            pytest.fail("Development Keycloak readiness timeout")
        server.setup()
        yield server
    finally:
        server.http.close()
        if created:
            subprocess.run(
                ["docker", "rm", "-f", name],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )


@pytest.fixture
def keyed_qdrant(monkeypatch):
    """Disposable cached Qdrant; both the API and server use the same random key."""
    name = "keycloak-qdrant-" + uuid4().hex
    key = secrets.token_urlsafe(32)
    origin = f"http://127.0.0.1:{unused_loopback_port()}"
    port = urlsplit(origin).port
    created = False
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--pull=never",
                "--rm",
                "-d",
                "--name",
                name,
                "--env",
                "QDRANT__SERVICE__API_KEY",
                "--publish",
                f"127.0.0.1:{port}:6333",
                "qdrant/qdrant:v1.12.6",
            ],
            env={**os.environ, "QDRANT__SERVICE__API_KEY": key},
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        created = True
        with httpx.Client(base_url=origin, trust_env=False, timeout=2) as client:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                try:
                    if client.get("/collections", headers={"api-key": key}).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("Disposable keyed Qdrant readiness timeout")
            assert client.get("/collections").status_code == 401
            assert (
                client.get("/collections", headers={"api-key": "wrong-validation-key"}).status_code
                == 401
            )
            monkeypatch.setenv("QDRANT_URL", origin)
            monkeypatch.setenv("QDRANT_API_KEY", key)
            monkeypatch.setenv("NO_PROXY", os.getenv("NO_PROXY", "") + ",localhost,127.0.0.1")
            monkeypatch.setenv("no_proxy", os.getenv("no_proxy", "") + ",localhost,127.0.0.1")
            yield origin
    finally:
        if created:
            subprocess.run(
                ["docker", "rm", "-f", name],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
