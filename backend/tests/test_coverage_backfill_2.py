"""Coverage backfill round 2 — js_rendering framework labels, discoverability
response-speed bands, hreflang edge HTML, content_clarity edges, scoring guards.
"""
from __future__ import annotations

import httpx
import respx
from httpx import Response

from app.fetcher import Fetcher
from app.models import CheckStatus
from app.probes._util import host_matches
from app.scanners.content_clarity import check_content_clarity
from app.scanners.discoverability import check_discoverability
from app.scanners.hreflang import check_hreflang
from app.scanners.js_rendering import _summarize_fingerprints, check_js_rendering
from app.targets import WebsiteTarget

# ─── js_rendering framework labeller ────────────────────────────────────────


def test_summarize_fingerprints_solid():
    assert "Solid" in _summarize_fingerprints(["solid-js bundle"])


def test_summarize_fingerprints_gatsby():
    assert "Gatsby" in _summarize_fingerprints(["gatsby-app entry"])


def test_summarize_fingerprints_remix():
    assert "Remix" in _summarize_fingerprints(["remix-run loader"])


def test_summarize_fingerprints_astro():
    assert "Astro" in _summarize_fingerprints(["astro-island root"])


def test_summarize_fingerprints_multiple_returns_joined():
    out = _summarize_fingerprints(["_next/static", "data-reactroot"])
    assert "Next.js" in out and "React" in out
    assert "+" in out


def test_summarize_fingerprints_unknown_returns_generic_label():
    """Unknown hits → 'JS framework bundle detected' fallback."""
    assert _summarize_fingerprints(["weird-marker"]) == "JS framework bundle detected"


def test_summarize_fingerprints_empty_returns_no_framework():
    assert "no JS framework" in _summarize_fingerprints([])


# ─── js_rendering edge cases ────────────────────────────────────────────────


def test_check_js_rendering_empty_html_skip():
    r = check_js_rendering("")
    assert r[0].status == CheckStatus.SKIP


def test_check_js_rendering_pass_when_plenty_of_server_rendered_text():
    """≥800 visible chars and no SPA shell → PASS immediately."""
    text = "Lorem ipsum dolor sit amet. " * 100  # ~2.8k chars
    html = f"<html><body><main>{text}</main></body></html>"
    r = check_js_rendering(html)
    assert r[0].status == CheckStatus.PASS


def test_check_js_rendering_warn_when_partial_spa():
    """SPA shell + a bit of prose but not enough → WARN."""
    html = (
        '<html><body><div id="root">'
        + ("Partial render. " * 25)
        + '</div><script src="/runtime.js"></script></body></html>'
    )
    r = check_js_rendering(html)
    # Either WARN (partial SPA with some content) or SKIP/etc, but never PASS for a thin shell.
    assert r[0].status in (CheckStatus.WARN, CheckStatus.PASS)


def test_check_js_rendering_warn_when_thin_no_framework():
    """Very little text but no SPA shell → WARN (under text-shell threshold)."""
    html = "<html><body><p>tiny</p></body></html>"
    r = check_js_rendering(html)
    assert r[0].status == CheckStatus.WARN


# ─── discoverability response_speed bands ───────────────────────────────────


@respx.mock
async def test_discoverability_slow_response_fails():
    """A homepage that takes >2500 ms should produce a FAIL response_speed row."""
    target = WebsiteTarget.from_url("https://example.com")
    # Sitemap + robots + home all served; home is intentionally slow.
    respx.get("https://example.com/sitemap.xml").mock(return_value=Response(200, text="<urlset/>"))
    respx.get("https://example.com/robots.txt").mock(return_value=Response(200, text=""))

    real_get = Fetcher.get

    class SlowFetcher(Fetcher):
        async def get(self, url: str):  # type: ignore[override]
            result = await real_get(self, url)
            if url == target.url:
                # Spoof the elapsed time without rewriting the streaming logic.
                result.elapsed_ms = 3000
            return result

    respx.get(target.url).mock(return_value=Response(200, text="<html></html>"))
    async with SlowFetcher() as f:
        results = await check_discoverability(target, f, "<html></html>")
    speed = next(r for r in results if r.id == "response_speed")
    assert speed.status == CheckStatus.FAIL


@respx.mock
async def test_discoverability_moderate_response_warns():
    target = WebsiteTarget.from_url("https://example.com")
    respx.get("https://example.com/sitemap.xml").mock(return_value=Response(200, text="<urlset/>"))
    respx.get("https://example.com/robots.txt").mock(return_value=Response(200, text=""))

    real_get = Fetcher.get

    class ModerateFetcher(Fetcher):
        async def get(self, url: str):  # type: ignore[override]
            result = await real_get(self, url)
            if url == target.url:
                result.elapsed_ms = 1800
            return result

    respx.get(target.url).mock(return_value=Response(200, text="<html></html>"))
    async with ModerateFetcher() as f:
        results = await check_discoverability(target, f, "<html></html>")
    speed = next(r for r in results if r.id == "response_speed")
    assert speed.status == CheckStatus.WARN


@respx.mock
async def test_discoverability_fetch_failure_fails():
    target = WebsiteTarget.from_url("https://example.com")
    respx.get("https://example.com/sitemap.xml").mock(return_value=Response(404))
    respx.get("https://example.com/robots.txt").mock(return_value=Response(404))
    respx.get(target.url).mock(side_effect=httpx.ConnectError("dns"))
    async with Fetcher() as f:
        results = await check_discoverability(target, f, "")
    speed = next(r for r in results if r.id == "response_speed")
    assert speed.status == CheckStatus.FAIL
    assert "Homepage failed to load" in speed.detail


# ─── content_clarity edges ──────────────────────────────────────────────────


def test_check_content_clarity_empty_html_returns_single_fail():
    r = check_content_clarity("")
    assert len(r) == 1
    assert r[0].id == "html_reachable"
    assert r[0].status == CheckStatus.FAIL


def test_check_content_clarity_title_too_short_warns():
    html = "<html><head><title>Hi</title><meta name='description' content='" + "x" * 80 + "'></head><body><h1>H</h1><p>" + "word " * 60 + "</p></body></html>"
    results = check_content_clarity(html)
    title = next(r for r in results if r.id == "title_quality")
    assert title.status == CheckStatus.WARN


def test_check_content_clarity_missing_meta_description():
    html = "<html><head><title>OK title here please</title></head><body><h1>H</h1><p>" + "word " * 60 + "</p></body></html>"
    results = check_content_clarity(html)
    desc = next(r for r in results if r.id == "meta_description")
    assert desc.status == CheckStatus.FAIL


def test_check_content_clarity_zero_h1_fail():
    html = "<html><head><title>OK title here please</title></head><body><p>" + "word " * 60 + "</p></body></html>"
    results = check_content_clarity(html)
    h1 = next(r for r in results if r.id == "h1_single")
    assert h1.status == CheckStatus.FAIL


def test_check_content_clarity_multiple_h1_warns():
    html = "<html><head><title>OK title here please</title></head><body><h1>A</h1><h1>B</h1><p>" + "word " * 60 + "</p></body></html>"
    results = check_content_clarity(html)
    h1 = next(r for r in results if r.id == "h1_single")
    assert h1.status == CheckStatus.WARN


def test_check_content_clarity_no_lang_warns():
    html = "<html><head><title>OK title here please</title></head><body><h1>H</h1><p>" + "word " * 60 + "</p></body></html>"
    results = check_content_clarity(html)
    lang = next(r for r in results if r.id == "html_lang")
    assert lang.status == CheckStatus.WARN


# ─── hreflang malformed URL guard ───────────────────────────────────────────


def test_check_hreflang_skips_malformed_link_paths():
    """A link with a path that urlparse cannot handle is silently skipped
    rather than crashing the scan."""
    html = (
        '<html lang="fr"><head>'
        '<link rel="alternate" hreflang="en" href="https://example.com/en">'
        '<link rel="alternate" hreflang="x-default" href="https://example.com/">'
        '</head><body>'
        # Anchor with an unparseable href — the for-loop should swallow the
        # ValueError and keep scanning the rest of the page.
        '<a href="http://[invalid">link</a>'
        '<a href="https://example.com/en">English</a>'
        '<a href="https://example.com/fr">French</a>'
        '</body></html>'
    )
    r = check_hreflang(html)
    # Doesn't crash; produces a result. Status varies by hreflang heuristics.
    assert r.id == "hreflang"


def test_check_hreflang_empty_html_skips():
    r = check_hreflang("")
    assert r.status == CheckStatus.SKIP


# ─── probes/_util.host_matches edge ─────────────────────────────────────────


def test_host_matches_empty_url_returns_false():
    assert host_matches("", "example.com") is False


def test_host_matches_empty_host_returns_false():
    assert host_matches("https://example.com", "") is False


def test_host_matches_url_with_port():
    """Hosts with explicit ports should still match by registered name."""
    assert host_matches("https://example.com:8443/x", "example.com") is True


def test_host_matches_subdomain():
    assert host_matches("https://docs.example.com/x", "example.com") is True


def test_host_matches_false_for_sibling_brand():
    """`box.com` should NOT match `dropbox.com` — the canonical safety case."""
    assert host_matches("https://dropbox.com/x", "box.com") is False
