"""End-to-end test of the /api/scan route with mocked external HTTP."""
from __future__ import annotations

import respx
from fastapi.testclient import TestClient
from httpx import Response

from app.main import app

HOMEPAGE = """<!doctype html><html lang="en"><head>
<title>Example — The best example site</title>
<meta name="description" content="Paste any URL and get an AgentGEOScore. This is a long enough description for the check.">
<link rel="canonical" href="https://example.com/">
<meta property="og:title" content="Example">
<meta property="og:description" content="d">
<meta property="og:type" content="website">
<meta property="og:url" content="https://example.com">
<meta property="og:image" content="https://example.com/i.png">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Organization","name":"Example"}</script>
</head>
<body>
<header><nav>N</nav></header>
<main><article>
<h1>Welcome</h1>
<h2>About</h2>
<p>""" + ("This is content. " * 60) + """</p>
<h2>Features</h2>
<p>""" + ("More content here. " * 40) + """</p>
</article></main>
<footer>F</footer>
</body></html>"""

ROBOTS_OK = """User-agent: *
Allow: /

User-agent: GPTBot
Allow: /

User-agent: ClaudeBot
Allow: /

Sitemap: https://example.com/sitemap.xml
"""

LLMS_TXT = """# Example

> Example is a demo site for AgentGEOScore.

## Docs
- [Getting started](/docs)
"""

SITEMAP = """<?xml version='1.0' encoding='UTF-8'?>
<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>
<url><loc>https://example.com/</loc></url>
</urlset>"""


def _setup_mocks(include_llms: bool = True, include_sitemap: bool = True):
    respx.get("https://example.com/").mock(return_value=Response(200, text=HOMEPAGE))
    respx.get("https://example.com/robots.txt").mock(return_value=Response(200, text=ROBOTS_OK))
    if include_llms:
        respx.get("https://example.com/llms.txt").mock(return_value=Response(200, text=LLMS_TXT))
    else:
        respx.get("https://example.com/llms.txt").mock(return_value=Response(404))
    respx.get("https://example.com/llms-full.txt").mock(return_value=Response(404))
    if include_sitemap:
        respx.get("https://example.com/sitemap.xml").mock(return_value=Response(200, text=SITEMAP))
    else:
        respx.get("https://example.com/sitemap.xml").mock(return_value=Response(404))


@respx.mock
def test_scan_happy_path(monkeypatch):
    # No probe keys → probe category skipped
    for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "BRAVE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DISABLE_DUCK_AI", "1")
    _setup_mocks()

    client = TestClient(app)
    resp = client.post("/api/scan", json={"url": "https://example.com"})
    assert resp.status_code == 200
    report = resp.json()
    assert report["domain"] == "example.com"
    assert 0 <= report["score"] <= 100
    # High-quality fixture should score well
    assert report["score"] >= 60
    assert report["grade"] in ("A", "B", "C")
    assert len(report["categories"]) >= 4
    # The generated llms.txt is always returned
    assert report["suggested_llms_txt"].startswith("# ")
    # Fix list (new rich model)
    assert isinstance(report["fixes"], list)
    for fix in report["fixes"]:
        assert fix["severity"] in ("critical", "important", "minor")
        assert fix["effort"] in ("low", "medium", "high")
        assert fix["score_lift"] >= 0


@respx.mock
def test_scan_bad_site_low_score(monkeypatch):
    for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "BRAVE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("DISABLE_DUCK_AI", "1")

    bad_html = "<html><body><div id='root'></div></body></html>"
    respx.get("https://bad.com/").mock(return_value=Response(200, text=bad_html))
    respx.get("https://bad.com/robots.txt").mock(
        return_value=Response(200, text="User-agent: *\nDisallow: /\n")
    )
    respx.get("https://bad.com/llms.txt").mock(return_value=Response(404))
    respx.get("https://bad.com/llms-full.txt").mock(return_value=Response(404))
    respx.get("https://bad.com/sitemap.xml").mock(return_value=Response(404))

    client = TestClient(app)
    resp = client.post("/api/scan", json={"url": "https://bad.com"})
    assert resp.status_code == 200
    report = resp.json()
    assert report["score"] < 40
    assert report["grade"] in ("D", "F")
    assert len(report["fixes"]) > 0
    # Critical fixes surface first
    assert report["fixes"][0]["severity"] == "critical"


def test_scan_rejects_invalid_url():
    client = TestClient(app)
    resp = client.post("/api/scan", json={"url": "not a url"})
    assert resp.status_code == 422  # pydantic validation


def test_healthz():
    client = TestClient(app)
    assert client.get("/api/healthz").json() == {"ok": True}
