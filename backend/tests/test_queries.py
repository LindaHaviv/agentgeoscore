"""Tests for probe-query derivation."""
from __future__ import annotations

from app.probes.queries import derive_queries


def test_fallback_for_empty_html():
    q = derive_queries("", "example.com")
    assert q == ["example.com review"]


def test_uses_title_and_description():
    html = """<html><head>
<title>Notion — Your wiki, docs, & projects. Together.</title>
<meta name="description" content="Notion is the happier workspace. Write, plan, share.">
</head><body><h1>Welcome</h1><h2>Features</h2><h2>Pricing</h2></body></html>"""
    q = derive_queries(html, "notion.so")
    # Description becomes query 1
    assert any("happier workspace" in x.lower() for x in q)
    # Something recommending-style
    assert any("best" in x.lower() for x in q)
    # Domain-review style
    assert any("notion.so" in x for x in q)


def test_dedup_preserves_order():
    html = "<html><head><title>Foo</title><meta name='description' content='Foo'></head><body></body></html>"
    q = derive_queries(html, "foo.com")
    # Lowercased dedup
    assert len(q) == len(set(x.lower() for x in q))


def test_respects_max_queries():
    html = """<html><head>
<title>Detailed title here</title>
<meta name="description" content="A long description about the thing">
</head><body><h1>H</h1><h2>A</h2><h2>B</h2></body></html>"""
    q = derive_queries(html, "thing.com", max_queries=2)
    assert len(q) <= 2
