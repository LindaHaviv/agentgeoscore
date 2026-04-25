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
    assert lines[1].startswith("> ")
    assert "widgets" in lines[1].lower()
    assert "/about" in out
    assert "/docs" in out
    assert "external.com" not in out
    assert "## Key pages" in out


def test_generate_with_empty_html():
    out = generate_llms_txt("", "https://acme.example", "acme.example")
    assert out.startswith("# Acme")
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


def test_prefers_og_site_name_over_h1():
    """Big marketing sites' H1 is often a campaign tagline ("Be the next
    big thing"), not the brand. og:site_name is the canonical brand."""
    html = """
    <html><head>
      <title>Be the next big thing — Shopify</title>
      <meta property="og:site_name" content="Shopify">
      <meta name="description" content="Try Shopify free and start a business.">
    </head><body>
      <h1>Be the next big thing</h1>
    </body></html>
    """
    out = generate_llms_txt(html, "https://shopify.com", "shopify.com")
    assert out.startswith("# Shopify\n")
    assert "Be the next big thing" not in out.splitlines()[0]


def test_prefers_jsonld_organization_name_when_no_og_site_name():
    html = """
    <html><head>
      <title>Hire the best AI software engineer | Devin</title>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Organization","name":"Cognition AI","url":"https://devin.ai"}
      </script>
      <meta name="description" content="Devin is an AI coding agent.">
    </head><body>
      <h1>Hire the best AI software engineer</h1>
    </body></html>
    """
    out = generate_llms_txt(html, "https://devin.ai", "devin.ai")
    assert out.startswith("# Cognition AI\n")


def test_jsonld_with_graph_array():
    """schema.org @graph wrapper is common — must traverse it."""
    html = """
    <html><head>
      <title>Page</title>
      <script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"WebSite","name":"Acme Inc","url":"https://acme.example"},
          {"@type":"WebPage","name":"Home"}
        ]}
      </script>
    </head><body><h1>Page</h1></body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert out.startswith("# Acme Inc\n")


def test_falls_back_to_branded_title_segment():
    """Strip 'Brand | Tagline' to just 'Brand'."""
    html = """
    <html><head>
      <title>Stripe | Financial Infrastructure for the Internet</title>
    </head><body><h1>Move money. Anywhere.</h1></body></html>
    """
    out = generate_llms_txt(html, "https://stripe.com", "stripe.com")
    assert out.startswith("# Stripe\n")


def test_handles_tagline_dash_brand_title():
    """For 'Tagline - Brand' style titles, prefer the trailing brand."""
    html = """
    <html><head>
      <title>Best widgets for every team — Acme</title>
    </head><body></body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    # Either the cleaned full title or just "Acme" — must NOT use the H1.
    assert "Best widgets for every team" not in out.splitlines()[0]


def test_h1_used_when_short_and_no_other_signal():
    """Plain sites where the H1 IS the brand should still work."""
    html = """
    <html><head>
      <title>Home</title>
    </head><body><h1>MyApp</h1></body></html>
    """
    out = generate_llms_txt(html, "https://myapp.example", "myapp.example")
    # Title is "Home" — should fall back to H1 "MyApp"
    assert out.startswith("# MyApp\n")


def test_h1_rejected_when_too_long():
    """H1s that are full sentences are campaigns, not brands."""
    html = """
    <html><head><title></title></head>
    <body><h1>The all-in-one platform that helps you grow your business faster than ever before</h1></body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    # Must fall back to host-derived name.
    assert out.startswith("# Acme\n")


def test_skips_self_homepage_link():
    """Don't emit a Key Page entry that just points back at the root."""
    html = """
    <html><head>
      <title>Acme</title>
      <meta name="description" content="A summary.">
    </head><body>
      <a href="/">Home</a>
      <a href="/pricing">Pricing</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "(https://acme.example)" not in out
    assert "/pricing" in out


def test_filters_login_and_legal_paths():
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="/login">Log in</a>
      <a href="/account">Account</a>
      <a href="/legal/terms">Terms</a>
      <a href="/privacy">Privacy</a>
      <a href="/cookies">Cookies</a>
      <a href="/about">About</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "/login" not in out
    assert "/account" not in out
    assert "/legal" not in out
    assert "/privacy" not in out
    assert "/cookies" not in out
    assert "/about" in out


def test_rejects_long_hero_card_labels():
    """A link with text > 50 chars and no aria-label should be dropped, not
    truncated to an ugly half-sentence label."""
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="/sell">Switch to Shopify Get more customers Make more sales today and tomorrow forever</a>
      <a href="/pricing">Pricing</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    # The long label produces a truncated label, not the original sentence.
    assert "Switch to Shopify Get more customers Make more sales" not in out
    assert "/pricing" in out


def test_uses_aria_label_when_anchor_text_is_long():
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="/products/widget" aria-label="Widget product page">
        <span>Widget</span>
        <p>The greatest widget ever invented, period, full stop, no exceptions whatsoever.</p>
      </a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "[Widget product page]" in out


def test_priority_paths_sort_first():
    """Pricing/about/docs should appear before generic non-priority paths."""
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="/random-page">Random page</a>
      <a href="/another-thing">Another thing</a>
      <a href="/pricing">Pricing</a>
      <a href="/about">About</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    pricing_idx = out.find("/pricing")
    random_idx = out.find("/random-page")
    assert 0 < pricing_idx < random_idx, "priority paths must sort before generic ones"


def test_dedupes_and_caps_link_count():
    """Even huge homepages should produce at most _MAX_LINKS entries."""
    body_links = "".join(f'<a href="/page{i}">Page {i}</a>' for i in range(40))
    html = f"<html><head><title>Acme</title></head><body>{body_links}</body></html>"
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    key_pages_section = out.split("## Key pages", 1)[1]
    bullet_count = sum(1 for line in key_pages_section.splitlines() if line.startswith("- ["))
    assert bullet_count <= 7


def test_drops_redundant_slug_hint():
    """A hint shouldn't just repeat words from the label."""
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="/pricing">Pricing</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    # The label is "Pricing" and the slug is "pricing" — no `: pricing` tail.
    assert "[Pricing](https://acme.example/pricing)" in out
    assert "[Pricing](https://acme.example/pricing): pricing" not in out


def test_rejects_cta_summary_meta_description():
    """Some sites set <meta name=description> to a CTA — fall through."""
    html = """
    <html><head>
      <title>Acme</title>
      <meta name="description" content="Get started today.">
      <meta property="og:description" content="Acme makes widgets that scale to a million customers and beyond.">
    </head><body><h1>Acme</h1></body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "Acme makes widgets" in out
    assert "Get started today." not in out


def test_off_host_links_excluded():
    html = """
    <html><head><title>Acme</title></head><body>
      <a href="https://docs.acme.example">Docs subdomain</a>
      <a href="https://twitter.com/acme">External</a>
    </body></html>
    """
    out = generate_llms_txt(html, "https://acme.example", "acme.example")
    assert "twitter.com" not in out
    # docs.acme.example should be allowed (subdomain of acme.example).
    assert "docs.acme.example" in out
