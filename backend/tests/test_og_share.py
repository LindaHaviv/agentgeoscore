"""Tests for the OG image + share endpoints."""
from __future__ import annotations

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.og import HEIGHT, WIDTH, render_brand_card, render_share_card

client = TestClient(app)


# ---------------------------------------------------------------------------
# Pure renderer
# ---------------------------------------------------------------------------


def _open(png_bytes: bytes) -> Image.Image:
    return Image.open(BytesIO(png_bytes))


@pytest.mark.parametrize(
    ("score", "grade"),
    [(94, "A"), (80, "B"), (70, "C"), (47, "D"), (20, "F")],
)
def test_share_card_renders_correct_dimensions(score: int, grade: str) -> None:
    png = render_share_card(domain="example.com", score=score, grade=grade)
    img = _open(png)
    # OG-spec canvas (1200x630 = 1.91:1).
    assert (img.width, img.height) == (WIDTH, HEIGHT)
    assert img.format == "PNG"


def test_share_card_handles_long_domain_without_overflow() -> None:
    """Domain longer than the content width must be truncated with an ellipsis,
    not spill over the canvas edge."""
    long_domain = "a" * 80 + ".example.com"
    png = render_share_card(domain=long_domain, score=50, grade="D")
    img = _open(png)
    assert (img.width, img.height) == (WIDTH, HEIGHT)
    # Sanity: the PNG isn't empty / corrupt — Pillow can re-decode it.
    assert len(png) > 1000


def test_brand_card_renders() -> None:
    png = render_brand_card()
    img = _open(png)
    assert (img.width, img.height) == (WIDTH, HEIGHT)


def test_share_card_is_deterministic() -> None:
    """Same inputs produce byte-identical output (matters for HTTP caching)."""
    a = render_share_card(domain="stripe.com", score=94, grade="A")
    b = render_share_card(domain="stripe.com", score=94, grade="A")
    assert a == b


def test_bundled_fonts_are_actually_loaded() -> None:
    """If the bundled font files disappear (e.g. aren't copied into the deploy
    image), Pillow silently falls back to an ~8px bitmap font and the card
    renders nearly blank. This size floor catches that failure mode."""
    png = render_share_card(domain="stripe.com", score=94, grade="A")
    # A properly-rendered card is ~40-50KB. A bitmap-fallback card is ~10KB.
    # 25KB leaves headroom for PNG entropy variance but still catches fallback.
    assert len(png) > 25_000, (
        f"Share card rendered too small ({len(png)} bytes) — bundled fonts "
        "may be missing from the deploy image."
    )


# ---------------------------------------------------------------------------
# /api/og endpoint
# ---------------------------------------------------------------------------


def test_og_endpoint_returns_png_with_cache_header() -> None:
    r = client.get("/api/og", params={"d": "stripe.com", "s": 94, "g": "A"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Cache header lets Twitter / Slack / Discord's image proxy hold the PNG.
    assert "max-age" in r.headers.get("cache-control", "")
    img = _open(r.content)
    assert (img.width, img.height) == (WIDTH, HEIGHT)


def test_og_endpoint_brand_mode() -> None:
    r = client.get("/api/og", params={"brand": 1})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    img = _open(r.content)
    assert (img.width, img.height) == (WIDTH, HEIGHT)


def test_og_endpoint_requires_domain_in_report_mode() -> None:
    r = client.get("/api/og")
    assert r.status_code == 400


def test_og_endpoint_clamps_score_and_grade() -> None:
    # Score out of 0-100 band — clamped, not rejected.
    r = client.get("/api/og", params={"d": "example.com", "s": 50, "g": "Z"})
    # FastAPI validates score range via Query(ge=0, le=100) — out-of-band hits 422.
    # But unknown grade letters should just be rendered as "?", not error.
    assert r.status_code == 200


def test_og_endpoint_rejects_out_of_range_score() -> None:
    r = client.get("/api/og", params={"d": "example.com", "s": 150, "g": "A"})
    # Pydantic Query validation rejects this at the FastAPI layer.
    assert r.status_code == 422


def test_og_endpoint_sanitizes_malicious_domain() -> None:
    # Script tags / control characters in the query must not crash the renderer
    # or leak into the response.
    r = client.get(
        "/api/og",
        params={"d": '<script>alert(1)</script>.com', "s": 50, "g": "D"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


# ---------------------------------------------------------------------------
# /share endpoint
# ---------------------------------------------------------------------------


def test_share_page_contains_og_meta_tags() -> None:
    r = client.get("/share", params={"d": "stripe.com", "s": 94, "g": "A"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    body = r.text
    # Core OG tags — Twitter / Slack / Discord need all of these.
    assert '<meta property="og:title"' in body
    assert '<meta property="og:description"' in body
    assert '<meta property="og:url"' in body
    assert '<meta property="og:image"' in body
    assert '<meta property="og:image:width" content="1200"' in body
    assert '<meta property="og:image:height" content="630"' in body
    assert '<meta name="twitter:card" content="summary_large_image"' in body
    # Metadata is encoded into the visible title/image URL.
    assert "stripe.com" in body
    assert "94/100" in body
    assert "(A)" in body
    # og:image points at the /api/og route with the same params.
    assert "/api/og?d=stripe.com&amp;s=94&amp;g=A" in body


def test_share_page_redirects_humans_to_spa_report() -> None:
    r = client.get("/share", params={"d": "stripe.com", "s": 94, "g": "A"})
    # Meta refresh + JS redirect both point at the SPA. FRONTEND_ORIGIN default
    # is the devinapps deploy, but any non-empty URL ending in /report/<d> passes.
    assert "/report/stripe.com" in r.text
    assert 'http-equiv="refresh"' in r.text


def test_share_page_requires_domain() -> None:
    r = client.get("/share")
    assert r.status_code == 400


def test_share_page_escapes_html_in_domain() -> None:
    """Crawler pages that blindly echo URL params are classic XSS vectors.
    The domain is sanitized down to host-safe chars AND html-escaped."""
    r = client.get(
        "/share",
        params={"d": '"><script>alert(1)</script>', "s": 50, "g": "D"},
    )
    assert r.status_code == 200
    # The raw script tag must NEVER appear in the rendered HTML.
    assert "<script>alert(1)</script>" not in r.text
    # And the attribute-breaking quote must be escaped.
    assert 'value=""><script' not in r.text


def test_share_page_clamps_unknown_grade() -> None:
    r = client.get("/share", params={"d": "example.com", "s": 50, "g": "Q"})
    assert r.status_code == 200
    # Unknown grades fall back to "?" rather than 400-ing the embed.
    assert "(?)" in r.text


def test_share_page_honours_x_forwarded_proto_for_og_image() -> None:
    """Fly terminates TLS at the edge; the app server sees http internally.
    The og:image must use https so Slack/Twitter image proxies accept it."""
    r = client.get(
        "/share",
        params={"d": "stripe.com", "s": 94, "g": "A"},
        headers={"x-forwarded-proto": "https", "host": "example.test"},
    )
    assert r.status_code == 200
    # og:image URL must be absolute + https when the forwarded scheme says so.
    assert 'content="https://example.test/api/og?' in r.text
    assert 'content="http://example.test/api/og?' not in r.text


def test_backend_origin_env_overrides_host_header(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pinned BACKEND_ORIGIN wins over a spoofed Host header — prevents
    attackers from making embeds render an og:image pointing at a host they
    control via a crafted request."""
    from app import main as main_mod

    monkeypatch.setattr(main_mod, "BACKEND_ORIGIN", "https://pinned.example")
    r = client.get(
        "/share",
        params={"d": "stripe.com", "s": 94, "g": "A"},
        headers={"host": "attacker.test", "x-forwarded-proto": "https"},
    )
    assert r.status_code == 200
    assert "https://pinned.example/api/og?" in r.text
    # The spoofed host must NOT appear in the og:image URL.
    assert "attacker.test/api/og" not in r.text
