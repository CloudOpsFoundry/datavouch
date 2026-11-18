"""Explicit trust boundary for an existing OIDC gateway and scoped local authorization."""

import hmac
import ipaddress
import re
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from datavouch.web.evidence import strict_json


@dataclass(frozen=True)
class Principal:
    subject: str
    role: str
    connections: frozenset[str] | None

    def permits(self, connection: str) -> bool:
        return self.connections is None or connection in self.connections


LOCAL_ADMIN = Principal("local:datavouch", "admin", None)


def policy(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        raw = source.read(65537)
    if len(raw) > 65536:
        raise ValueError("Gateway policy exceeds 64 KiB")
    value = strict_json(raw.decode())
    if not isinstance(value, dict) or set(value) != {
        "allowed_hosts",
        "trusted_proxy_networks",
        "principals",
    }:
        raise ValueError("Invalid gateway policy fields")
    hosts = value["allowed_hosts"]
    if (
        not isinstance(hosts, list)
        or not 1 <= len(hosts) <= 20
        or any(
            not isinstance(h, str) or not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", h) for h in hosts
        )
    ):
        raise ValueError("Configure exact gateway host names without wildcards")
    networks = value["trusted_proxy_networks"]
    if not isinstance(networks, list) or not 1 <= len(networks) <= 20:
        raise ValueError("Configure trusted proxy networks")
    for network in networks:
        if ipaddress.ip_network(network).prefixlen == 0:
            raise ValueError("A gateway must not trust all peer addresses")
    people = value["principals"]
    if not isinstance(people, dict) or len(people) > 100:
        raise ValueError("Gateway policy supports at most 100 explicit subjects")
    for subject, account in people.items():
        if (
            not isinstance(subject, str)
            or not subject
            or len(subject) > 200
            or not subject.isprintable()
        ):
            raise ValueError("Invalid subject")
        if (
            not isinstance(account, dict)
            or set(account) != {"role", "connections"}
            or account["role"] not in {"viewer", "operator", "admin"}
        ):
            raise ValueError("Invalid subject role")
        scopes = account["connections"]
        if (
            not isinstance(scopes, list)
            or len(scopes) > 100
            or any(not isinstance(c, str) or not c.strip() or len(c) > 200 for c in scopes)
        ):
            raise ValueError("Invalid subject connection scopes")
    return dict(value)


def account(path: Path, subject: str) -> Principal:
    record = policy(path)["principals"].get(subject)
    if record is None:
        raise ValueError("Subject is not approved")
    return Principal(subject, record["role"], frozenset(record["connections"]))


def gateway_principal(request: Request, path: Path, secret: str) -> Principal:
    try:
        current = policy(path)
        peer = ipaddress.ip_address(request.client.host if request.client else "")
        if not any(
            peer in ipaddress.ip_network(network) for network in current["trusted_proxy_networks"]
        ):
            raise ValueError("Untrusted peer")
        tokens = request.headers.getlist("x-datavouch-gateway-token")
        subjects = request.headers.getlist("x-auth-request-user")
        if (
            len(tokens) != 1
            or len(subjects) != 1
            or not secrets.compare_digest(tokens[0].encode(), secret.encode())
        ):
            raise ValueError("Gateway verification failed")
        return account(path, subjects[0])
    except (ValueError, TypeError, OSError, UnicodeError) as exc:
        raise HTTPException(403, "Gateway access denied") from exc


def principal(request: Request) -> Principal:
    result = request.state.principal
    if not isinstance(result, Principal):
        raise HTTPException(403, "Identity unavailable")
    return result


def operator(request: Request) -> Principal:
    user = principal(request)
    if user.role not in {"operator", "admin"}:
        raise HTTPException(403, "Operator access required")
    return user


def administrator(request: Request) -> Principal:
    user = principal(request)
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user


def form_token(secret: str, request: Request) -> str:
    """Bind form authorization to the authenticated subject, including behind a gateway."""
    return hmac.new(secret.encode(), principal(request).subject.encode(), "sha256").hexdigest()
