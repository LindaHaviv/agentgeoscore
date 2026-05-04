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


# ---- JSON-LD validator-conformance (gap #5) -------------------------------


def _html_with_jsonld(*blocks: str) -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{b}</script>' for b in blocks
    )
    return f"<html><head>{scripts}</head><body></body></html>"


def _find_validity(html: str):
    for r in check_structured_data(html):
        if r.id == "jsonld_validity":
            return r
    return None


def test_jsonld_validity_pass_for_complete_article():
    block = """{
      "@context":"https://schema.org","@type":"Article",
      "headline":"Hello","author":{"@type":"Person","name":"Jane"},
      "datePublished":"2026-04-20","dateModified":"2026-04-21",
      "image":"https://ex.com/a.jpg","publisher":{"@type":"Organization","name":"Acme"}
    }"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "pass"
    assert r.evidence["validated"] == 1
    assert r.evidence["broken_required"] == 0


def test_jsonld_validity_fail_when_article_missing_headline():
    block = """{
      "@context":"https://schema.org","@type":"Article",
      "author":{"@type":"Person","name":"Jane"},
      "datePublished":"2026-04-20"
    }"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "fail"
    assert r.evidence["broken_required"] == 1
    assert "headline" in r.detail


def test_jsonld_validity_warn_when_only_recommended_missing():
    # All required present, but missing recommended logo/sameAs.
    block = """{"@context":"https://schema.org","@type":"Organization",
               "name":"Acme","url":"https://example.com"}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "warn"
    assert r.evidence["missing_recommended"] == 1
    assert "logo" in r.detail or "sameAs" in r.detail


def test_jsonld_validity_fail_product_missing_name():
    block = """{"@context":"https://schema.org","@type":"Product",
               "offers":{"@type":"Offer","price":"9","priceCurrency":"USD"}}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "fail"
    assert "name" in r.detail


def test_jsonld_validity_fail_faqpage_without_mainentity():
    block = """{"@context":"https://schema.org","@type":"FAQPage"}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "fail"
    assert "mainEntity" in r.detail


def test_jsonld_validity_fail_faqpage_with_malformed_question():
    """Question missing acceptedAnswer.text — structurally broken despite mainEntity."""
    block = """{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":"Q?","acceptedAnswer":{"@type":"Answer"}}
    ]}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "fail"
    # Evidence must surface the specific problem, not just the top-level type.
    block_entry = r.evidence["blocks"][0]
    assert any("acceptedAnswer" in p for p in block_entry["missing_required"])


def test_jsonld_validity_pass_faqpage_with_two_valid_questions():
    block = """{"@context":"https://schema.org","@type":"FAQPage","mainEntity":[
        {"@type":"Question","name":"Q1?","acceptedAnswer":{"@type":"Answer","text":"A1"}},
        {"@type":"Question","name":"Q2?","acceptedAnswer":{"@type":"Answer","text":"A2"}}
    ]}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "pass"


def test_jsonld_validity_skip_when_only_untyped_or_unknown_types():
    # WebSite is a real schema.org type but not one we validate — should skip.
    block = """{"@context":"https://schema.org","@type":"WebSite","name":"x","url":"https://x"}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    assert r.status.value == "skip"
    assert r.evidence["validated"] == 0


def test_jsonld_validity_not_emitted_when_no_jsonld_at_all():
    """When the page has zero JSON-LD, jsonld_present owns the messaging;
    the validity row must NOT be emitted (would double-report)."""
    html = "<html><head></head><body>no jsonld</body></html>"
    ids = {r.id for r in check_structured_data(html)}
    assert "jsonld_validity" not in ids
    assert "jsonld_present" in ids


def test_jsonld_validity_walks_nested_blocks():
    """A valid Article nested inside an @graph wrapper should be validated."""
    block = """{"@context":"https://schema.org","@graph":[
        {"@type":"Organization","name":"Acme","url":"https://ex.com","logo":"https://ex.com/l.png"},
        {"@type":"Article","headline":"Hi","author":{"@type":"Person","name":"J"},
         "datePublished":"2026-01-01","dateModified":"2026-01-02",
         "image":"https://ex.com/i.jpg","publisher":{"@type":"Organization","name":"Acme"}}
    ]}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    # Both blocks inside @graph should be counted.
    assert r.evidence["validated"] >= 2


def test_jsonld_validity_evidence_includes_block_label_when_available():
    """The evidence should surface a human-identifiable label per block."""
    block = """{"@context":"https://schema.org","@type":"Article",
               "headline":"The long headline for this article",
               "author":{"@type":"Person","name":"X"},
               "datePublished":"2026-01-01"}"""
    r = _find_validity(_html_with_jsonld(block))
    assert r is not None
    labels = [b.get("label") for b in r.evidence["blocks"]]
    assert "The long headline for this article" in labels
