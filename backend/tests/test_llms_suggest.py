"""Tests for the starter-llms.txt generator."""
from __future__ import annotations

from app.llms_suggest import generate_llms_txt

FULL_HTML = """
<html><head>
<title>Acme Widgets — Best widgets in the galaxy</title>
<meta name="description" content="Acme Widgets makes the most reliable widgets for teams of every size.">
</head><body>
<h1>The Acme Widget</h1>
<p>Acme Widgets has been crafting dependable widgets since 1842, trusted by teams across industries.</p>
<nav>
  <a href="/about">About us</a>
  <a href="/docs">Documentation</a>
  <a href="/pricing">Pricing</a>
  <a href="https://external.com/offsite">Off-site link</a>
</nav>
</body></html>
"""


def test_generate_with_full_html():
    out = generate_llms_txt(FULL_HTML, "https://acme.example", "acme.example")
    lines = out.splitlines()
    assert lines[0].startswith("# ")
    assert "Acme Widget" in lines[0]
    # Second line is the > summary
    assert lines[1].startswith("> ")
    assert "widgets" in lines[1].lower()
    # Internal links only — no off-site
    assert "/about" in out
    assert "/docs" in out
    assert "external.com" not in out
    # Section header for key pages
    assert "## Key pages" in out


def test_generate_with_empty_html():
    out = generate_llms_txt("", "https://acme.example", "acme.example")
    assert out.startswith("# acme.example")
    assert "## Key pages" in out


def test_generate_falls_back_to_og_description():
    html = """
    <html><head>
      <title>Acme</title>
      <meta property="og:description" content="Fallback summary from OG tag.">
    </head><body><h1>Acme</h1></body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "Fallback summary from OG tag." in out
