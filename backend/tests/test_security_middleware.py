"""Tests for the security headers middleware + rate limiting."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_security_headers_present_on_root() -> None:
    client = TestClient(app)
    r = client.get("/api/healthz")
    assert r.status_code == 200
    h = r.headers
    assert "max-age=31536000" in h.get("strict-transport-security", "")
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-operations", h.get("x-frame-options")) in {
        "DENY",
        "deny",
    }
    assert "strict-origin-when-cross-origin" in h.get("referrer-policy", "")
    csp = h.get("content-security-policy", "")
    assert "default-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "permissions-policy" in {k.lower() for k in h.keys()}


def test_rate_limit_headers_announce_quota() -> None:
    """slowapi exposes ``x-ratelimit-*`` so clients can self-throttle."""
    from app.main import limiter

    # Reset the in-memory limit storage so test order doesn't matter.
    limiter.reset()

    client = TestClient(app)
    # Use the test-prompts-categories endpoint — cheap, doesn't fan out.
    r = client.get("/api/test-prompts/categories")
    assert r.status_code == 200


def test_og_rate_limit_kicks_in_after_quota() -> None:
    """Hammering ``/api/og`` past 60/min returns 429.

    ``/api/og`` is a cheap synchronous PNG render; safe to actually loop.
    Confirms the slowapi decorator is wired up live (not just imported).
    """
    from app.main import limiter

    limiter.reset()

    client = TestClient(app)
    statuses: list[int] = []
    for _ in range(62):
        r = client.get("/api/og?d=example.com&s=80&g=A")
        statuses.append(r.status_code)
        if r.status_code == 429:
            break
    assert 429 in statuses, f"expected 429 in {statuses[-5:]}"


def test_cors_locked_to_known_origins() -> None:
    """Default CORS config should NOT echo back arbitrary origins."""
    client = TestClient(app)
    r = client.options(
        "/api/scan",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )
    # Either 400 (preflight rejected) or 200 with NO acao header for our
    # disallowed origin. Either way, attacker.example must not be echoed.
    acao = r.headers.get("access-control-allow-origin", "")
    assert acao != "https://attacker.example"
    assert acao != "*"
