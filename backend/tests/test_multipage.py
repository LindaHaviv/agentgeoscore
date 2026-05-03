"""Tests for the multi-page sample scanner."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.fetcher import FetchResult
from app.models import CheckStatus
from app.scanners.multipage import (
    _has_recent_date_signal,
    _is_sampleable_href,
    _PageStats,
    _path_priority,
    _summarize_page,
    check_multipage_depth,
    pick_sample_urls,
)
from app.targets import WebsiteTarget

# ---- Fixtures -------------------------------------------------------------


def _target(host: str = "example.com") -> WebsiteTarget:
    return WebsiteTarget.from_url(f"https://{host}")


def _homepage_with_links(*hrefs: str) -> str:
    """Build a minimal homepage that contains the given hrefs in nav order."""
    nav = "".join(f'<a href="{h}">link</a>' for h in hrefs)
    return (
        "<!doctype html><html><body>"
        f"<header><nav>{nav}</nav></header>"
        "<main><p>Hello</p></main>"
        "</body></html>"
    )


def _content_page(words: int, *, with_jsonld: bool = False, with_recent_date: bool = False) -> str:
    """Build a content page with the requested signals.

    ``words`` controls visible word count via repetition. JSON-LD and
    dateModified are added on demand so each test can isolate one signal.
    """
    body_parts = ["<h1>Article title</h1>"]
    if with_recent_date:
        recent = (datetime.now(UTC) - timedelta(days=10)).strftime("%Y-%m-%d")
        body_parts.append(f'<time datetime="{recent}">recent</time>')
    if with_jsonld:
        body_parts.append(
            '<script type="application/ld+json">'
            '{"@context":"https://schema.org","@type":"Article","headline":"Hi"}'
            "</script>"
        )
    body_parts.append("<main><p>" + ("word " * words).strip() + "</p></main>")
    return "<!doctype html><html><body>" + "".join(body_parts) + "</body></html>"


# ---- _is_sampleable_href --------------------------------------------------


@pytest.mark.parametrize(
    "href,expected",
    [
        ("/blog", True),
        ("/about", True),
        ("https://example.com/pricing", True),
        # Same-host but absolute URL — still sampleable.
        ("https://example.com/blog/post-1", True),
        # External — never sampleable.
        ("https://twitter.com/example", False),
        # Anchors and empty.
        ("", False),
        ("#section", False),
        # Disallowed schemes.
        ("mailto:hi@example.com", False),
        ("tel:+15551234", False),
        ("javascript:void(0)", False),
        # File extensions we never sample.
        ("/whitepaper.pdf", False),
        ("/logo.png", False),
        # Navigational chrome.
        ("/login", False),
        ("/signup", False),
        ("/cart", False),
        ("/api/health", False),
        # The homepage itself.
        ("/", False),
    ],
)
def test_is_sampleable_href(href: str, expected: bool) -> None:
    target = _target()
    ok, _ = _is_sampleable_href(href, target.host, target.url)
    assert ok is expected


def test_is_sampleable_href_strips_fragment() -> None:
    target = _target()
    ok, normalized = _is_sampleable_href("/about#team", target.host, target.url)
    assert ok is True
    assert normalized.endswith("/about")


# ---- _path_priority -------------------------------------------------------


def test_path_priority_orders_blog_above_about_above_other() -> None:
    blog_score, blog_topic = _path_priority("/blog/my-post")
    about_score, about_topic = _path_priority("/about/team")
    pricing_score, _ = _path_priority("/pricing")
    docs_score, _ = _path_priority("/docs/getting-started")
    other_score, other_topic = _path_priority("/random-page")
    assert blog_topic == "blog"
    assert about_topic == "about"
    assert other_topic == "other"
    assert blog_score > about_score > pricing_score > docs_score > other_score


# ---- pick_sample_urls -----------------------------------------------------


def test_pick_sample_urls_prefers_blog_over_pricing_over_other() -> None:
    home = _homepage_with_links(
        "/random",
        "/pricing",
        "/blog",
        "/login",  # filtered
        "https://twitter.com/example",  # filtered (external)
    )
    picked = pick_sample_urls(home, _target())
    paths = [c.url.split(_target().host, 1)[1] for c in picked]
    assert "/blog" in paths
    assert "/pricing" in paths
    # The "/random" link is "other" tier — only included if we haven't filled
    # the limit; with /blog and /pricing both present we should have two
    # different topics.
    assert all(p not in {"/login"} for p in paths)


def test_pick_sample_urls_caps_at_limit() -> None:
    home = _homepage_with_links("/blog", "/about", "/pricing", "/docs", "/cases")
    picked = pick_sample_urls(home, _target(), limit=2)
    assert len(picked) == 2


def test_pick_sample_urls_diversifies_topics() -> None:
    """Two same-topic links shouldn't both be picked when we have 2 slots."""
    home = _homepage_with_links("/blog/post-a", "/blog/post-b", "/about")
    picked = pick_sample_urls(home, _target(), limit=2)
    topics = {c.topic for c in picked}
    assert "about" in topics  # /about included
    assert "blog" in topics  # exactly one blog post included


def test_pick_sample_urls_returns_empty_for_spa_homepage() -> None:
    # No anchor tags at all — typical bare CSR shell.
    home = '<html><body><div id="root"></div></body></html>'
    assert pick_sample_urls(home, _target()) == []


def test_pick_sample_urls_dedupes_same_path_with_query() -> None:
    home = _homepage_with_links(
        "/blog?utm=a",
        "/blog?utm=b",
        "/blog#anchor",
    )
    picked = pick_sample_urls(home, _target())
    # All three normalize to the same /blog path.
    assert len(picked) == 1


# ---- _has_recent_date_signal / _summarize_page ----------------------------


def test_recent_date_signal_via_time_tag() -> None:
    from bs4 import BeautifulSoup

    recent = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%d")
    soup = BeautifulSoup(f'<time datetime="{recent}">date</time>', "html.parser")
    assert _has_recent_date_signal(soup) is True


def test_recent_date_signal_rejects_old_date() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup('<time datetime="2010-01-01">old</time>', "html.parser")
    assert _has_recent_date_signal(soup) is False


def test_summarize_page_counts_words_and_jsonld() -> None:
    html = _content_page(words=400, with_jsonld=True, with_recent_date=True)
    word_count, has_jsonld, has_date, citations = _summarize_page(html, "example.com")
    assert word_count >= 400
    assert has_jsonld is True
    assert has_date is True
    assert citations == 0


def test_summarize_page_counts_outbound_citations_only() -> None:
    html = (
        "<html><body>"
        '<a href="/internal">internal</a>'
        '<a href="https://en.wikipedia.org/wiki/X">cite 1</a>'
        '<a href="https://example.com/other">same host</a>'
        '<a href="https://nytimes.com/x">cite 2</a>'
        "</body></html>"
    )
    _, _, _, citations = _summarize_page(html, "example.com")
    assert citations == 2


def test_summarize_page_handles_empty_html() -> None:
    word_count, has_jsonld, has_date, citations = _summarize_page("", "example.com")
    assert (word_count, has_jsonld, has_date, citations) == (0, False, False, 0)


# ---- _PageStats.per_page_score -------------------------------------------


def test_per_page_score_thin_page() -> None:
    stats = _PageStats(url="x", fetched=True, word_count=50)
    assert stats.per_page_score == pytest.approx(0.1)


def test_per_page_score_substantive_page_with_signals() -> None:
    stats = _PageStats(
        url="x",
        fetched=True,
        word_count=600,
        has_jsonld=True,
        has_recent_date=True,
    )
    assert stats.per_page_score == pytest.approx(1.0)


def test_per_page_score_failed_fetch_is_zero() -> None:
    stats = _PageStats(url="x", fetched=False, error="timeout")
    assert stats.per_page_score == 0.0


# ---- check_multipage_depth (end-to-end with mocked fetcher) ---------------


def _mock_fetcher_returning(pages: dict[str, FetchResult]) -> object:
    """Build a mock Fetcher whose .get(url) returns the canned FetchResult."""
    fetcher = MagicMock()

    async def get(url: str) -> FetchResult:
        return pages.get(
            url,
            FetchResult(url=url, status=404, text="", error="not found"),
        )

    fetcher.get = AsyncMock(side_effect=get)
    return fetcher


@pytest.mark.asyncio
async def test_check_multipage_depth_pass_when_pages_are_substantive() -> None:
    home = _homepage_with_links("/blog", "/about")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page(words=600, with_jsonld=True, with_recent_date=True),
        ),
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page(words=500, with_jsonld=True, with_recent_date=True),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [check] = await check_multipage_depth(_target(), fetcher, home)
    assert check.id == "multipage_depth"
    assert check.status == CheckStatus.PASS
    assert check.evidence is not None
    assert len(check.evidence["sampled"]) == 2
    assert all(s["word_count"] >= 500 for s in check.evidence["sampled"])


@pytest.mark.asyncio
async def test_check_multipage_depth_warn_when_pages_thin() -> None:
    home = _homepage_with_links("/blog", "/about")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page(words=150, with_jsonld=False, with_recent_date=False),
        ),
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page(words=200, with_jsonld=True, with_recent_date=False),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [check] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.WARN


@pytest.mark.asyncio
async def test_check_multipage_depth_fail_all_fetches_failed() -> None:
    home = _homepage_with_links("/blog", "/about")
    fetcher = _mock_fetcher_returning({})  # every URL → 404
    [check] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_no_internal_links() -> None:
    home = '<html><body><div id="root"></div></body></html>'
    fetcher = _mock_fetcher_returning({})
    [check] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.SKIP
    assert "single-page app" in check.detail.lower() or "no internal" in check.detail.lower()


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_empty_homepage() -> None:
    fetcher = _mock_fetcher_returning({})
    [check] = await check_multipage_depth(_target(), fetcher, "")
    assert check.status == CheckStatus.SKIP
