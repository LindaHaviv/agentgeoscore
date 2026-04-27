"""Tests for backend/app/test_prompts.py — category detection + prompt generation."""
from __future__ import annotations

from urllib.parse import unquote_plus

import pytest

from app.test_prompts import (
    CATEGORY_DEFS,
    build_test_prompts_bundle,
    detect_category,
    extract_brand,
    generate_prompts,
    list_categories,
)

# ---- Brand extraction ------------------------------------------------------


def test_extract_brand_prefers_og_site_name():
    html = """<html><head>
<meta property="og:site_name" content="Acme Inc" />
<title>Pricing - Acme Inc</title>
</head></html>"""
    assert extract_brand(html, "acme.com") == "Acme Inc"


def test_extract_brand_falls_back_to_jsonld_organization_name():
    html = """<html><head>
<title>Pricing | Sample</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Organization","name":"WidgetCo"}
</script>
</head></html>"""
    assert extract_brand(html, "widget.com") == "WidgetCo"


def test_extract_brand_falls_back_to_branded_title_segment():
    html = """<html><head><title>Buy something cool | Cool Co</title></head></html>"""
    assert extract_brand(html, "coolco.com") == "Cool Co"


def test_extract_brand_humanizes_host_when_nothing_else_works():
    assert extract_brand("<html></html>", "example.com") == "Example"


# ---- Category detection ----------------------------------------------------


def test_detect_dev_tools_via_schema_and_paths():
    html = """<html><head>
<title>SDK</title>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"SoftwareSourceCode"}
</script>
</head><body>
<a href="/docs">docs</a><a href="/api">api</a><a href="/changelog">changelog</a>
</body></html>"""
    cat = detect_category(html, [{"@type": "SoftwareSourceCode"}], "example.dev")
    assert cat.slug == "dev-tools"
    assert cat.confidence == "high"


def test_detect_fintech_via_path_hints_and_keywords():
    html = """<html><head><title>Stripe — payments</title>
<meta name="description" content="Online payment processing for internet businesses." />
</head><body>
<a href="/payments">Payments</a><a href="/billing">Billing</a><a href="/payouts">Payouts</a>
<h1>Financial infrastructure for the internet</h1>
</body></html>"""
    cat = detect_category(html, [], "stripe.com")
    assert cat.slug == "fintech-payments"


def test_detect_ai_tools_via_strong_keywords_in_h1():
    """Devin's homepage has a thin meta description but strong AI signals in the hero."""
    html = """<html><head><title>Devin</title></head>
<body>
<h1>The AI software engineer</h1>
<h2>Devin is an AI coding agent that ships PRs autonomously.</h2>
<a href="/pricing">Pricing</a><a href="/customers">Customers</a>
</body></html>"""
    cat = detect_category(html, [], "devin.ai")
    assert cat.slug == "ai-tools"
    # Strong keywords should drive confidence high enough that b2b-saas (which
    # also matches /pricing /customers) doesn't win.
    assert cat.confidence in ("high", "medium")


def test_detect_news_via_schema_NewsArticle():
    cat = detect_category(
        "<html><body></body></html>",
        [{"@type": "NewsArticle", "headline": "x"}],
        "news.example",
    )
    assert cat.slug == "news-media"


def test_detect_restaurant_via_path_hints():
    html = """<html><head><title>Joe's</title></head><body>
<a href="/menu">Menu</a><a href="/reservations">Book</a><a href="/locations">Locations</a>
</body></html>"""
    cat = detect_category(html, [], "joes.example")
    assert cat.slug == "restaurants-local"


def test_detect_falls_back_to_generic_on_empty_page():
    cat = detect_category("<html></html>", [], "anything.example")
    assert cat.slug == "generic"
    assert cat.confidence == "low"


def test_detect_does_not_misfire_when_a_path_hint_is_a_substring_of_an_unrelated_path():
    """Regression: ``/services`` (agency hint) shouldn't match ``/services/cooking``
    on a marketplace; we accept ``/services`` as a literal nav path only.

    Airbnb and similar marketplaces use ``/services`` for a different meaning,
    so the agency-consulting category was tightened — its hints no longer
    include ``/services``. This test pins that behaviour.
    """
    html = """<html><body>
<a href="/services">Services</a><a href="/host">Host</a>
</body></html>"""
    cat = detect_category(html, [], "marketplace.example")
    assert cat.slug != "agency-consulting"


def test_detect_does_not_classify_furniture_store_as_design_software():
    """Regression: removing generic 'design'/'designer' keywords from
    design-creative so an interior-decor brand doesn't mis-trigger.
    """
    html = """<html><head><title>IKEA</title>
<meta name="description" content="Affordable furniture and home design ideas." />
</head><body>
<h1>Hej, design lovers</h1>
<h2>Beautiful, functional and well designed.</h2>
</body></html>"""
    cat = detect_category(html, [], "ikea.com")
    assert cat.slug != "design-creative"


# ---- Prompt generation -----------------------------------------------------


def test_generate_prompts_returns_four_angles_in_order():
    prompts = generate_prompts("fintech-payments", "Acme")
    assert [p.angle for p in prompts] == ["category", "use_case", "comparison", "long_tail"]


def test_generate_prompts_substitutes_brand_in_comparison():
    prompts = generate_prompts("fintech-payments", "Acme")
    comp = next(p for p in prompts if p.angle == "comparison")
    assert "Acme vs alternatives" in comp.text


def test_generate_prompts_uses_an_for_vowel_initial_descriptor():
    """Regression: 'a ecommerce platform' -> 'an ecommerce platform'."""
    prompts = generate_prompts("ecommerce-platform", "Acme")
    long_tail = next(p for p in prompts if p.angle == "long_tail")
    assert "an ecommerce platform" in long_tail.text
    assert "a ecommerce" not in long_tail.text


def test_generate_prompts_uses_a_for_consonant_initial_descriptor():
    prompts = generate_prompts("fintech-payments", "Acme")
    long_tail = next(p for p in prompts if p.angle == "long_tail")
    assert "a payment processor" in long_tail.text


def test_generate_prompts_handles_empty_brand():
    prompts = generate_prompts("dev-tools", "")
    comp = next(p for p in prompts if p.angle == "comparison")
    assert "this site vs alternatives" in comp.text


def test_generate_prompts_unknown_slug_falls_back_to_generic():
    prompts = generate_prompts("not-a-real-category", "Brand")
    # Generic category produces 4 prompts without crashing.
    assert len(prompts) == 4


# ---- Deep links ------------------------------------------------------------


def test_deep_links_url_encode_prompt_for_each_platform():
    prompts = generate_prompts("ai-tools", "Brand")
    cat_prompt = prompts[0]
    expected_q = cat_prompt.text
    for url in (
        cat_prompt.deep_links.chatgpt,
        cat_prompt.deep_links.perplexity,
        cat_prompt.deep_links.claude,
        cat_prompt.deep_links.google_ai,
    ):
        # Each URL must round-trip the prompt text via its q= param.
        assert "?q=" in url or "&q=" in url
        q = url.split("q=", 1)[1].split("&", 1)[0]
        assert unquote_plus(q) == expected_q


def test_deep_links_target_documented_endpoints():
    prompts = generate_prompts("ai-tools", "Brand")
    dl = prompts[0].deep_links
    assert dl.chatgpt.startswith("https://chatgpt.com/")
    assert dl.perplexity.startswith("https://www.perplexity.ai/")
    assert dl.claude.startswith("https://claude.ai/")
    assert dl.google_ai.startswith("https://www.google.com/search")
    # Google AI Mode is gated by udm=50 — guard against that getting dropped.
    assert "udm=50" in dl.google_ai


# ---- Bundle assembly -------------------------------------------------------


def test_bundle_contains_detected_category_and_all_categories():
    html = """<html><head><title>Acme</title></head>
<body><a href="/menu">menu</a></body></html>"""
    bundle = build_test_prompts_bundle(html, [], "acme.com")
    assert bundle.detected_category.slug == "restaurants-local"
    # all_categories powers the override dropdown.
    slugs = {c["slug"] for c in bundle.all_categories}
    expected = {c.slug for c in CATEGORY_DEFS}
    assert slugs == expected


def test_bundle_honors_category_override():
    html = """<html><body><a href="/menu">menu</a></body></html>"""
    bundle = build_test_prompts_bundle(html, [], "acme.com", category_override="b2b-saas")
    # Override forces the slug regardless of detection signals
    assert bundle.detected_category.slug == "b2b-saas"
    assert bundle.detected_category.confidence == "high"
    assert "user override" in bundle.detected_category.signals


def test_bundle_ignores_unknown_override_slug():
    """An attacker-supplied or stale override slug should fall through to
    auto-detection rather than crash or render garbage."""
    html = """<html><body><a href="/menu">menu</a></body></html>"""
    bundle = build_test_prompts_bundle(html, [], "acme.com", category_override="🦄-not-real")
    # Falls through to detection
    assert bundle.detected_category.slug == "restaurants-local"


def test_list_categories_returns_tuples_of_slug_and_label():
    cats = list_categories()
    assert all("slug" in c and "label" in c for c in cats)
    assert len(cats) == len(CATEGORY_DEFS)


# ---- Sanity: all prompts are non-empty for every category ------------------


@pytest.mark.parametrize("cat", [c for c in CATEGORY_DEFS])
def test_every_category_renders_four_non_empty_prompts(cat):
    prompts = generate_prompts(cat.slug, "Brand")
    assert len(prompts) == 4
    for p in prompts:
        assert p.text and p.text.strip()
        assert p.rationale and p.rationale.strip()
