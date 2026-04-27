"""Tests for structured data extraction."""
from __future__ import annotations

from app.scanners.structured_data import (
    check_structured_data,
    extract_jsonld,
    extract_og,
    extract_twitter,
)


def test_jsonld_single_object():
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"Foo"}
</script></head><body></body></html>"""
    out = extract_jsonld(html)
    assert len(out) == 1
    assert out[0]["@type"] == "Organization"


def test_jsonld_list():
    html = """<html><head>
<script type="application/ld+json">
[{"@type":"Article","headline":"A"},{"@type":"Person","name":"B"}]
</script></head></html>"""
    out = extract_jsonld(html)
    assert [x["@type"] for x in out] == ["Article", "Person"]


def test_jsonld_graph_wrapper():
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@graph":[
  {"@type":"WebSite","name":"S"},
  {"@type":"Organization","name":"O"}
]}
</script></head></html>"""
    out = extract_jsonld(html)
    assert {x["@type"] for x in out} == {"WebSite", "Organization"}


def test_jsonld_malformed_is_skipped():
    html = """<html><head>
<script type="application/ld+json">{not valid json}</script>
<script type="application/ld+json">{"@type":"Thing"}</script>
</head></html>"""
    out = extract_jsonld(html)
    assert len(out) == 1
    assert out[0]["@type"] == "Thing"


def test_jsonld_empty():
    assert extract_jsonld("") == []
    assert extract_jsonld("<html></html>") == []


def test_og_extraction():
    html = """<html><head>
<meta property="og:title" content="Hello">
<meta property="og:image" content="https://example.com/img.png">
<meta property="article:author" content="Alice">
<meta name="description" content="not og">
</head></html>"""
    og = extract_og(html)
    assert og["og:title"] == "Hello"
    assert og["og:image"] == "https://example.com/img.png"
    assert og["article:author"] == "Alice"
    assert "description" not in og


def test_twitter_extraction():
    html = """<html><head>
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="T">
</head></html>"""
    tw = extract_twitter(html)
    assert tw["twitter:card"] == "summary_large_image"


def test_check_bundles_full_pass():
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"A"}
</script>
<meta property="og:title" content="A">
<meta property="og:description" content="d">
<meta property="og:type" content="website">
<meta property="og:url" content="https://a.com">
<meta property="og:image" content="https://a.com/i.png">
<meta name="twitter:card" content="summary">
</head></html>"""
    results = check_structured_data(html)
    ids = {r.id: r for r in results}
    assert ids["jsonld_present"].status.value == "pass"
    assert ids["opengraph"].status.value == "pass"
    assert ids["twitter_card"].status.value == "pass"


def test_check_bundles_missing_everything():
    html = "<html><head></head><body></body></html>"
    results = check_structured_data(html)
    ids = {r.id: r for r in results}
    assert ids["jsonld_present"].status.value == "fail"
    assert ids["opengraph"].status.value == "fail"
    assert ids["twitter_card"].status.value == "warn"


# ---------------------------------------------------------------------------
# Author Person schema with sameAs (E-E-A-T canonical)
# ---------------------------------------------------------------------------


def test_person_sameas_pass_with_two_links():
    html = """<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Person","name":"Jane",
 "sameAs":["https://linkedin.com/in/jane","https://github.com/jane"]}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["person_schema_sameas"].status.value == "pass"


def test_person_sameas_warn_with_one_link():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Person","name":"Jane","sameAs":["https://linkedin.com/in/jane"]}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["person_schema_sameas"].status.value == "warn"


def test_person_sameas_warn_when_no_sameas():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Person","name":"Jane"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    chk = ids["person_schema_sameas"]
    assert chk.status.value == "warn"
    assert chk.evidence["sameAs_count"] == 0


def test_person_sameas_skip_when_no_person_schema():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Organization","name":"Acme"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["person_schema_sameas"].status.value == "skip"


def test_person_sameas_finds_nested_person_inside_article():
    """Person nested inside an Article.author should still be detected."""
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Article","headline":"X",
 "author":{"@type":"Person","name":"Jane",
           "sameAs":["https://linkedin.com/in/jane","https://x.com/jane"]}}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["person_schema_sameas"].status.value == "pass"


# ---------------------------------------------------------------------------
# dateModified on Article schema (freshness)
# ---------------------------------------------------------------------------


def test_datemodified_pass_when_present_on_article():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Article","headline":"X","dateModified":"2026-04-20"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["freshness_datemodified"].status.value == "pass"


def test_datemodified_warn_when_only_published():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"BlogPosting","headline":"X","datePublished":"2025-01-15"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["freshness_datemodified"].status.value == "warn"


def test_datemodified_fail_when_article_has_neither_date():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Article","headline":"X"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["freshness_datemodified"].status.value == "fail"


def test_datemodified_skip_when_no_article_schema():
    html = """<html><head>
<script type="application/ld+json">
{"@type":"Organization","name":"A"}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["freshness_datemodified"].status.value == "skip"


def test_datemodified_handles_news_article_and_graph_wrapper():
    html = """<html><head>
<script type="application/ld+json">
{"@graph":[
  {"@type":"WebSite","name":"S"},
  {"@type":"NewsArticle","headline":"X","dateModified":"2026-04-20"}
]}
</script></head></html>"""
    ids = {r.id: r for r in check_structured_data(html)}
    assert ids["freshness_datemodified"].status.value == "pass"
