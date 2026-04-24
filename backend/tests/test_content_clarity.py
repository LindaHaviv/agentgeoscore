"""Tests for content clarity scanner."""
from __future__ import annotations

from app.scanners.content_clarity import check_content_clarity


def _ids(results):
    return {r.id: r for r in results}


def test_empty_html_fails_everything():
    out = check_content_clarity("")
    assert out[0].id == "html_reachable"
    assert out[0].status.value == "fail"


def test_good_page_passes():
    html = """<!doctype html><html lang="en">
<head>
  <title>AgentGEOScore — SEO for AI</title>
  <meta name="description" content="Paste a URL and get a 0 to 100 score for how well AI agents find and cite your site.">
</head>
<body>
<header><nav>Nav</nav></header>
<main><article>
  <h1>AgentGEOScore</h1>
  <h2>Why it matters</h2>
  <p>This is a paragraph with plenty of extractable text content for AI agents to read and index. """ + ("More words here to hit the 50-word threshold. " * 5) + """</p>
  <h2>How it works</h2>
  <p>Another body paragraph with plenty of text. """ + ("More content. " * 10) + """</p>
</article></main>
<footer>Footer</footer>
</body></html>"""
    ids = _ids(check_content_clarity(html))
    assert ids["title_quality"].status.value == "pass"
    assert ids["meta_description"].status.value == "pass"
    assert ids["h1_single"].status.value == "pass"
    assert ids["semantic_html"].status.value == "pass"
    assert ids["heading_hierarchy"].status.value == "pass"
    assert ids["text_extractable"].status.value == "pass"
    assert ids["html_lang"].status.value == "pass"


def test_spa_shell_fails_text_extractable():
    html = """<html><head><title>App</title></head><body><div id="root"></div></body></html>"""
    ids = _ids(check_content_clarity(html))
    assert ids["text_extractable"].status.value == "fail"
    assert ids["h1_single"].status.value == "fail"


def test_multiple_h1s_warns():
    html = "<html><body><h1>One</h1><h1>Two</h1></body></html>"
    ids = _ids(check_content_clarity(html))
    assert ids["h1_single"].status.value == "warn"


def test_title_too_long_warns():
    long_title = "A" * 120
    html = f"<html><head><title>{long_title}</title></head><body><h1>X</h1></body></html>"
    ids = _ids(check_content_clarity(html))
    assert ids["title_quality"].status.value == "warn"
