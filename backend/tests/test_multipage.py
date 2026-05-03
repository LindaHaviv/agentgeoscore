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
    word_count, has_jsonld, has_date, citations, subheads = _summarize_page(
        html, "example.com"
    )
    assert word_count >= 400
    assert has_jsonld is True
    assert has_date is True
    assert citations == 0
    assert subheads == 0  # _content_page emits an h1, no h2/h3


def test_summarize_page_counts_outbound_citations_only() -> None:
    html = (
        "<html><body>"
        '<a href="/internal">internal</a>'
        '<a href="https://en.wikipedia.org/wiki/X">cite 1</a>'
        '<a href="https://example.com/other">same host</a>'
        '<a href="https://nytimes.com/x">cite 2</a>'
        "</body></html>"
    )
    _, _, _, citations, _ = _summarize_page(html, "example.com")
    assert citations == 2


def test_summarize_page_counts_subheadings() -> None:
    html = (
        "<html><body>"
        "<h1>Title</h1>"
        "<h2>Section A</h2><p>x</p>"
        "<h3>Sub A</h3><p>y</p>"
        "<h2>Section B</h2><p>z</p>"
        "<h4>Ignored</h4>"
        "</body></html>"
    )
    _, _, _, _, subheads = _summarize_page(html, "example.com")
    assert subheads == 3  # 2 h2 + 1 h3, h1 and h4 not counted


def test_summarize_page_handles_empty_html() -> None:
    word_count, has_jsonld, has_date, citations, subheads = _summarize_page(
        "", "example.com"
    )
    assert (word_count, has_jsonld, has_date, citations, subheads) == (
        0,
        False,
        False,
        0,
        0,
    )


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
    checks = await check_multipage_depth(_target(), fetcher, home)
    [check, content_depth] = checks
    assert check.id == "multipage_depth"
    assert check.status == CheckStatus.PASS
    assert check.evidence is not None
    assert len(check.evidence["sampled"]) == 2
    assert all(s["word_count"] >= 500 for s in check.evidence["sampled"])
    # content_depth row is always emitted alongside the multipage row.
    assert content_depth.id == "content_depth"


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
    [check, _content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.WARN


@pytest.mark.asyncio
async def test_check_multipage_depth_fail_all_fetches_failed() -> None:
    home = _homepage_with_links("/blog", "/about")
    fetcher = _mock_fetcher_returning({})  # every URL → 404
    [check, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.FAIL
    # No successful sample → content_depth must skip with an explanatory detail.
    assert content_depth.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_no_internal_links() -> None:
    home = '<html><body><div id="root"></div></body></html>'
    fetcher = _mock_fetcher_returning({})
    [check, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.SKIP
    assert "single-page app" in check.detail.lower() or "no internal" in check.detail.lower()
    assert content_depth.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_empty_homepage() -> None:
    fetcher = _mock_fetcher_returning({})
    [check, content_depth] = await check_multipage_depth(_target(), fetcher, "")
    assert check.status == CheckStatus.SKIP
    assert content_depth.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_pass_detail_does_not_overclaim_per_page_signals() -> None:
    """PR #15 review regression: with avg_score >= 0.85 the detail must not
    claim every page has every signal. See pull/15#discussion_r3178406411 —
    Page A 0.9 (words + JSON-LD, no date) + Page B 0.8 (words only) averages
    0.85 and triggers PASS, but neither page has a recent date and Page B
    has no JSON-LD.
    """
    home = _homepage_with_links("/blog", "/about")
    pages = {
        # Page A: words + JSON-LD, no date  → per_page_score = 0.9
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page(words=400, with_jsonld=True, with_recent_date=False),
        ),
        # Page B: words only, no JSON-LD, no date  → per_page_score = 0.8
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page(words=400, with_jsonld=False, with_recent_date=False),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [check, _content_depth] = await check_multipage_depth(_target(), fetcher, home)
    # Confirm the underlying threshold still triggers PASS so this test is
    # exercising the overclaim path, not skipping it.
    assert check.status == CheckStatus.PASS
    # The detail must NOT contain the categorical "all show … structured
    # data, and a recent date" wording from before the fix.
    assert "all show substantive content" not in check.detail
    assert "and a recent date" not in check.detail
    # It MUST report the actual counts honestly: 0/2 with a recent date.
    assert "0/2 with a recent date" in check.detail
    # And reflect that JSON-LD coverage is partial, not universal.
    assert "1/2 with JSON-LD" in check.detail


# ---- content_depth check (Princeton 1500–2500 word band) ------------------


def _content_page_with_subheads(words: int, subheads: int) -> str:
    """Build a page with N words spread across `subheads` h2 sections."""
    parts = ["<h1>Article</h1>"]
    per_section_words = max(1, words // max(1, subheads)) if subheads else words
    if subheads == 0:
        parts.append("<main><p>" + ("word " * words).strip() + "</p></main>")
    else:
        remaining = words
        for i in range(subheads):
            section_words = min(per_section_words, remaining)
            remaining -= section_words
            parts.append(f"<h2>Section {i + 1}</h2>")
            parts.append(f"<p>{('word ' * section_words).strip()}</p>")
        if remaining > 0:
            parts.append(f"<p>{('word ' * remaining).strip()}</p>")
    return "<!doctype html><html><body>" + "".join(parts) + "</body></html>"


@pytest.mark.asyncio
async def test_content_depth_pass_in_sweet_spot() -> None:
    """1500–2500 word page → PASS, score 1.0, detail mentions the sweet spot."""
    home = _homepage_with_links("/blog", "/about")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=1800, subheads=4),
        ),
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page_with_subheads(words=400, subheads=1),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.id == "content_depth"
    assert content_depth.status == CheckStatus.PASS
    assert content_depth.score == pytest.approx(1.0)
    # Picked the *deepest* page (the blog), not the average.
    assert content_depth.evidence is not None
    assert content_depth.evidence["deepest_url"].endswith("/blog")
    assert "1500" in content_depth.detail and "2500" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_fail_when_thin() -> None:
    """Deepest page < 800 words → FAIL with the Princeton citation rationale."""
    home = _homepage_with_links("/blog")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=300, subheads=2),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.FAIL
    assert "Princeton" in content_depth.detail
    assert "1500" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_warn_when_below_sweet_spot() -> None:
    """800–1499 word page → WARN (passable but under sweet spot)."""
    home = _homepage_with_links("/about")
    pages = {
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page_with_subheads(words=1100, subheads=3),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.WARN
    assert "sweet spot" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_warn_on_wall_of_text() -> None:
    """>4000 words with <3 sub-headings → WARN (wall-of-text)."""
    home = _homepage_with_links("/blog")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=5000, subheads=1),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.WARN
    assert "wall-of-text" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_pass_on_long_but_structured() -> None:
    """>4000 words WITH ≥3 sub-headings → PASS (long but parseable)."""
    home = _homepage_with_links("/blog")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=5000, subheads=6),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.PASS
    assert "long-form" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_picks_deepest_not_first_page() -> None:
    """Tests the 'longest page wins' selection — first sampled url is thin,
    second is in the sweet spot. content_depth should reflect the second."""
    home = _homepage_with_links("/about", "/blog")  # /about ranks higher in priority
    pages = {
        "https://example.com/about": FetchResult(
            url="https://example.com/about",
            status=200,
            text=_content_page_with_subheads(words=200, subheads=0),
        ),
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=2000, subheads=4),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.evidence is not None
    assert content_depth.evidence["deepest_url"].endswith("/blog")
    assert content_depth.status == CheckStatus.PASS
