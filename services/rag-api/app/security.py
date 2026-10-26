"""Fail-closed JWT validation and document policy shared by API and Qdrant."""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from os import getenv
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ROLES = frozenset({"reader", "uploader", "tenant_admin"})
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,199}$")
audit_logger = logging.getLogger("rag.audit")
if not audit_logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    audit_logger.addHandler(handler)
audit_logger.setLevel(logging.INFO)
audit_logger.propagate = False


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    subject: str
    roles: frozenset[str]


def audit(event: str, *, principal: Principal | None = None, **details) -> None:
    """Callers supply only enums, generated document IDs, counts, and outcomes."""
    record = {"time": datetime.now(timezone.utc).isoformat(), "event": event, **details}
    if principal:
        record["tenant_ref"] = sha256(principal.tenant_id.encode()).hexdigest()[:24]
        record["actor_ref"] = sha256(
            (principal.tenant_id + "\0" + principal.subject).encode()
        ).hexdigest()[:24]
    audit_logger.info(json.dumps(record, separators=(",", ":")))


def validate_identifier(value) -> bool:
    return isinstance(value, str) and bool(IDENTIFIER.fullmatch(value))


class RotatingJWKClient(jwt.PyJWKClient):
    """Bound unknown-kid refresh traffic while retaining normal JWKS TTL caching."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rotation_lock = Lock()
        self._next_rotation_check = 0.0

    def get_signing_key(self, kid):
        with self._rotation_lock:
            keys = self.get_signing_keys()
            key = self.match_kid(keys, kid)
            if key:
                return key
            if monotonic() < self._next_rotation_check:
                raise jwt.PyJWKClientError("Unknown signing key")
            self._next_rotation_check = monotonic() + 30
            key = self.match_kid(self.get_signing_keys(refresh=True), kid)
            if not key:
                raise jwt.PyJWKClientError("Unknown signing key")
            return key


class JWTVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str, *, allow_loopback_http=False):
        for value in (issuer, jwks_url):
            parsed = urlsplit(value)
            loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if (
                (
                    parsed.scheme != "https"
                    and not (allow_loopback_http and loopback and parsed.scheme == "http")
                )
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise ValueError("OIDC issuer and JWKS URL must be trusted HTTPS URLs")
        if not audience or len(audience) > 200:
            raise ValueError("OIDC_AUDIENCE is required")
        self.issuer, self.audience = issuer, audience
        # Configured endpoint only: never follow token-supplied jku/x5u URLs.
        self.jwks = RotatingJWKClient(jwks_url, cache_keys=False, lifespan=300, timeout=5)

    @classmethod
    def from_environment(cls):
        return cls(
            getenv("OIDC_ISSUER", ""),
            getenv("OIDC_AUDIENCE", ""),
            getenv("OIDC_JWKS_URL", ""),
            allow_loopback_http=getenv("OIDC_ALLOW_LOOPBACK_HTTP") == "true",
        )

    def verify(self, token: str) -> Principal:
        if len(token) > 16384:
            raise jwt.InvalidTokenError("Oversized token")
        header = jwt.get_unverified_header(token)
        if (
            header.get("alg") != "RS256"
            or not isinstance(header.get("kid"), str)
            or not 1 <= len(header["kid"]) <= 200
            or header.get("crit")
        ):
            raise jwt.InvalidTokenError("Unsupported signing header")
        key = self.jwks.get_signing_key_from_jwt(token).key
        if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
            raise jwt.InvalidTokenError("RSA key must be at least 2048 bits")
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=self.issuer,
            audience=self.audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "tenant_id", "typ"]},
        )
        if claims["typ"] != "Bearer":
            raise jwt.InvalidTokenError("Access token required")
        if not validate_identifier(claims["tenant_id"]) or not validate_identifier(claims["sub"]):
            raise jwt.InvalidTokenError("Invalid principal")
        if any(
            isinstance(claims[k], bool) or not isinstance(claims[k], (int, float))
            for k in ("exp", "iat")
        ):
            raise jwt.InvalidTokenError("Invalid timestamps")
        # Keycloak realm roles: configure a mapper restricted to this API's roles.
        realm = claims.get("realm_access", {})
        roles = realm.get("roles", []) if isinstance(realm, dict) else None
        if not isinstance(roles, list) or not all(isinstance(r, str) for r in roles):
            raise jwt.InvalidTokenError("Invalid roles")
        return Principal(claims["tenant_id"], claims["sub"], frozenset(roles) & ROLES)


def get_token_verifier(request: Request) -> JWTVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        raise HTTPException(503, "Authentication service is not initialized")
    return verifier


bearer = HTTPBearer(auto_error=False)


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
    verifier: JWTVerifier = Depends(get_token_verifier),
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        audit("authentication_failure", reason="missing_bearer")
        raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": "Bearer"})
    try:
        return verifier.verify(credentials.credentials)
    except jwt.PyJWKClientConnectionError:
        audit("authentication_failure", reason="identity_provider_unavailable")
        raise HTTPException(503, "Identity provider unavailable") from None
    except (jwt.PyJWTError, ValueError, TypeError, KeyError, OverflowError):
        audit("authentication_failure", reason="invalid_token")
        raise HTTPException(
            401, "Invalid access token", headers={"WWW-Authenticate": "Bearer"}
        ) from None


def require_permission(principal: Principal, operation: str) -> None:
    allowed = {
        "read": ROLES,
        "upload": {"uploader", "tenant_admin"},
        "manage": {"uploader", "tenant_admin"},
        "metrics": {"tenant_admin"},
    }
    if not principal.roles.intersection(allowed[operation]):
        audit("authorization_denial", principal=principal, operation=operation)
        raise HTTPException(403, "Permission denied")


def valid_acl(payload: dict) -> bool:
    return (
        isinstance(payload, dict)
        and type(payload.get("acl_version")) is int
        and payload.get("acl_version") == 1
        and validate_identifier(payload.get("tenant_id"))
        and validate_identifier(payload.get("owner_id"))
        and payload.get("visibility") in ("private", "tenant")
        and isinstance(payload.get("allowed_subjects"), list)
        and len(payload["allowed_subjects"]) <= 100
        and all(validate_identifier(s) for s in payload["allowed_subjects"])
    )


def can_read(principal: Principal, payload: dict) -> bool:
    if not valid_acl(payload) or payload["tenant_id"] != principal.tenant_id:
        return False
    return bool(principal.roles & ROLES) and (
        "tenant_admin" in principal.roles
        or payload["owner_id"] == principal.subject
        or payload["visibility"] == "tenant"
        or principal.subject in payload["allowed_subjects"]
    )
