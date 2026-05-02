"""Tests for backend/app/test_prompts.py — category detection + prompt generation."""

from __future__ import annotations

from urllib.parse import unquote_plus

import pytest

from app.test_prompts import (
    CATEGORY_DEFS,
    build_test_prompts_bundle,
    detect_category,
    extract_brand,
    extract_page_topics,
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
    # Multiple corroborating signals so the bundle hits the
    # min-detection threshold (3.5) — a single ``/menu`` link is no longer
    # enough to classify a site, by design (see the threshold fix that
    # stopped Mayo Clinic being mis-detected as 'online store' from a stray
    # ``/store`` link).
    html = """<html><head><title>Joe's</title></head>
<body><a href="/menu">menu</a><a href="/reservations">book</a></body></html>"""
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
    html = """<html><body><a href="/menu">menu</a><a href="/reservations">book</a></body></html>"""
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


# ---- New verticals: travel, sportswear, streaming, automotive --------------


def test_detect_travel_hospitality_via_title_and_paths():
    """Airbnb-shaped homepage: vacation rentals + /experiences nav."""
    html = """<html><head>
<title>Airbnb: Vacation Rentals, Cabins, Beach Houses, Unique Homes &amp; Experiences</title>
<meta name="description" content="Get an Airbnb for every kind of trip — 8 million vacation rentals worldwide" />
<meta property="og:site_name" content="Airbnb" />
</head><body>
<a href="/homes">Homes</a><a href="/experiences">Experiences</a><a href="/host">Host</a>
<h2>Homes on Airbnb</h2>
</body></html>"""
    cat = detect_category(html, [], "airbnb.com")
    assert cat.slug == "travel-hospitality"


def test_detect_apparel_sportswear_via_strong_keywords_and_paths():
    """Nike-shaped homepage: 'world's athletes' + /running /basketball nav."""
    html = """<html><head>
<title>Nike. Just Do It. Nike.com</title>
<meta name="description" content="Inspiring the world's athletes, Nike delivers innovative products and gear." />
</head><body>
<a href="/running">Running</a><a href="/basketball">Basketball</a><a href="/training">Training</a>
</body></html>"""
    cat = detect_category(html, [], "nike.com")
    assert cat.slug == "apparel-sportswear"


def test_detect_entertainment_streaming_via_title_and_strong_keywords():
    """Netflix-shaped homepage: 'watch tv shows online' + /watch nav."""
    html = """<html><head>
<title>Netflix - Watch TV Shows Online, Watch Movies Online</title>
<meta name="description" content="Watch Netflix movies &amp; TV shows online or stream right to your smart TV." />
</head><body>
<a href="/watch">Watch</a><a href="/browse/genre/839338">Comedy</a>
<h2>Trending Now</h2>
</body></html>"""
    cat = detect_category(html, [], "netflix.com")
    assert cat.slug == "entertainment-streaming"


# ---- Threshold: weak single-signal sites should fall back to generic -------


def test_single_weak_nav_link_does_not_misclassify_site():
    """Regression: a healthcare site with a stray ``/store`` nav link must
    *not* be classified as ``ecommerce-store`` from that single signal alone.

    This was the Mayo Clinic bug — one nav link to /store was outranking
    a richer healthcare context. The min-detection threshold (3.5) requires
    multiple corroborating signals before any classification fires.
    """
    html = """<html><head><title>Some Site</title></head>
<body><a href="/store">Store</a></body></html>"""
    cat = detect_category(html, [], "example.com")
    # Single nav-link match (2.0) does not pass the 3.5 threshold.
    assert cat.slug == "generic"


# ---- Brand TLD-suffix stripping --------------------------------------------


def test_extract_brand_strips_dot_com_suffix_from_og_site_name():
    """Regression: ``Nike.com`` → ``Nike``. Some sites set og:site_name to
    their domain literal; we shouldn't render ``Nike.com vs alternatives``.
    """
    html = '<html><head><meta property="og:site_name" content="Nike.com" /></head></html>'
    assert extract_brand(html, "nike.com") == "Nike"


def test_extract_brand_strips_dot_co_suffix():
    html = '<html><head><meta property="og:site_name" content="Linear.app" /></head></html>'
    assert extract_brand(html, "linear.app") == "Linear"


def test_extract_brand_does_not_strip_when_internal_dot():
    """``IO Interactive`` is a brand name, not a TLD-suffixed brand."""
    html = '<html><head><meta property="og:site_name" content="IO Interactive" /></head></html>'
    assert extract_brand(html, "ioi.dk") == "IO Interactive"


# ---- Page topic extraction --------------------------------------------------


def test_extract_page_topics_picks_up_repeated_h2():
    html = """<html><body>
<h2>Vacation Rentals</h2>
<h2>Vacation Rentals</h2>
<h3>Beach Houses</h3>
<a href="/x">Privacy</a>
</body></html>"""
    topics = extract_page_topics(html)
    # Most-repeated phrase wins, boilerplate (Privacy) is filtered.
    assert "vacation rentals" in topics
    assert "privacy" not in topics


def test_extract_page_topics_collapses_repeated_tokens_and_badges():
    """Airbnb's nav renders "Experiences" + a NEW badge as the literal text
    ``"Experiences Experiences, NEW"``. The normalizer collapses duplicate
    tokens and strips the badge so the topic is just ``"experiences"``."""
    html = """<html><body>
<a href="/experiences">Experiences Experiences, NEW</a>
<a href="/experiences">Experiences Experiences, NEW</a>
<a href="/host">Become a host</a>
</body></html>"""
    topics = extract_page_topics(html)
    assert "experiences" in topics
    # The duplicated/badge-suffixed form must NOT slip through.
    assert "experiences experiences, new" not in topics


def test_extract_page_topics_filters_brand_substring():
    """``Homes on Airbnb`` repeats 3x on Airbnb's homepage but contains the
    brand and would render awkwardly as ``…focused on homes on airbnb``."""
    html = """<html><body>
<h2>Homes on Airbnb</h2><h2>Homes on Airbnb</h2><h2>Homes on Airbnb</h2>
<h3>Vacation Rentals</h3>
</body></html>"""
    topics = extract_page_topics(html, exclude_brand="Airbnb")
    assert "homes on airbnb" not in topics
    assert "vacation rentals" in topics


def test_extract_page_topics_filters_cta_phrases():
    """``Get the report``, ``Talk to sales`` and similar CTAs would corrupt the
    long-tail prompt — they're filtered by first-word and stoplist matches."""
    html = """<html><body>
<a href="/sales">Talk to sales</a>
<a href="/sales">Contact Sales</a>
<a href="/report">Get the report</a>
<a href="/demo">Book a demo</a>
<h2>Subscription Billing</h2>
</body></html>"""
    topics = extract_page_topics(html)
    for cta in ("talk to sales", "contact sales", "get the report", "book a demo"):
        assert cta not in topics
    assert "subscription billing" in topics


def test_extract_page_topics_filters_generic_chrome():
    """Stoplisted boilerplate (login, sign up, privacy) must not appear."""
    html = """<html><body>
<a href="/login">Log in</a>
<a href="/signup">Sign up</a>
<a href="/about">About us</a>
<a href="/help">Help</a>
<h2>Beach Houses</h2>
</body></html>"""
    topics = extract_page_topics(html)
    for stop in ("log in", "sign up", "about us", "help"):
        assert stop not in topics


def test_long_tail_prompt_interpolates_extracted_topic():
    """Topic appears in long_tail prompt as ``focused on <topic>``."""
    prompts = generate_prompts("travel-hospitality", "Airbnb", topics=["vacation rentals"])
    long_tail = next(p for p in prompts if p.angle == "long_tail")
    assert "focused on vacation rentals" in long_tail.text


def test_long_tail_prompt_omits_topic_clause_when_no_topics():
    """Without topics, long_tail falls back to the bare persona phrasing."""
    prompts = generate_prompts("travel-hospitality", "Airbnb")
    long_tail = next(p for p in prompts if p.angle == "long_tail")
    assert "focused on" not in long_tail.text


def test_generic_category_does_not_take_topic_interpolation():
    """If the category is unknown, don't fake site-specificity by
    appending a topic — render the bare generic persona instead."""
    prompts = generate_prompts("generic", "Acme", topics=["vacation rentals"])
    long_tail = next(p for p in prompts if p.angle == "long_tail")
    assert "focused on" not in long_tail.text
