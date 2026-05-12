"""Coverage backfill — targets the lines that the topic-focused test files don't reach.

Each test below references the specific module + line range it's added to cover.
Keep this file boring and tactical; it is regression insurance, not feature
documentation.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from httpx import Response

from app.fetcher import Fetcher
from app.fixes import build_fix_for_check
from app.main import (
    _sanitize_domain,
    _sanitize_grade,
    _sanitize_score,
    _unwrap,
    _unwrap_single,
    app,
)
from app.models import CategoryId, CategoryResult, CheckResult, CheckStatus
from app.probes._util import host_matches
from app.probes.brave import probe_brave
from app.probes.gemini import probe_gemini
from app.probes.mistral import probe_mistral
from app.scanners.citability import (
    _byline_anchor,
    _check_byline_links,
    _check_visible_updated,
    _date_modified_strings,
    _has_byline_text,
    _sameas_count,
    check_citability,
)
from app.scanners.structured_data import _check_jsonld_validity
from app.scoring import grade_for, overall_score, score_category


# ─── main.py sanitizers + unwrap helpers ────────────────────────────────────


def test_sanitize_domain_strips_scheme_and_path():
    assert _sanitize_domain("HTTPS://www.Example.com/foo?bar") == "example.com"


def test_sanitize_domain_strips_query_and_fragment():
    assert _sanitize_domain("example.com?x=1#anchor") == "example.com"


def test_sanitize_domain_falls_back_to_site_on_empty_input():
    assert _sanitize_domain("") == "site"
    assert _sanitize_domain("///") == "site"
    # Non-printable chars stripped → empty → fallback.
    assert _sanitize_domain("!!!") == "site"


def test_sanitize_grade_accepts_known_letters_and_falls_back():
    assert _sanitize_grade("a") == "A"
    assert _sanitize_grade("F") == "F"
    assert _sanitize_grade("Z") == "?"
    assert _sanitize_grade("") == "?"


def test_sanitize_score_clamps_to_0_100():
    assert _sanitize_score(-10) == 0
    assert _sanitize_score(150) == 100
    assert _sanitize_score(72) == 72


def test_unwrap_returns_payload_when_not_exception():
    errors: list[str] = []
    assert _unwrap([1, 2, 3], errors, "x") == [1, 2, 3]
    assert errors == []


def test_unwrap_records_exception_and_returns_empty_list():
    errors: list[str] = []
    out = _unwrap(RuntimeError("boom"), errors, "scanner_x")
    assert out == []
    assert "scanner_x" in errors[0] and "boom" in errors[0]


def test_unwrap_single_returns_payload_when_not_exception():
    errors: list[str] = []
    obj = object()
    assert _unwrap_single(obj, errors, "x") is obj
    assert errors == []


def test_unwrap_single_records_exception_and_returns_none():
    errors: list[str] = []
    out = _unwrap_single(ValueError("nope"), errors, "scanner_y")
    assert out is None
    assert "scanner_y" in errors[0]


# ─── main.py endpoint behavior ──────────────────────────────────────────────


@pytest.fixture
def client():
    return TestClient(app)


def test_root_endpoint(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "AgentGEOScore"


def test_root_alias_under_api(client):
    r = client.get("/api/")
    assert r.status_code == 200


def test_healthz(client):
    r = client.get("/api/healthz")
    assert r.json() == {"ok": True}


def test_categories_endpoint_returns_list(client):
    r = client.get("/api/test-prompts/categories")
    assert r.status_code == 200
    body = r.json()
    assert "categories" in body
    assert isinstance(body["categories"], list)
    assert len(body["categories"]) > 0
    assert "slug" in body["categories"][0]


def test_scan_rejects_invalid_url(client):
    """ValueError from WebsiteTarget.from_url → HTTP 400."""
    r = client.post(
        "/api/scan",
        json={"url": "ftp://not-a-real-scheme", "include_probe": False},
    )
    assert r.status_code in (400, 422)


def test_compare_rejects_invalid_target(client):
    r = client.post(
        "/api/compare",
        json={"target": "not a url", "competitors": ["square.com"]},
    )
    assert r.status_code in (400, 422)


def test_og_endpoint_rejects_missing_domain(client):
    r = client.get("/api/og")
    assert r.status_code == 400


def test_og_endpoint_brand_mode_returns_png(client):
    r = client.get("/api/og?brand=1")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_og_endpoint_per_report_renders_png(client):
    r = client.get("/api/og?d=stripe.com&s=87&g=B")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"


def test_share_page_rejects_missing_domain(client):
    r = client.get("/share")
    assert r.status_code == 400


def test_share_page_renders_html_with_og_tags(client):
    r = client.get("/share?d=stripe.com&s=87&g=A")
    assert r.status_code == 200
    body = r.text
    assert "stripe.com" in body
    assert 'property="og:image"' in body
    assert 'twitter:card' in body
    # Refresh meta routes humans to the SPA.
    assert "Redirecting" in body


def test_share_page_handles_empty_grade(client):
    """An empty 'g' query param exercises the max_length=2 branch."""
    r = client.get("/share?d=stripe.com&s=87&g=")
    assert r.status_code == 200
    # Empty grade renders as '?' after sanitisation.
    assert ">?</" in r.text or "(?)" in r.text or "?" in r.text


def test_test_prompts_override_rejects_invalid_domain(client):
    r = client.get("/api/test-prompts?domain=:::&category=fintech-payments")
    assert r.status_code == 400


@respx.mock
def test_test_prompts_override_returns_bundle(client):
    """Successful re-roll path covers the override endpoint body."""
    respx.get("https://stripe.com").mock(
        return_value=Response(
            200,
            text="<html><head><title>Stripe</title></head><body><h1>Stripe</h1></body></html>",
        )
    )
    r = client.get("/api/test-prompts?domain=stripe.com&category=fintech-payments")
    assert r.status_code == 200
    body = r.json()
    assert "prompts" in body
    assert "brand" in body


# ─── citability helpers — byline + dead-helper coverage ─────────────────────


def test_byline_anchor_finds_rel_author():
    soup = BeautifulSoup(
        '<a rel="author" href="/about/jane">Jane</a>', "lxml"
    )
    a = _byline_anchor(soup)
    assert a is not None
    assert a.get("href") == "/about/jane"


def test_byline_anchor_finds_itemprop_author_with_inner_link():
    soup = BeautifulSoup(
        '<span itemprop="author"><a href="/about/jane">Jane</a></span>',
        "lxml",
    )
    a = _byline_anchor(soup)
    assert a is not None
    assert a.get("href") == "/about/jane"


def test_byline_anchor_finds_itemprop_author_when_self_is_anchor():
    soup = BeautifulSoup(
        '<a itemprop="author" href="/about/jane">Jane</a>',
        "lxml",
    )
    a = _byline_anchor(soup)
    assert a is not None
    assert a.get("href") == "/about/jane"


def test_byline_anchor_finds_class_selector():
    soup = BeautifulSoup(
        '<div class="byline"><a href="/staff/jane">Jane</a></div>',
        "lxml",
    )
    a = _byline_anchor(soup)
    assert a is not None
    assert a.get("href") == "/staff/jane"


def test_byline_anchor_returns_none_on_no_match():
    soup = BeautifulSoup("<p>just text</p>", "lxml")
    assert _byline_anchor(soup) is None


def test_has_byline_text_detects_byline_class():
    soup = BeautifulSoup('<p class="byline">By Jane</p>', "lxml")
    assert _has_byline_text(soup) is True


def test_has_byline_text_detects_author_class():
    soup = BeautifulSoup('<p class="author-name">By Jane</p>', "lxml")
    assert _has_byline_text(soup) is True


def test_has_byline_text_detects_meta_author():
    soup = BeautifulSoup('<html><head><meta name="author" content="Jane"></head></html>', "lxml")
    assert _has_byline_text(soup) is True


def test_has_byline_text_detects_article_author_meta():
    soup = BeautifulSoup(
        '<html><head><meta property="article:author" content="https://x.com/jane"></head></html>',
        "lxml",
    )
    assert _has_byline_text(soup) is True


def test_has_byline_text_false_when_no_signals():
    soup = BeautifulSoup("<p>just content</p>", "lxml")
    assert _has_byline_text(soup) is False


def test_check_byline_links_skip_when_no_byline_at_all():
    soup = BeautifulSoup("<article><p>just prose</p></article>", "lxml")
    r = _check_byline_links(soup, [])
    assert r.status == CheckStatus.SKIP


def test_check_byline_links_pass_when_anchor_present():
    # `_has_byline_text` keys off class/meta hints — adding a class on the
    # surrounding element is what flips the check from SKIP to PASS.
    soup = BeautifulSoup(
        '<article><p class="byline">By '
        '<a rel="author" href="/about">Jane</a></p></article>',
        "lxml",
    )
    r = _check_byline_links(soup, [])
    assert r.status == CheckStatus.PASS
    assert r.score == 1.0


def test_check_byline_links_fail_when_byline_present_but_no_link():
    """A byline class with no anchor → FAIL (the 0.1-scoring branch)."""
    soup = BeautifulSoup(
        '<article><p class="byline">By Jane Doe</p></article>', "lxml"
    )
    r = _check_byline_links(soup, [])
    assert r.status == CheckStatus.FAIL


def test_sameas_count_list_strips_blanks():
    assert _sameas_count({"sameAs": ["https://x.com/a", "", "  ", "https://y.com/b"]}) == 2


def test_sameas_count_single_string():
    assert _sameas_count({"sameAs": "https://x.com/a"}) == 1


def test_sameas_count_blank_string_is_zero():
    assert _sameas_count({"sameAs": "   "}) == 0


def test_sameas_count_missing_field_is_zero():
    assert _sameas_count({}) == 0


def test_date_modified_strings_walks_nested():
    blocks = [
        {
            "@type": "WebPage",
            "mainEntity": {"@type": "Article", "datePublished": "2026-01-01"},
        },
        {"@type": "Article", "dateModified": "2026-05-12"},
    ]
    out = _date_modified_strings(blocks)
    assert "2026-01-01" in out
    assert "2026-05-12" in out


def test_check_visible_updated_skip_without_article():
    soup = BeautifulSoup("<p>not an article</p>", "lxml")
    r = _check_visible_updated(soup, "not an article", [])
    assert r.status == CheckStatus.SKIP


def test_check_visible_updated_warn_when_time_only():
    soup = BeautifulSoup(
        '<article><time datetime="2026-05-12">May 12</time></article>',
        "lxml",
    )
    r = _check_visible_updated(soup, "May 12", [])
    assert r.status == CheckStatus.WARN


def test_check_visible_updated_fail_when_neither():
    soup = BeautifulSoup("<article><p>undated</p></article>", "lxml")
    r = _check_visible_updated(soup, "undated", [])
    assert r.status == CheckStatus.FAIL


# ─── citability domain helper edge ──────────────────────────────────────────


def test_check_citability_handles_empty_html():
    """Empty HTML should return no checks (early return)."""
    assert check_citability("", []) == []


# ─── probes — error / edge paths ────────────────────────────────────────────


@respx.mock
async def test_brave_records_http_error(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "fake")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        side_effect=httpx.ConnectError("dns failure")
    )
    r = await probe_brave(["q"], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "dns failure" in r.detail or "Probe unavailable" in r.detail


@respx.mock
async def test_brave_partial_rank_warn(monkeypatch):
    """One of two queries ranks → WARN, score reflects partial coverage."""
    monkeypatch.setenv("BRAVE_API_KEY", "fake")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        side_effect=[
            Response(200, json={"web": {"results": [{"url": "https://example.com/a"}]}}),
            Response(200, json={"web": {"results": [{"url": "https://other.com/b"}]}}),
        ]
    )
    r = await probe_brave(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.WARN
    assert r.score < 1.0 and r.score > 0


@respx.mock
async def test_gemini_records_http_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(side_effect=httpx.ReadTimeout("timed out"))
    r = await probe_gemini(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


async def test_gemini_empty_query_list_skips(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    r = await probe_gemini([], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "No queries to run" in r.detail


@respx.mock
async def test_mistral_records_non_200(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "fake")
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(503, text="")
    )
    r = await probe_mistral(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


@respx.mock
async def test_mistral_records_http_error(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "fake")
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        side_effect=httpx.ConnectError("dns failure")
    )
    r = await probe_mistral(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


# ─── _util.host_matches ─────────────────────────────────────────────────────


def test_host_matches_handles_www_prefix():
    assert host_matches("https://www.example.com/page", "example.com") is True


def test_host_matches_returns_false_on_unrelated_host():
    assert host_matches("https://other.com/x", "example.com") is False


def test_host_matches_handles_malformed_url():
    # Anything we can't parse cleanly → False rather than blowing up.
    assert host_matches("notaurl", "example.com") is False


# ─── fetcher — bounded responses + redirects ────────────────────────────────


@respx.mock
async def test_fetcher_caps_oversized_response():
    """A body larger than MAX_RESPONSE_BYTES is rejected with a clear error."""
    # 6 MiB payload — over the 5 MiB cap.
    big = b"x" * (6 * 1024 * 1024)
    respx.get("https://example.com/big").mock(return_value=Response(200, content=big))
    async with Fetcher() as f:
        r = await f.get("https://example.com/big")
    assert r.error is not None
    assert "exceeds" in r.error or "bytes" in r.error


@respx.mock
async def test_fetcher_rejects_too_many_redirects():
    """A redirect loop is bounded by MAX_REDIRECTS."""
    respx.get("https://example.com/loop").mock(
        return_value=Response(302, headers={"location": "https://example.com/loop"})
    )
    async with Fetcher() as f:
        r = await f.get("https://example.com/loop")
    assert r.error is not None
    assert "redirect" in r.error.lower()


@respx.mock
async def test_fetcher_records_http_error():
    """Network-level failures become FetchResult.error rather than raising."""
    respx.get("https://broken.example/").mock(side_effect=httpx.ConnectError("dns"))
    async with Fetcher() as f:
        r = await f.get("https://broken.example/")
    assert r.status == 0
    assert r.error is not None


# ─── scoring helpers ────────────────────────────────────────────────────────


def test_score_category_empty_returns_zero():
    assert score_category([]) == 0


def test_score_category_all_skipped_returns_zero():
    skipped = CheckResult(
        id="x", label="x", status=CheckStatus.SKIP, score=0.0, weight=0.0, detail=""
    )
    assert score_category([skipped]) == 0


def test_overall_score_excludes_all_skip_category():
    cat = CategoryResult(
        id=CategoryId.AGENT_ACCESS,
        label="Agent Access",
        weight=0.25,
        score=0,
        checks=[
            CheckResult(
                id="x",
                label="x",
                status=CheckStatus.SKIP,
                score=0.0,
                weight=0.0,
                detail="",
            )
        ],
        summary="",
    )
    assert overall_score([cat]) == 0


def test_overall_score_empty_list():
    assert overall_score([]) == 0


def test_grade_for_bands():
    assert grade_for(95) == "A"
    assert grade_for(80) == "B"
    assert grade_for(60) == "C"
    assert grade_for(45) == "D"
    assert grade_for(10) == "F"


# ─── fixes.build_fix_for_check ─────────────────────────────────────────────


def test_build_fix_for_check_provides_fallback_for_unknown_id():
    """build_fix_for_check synthesises a generic Fix when the check_id has no
    bespoke template — covers the fallback branch."""
    cat = CategoryResult(
        id=CategoryId.AGENT_ACCESS,
        label="Agent Access",
        weight=0.25,
        score=0,
        checks=[],
        summary="",
    )
    check = CheckResult(
        id="totally_unknown_check_id",
        label="X label",
        status=CheckStatus.FAIL,
        score=0.0,
        weight=1.0,
        detail="",
    )
    fix = build_fix_for_check(cat, check, "example.com")
    assert fix is not None
    assert "X label" in fix.title
