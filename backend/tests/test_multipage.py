"""Tests for the multi-page sample scanner."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.fetcher import FetchResult
from app.models import CheckStatus
from app.scanners.multipage import (
    _AnchorInfo,
    _build_internal_linking_check,
    _classify_anchor_quality,
    _extract_anchors,
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
    [check, content_depth, internal_linking] = checks
    assert check.id == "multipage_depth"
    assert check.status == CheckStatus.PASS
    assert check.evidence is not None
    assert len(check.evidence["sampled"]) == 2
    assert all(s["word_count"] >= 500 for s in check.evidence["sampled"])
    # content_depth + internal_linking rows are always emitted alongside.
    assert content_depth.id == "content_depth"
    assert internal_linking.id == "internal_linking"


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
    [check, _content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.WARN


@pytest.mark.asyncio
async def test_check_multipage_depth_fail_all_fetches_failed() -> None:
    home = _homepage_with_links("/blog", "/about")
    fetcher = _mock_fetcher_returning({})  # every URL → 404
    [check, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.FAIL
    # No successful sample → content_depth must skip with an explanatory detail.
    assert content_depth.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_no_internal_links() -> None:
    home = '<html><body><div id="root"></div></body></html>'
    fetcher = _mock_fetcher_returning({})
    [check, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert check.status == CheckStatus.SKIP
    assert "single-page app" in check.detail.lower() or "no internal" in check.detail.lower()
    assert content_depth.status == CheckStatus.SKIP


@pytest.mark.asyncio
async def test_check_multipage_depth_skip_empty_homepage() -> None:
    fetcher = _mock_fetcher_returning({})
    [check, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, "")
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
    [check, _content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
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
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.evidence is not None
    assert content_depth.evidence["deepest_url"].endswith("/blog")
    assert content_depth.status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_content_depth_warn_above_sweet_spot_without_subheadings() -> None:
    """Devin Review #18 regression: 2501–4000 words with <3 sub-headings must
    NOT be reported as 'well-structured' — the lack of H2/H3 makes it hard
    for AI engines to extract sub-claims regardless of total length."""
    home = _homepage_with_links("/blog")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=3500, subheads=0),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.WARN
    # Must NOT contain the contradictory "well-structured with 0 sub-heading(s)" wording.
    assert "well-structured" not in content_depth.detail
    # Must explicitly cite the missing structure.
    assert "sub-heading" in content_depth.detail


@pytest.mark.asyncio
async def test_content_depth_pass_above_sweet_spot_with_subheadings() -> None:
    """Counterpart: 2501–4000 words WITH ≥3 sub-headings should still PASS
    so the WARN branch above can't silently swallow the well-structured case."""
    home = _homepage_with_links("/blog")
    pages = {
        "https://example.com/blog": FetchResult(
            url="https://example.com/blog",
            status=200,
            text=_content_page_with_subheads(words=3500, subheads=5),
        ),
    }
    fetcher = _mock_fetcher_returning(pages)
    [_multipage, content_depth, _internal] = await check_multipage_depth(_target(), fetcher, home)
    assert content_depth.status == CheckStatus.PASS
    assert content_depth.score == pytest.approx(0.85)
    assert "well-structured" in content_depth.detail


# ---- internal_linking signal ---------------------------------------------


def _homepage_with_anchors(anchors_html: str) -> str:
    """Wrap raw <a> markup in a minimal homepage. Useful when each test
    needs to control anchor text and attributes individually."""
    return (
        "<!doctype html><html><body>"
        f"<header><nav>{anchors_html}</nav></header>"
        "<main><p>Hello</p></main>"
        "</body></html>"
    )


def test_extract_anchors_skips_fragments_and_non_http() -> None:
    html = _homepage_with_anchors(
        '<a href="/blog">Blog</a>'
        '<a href="#section">Section</a>'
        '<a href="mailto:hi@example.com">Email</a>'
        '<a href="javascript:void(0)">JS</a>'
        '<a href="https://other.com/x">External</a>'
    )
    target = _target()
    anchors = _extract_anchors(html, target.host, target.url)
    # /blog (internal) + https://other.com/x (external). The fragment, mailto,
    # and javascript: anchors are dropped before classification.
    assert len(anchors) == 2
    assert any(a.is_internal and a.href.endswith("/blog") for a in anchors)
    assert any(not a.is_internal and "other.com" in a.href for a in anchors)


def test_extract_anchors_picks_up_aria_label_as_accessible_name() -> None:
    html = _homepage_with_anchors(
        '<a href="/blog" aria-label="Engineering blog">'
        '<svg></svg></a>'
        '<a href="/about"></a>'  # truly anonymous — no text, no aria, no img alt
    )
    target = _target()
    anchors = _extract_anchors(html, target.host, target.url)
    by_href = {a.href.rsplit("/", 1)[-1]: a for a in anchors}
    assert by_href["blog"].has_accessible_name is True
    assert by_href["about"].has_accessible_name is False


def test_extract_anchors_picks_up_image_alt_as_accessible_name() -> None:
    html = _homepage_with_anchors(
        '<a href="/blog"><img src="/icon.svg" alt="Engineering blog"></a>'
    )
    target = _target()
    anchors = _extract_anchors(html, target.host, target.url)
    assert len(anchors) == 1
    assert anchors[0].text == ""
    assert anchors[0].has_accessible_name is True


@pytest.mark.parametrize(
    "text,expected",
    [
        ("How we cut our AWS bill by $100k", "good"),
        ("View pricing for Pro and Enterprise plans", "good"),
        ("click here", "bad"),
        ("Click Here", "bad"),
        ("read more", "bad"),
        ("learn more", "bad"),
        ("more", "bad"),
        ("here", "bad"),
        ("→", "bad"),
        ("https://example.com/blog/post-1", "bad"),
        ("www.example.com/about", "bad"),
    ],
)
def test_classify_anchor_quality_text_buckets(text: str, expected: str) -> None:
    anchor = _AnchorInfo(
        href="https://example.com/x",
        text=text,
        is_internal=True,
        has_accessible_name=bool(text),
    )
    assert _classify_anchor_quality(anchor) == expected


def test_classify_anchor_quality_empty_with_accessible_name_is_empty_named() -> None:
    """Image-only / aria-labeled anchors don't count as ``bad`` — they have
    an accessible name a crawler can read."""
    anchor = _AnchorInfo(
        href="https://example.com/x",
        text="",
        is_internal=True,
        has_accessible_name=True,
    )
    assert _classify_anchor_quality(anchor) == "empty_named"


def test_classify_anchor_quality_empty_without_name_is_bad() -> None:
    anchor = _AnchorInfo(
        href="https://example.com/x",
        text="",
        is_internal=True,
        has_accessible_name=False,
    )
    assert _classify_anchor_quality(anchor) == "bad"


def test_internal_linking_pass_when_anchors_are_descriptive() -> None:
    home = _homepage_with_anchors(
        '<a href="/blog/aws-savings">How we cut our AWS bill by $100k</a>'
        '<a href="/pricing">View pricing for Pro and Enterprise plans</a>'
        '<a href="/about">About our team and mission</a>'
        '<a href="/cases/acme">Case study: Acme reduced support tickets 40%</a>'
        '<a href="/docs">Engineering documentation</a>'
    )
    check = _build_internal_linking_check(home, _target(), [])
    assert check.id == "internal_linking"
    assert check.status == CheckStatus.PASS
    assert check.score == pytest.approx(1.0)
    assert check.evidence is not None
    assert check.evidence["bad"] == 0
    assert check.evidence["internal_anchors_total"] == 5


def test_internal_linking_warn_at_mid_bad_ratio() -> None:
    """30 % bad triggers WARN (above OK threshold 0.25, below WARN 0.50)."""
    home = _homepage_with_anchors(
        '<a href="/a">Engineering blog</a>'
        '<a href="/b">Pricing for teams</a>'
        '<a href="/c">About our mission</a>'
        '<a href="/d">Customer case studies</a>'
        '<a href="/e">Documentation hub</a>'
        '<a href="/f">Security overview</a>'
        '<a href="/g">click here</a>'
        '<a href="/h">read more</a>'
        '<a href="/i">learn more</a>'
        '<a href="/j">https://example.com/blog</a>'
    )
    check = _build_internal_linking_check(home, _target(), [])
    assert check.status == CheckStatus.WARN
    assert check.evidence is not None
    assert check.evidence["internal_anchors_total"] == 10
    assert check.evidence["bad"] == 4


def test_internal_linking_fail_when_majority_anchors_are_generic() -> None:
    home = _homepage_with_anchors(
        '<a href="/a">click here</a>'
        '<a href="/b">read more</a>'
        '<a href="/c">learn more</a>'
        '<a href="/d">more</a>'
        '<a href="/e">https://example.com/x</a>'
        '<a href="/f">Engineering blog</a>'
    )
    check = _build_internal_linking_check(home, _target(), [])
    assert check.status == CheckStatus.FAIL
    assert check.score == pytest.approx(0.25)
    assert check.evidence is not None
    assert check.evidence["bad"] == 5
    # Detail should name a concrete example with the bad text.
    assert "click here" in check.detail.lower()


def test_internal_linking_fail_when_homepage_has_zero_internal_links() -> None:
    """Pure CSR shell or external-only homepage — flags structural failure."""
    home = _homepage_with_anchors(
        '<a href="https://twitter.com/x">Twitter</a>'
        '<a href="https://github.com/x">GitHub</a>'
    )
    check = _build_internal_linking_check(home, _target(), [])
    assert check.status == CheckStatus.FAIL
    assert check.score == pytest.approx(0.1)
    assert "zero internal links" in check.detail.lower()


def test_internal_linking_skip_when_too_few_internal_anchors_to_score() -> None:
    home = _homepage_with_anchors(
        '<a href="/blog">Blog</a>'
        '<a href="/about">About</a>'
    )
    check = _build_internal_linking_check(home, _target(), [])
    # Only 2 internal anchors — below _LINK_MIN_INTERNAL_ANCHORS=4.
    assert check.status == CheckStatus.SKIP


def test_internal_linking_combines_homepage_and_sampled_pages() -> None:
    """Anchors from sampled pages should add to the pool, so a thin
    homepage with rich sampled-page anchors can still PASS."""
    home = _homepage_with_anchors(
        '<a href="/blog">Engineering blog</a>'
        '<a href="/about">About our team</a>'
    )
    sampled_html = _homepage_with_anchors(
        '<a href="/blog/post-1">How we cut latency in half</a>'
        '<a href="/blog/post-2">Postmortem: the great cache miss of 2024</a>'
        '<a href="/pricing">View pricing</a>'
        '<a href="/docs">Read the engineering documentation</a>'
    )
    sampled = _PageStats(
        url="https://example.com/blog",
        fetched=True,
        word_count=600,
        html=sampled_html,
    )
    check = _build_internal_linking_check(home, _target(), [sampled])
    assert check.status == CheckStatus.PASS
    assert check.evidence is not None
    assert check.evidence["internal_anchors_total"] == 6


def test_internal_linking_orphan_note_when_sampled_page_has_no_inbound() -> None:
    """A sampled URL that nothing links to should be reported as an orphan
    in the detail (informational; not gating)."""
    home = _homepage_with_anchors(
        '<a href="/blog">Engineering blog</a>'
        '<a href="/about">About our team</a>'
        '<a href="/pricing">View pricing</a>'
        '<a href="/docs">Read the engineering documentation</a>'
    )
    # /orphan is fetched + sampled, but nothing links to it.
    sampled_html = _homepage_with_anchors(
        '<a href="/blog">Back to blog</a>'
    )
    sampled = _PageStats(
        url="https://example.com/orphan",
        fetched=True,
        word_count=600,
        html=sampled_html,
    )
    check = _build_internal_linking_check(home, _target(), [sampled])
    assert check.evidence is not None
    assert "/orphan" in check.evidence["orphan_urls_in_sample"]
    assert "orphan" in check.detail.lower()


def test_internal_linking_skip_when_no_html_available() -> None:
    check = _build_internal_linking_check("", _target(), [])
    assert check.status == CheckStatus.SKIP
    assert check.evidence is None
