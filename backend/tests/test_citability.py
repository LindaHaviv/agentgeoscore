"""Tests for citability scanner.

Covers the Princeton-GEO-derived checks (citations, statistics, quotations,
fan-out) plus the ancillary signals (visible "Updated" line, byline-links,
transcripts).
"""
from __future__ import annotations

from app.scanners.citability import check_citability
from app.scanners.structured_data import extract_jsonld


def _ids(results):
    return {r.id: r for r in results}


def _run(html: str):
    blocks = extract_jsonld(html)
    return _ids(check_citability(html, blocks))


# ---------------------------------------------------------------------------
# Outbound citations
# ---------------------------------------------------------------------------


def test_outbound_citations_pass_with_three_distinct_external_domains():
    body_words = "word " * 200
    html = f"""<html><body>
<article>
  <p>{body_words}</p>
  <p>According to <a href="https://www.nytimes.com/article">the NYT</a>,
     and a <a href="https://arxiv.org/abs/123">paper on arXiv</a>,
     and <a href="https://nature.com/x">Nature</a>.</p>
</article>
</body></html>"""
    out = _run(html)
    chk = out["outbound_citations"]
    assert chk.status.value == "pass"
    assert chk.evidence["count"] == 3


def test_outbound_citations_warn_on_one_link():
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>{body_words} <a href="https://example.com">one</a></p>
</article></body></html>"""
    out = _run(html)
    assert out["outbound_citations"].status.value == "warn"


def test_outbound_citations_fail_with_no_external_links():
    body_words = "word " * 200
    html = f"""<html><body><article><p>{body_words}</p></article></body></html>"""
    out = _run(html)
    assert out["outbound_citations"].status.value == "fail"


def test_outbound_citations_skip_on_thin_page():
    html = """<html><body><article><p>Tiny.</p></article></body></html>"""
    out = _run(html)
    assert out["outbound_citations"].status.value == "skip"


def test_outbound_citations_ignores_self_links():
    """Subdomain self-links shouldn't count as outbound."""
    body_words = "word " * 200
    html = f"""<html><head>
<link rel="canonical" href="https://acme.example/blog/x">
</head><body><article>
<p>{body_words}
   <a href="https://acme.example/about">about</a>
   <a href="https://docs.acme.example/api">docs</a>
   <a href="https://blog.acme.example/y">blog</a>
</p>
</article></body></html>"""
    out = _run(html)
    # All three resolve to the same registered domain (acme.example)
    assert out["outbound_citations"].status.value == "fail"


def test_outbound_citations_dedupe_by_registered_domain():
    """Five links to the same external site count as 1, not 5."""
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>{body_words}
   <a href="https://nytimes.com/a">a</a>
   <a href="https://nytimes.com/b">b</a>
   <a href="https://www.nytimes.com/c">c</a>
   <a href="https://nytimes.com/d">d</a>
   <a href="https://nytimes.com/e">e</a>
</p></article></body></html>"""
    out = _run(html)
    # Only 1 distinct registered domain → fail/warn, not pass
    assert out["outbound_citations"].evidence["count"] == 1


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def test_statistics_pass_with_diverse_units():
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>We saw a 42% lift in conversions across 2024 in $1.2B in transactions
   spanning 1,500 customers over 18 months at 5x speed.</p>
<p>{body_words}</p>
</article></body></html>"""
    out = _run(html)
    chk = out["statistics_density"]
    assert chk.status.value == "pass"
    assert chk.evidence["count"] >= 4


def test_statistics_warn_on_thin_numeric_signal():
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>We grew 12% last year.</p>
<p>{body_words}</p>
</article></body></html>"""
    out = _run(html)
    # 12% + 'last year' (no specific year) → exactly one stat
    assert out["statistics_density"].status.value == "warn"


def test_statistics_fail_with_no_numbers():
    body_words = "abstract qualitative narrative without any numeric content " * 30
    html = f"""<html><body><article><p>{body_words}</p></article></body></html>"""
    out = _run(html)
    assert out["statistics_density"].status.value == "fail"


def test_statistics_skip_on_thin_page():
    html = """<html><body><p>Hi.</p></body></html>"""
    out = _run(html)
    assert out["statistics_density"].status.value == "skip"


def test_statistics_ignores_bare_phone_numbers():
    """A page consisting only of a phone number / SKU shouldn't pass."""
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>{body_words} Call 5551234567 or fax 5559876.</p>
</article></body></html>"""
    out = _run(html)
    # Bare digits without units shouldn't count as statistics → fail
    assert out["statistics_density"].status.value == "fail"


# ---------------------------------------------------------------------------
# Quotations
# ---------------------------------------------------------------------------


def test_quotations_pass_with_two_blockquotes():
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>{body_words}</p>
<blockquote><p>"First quote."</p></blockquote>
<blockquote><p>"Second quote."</p></blockquote>
</article></body></html>"""
    out = _run(html)
    assert out["quotation_density"].status.value == "pass"


def test_quotations_warn_with_one():
    body_words = "word " * 200
    html = f"""<html><body><article>
<p>{body_words}</p>
<blockquote><p>"Just one quote."</p></blockquote>
</article></body></html>"""
    out = _run(html)
    assert out["quotation_density"].status.value == "warn"


def test_quotations_fail_with_none():
    body_words = "word " * 200
    html = f"""<html><body><article><p>{body_words}</p></article></body></html>"""
    out = _run(html)
    assert out["quotation_density"].status.value == "fail"


# ---------------------------------------------------------------------------
# Fan-out H2 questions
# ---------------------------------------------------------------------------


def test_fanout_pass_with_two_question_h2s():
    html = """<html><body>
<h2>What is GEO?</h2><p>x</p>
<h2>How is it different from SEO?</h2><p>y</p>
</body></html>"""
    out = _run(html)
    assert out["fanout_h2_questions"].status.value == "pass"


def test_fanout_warn_with_one():
    html = """<html><body>
<h2>What is GEO?</h2><p>x</p>
<h2>About us</h2>
</body></html>"""
    out = _run(html)
    assert out["fanout_h2_questions"].status.value == "warn"


def test_fanout_warn_with_none():
    html = """<html><body>
<h2>About</h2>
<h2>Pricing</h2>
</body></html>"""
    out = _run(html)
    chk = out["fanout_h2_questions"]
    # No questions at all → still warn (lower score), not pass/fail
    assert chk.status.value == "warn"
    assert chk.evidence["count"] == 0


def test_fanout_recognizes_how_to_pattern():
    html = """<html><body>
<h2>How to install your tool</h2>
<h2>What is GEO?</h2>
</body></html>"""
    out = _run(html)
    # "How to install" + "What is …?" both count
    assert out["fanout_h2_questions"].status.value == "pass"


# ---------------------------------------------------------------------------
# Visible "Updated" date
# ---------------------------------------------------------------------------


def test_freshness_pass_with_visible_updated_and_time():
    html = """<html><body><article>
<h1>Post</h1>
<p>Updated April 20, 2026 — by Jane.</p>
<time datetime="2026-04-20">April 20, 2026</time>
<p>Body text here.</p>
</article></body></html>"""
    out = _run(html)
    assert out["freshness_visible_updated"].status.value == "pass"


def test_freshness_pass_with_day_month_year_format():
    """Wikipedia / EU sites write "last edited 22 April 2026" — the regex
    must match both month-day-year (US) and day-month-year (EU/Wikipedia)."""
    html = """<html><body><article>
<h1>Post</h1>
<p>This page was last edited on 22 April 2026, at 12:34 (UTC).</p>
<time datetime="2026-04-22">22 April 2026</time>
</article></body></html>"""
    out = _run(html)
    assert out["freshness_visible_updated"].status.value == "pass"


def test_freshness_pass_when_article_is_nested_inside_webpage_jsonld():
    """Common CMS pattern: Article schema nested under WebPage.mainEntity.

    Regression for the original `_has_article_jsonld` that only walked the
    top-level — that version would SKIP this case because the outer @type
    is "WebPage", even though an Article is one level down.
    """
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"WebPage",
 "mainEntity":{"@type":"Article","headline":"X",
               "dateModified":"2026-04-20"}}
</script></head><body>
<h1>Post</h1>
<p>Updated April 20, 2026 — by Jane.</p>
<time datetime="2026-04-20">April 20, 2026</time>
<p>Body.</p>
</body></html>"""
    out = _run(html)
    # Article-type detected via deep walk, so freshness check runs (not SKIP)
    assert out["freshness_visible_updated"].status.value == "pass"


def test_freshness_skip_on_marketing_homepage():
    """Pages without an <article> or Article schema should SKIP, not penalize."""
    html = """<html><body>
<header><h1>Acme</h1></header>
<main><p>Marketing copy.</p></main>
</body></html>"""
    out = _run(html)
    assert out["freshness_visible_updated"].status.value == "skip"


def test_freshness_warn_with_only_time_element():
    html = """<html><body><article>
<h1>Post</h1>
<time datetime="2026-04-20">April 20, 2026</time>
<p>Body.</p>
</article></body></html>"""
    out = _run(html)
    assert out["freshness_visible_updated"].status.value == "warn"


def test_freshness_fail_with_no_date_signals_on_article():
    html = """<html><body><article>
<h1>Post</h1>
<p>Body without any dates or "updated" markers anywhere.</p>
</article></body></html>"""
    out = _run(html)
    assert out["freshness_visible_updated"].status.value == "fail"


# ---------------------------------------------------------------------------
# Byline links
# ---------------------------------------------------------------------------


def test_byline_pass_with_rel_author_anchor():
    html = """<html><body>
<p class="byline">By <a rel="author" href="/author/jane">Jane Doe</a></p>
</body></html>"""
    out = _run(html)
    assert out["byline_links"].status.value == "pass"


def test_byline_skip_when_no_byline_present():
    html = """<html><body><h1>Acme</h1><p>Marketing copy.</p></body></html>"""
    out = _run(html)
    assert out["byline_links"].status.value == "skip"


def test_byline_fail_when_byline_text_does_not_link():
    html = """<html><body>
<p class="byline">By Jane Doe</p>
<p>Body.</p>
</body></html>"""
    out = _run(html)
    assert out["byline_links"].status.value == "fail"


def test_byline_pass_with_meta_author_and_anchor():
    html = """<html><head>
<meta name="author" content="Jane Doe">
</head><body>
<p>By <a class="author" href="/author/jane">Jane Doe</a></p>
</body></html>"""
    out = _run(html)
    assert out["byline_links"].status.value == "pass"


# ---------------------------------------------------------------------------
# Transcripts
# ---------------------------------------------------------------------------


def test_transcripts_skip_when_no_media():
    html = """<html><body><p>Just text.</p></body></html>"""
    out = _run(html)
    assert out["transcripts_for_media"].status.value == "skip"


def test_transcripts_pass_with_track_kind_captions():
    html = """<html><body>
<video><track kind="captions" src="/c.vtt"></video>
</body></html>"""
    out = _run(html)
    assert out["transcripts_for_media"].status.value == "pass"


def test_transcripts_pass_with_youtube_embed_and_transcript_link():
    html = """<html><body>
<iframe src="https://www.youtube.com/embed/abc123"></iframe>
<details><summary>Read the full transcript</summary><p>...</p></details>
</body></html>"""
    out = _run(html)
    assert out["transcripts_for_media"].status.value == "pass"


def test_transcripts_fail_when_video_without_transcript():
    html = """<html><body>
<iframe src="https://www.youtube.com/embed/abc"></iframe>
<p>Short caption.</p>
</body></html>"""
    out = _run(html)
    assert out["transcripts_for_media"].status.value == "fail"


# ---------------------------------------------------------------------------
# Empty / edge cases
# ---------------------------------------------------------------------------


def test_empty_html_returns_no_checks():
    assert check_citability("", []) == []


def test_marketing_homepage_skips_article_specific_checks():
    """A typical marketing homepage shouldn't be punished by article-only checks."""
    body_words = "marketing copy " * 100
    html = f"""<html><head><title>Acme</title></head><body>
<header><h1>Acme</h1></header>
<main><p>{body_words}</p></main>
</body></html>"""
    out = _run(html)
    # Article-specific checks SKIP on a homepage
    assert out["freshness_visible_updated"].status.value == "skip"
    assert out["byline_links"].status.value == "skip"
    assert out["transcripts_for_media"].status.value == "skip"
