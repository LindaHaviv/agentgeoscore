"""Tests for the SPA / JS-rendering heuristic."""
from __future__ import annotations

import pytest

from app.models import CheckStatus
from app.scanners.js_rendering import (
    _summarize_fingerprints,
    check_js_rendering,
)

# ---- Test fixtures --------------------------------------------------------


def _ssr_page(text_chars: int = 1500) -> str:
    """A normal server-rendered page — a hero, several sections, footer."""
    body = (
        "<header><nav>Home Pricing Docs Blog Contact</nav></header>"
        "<main>"
        "<h1>Welcome to Acme</h1>"
        f"<p>{('Acme builds delightful tools for product teams. ' * 30)[:text_chars]}</p>"
        "<section><h2>Why teams choose Acme</h2><p>Lots of detail.</p></section>"
        "</main>"
        "<footer>© Acme 2026</footer>"
    )
    return f"<!doctype html><html lang='en'><body>{body}</body></html>"


def _pure_csr_react() -> str:
    """A bare Create-React-App / Vite-React shell — empty root, react bundle."""
    return (
        "<!doctype html><html lang='en'>"
        "<head><title>Acme</title></head>"
        "<body>"
        "<noscript>You need to enable JavaScript to run this app.</noscript>"
        '<div id="root"></div>'
        '<script src="/static/js/main.abc123.js"></script>'
        '<script>window.__REACT_DEVTOOLS_GLOBAL_HOOK__||({})</script>'
        '<script src="https://unpkg.com/react-dom/umd/react-dom.production.min.js"></script>'
        "</body></html>"
    )


def _empty_nextjs_csr() -> str:
    """Next.js app router page that ships an empty __next div + bundle."""
    return (
        "<!doctype html><html><body>"
        '<div id="__next"></div>'
        '<script src="/_next/static/chunks/main.js"></script>'
        '<script id="__NEXT_DATA__" type="application/json">{}</script>'
        "</body></html>"
    )


def _ssg_nextjs_with_content() -> str:
    """Next.js with prerendered content — has __next root AND lots of text."""
    body_text = "Stripe builds payments infrastructure. " * 30
    return (
        "<!doctype html><html><body>"
        f'<div id="__next"><h1>Stripe</h1><p>{body_text}</p>'
        "<section><h2>Products</h2><p>Payments, billing, treasury, atlas, "
        "issuing, capital, identity. Each one is described in detail "
        "to demonstrate substantial server-rendered content.</p></section>"
        "</div>"
        '<script src="/_next/static/chunks/main.js"></script>'
        "</body></html>"
    )


def _angular_shell() -> str:
    """Angular app-root with no rendered content."""
    return (
        "<!doctype html><html ng-version='17.0.0'><body>"
        "<app-root></app-root>"
        '<script src="runtime.js"></script>'
        '<script src="polyfills.js"></script>'
        '<script src="main.js"></script>'
        "</body></html>"
    )


def _vue_shell() -> str:
    return (
        "<!doctype html><html><body>"
        '<div id="app"></div>'
        '<script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>'
        '<script src="/main.js"></script>'
        "</body></html>"
    )


def _thin_brochure() -> str:
    """Very short content but no JS framework. Should not get blamed for SPA."""
    return (
        "<!doctype html><html><body>"
        "<h1>Coming Soon</h1>"
        "<p>Site under construction.</p>"
        "</body></html>"
    )


# ---- Tests ----------------------------------------------------------------


def test_ssr_page_passes():
    [r] = check_js_rendering(_ssr_page())
    assert r.id == "js_rendering"
    assert r.status == CheckStatus.PASS
    assert "AI crawlers" in r.detail
    assert r.evidence is not None
    assert r.evidence["spa_shell"] is None


def test_pure_csr_react_app_fails():
    [r] = check_js_rendering(_pure_csr_react())
    assert r.status == CheckStatus.FAIL
    assert "React" in r.detail
    assert r.evidence is not None
    assert r.evidence["spa_shell"] == "root"
    assert r.evidence["visible_chars"] < 200


def test_empty_nextjs_csr_fails():
    [r] = check_js_rendering(_empty_nextjs_csr())
    assert r.status == CheckStatus.FAIL
    assert "Next.js" in r.detail
    assert r.evidence is not None
    assert r.evidence["spa_shell"] == "__next"


def test_ssg_nextjs_passes_despite_having_a_next_root():
    """A Next.js SSG site with prerendered content should NOT be flagged.

    This is the most important false-positive guard — half the modern web
    is some flavour of Next.js or Nuxt with content baked into HTML, and
    flagging those would tank our credibility instantly.
    """
    [r] = check_js_rendering(_ssg_nextjs_with_content())
    assert r.status == CheckStatus.PASS
    assert r.evidence is not None
    assert r.evidence["visible_chars"] >= 800


def test_angular_shell_fails():
    [r] = check_js_rendering(_angular_shell())
    assert r.status == CheckStatus.FAIL
    assert "Angular" in r.detail


def test_vue_empty_shell_fails():
    [r] = check_js_rendering(_vue_shell())
    assert r.status == CheckStatus.FAIL
    assert "Vue" in r.detail


def test_thin_brochure_warns_but_does_not_blame_js():
    """Page with little text but no SPA shell — warn, don't blame frameworks."""
    [r] = check_js_rendering(_thin_brochure())
    assert r.status == CheckStatus.WARN
    # Crucially: detail does NOT name a framework, since none is present.
    assert "React" not in r.detail
    assert "Vue" not in r.detail
    assert "Next.js" not in r.detail


def test_partial_render_warns_not_fails():
    """Empty SPA shell but a few hundred chars of sibling text — warn,
    not fail. This is the "thinly-prerendered" case (e.g. a Next.js page
    that renders its <Header> / <Footer> server-side but defers the hero
    to a client component)."""
    sibling = "Documentation links, footer text, nav copy. " * 8  # ~360 chars
    html = (
        "<!doctype html><html><body>"
        "<header><nav>Home Pricing Docs Blog</nav></header>"
        f"<main><p>{sibling}</p></main>"
        '<div id="root"></div>'
        '<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>'
        "</body></html>"
    )
    [r] = check_js_rendering(html)
    assert r.status == CheckStatus.WARN
    assert "partially-rendered" in r.detail.lower()


def test_empty_html_skips():
    [r] = check_js_rendering("")
    assert r.status == CheckStatus.SKIP


def test_whitespace_only_html_skips():
    [r] = check_js_rendering("   \n\t  ")
    assert r.status == CheckStatus.SKIP


def test_evidence_is_serialisable_and_truthful():
    [r] = check_js_rendering(_pure_csr_react())
    assert isinstance(r.evidence, dict)
    assert r.evidence["spa_shell"] == "root"
    # Should mention at least one fingerprint.
    assert any(
        "react" in fp.lower() or "react-dom" in fp.lower()
        for fp in r.evidence["framework_fingerprints"]
    )
    # Truncated to 8 — never blow up the report payload.
    assert len(r.evidence["framework_fingerprints"]) <= 8


@pytest.mark.parametrize(
    "hits,expected_substr",
    [
        (["/_next/static/", "__NEXT_DATA__"], "Next.js"),
        (["__NUXT__"], "Nuxt"),
        (["data-reactroot", "react-dom"], "React"),
        (["vue.global.js"], "Vue"),
        (["ng-version", "/runtime.js"], "Angular"),
        ([], "no JS framework"),
        (["/_next/static/", "vue.global.js"], "Next.js+Vue"),
    ],
)
def test_summarize_fingerprints(hits, expected_substr):
    assert expected_substr in _summarize_fingerprints(hits)


def test_check_runs_on_a_page_without_body_tag():
    """Defensive: malformed HTML without <body> should not crash."""
    html = "<html><div id='root'></div></html>"
    [r] = check_js_rendering(html)
    # Should still produce a result, not raise.
    assert r.id == "js_rendering"
    assert r.status in {CheckStatus.PASS, CheckStatus.WARN, CheckStatus.FAIL}


def test_textual_threshold_pass_is_inclusive_of_visible_text_only():
    """<noscript> content should NOT count toward the visible-text budget,
    so sites can't game the heuristic by stuffing prose into <noscript>."""
    long_noscript = "Hello world. " * 100  # 1300 chars
    html = (
        "<!doctype html><html><body>"
        '<div id="root"></div>'
        f"<noscript>{long_noscript}</noscript>"
        '<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>'
        "</body></html>"
    )
    [r] = check_js_rendering(html)
    # noscript text excluded → still classified as a CSR shell.
    assert r.status == CheckStatus.FAIL
