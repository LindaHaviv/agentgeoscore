"""Generate AI-search test prompts for a scanned site.

Goal: tell the user *exactly* which prompts to paste into ChatGPT, Perplexity,
Claude, or Google's AI Mode to see whether their site shows up in answers
within its own category. Visibility in AI search is not the same thing as
SEO ranking, and a tool that scores GEO without offering a way to verify the
score in the field would feel hollow.

Architecture:

  detect_category(home_html, jsonld_blocks, host) -> DetectedCategory
    Reads cheap signals already collected during the main scan
    (no new HTTP fetches): schema.org @type, link paths in nav, meta keywords
    against a curated lexicon. Returns a category slug + confidence.

  generate_prompts(category, brand) -> list[TestPrompt]
    Renders 4 prompt angles per category (recommendation / use-case /
    comparison / persona-long-tail). Each prompt comes with deep links to
    ChatGPT / Perplexity / Claude / Google AI Mode that pre-fill the prompt
    via the platform's documented `?q=` URL param.

  build_test_prompts_bundle(...) -> TestPromptsBundle
    Top-level orchestration; this is what main.py wires into the Report.

The category lexicon below is hand-curated rather than learned. With ~14
verticals, a small lexicon is more legible (and easier to debug a
mis-classification on a real site) than a TF-IDF or embedding pipeline.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import quote_plus

from bs4 import BeautifulSoup, Tag

from .models import (
    DetectedCategory,
    PromptDeepLinks,
    TestPrompt,
    TestPromptsBundle,
)

# ---- Category lexicon ------------------------------------------------------


@dataclass(frozen=True)
class CategoryDef:
    """Self-contained definition of a vertical for prompt generation."""

    slug: str
    label: str            # display name shown in UI
    descriptor: str       # noun phrase for prompts: "payment processor"
    persona: str          # default persona: "developers integrating payments"
    use_case: str         # what users come to this category to do
    long_tail_persona: str  # specific persona for long-tail prompt
    schema_types: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()        # general title/meta/H1 terms (weight 1.0)
    strong_keywords: tuple[str, ...] = ()  # high-confidence terms (weight 3.0)
    path_hints: tuple[str, ...] = ()      # nav-link paths that suggest this vertical


# Order matters for prompt phrasing only; detection picks the highest-scoring
# definition regardless of order.
CATEGORY_DEFS: tuple[CategoryDef, ...] = (
    CategoryDef(
        slug="ai-tools",
        label="AI / ML tools",
        descriptor="AI tool",
        persona="people building with LLMs",
        use_case="add an AI feature to my product",
        long_tail_persona="a startup founder evaluating AI agents in 2026",
        schema_types=("SoftwareApplication",),
        keywords=("llm", "machine learning", "artificial intelligence", "neural", "gpt", "claude", "ai assistant", "transformer", "fine-tune", "embeddings"),
        strong_keywords=("ai agent", "ai agents", "agentic", "ai coding", "coding agent", "ai coding agent", "ai engineer", "autonomous agent", "ai software engineer"),
        path_hints=("/agents", "/models", "/playground"),
    ),
    CategoryDef(
        slug="dev-tools",
        label="developer tools",
        descriptor="developer tool",
        persona="software engineers",
        use_case="ship and run software faster",
        long_tail_persona="a backend engineer at a fast-growing startup",
        schema_types=("SoftwareApplication", "SoftwareSourceCode"),
        keywords=("api", "sdk", "developer", "developers", "open source", "github", "cli", "library", "framework", "infrastructure", "devops", "deploy", "ci/cd", "self-hosted"),
        path_hints=("/docs", "/api", "/developers", "/sdk", "/cli", "/changelog"),
    ),
    CategoryDef(
        slug="fintech-payments",
        label="payments / fintech",
        descriptor="payment processor",
        persona="developers building checkout",
        use_case="accept credit cards online",
        long_tail_persona="a SaaS founder handling subscription billing",
        schema_types=("FinancialService", "FinancialProduct"),
        keywords=("payment", "payments", "checkout", "billing", "invoice", "subscriptions", "fintech", "credit card", "payout", "merchant", "acquirer"),
        strong_keywords=(
            "payment processing",
            "payment infrastructure",
            "online payments",
            "process payments",
            "financial infrastructure",
            "payment gateway",
            "subscription billing",
        ),
        path_hints=("/payments", "/billing", "/checkout", "/payouts"),
    ),
    CategoryDef(
        slug="ecommerce-platform",
        label="ecommerce platform",
        descriptor="ecommerce platform",
        persona="people starting an online store",
        use_case="launch an online store",
        long_tail_persona="a creator launching a DTC brand",
        schema_types=("Store", "OnlineStore", "Service"),
        keywords=("ecommerce", "online store", "sell online", "merchant", "marketplace", "storefront", "shopify", "woocommerce"),
        path_hints=("/sell", "/start", "/themes", "/storefront"),
    ),
    CategoryDef(
        slug="ecommerce-store",
        label="online store",
        descriptor="brand",
        persona="people shopping online",
        use_case="buy something online",
        long_tail_persona="a customer comparing options for a specific product",
        schema_types=("Store", "Product", "ProductGroup", "OfferCatalog"),
        keywords=("buy", "cart", "shipping", "free shipping", "men's", "women's", "kids", "sale", "new arrivals"),
        strong_keywords=("add to cart", "free returns", "product details"),
        path_hints=("/shop", "/products", "/cart", "/collections", "/store", "/p/", "/pd/", "/cat/", "/category/", "/department/", "/rooms/"),
    ),
    CategoryDef(
        slug="design-creative",
        label="design / creative tools",
        descriptor="design tool",
        persona="designers",
        use_case="design a product, brand, or interface",
        long_tail_persona="a product designer collaborating with engineers",
        schema_types=("SoftwareApplication",),
        # Avoid generic "design" / "designer" — too noisy on furniture and decor
        # sites. Anchor on terms that are specific to the design-software space.
        keywords=("figma", "sketch app", "illustrator", "photoshop", "canvas", "vector", "ux/ui"),
        strong_keywords=("design tool", "prototyping tool", "wireframing tool", "design system", "ui design tool"),
        path_hints=("/templates", "/community", "/plugins"),
    ),
    CategoryDef(
        slug="b2b-saas",
        label="B2B SaaS",
        descriptor="SaaS tool",
        persona="business teams",
        use_case="solve a business workflow with software",
        long_tail_persona="an operations lead at a 50-person company",
        # Don't list generic "Organization" — too many sites declare it.
        schema_types=("SoftwareApplication", "Service"),
        keywords=("crm", "marketing automation", "workflow", "team", "enterprise", "dashboard", "reporting"),
        strong_keywords=("saas platform", "team collaboration", "all-in-one platform"),
        path_hints=("/pricing", "/customers", "/case-studies", "/enterprise", "/security"),
    ),
    CategoryDef(
        slug="consumer-saas",
        label="consumer software",
        descriptor="app",
        persona="people who want to be more productive",
        use_case="organize my work and life",
        long_tail_persona="a knowledge worker juggling many projects",
        schema_types=("SoftwareApplication", "MobileApplication"),
        keywords=("app", "notes", "calendar", "todo", "tasks", "personal", "productivity", "habit", "journal"),
        path_hints=("/download", "/ios", "/android"),
    ),
    CategoryDef(
        slug="news-media",
        label="news / media",
        descriptor="news source",
        persona="readers looking for trustworthy news",
        use_case="follow breaking news in my industry",
        long_tail_persona="a reader looking for original reporting on a specific topic",
        schema_types=("NewsArticle", "NewsMediaOrganization", "Newspaper", "Magazine"),
        keywords=("news", "latest", "reporter", "editor", "magazine", "newspaper", "press", "headlines", "exclusive"),
        path_hints=("/news", "/latest", "/section", "/world", "/politics"),
    ),
    CategoryDef(
        slug="healthcare",
        label="healthcare",
        descriptor="healthcare provider",
        persona="patients and caregivers",
        use_case="find trustworthy medical information",
        long_tail_persona="someone researching treatment options for a specific condition",
        schema_types=("MedicalOrganization", "Hospital", "Physician", "MedicalClinic"),
        keywords=("health", "medical", "clinic", "hospital", "patient", "doctor", "treatment", "symptoms", "diagnosis", "wellness"),
        path_hints=("/patients", "/find-a-doctor", "/conditions", "/treatments"),
    ),
    CategoryDef(
        slug="education",
        label="education",
        descriptor="course or program",
        persona="learners",
        use_case="learn a new skill",
        long_tail_persona="a working professional looking to upskill on weekends",
        schema_types=("EducationalOrganization", "School", "University", "Course"),
        keywords=("course", "courses", "learn", "tutorial", "bootcamp", "university", "school", "students", "curriculum", "degree"),
        path_hints=("/courses", "/students", "/admissions", "/programs", "/learn"),
    ),
    CategoryDef(
        slug="restaurants-local",
        label="restaurant / local business",
        descriptor="local business",
        persona="people nearby looking for a place to go",
        use_case="find a great spot near me",
        long_tail_persona="a visitor planning a meal in a new neighborhood",
        schema_types=("Restaurant", "LocalBusiness", "FoodEstablishment", "Bar", "Cafe"),
        keywords=("menu", "reservations", "open today", "delivery", "takeout", "hours", "location", "near me"),
        path_hints=("/menu", "/reservations", "/locations", "/hours"),
    ),
    CategoryDef(
        slug="agency-consulting",
        label="agency / consulting",
        descriptor="agency",
        persona="teams hiring an outside partner",
        use_case="hire help with a specific project",
        long_tail_persona="a marketing lead vetting agencies for a rebrand",
        schema_types=("ProfessionalService",),
        # Avoid generic "/services" path — Airbnb and many marketplaces use it
        # for a different meaning. Keep agency hints to high-specificity terms.
        keywords=("consulting", "consultancy", "our clients"),
        strong_keywords=("our work", "case studies", "our agency", "branding agency", "design agency", "marketing agency"),
        path_hints=("/work", "/case-studies", "/clients", "/our-work"),
    ),
    CategoryDef(
        slug="nonprofit",
        label="non-profit",
        descriptor="organization",
        persona="donors and supporters",
        use_case="support a cause I care about",
        long_tail_persona="someone choosing where to direct a year-end donation",
        # NGO is the specific schema type; plain "Organization" is too generic.
        schema_types=("NGO", "GovernmentOrganization"),
        keywords=("donate", "donation", "nonprofit", "non-profit", "charity", "volunteer", "mission", "impact"),
        path_hints=("/donate", "/give", "/volunteer", "/impact"),
    ),
    CategoryDef(
        slug="generic",
        label="this site",
        descriptor="site",
        persona="people in your industry",
        use_case="find what you offer",
        long_tail_persona="someone evaluating you against alternatives",
    ),
)


_CATEGORY_BY_SLUG: dict[str, CategoryDef] = {c.slug: c for c in CATEGORY_DEFS}


def list_categories() -> list[dict]:
    """Public list of selectable categories for the UI override dropdown."""
    return [{"slug": c.slug, "label": c.label} for c in CATEGORY_DEFS]


def get_category(slug: str) -> CategoryDef:
    return _CATEGORY_BY_SLUG.get(slug, _CATEGORY_BY_SLUG["generic"])


# ---- Detection -------------------------------------------------------------


@dataclass
class _DetectionScore:
    cat: CategoryDef
    score: float = 0.0
    signals: list[str] = field(default_factory=list)


def _walk_jsonld_types(blocks: list[dict]) -> list[str]:
    """Flatten every @type string in the JSON-LD graph."""
    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str):
                out.append(t)
            elif isinstance(t, list):
                out.extend(x for x in t if isinstance(x, str))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for block in blocks:
        walk(block)
    return out


_BANG_PAREN = re.compile(r"[\(\)\[\]\{\}!]")


def _normalize_text(s: str) -> str:
    return _BANG_PAREN.sub(" ", s.lower())


def _meta_text(soup: BeautifulSoup) -> str:
    """Concatenate title + meta description + og tags + visible H1/H2 hero copy.

    H1/H2 matter because some sites (Devin, single-product DTC stores) keep
    meta descriptions almost empty but state the category clearly in the hero
    headline.
    """
    parts: list[str] = []
    title = soup.find("title")
    if title:
        parts.append(title.get_text(" ", strip=True) or "")
    m = soup.find("meta", attrs={"name": "description"})
    if isinstance(m, Tag) and m.get("content"):
        parts.append(str(m["content"]))
    for prop in ("og:description", "og:title", "og:site_name", "twitter:description"):
        m2 = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if isinstance(m2, Tag) and m2.get("content"):
            parts.append(str(m2["content"]))
    # First few headings — usually the hero / value-prop copy.
    for tag_name in ("h1", "h2"):
        for el in soup.find_all(tag_name, limit=4):
            txt = el.get_text(" ", strip=True)
            if txt:
                parts.append(txt[:240])  # cap each heading so a giant blob can't dominate
    return _normalize_text(" ".join(parts))


def _nav_paths(soup: BeautifulSoup) -> set[str]:
    """Collect lowercase URL paths of every <a href> on the page."""
    paths: set[str] = set()
    for a in soup.find_all("a"):
        href = a.get("href")
        if not isinstance(href, str):
            continue
        # Strip scheme/host and query/fragment, keep just /path.
        href = href.split("?", 1)[0].split("#", 1)[0].strip().lower()
        if href.startswith(("http://", "https://")):
            # Drop scheme + host
            after = href.split("://", 1)[1]
            slash = after.find("/")
            href = after[slash:] if slash >= 0 else "/"
        if href.startswith("/"):
            paths.add(href)
    return paths


def detect_category(
    home_html: str,
    jsonld_blocks: list[dict],
    host: str,
) -> DetectedCategory:
    """Pick the best-fit category for this site.

    Priority of signals (highest weight first):
      * Schema.org @type — explicit and authoritative when present
      * Path hints in nav (e.g. ``/menu`` → restaurants, ``/docs`` → dev-tools)
      * Title / meta-description keyword density against the lexicon
    """
    soup = BeautifulSoup(home_html or "", "html.parser")
    schema_types = _walk_jsonld_types(jsonld_blocks)
    schema_types_lc = {t.lower() for t in schema_types}
    nav_paths = _nav_paths(soup)
    text = _meta_text(soup)

    scores: list[_DetectionScore] = [_DetectionScore(c) for c in CATEGORY_DEFS if c.slug != "generic"]

    for s in scores:
        for st in s.cat.schema_types:
            if st.lower() in schema_types_lc:
                s.score += 6.0
                s.signals.append(f"schema.org @type={st}")
                break  # one schema match is enough; don't double-count
        for hint in s.cat.path_hints:
            # Match either an exact path, a path prefixed with hint/, or
            # (for trailing-slash hints like '/p/') any path containing it.
            hit = (
                hint in nav_paths
                or any(p.startswith(hint + "/") for p in nav_paths)
                or (hint.endswith("/") and any(hint in p for p in nav_paths))
            )
            if hit:
                s.score += 2.0
                s.signals.append(f"nav link: {hint}")
        for kw in s.cat.strong_keywords:
            if kw in text:
                s.score += 3.0
                s.signals.append(f"strong keyword: '{kw}'")
        for kw in s.cat.keywords:
            if kw in text:
                s.score += 1.0
                s.signals.append(f"keyword: '{kw}'")

    # Pick best; require a meaningful score to avoid false confidence on
    # near-empty or unparseable pages.
    scores.sort(key=lambda x: x.score, reverse=True)
    if not scores or scores[0].score < 2.0:
        return DetectedCategory(
            slug="generic",
            label=_CATEGORY_BY_SLUG["generic"].label,
            persona=_CATEGORY_BY_SLUG["generic"].persona,
            confidence="low",
            signals=["no strong category signals"],
        )

    best = scores[0]
    second = scores[1].score if len(scores) > 1 else 0.0
    if best.score >= 8 and best.score >= second + 4:
        confidence = "high"
    elif best.score >= 4:
        confidence = "medium"
    else:
        confidence = "low"
    return DetectedCategory(
        slug=best.cat.slug,
        label=best.cat.label,
        persona=best.cat.persona,
        confidence=confidence,
        signals=best.signals[:6],  # truncate so the UI tooltip stays readable
    )


# ---- Brand-name extraction (small reuse of llms_suggest's logic) -----------


_GENERIC_TITLE_WORDS = {"home", "homepage", "welcome", "page", "untitled"}


def extract_brand(home_html: str, host: str) -> str:
    """Best-effort brand name. Mirrors llms_suggest._extract_name signal order."""
    soup = BeautifulSoup(home_html or "", "html.parser")
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if isinstance(og, Tag) and og.get("content"):
        cand = " ".join(str(og["content"]).split()).strip()
        if cand:
            return cand

    # Schema.org Organization / WebSite name
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_jsonld_nodes(data):
            if not isinstance(node, dict):
                continue
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(
                isinstance(x, str)
                and x in {"Organization", "Corporation", "WebSite", "LocalBusiness"}
                for x in types
            ):
                name = node.get("name")
                if isinstance(name, str):
                    cand = " ".join(name.split()).strip()
                    if cand:
                        return cand

    title_tag = soup.find("title")
    if title_tag:
        title_text = (title_tag.get_text() or "").strip()
        # Take the shortest pipe/dash segment if one looks brandy.
        segments = re.split(r"\s*[\|\u2014\u2013\-]\s*", title_text)
        segments = [s.strip() for s in segments if s.strip()]
        if segments:
            shortest = min(segments, key=len)
            if (
                shortest
                and len(shortest) <= 40
                and shortest.lower() not in _GENERIC_TITLE_WORDS
            ):
                return shortest

    # Fallback: humanize the host.
    base = host.removeprefix("www.").split(".", 1)[0]
    return base[:1].upper() + base[1:]


def _iter_jsonld_nodes(data):
    """Yield every dict in a parsed JSON-LD block, including @graph entries."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
        return
    if isinstance(data, dict):
        if isinstance(data.get("@graph"), list):
            for item in data["@graph"]:
                yield from _iter_jsonld_nodes(item)
        yield data


# ---- Prompt generation -----------------------------------------------------


def _deep_links(prompt_text: str) -> PromptDeepLinks:
    """Build deep links that pre-fill the prompt on each AI search platform.

    URLs verified against each platform's documented (or de-facto) URL params:
      * ChatGPT: ``chatgpt.com/?q=…``
      * Perplexity: ``perplexity.ai/search?q=…``
      * Claude: ``claude.ai/new?q=…``
      * Google AI Mode: ``google.com/search?q=…&udm=50``
    """
    q = quote_plus(prompt_text)
    return PromptDeepLinks(
        chatgpt=f"https://chatgpt.com/?q={q}",
        perplexity=f"https://www.perplexity.ai/search?q={q}",
        claude=f"https://claude.ai/new?q={q}",
        google_ai=f"https://www.google.com/search?q={q}&udm=50",
    )


def _indef(noun: str) -> str:
    """Return 'a' or 'an' for ``noun`` based on its first sound."""
    n = noun.strip().lower()
    return "an" if n and n[0] in "aeiou" else "a"


def generate_prompts(category_slug: str, brand: str) -> list[TestPrompt]:
    """Render the four prompt angles for the given category."""
    cat = get_category(category_slug)
    brand = (brand or "").strip() or "this site"
    art = _indef(cat.descriptor)

    prompts: list[tuple[str, str, str, str]] = [
        (
            "category",
            "Category recommendation",
            f"What's the best {cat.descriptor} for {cat.persona} in 2026?",
            "Tests whether AI engines list you among top picks for your category.",
        ),
        (
            "use_case",
            "Use-case discovery",
            f"How do I {cat.use_case}?",
            "Tests whether you appear when a user searches for the problem you solve, not your name.",
        ),
        (
            "comparison",
            "Comparison",
            f"{brand} vs alternatives — which is best for {cat.persona}?",
            "Tests how AI engines describe you head-to-head with rivals.",
        ),
        (
            "long_tail",
            "Long-tail / persona",
            f"Recommend {art} {cat.descriptor} for {cat.long_tail_persona}.",
            "Tests whether you surface for specific persona queries — usually the highest-intent traffic.",
        ),
    ]
    return [
        TestPrompt(
            angle=angle,
            label=label,
            text=text,
            rationale=rationale,
            deep_links=_deep_links(text),
        )
        for angle, label, text, rationale in prompts
    ]


def build_test_prompts_bundle(
    home_html: str,
    jsonld_blocks: list[dict],
    host: str,
    category_override: str | None = None,
) -> TestPromptsBundle:
    """Top-level helper — what main.py calls during a scan."""
    if category_override and category_override in _CATEGORY_BY_SLUG:
        cat = get_category(category_override)
        detected = DetectedCategory(
            slug=cat.slug,
            label=cat.label,
            persona=cat.persona,
            confidence="high",
            signals=["user override"],
        )
    else:
        detected = detect_category(home_html, jsonld_blocks, host)

    brand = extract_brand(home_html, host)
    prompts = generate_prompts(detected.slug, brand)
    return TestPromptsBundle(
        detected_category=detected,
        brand=brand,
        prompts=prompts,
        all_categories=list_categories(),
    )
