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
    label: str  # display name shown in UI
    descriptor: str  # noun phrase for prompts: "payment processor"
    persona: str  # default persona: "developers integrating payments"
    use_case: str  # what users come to this category to do
    long_tail_persona: str  # specific persona for long-tail prompt
    schema_types: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()  # general title/meta/H1 terms (weight 1.0)
    strong_keywords: tuple[str, ...] = ()  # high-confidence terms (weight 3.0)
    path_hints: tuple[str, ...] = ()  # nav-link paths that suggest this vertical


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
        keywords=(
            "llm",
            "machine learning",
            "artificial intelligence",
            "neural",
            "gpt",
            "claude",
            "ai assistant",
            "transformer",
            "fine-tune",
            "embeddings",
        ),
        strong_keywords=(
            "ai agent",
            "ai agents",
            "agentic",
            "ai coding",
            "coding agent",
            "ai coding agent",
            "ai engineer",
            "autonomous agent",
            "ai software engineer",
        ),
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
        keywords=(
            "api",
            "sdk",
            "developer",
            "developers",
            "open source",
            "github",
            "cli",
            "library",
            "framework",
            "infrastructure",
            "devops",
            "deploy",
            "ci/cd",
            "self-hosted",
        ),
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
        keywords=(
            "payment",
            "payments",
            "checkout",
            "billing",
            "invoice",
            "subscriptions",
            "fintech",
            "credit card",
            "payout",
            "merchant",
            "acquirer",
        ),
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
        keywords=(
            "ecommerce",
            "online store",
            "sell online",
            "merchant",
            "marketplace",
            "storefront",
            "shopify",
            "woocommerce",
        ),
        path_hints=("/sell", "/start", "/themes", "/storefront"),
    ),
    CategoryDef(
        slug="apparel-sportswear",
        label="sports apparel / footwear",
        descriptor="athletic brand",
        persona="people shopping for sports gear",
        use_case="find athletic shoes or apparel that fit my training",
        long_tail_persona="a runner training for a marathon",
        # Brand schema is common, but we anchor on category-specific terminology
        # so we don't fight against any random store with a Brand JSON-LD block.
        keywords=(
            "running",
            "training",
            "athletes",
            "athletic",
            "sneakers",
            "footwear",
            "basketball",
            "soccer",
            "tennis",
            "marathon",
        ),
        strong_keywords=(
            "athletic apparel",
            "running shoes",
            "training shoes",
            "basketball shoes",
            "performance gear",
            "just do it",
            "world's athletes",
        ),
        path_hints=(
            "/running",
            "/basketball",
            "/training",
            "/baseball",
            "/soccer",
            "/tennis",
            "/footwear",
            "/men",
            "/women",
            "/kids/shoes",
        ),
    ),
    CategoryDef(
        slug="ecommerce-store",
        label="online store",
        descriptor="brand",
        persona="people shopping online",
        use_case="buy something online",
        long_tail_persona="a customer comparing options for a specific product",
        schema_types=("Store", "Product", "ProductGroup", "OfferCatalog"),
        keywords=(
            "buy",
            "cart",
            "shipping",
            "free shipping",
            "men's",
            "women's",
            "kids",
            "sale",
            "new arrivals",
        ),
        strong_keywords=("add to cart", "free returns", "product details"),
        path_hints=(
            "/shop",
            "/products",
            "/cart",
            "/collections",
            "/p/",
            "/pd/",
            "/cat/",
            "/category/",
            "/department/",
            "/rooms/",
        ),
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
        strong_keywords=(
            "design tool",
            "prototyping tool",
            "wireframing tool",
            "design system",
            "ui design tool",
        ),
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
        keywords=(
            "crm",
            "marketing automation",
            "workflow",
            "team",
            "enterprise",
            "dashboard",
            "reporting",
        ),
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
        keywords=(
            "app",
            "notes",
            "calendar",
            "todo",
            "tasks",
            "personal",
            "productivity",
            "habit",
            "journal",
        ),
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
        keywords=(
            "news",
            "latest",
            "reporter",
            "editor",
            "magazine",
            "newspaper",
            "press",
            "headlines",
            "exclusive",
        ),
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
        keywords=(
            "health",
            "medical",
            "clinic",
            "hospital",
            "patient",
            "doctor",
            "treatment",
            "symptoms",
            "diagnosis",
            "wellness",
        ),
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
        keywords=(
            "course",
            "courses",
            "learn",
            "tutorial",
            "bootcamp",
            "university",
            "school",
            "students",
            "curriculum",
            "degree",
        ),
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
        keywords=(
            "menu",
            "reservations",
            "open today",
            "delivery",
            "takeout",
            "hours",
            "location",
            "near me",
        ),
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
        strong_keywords=(
            "our work",
            "case studies",
            "our agency",
            "branding agency",
            "design agency",
            "marketing agency",
        ),
        path_hints=("/work", "/case-studies", "/clients", "/our-work"),
    ),
    CategoryDef(
        slug="travel-hospitality",
        label="travel / hospitality",
        descriptor="travel option",
        persona="travelers planning a trip",
        use_case="find a place to stay for an upcoming trip",
        long_tail_persona="a family planning a vacation in a new city",
        schema_types=("LodgingBusiness", "Hotel", "TravelAgency", "Resort"),
        keywords=(
            "vacation",
            "rentals",
            "hotel",
            "hotels",
            "stays",
            "trip",
            "travel",
            "booking",
            "reservation",
            "destinations",
            "flight",
            "flights",
            "cabins",
        ),
        strong_keywords=(
            "vacation rentals",
            "beach houses",
            "book a stay",
            "places to stay",
            "unique homes",
            "vacation rental",
            "guest favorites",
        ),
        path_hints=(
            "/homes",
            "/stays",
            "/hotels",
            "/rooms",
            "/destinations",
            "/experiences",
            "/flights",
            "/trips",
            "/host",
            "/rentals",
            "/cabins",
        ),
    ),
    CategoryDef(
        slug="entertainment-streaming",
        label="streaming / entertainment",
        descriptor="streaming service",
        persona="people choosing what to watch",
        use_case="find a streaming service for movies and shows",
        long_tail_persona="a household trying to consolidate streaming subscriptions",
        schema_types=("VideoOnDemandService", "BroadcastService"),
        keywords=(
            "watch",
            "stream",
            "streaming",
            "movies",
            "shows",
            "series",
            "originals",
            "episodes",
            "tv shows",
            "documentary",
            "documentaries",
        ),
        strong_keywords=(
            "watch tv shows online",
            "watch movies online",
            "stream movies",
            "streaming service",
            "originals and exclusives",
            "watch tv shows",
        ),
        path_hints=("/watch", "/browse/genre", "/shows", "/movies", "/originals"),
    ),
    CategoryDef(
        slug="automotive",
        label="automotive / vehicles",
        descriptor="vehicle",
        persona="people shopping for a new vehicle",
        use_case="research a car before buying",
        long_tail_persona="a buyer comparing electric vehicles in 2026",
        schema_types=("Vehicle", "Car", "AutoDealer", "AutoManufacturer"),
        keywords=("vehicle", "vehicles", "suv", "sedan", "truck", "dealer", "horsepower", "mpg"),
        strong_keywords=(
            "electric vehicle",
            "build your own",
            "test drive",
            "explore models",
            "all-electric",
            "all electric",
        ),
        path_hints=("/models", "/inventory", "/build", "/test-drive", "/dealers", "/electric"),
    ),
    CategoryDef(
        slug="real-estate",
        label="real estate",
        descriptor="real estate site",
        persona="home buyers and renters",
        use_case="search for homes for sale or rent",
        long_tail_persona="a first-time buyer in a competitive market",
        schema_types=("RealEstateAgent", "RealEstateListing"),
        keywords=(
            "for sale",
            "for rent",
            "listings",
            "mortgage",
            "neighborhoods",
            "buyers",
            "sellers",
            "apartments",
        ),
        strong_keywords=("homes for sale", "real estate", "find a home", "list your home"),
        path_hints=("/homes", "/listings", "/buy", "/rent", "/sell", "/agents", "/mortgage"),
    ),
    CategoryDef(
        slug="cpg-food-beverage",
        label="consumer brand (food / beverage / household)",
        descriptor="brand",
        persona="people interested in the brand or its products",
        use_case="learn about a consumer brand or its product lineup",
        long_tail_persona="a shopper researching the brand behind a product they use",
        schema_types=("Brand",),
        keywords=(
            "flavors",
            "ingredients",
            "responsibility",
            "sustainability",
            "history",
            "heritage",
        ),
        strong_keywords=("our company", "our brands", "global brands", "global iconic brands"),
        path_hints=("/brands", "/our-brands", "/sustainability", "/about-us", "/our-company"),
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
        keywords=(
            "donate",
            "donation",
            "nonprofit",
            "non-profit",
            "charity",
            "volunteer",
            "mission",
            "impact",
        ),
        path_hints=("/donate", "/give", "/volunteer", "/impact"),
    ),
    CategoryDef(
        slug="live-entertainment",
        label="live entertainment",
        descriptor="live entertainer",
        persona="event planners and hosts looking to book talent",
        use_case="book a band, DJ, or performer for an event",
        long_tail_persona="a couple booking a live act for their wedding reception",
        # No ``MusicArtist`` schema type exists, but ``MusicGroup`` and
        # ``PerformingGroup`` are both standard for bands / ensembles.
        schema_types=("MusicGroup", "PerformingGroup"),
        keywords=(
            "band",
            "dj",
            "musician",
            "musicians",
            "singer",
            "vocalist",
            "performer",
            "comedian",
            "magician",
            "entertainer",
            "setlist",
            "ensemble",
        ),
        strong_keywords=(
            "live music",
            "live band",
            "wedding band",
            "event entertainment",
            "hire a dj",
            "book a band",
            "private events",
            "corporate events",
        ),
        path_hints=("/book", "/events", "/performances", "/setlist", "/shows", "/calendar"),
    ),
    CategoryDef(
        slug="wedding-services",
        label="wedding services",
        descriptor="wedding service",
        persona="couples planning a wedding",
        use_case="plan and book vendors for a wedding",
        long_tail_persona="a bride finalizing vendors six months before her wedding",
        # Schema doesn't have a wedding-specific type. We keep the list empty
        # and lean on strong keywords + path hints — wedding sites rarely
        # use schema beyond ``LocalBusiness`` (which is too generic to claim).
        schema_types=(),
        keywords=(
            "wedding",
            "weddings",
            "bride",
            "groom",
            "bridal",
            "ceremony",
            "reception",
            "elopement",
        ),
        strong_keywords=(
            "wedding planning",
            "wedding planner",
            "wedding venue",
            "wedding vendor",
            "wedding photographer",
            "wedding florist",
            "wedding caterer",
            "wedding day",
            "destination wedding",
        ),
        path_hints=("/weddings", "/bridal", "/wedding", "/ceremonies", "/receptions"),
    ),
    CategoryDef(
        slug="fitness-wellness",
        label="fitness / wellness",
        descriptor="fitness studio",
        persona="people pursuing fitness or wellness goals",
        use_case="find a gym, studio, or trainer to reach a fitness goal",
        long_tail_persona="someone restarting a workout routine after a long break",
        schema_types=("ExerciseGym", "SportsActivityLocation", "HealthClub"),
        keywords=(
            "gym",
            "fitness",
            "workout",
            "trainer",
            "training",
            "yoga",
            "pilates",
            "crossfit",
            "spin",
            "barre",
            "membership",
            "memberships",
        ),
        strong_keywords=(
            "personal trainer",
            "personal training",
            "group classes",
            "fitness studio",
            "yoga studio",
            "book a class",
            "free trial",
            "class schedule",
        ),
        path_hints=("/classes", "/memberships", "/trainers", "/schedule", "/book-a-class"),
    ),
    CategoryDef(
        slug="home-services",
        label="home services",
        descriptor="home-services pro",
        persona="homeowners needing repair or maintenance",
        use_case="find a licensed pro to fix something at home",
        long_tail_persona="a homeowner with an emergency leak after hours",
        # Schema.org has rich ``HomeAndConstructionBusiness`` subtypes — using
        # them lets a Plumber / HVACBusiness / Electrician page classify
        # cleanly without competing against the generic ``LocalBusiness``.
        schema_types=(
            "HomeAndConstructionBusiness",
            "Plumber",
            "HVACBusiness",
            "Electrician",
            "RoofingContractor",
            "HousePainter",
            "MovingCompany",
            "Locksmith",
            "GeneralContractor",
        ),
        keywords=(
            "plumbing",
            "plumber",
            "electrician",
            "hvac",
            "heating",
            "cooling",
            "roofing",
            "landscaping",
            "cleaning",
            "handyman",
            "contractor",
            "renovation",
            "remodeling",
        ),
        strong_keywords=(
            "emergency service",
            "licensed and insured",
            "24/7 service",
            "free estimate",
            "request a quote",
            "same-day service",
            "service area",
        ),
        # Avoid bare ``/services`` — it collides with marketplace meanings
        # (Airbnb, similar). Prefer suffixed variants and quote/estimate paths.
        path_hints=("/estimate", "/quote", "/book", "/service-areas", "/our-services"),
    ),
    CategoryDef(
        slug="legal-services",
        label="legal services",
        descriptor="law firm",
        persona="people needing legal help",
        use_case="hire a lawyer for a specific legal matter",
        long_tail_persona="someone evaluating attorneys after an accident",
        schema_types=("LegalService", "Attorney"),
        keywords=(
            "attorney",
            "attorneys",
            "lawyer",
            "lawyers",
            "law firm",
            "litigation",
            "counsel",
            "paralegal",
            "esq",
            "legal",
        ),
        strong_keywords=(
            "free consultation",
            "personal injury",
            "criminal defense",
            "family law",
            "estate planning",
            "practice areas",
            "our attorneys",
            "case results",
            "no fee unless we win",
        ),
        path_hints=("/attorneys", "/lawyers", "/practice-areas", "/case-results", "/results"),
    ),
    CategoryDef(
        slug="photography-video",
        label="photography / video",
        descriptor="photographer",
        persona="people hiring a photographer or videographer",
        use_case="hire a photographer for a session, event, or shoot",
        long_tail_persona="a couple choosing a photographer for their engagement shoot",
        schema_types=("ProfessionalService",),
        keywords=(
            "photographer",
            "photography",
            "videographer",
            "videography",
            "portrait",
            "portraits",
            "headshots",
            "photoshoot",
            "gallery",
            "galleries",
        ),
        strong_keywords=(
            "portrait photography",
            "wedding photography",
            "event photography",
            "commercial photography",
            "book a session",
            "photo gallery",
            "view portfolio",
        ),
        path_hints=("/portfolio", "/galleries", "/gallery", "/sessions", "/portraits"),
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

    scores: list[_DetectionScore] = [
        _DetectionScore(c) for c in CATEGORY_DEFS if c.slug != "generic"
    ]

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
    # near-empty or unparseable pages. Threshold of 3.5 means a single weak
    # nav-link match (2.0) on its own won't classify — we need either two
    # corroborating signals, one schema match (6.0), one strong keyword
    # (3.0) + at least one corroboration, or a path + a couple of keywords.
    scores.sort(key=lambda x: x.score, reverse=True)
    if not scores or scores[0].score < 3.5:
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
    elif best.score >= 5:
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


# ---- Brand-name extraction --------------------------------------------------


_GENERIC_TITLE_WORDS = {"home", "homepage", "welcome", "page", "untitled"}

# TLD-like suffixes that some brands tack onto their og:site_name (e.g.
# "Nike.com", "Booking.com"). We strip these only when they're a *trailing*
# fragment after a single brandy token, never inside the brand string.
_TLD_SUFFIXES = {
    ".com",
    ".co",
    ".io",
    ".ai",
    ".org",
    ".net",
    ".us",
    ".gov",
    ".tv",
    ".app",
    ".dev",
    ".xyz",
    ".store",
    ".shop",
}


def _strip_tld_suffix(brand: str) -> str:
    """Remove a trailing TLD-like fragment from a brand string.

    ``"Nike.com"`` → ``"Nike"``. Leaves ``"IO Interactive"`` and
    ``"Stripe"`` alone — only strips when the suffix is a recognized TLD-ish
    token attached to the very end with a dot.
    """
    if not brand:
        return brand
    s = brand.strip()
    # Greedy match against any of our suffixes case-insensitively.
    lower = s.lower()
    for suf in _TLD_SUFFIXES:
        if lower.endswith(suf) and len(s) > len(suf) + 1:
            stripped = s[: -len(suf)].rstrip()
            # Don't strip if it would leave nothing meaningful.
            if stripped:
                return stripped
    return s


def extract_brand(home_html: str, host: str) -> str:
    """Best-effort brand name. Prefers og:site_name > schema.org Organization name > cleaned <title>."""
    soup = BeautifulSoup(home_html or "", "html.parser")
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if isinstance(og, Tag) and og.get("content"):
        cand = " ".join(str(og["content"]).split()).strip()
        if cand:
            return _strip_tld_suffix(cand)

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
                        return _strip_tld_suffix(cand)

    title_tag = soup.find("title")
    if title_tag:
        title_text = (title_tag.get_text() or "").strip()
        # Take the shortest pipe/dash segment if one looks brandy.
        segments = re.split(r"\s*[\|\u2014\u2013\-]\s*", title_text)
        segments = [s.strip() for s in segments if s.strip()]
        if segments:
            shortest = min(segments, key=len)
            if shortest and len(shortest) <= 40 and shortest.lower() not in _GENERIC_TITLE_WORDS:
                return _strip_tld_suffix(shortest)

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


# ---- Page-signal extraction (topics for prompt interpolation) --------------


# Generic / boilerplate phrases we never want to feed into a prompt. These are
# the chrome of every site (auth, legal, footer links) and would make every
# prompt sound like every other prompt.
_TOPIC_STOPLIST = {
    "home",
    "homepage",
    "about",
    "about us",
    "contact",
    "contact us",
    "contact sales",
    "talk to sales",
    "login",
    "log in",
    "sign in",
    "sign up",
    "signup",
    "register",
    "search",
    "help",
    "support",
    "privacy",
    "privacy policy",
    "terms",
    "terms of use",
    "terms of service",
    "careers",
    "press",
    "blog",
    "newsletter",
    "subscribe",
    "gift cards",
    "dark mode",
    "menu",
    "cart",
    "my account",
    "sitemap",
    "accessibility",
    "cookies",
    "cookie policy",
    "feedback",
    "events",
    "frequently asked questions",
    "faq",
    "company",
    "our team",
    "team",
    "investors",
    "more",
    "see more",
    "view all",
    "show more",
    "learn more",
    "discover",
    "shop now",
    "buy now",
    "spotlight",
    "trending now",
    "new",
    "all",
    "today",
    "now",
    "categories",
    "category",
    "request a demo",
    "book a demo",
    "schedule a demo",
    "get a demo",
    "get the report",
    "get the data",
    "get started",
    "get started for free",
    "start free trial",
    "free trial",
    "start now",
    "try it free",
    "try for free",
    "watch the demo",
    "view demo",
    "join now",
    "download now",
    "learn how",
    "find out more",
    "view pricing",
    # A11y skip-links — invisible to sighted users but render as anchor text
    # the topic extractor would otherwise pick up.
    "skip to content",
    "skip to main content",
    "skip navigation",
    "skip to footer",
    "skip to navigation",
    # Language-picker labels (Shopify, Wikipedia, etc. surface these as
    # heading-weighted text via i18n widgets).
    "english",
    "español",
    "spanish",
    "français",
    "french",
    "deutsch",
    "german",
    "italiano",
    "italian",
    "português",
    "portuguese",
    "日本語",
    "japanese",
    "中文",
    "chinese",
    "한국어",
    "korean",
    "русский",
    "russian",
    "العربية",
    "arabic",
    "हिन्दी",
    "hindi",
    "polski",
    "polish",
    "nederlands",
    "dutch",
    "türkçe",
    "turkish",
}

# Filler first-words that produce useless action-only fragments. A topic that
# starts with one of these is almost always a CTA ("Get the report", "Talk to
# sales", "Book a demo") and adds noise to the long-tail prompt.
_TOPIC_BAD_FIRST_WORDS = {
    "click",
    "tap",
    "copy",
    "open",
    "read",
    "go",
    "view",
    "see",
    "check",
    "get",
    "talk",
    "request",
    "book",
    "schedule",
    "join",
    "start",
    "try",
    "explore",
    "browse",
    "find",
    "learn",
    "discover",
    "shop",
    "buy",
    "watch",
    "download",
    "install",
    "subscribe",
    "register",
    "sign",
    "log",
    "contact",
    "become",
    "create",
    "make",
    "build",
    "stay",
    "save",
    "share",
}

_TOPIC_PHRASE_LEN_MIN = 4
_TOPIC_PHRASE_LEN_MAX = 50

# "What's New", ", new", ", beta" badges on nav links that get concatenated
# into the text content. We strip these as a trailing suffix only.
_TOPIC_BADGE_SUFFIX = re.compile(
    r"\s*,?\s+(new|beta|soon|coming soon|preview|alpha)$", re.IGNORECASE
)


def _normalize_topic(s: str) -> str:
    """Clean up a candidate topic string: collapse repeated tokens and strip
    badge suffixes that nav-link rendering frequently glues on.

    Real-world example: Airbnb's "Experiences" nav link with a "NEW" badge
    renders as the text ``"Experiences Experiences, NEW"``. We collapse the
    duplication and strip the badge so the topic is just ``"experiences"``.
    """
    s = s.strip()
    # Collapse internal whitespace to a single space.
    s = re.sub(r"\s+", " ", s)
    # Remove trailing badge suffixes (case-insensitive).
    s = _TOPIC_BADGE_SUFFIX.sub("", s, count=1)
    # Dedupe consecutive identical tokens. Comparison strips trailing
    # punctuation so "Experiences" and "Experiences," collapse together.
    tokens = s.split(" ")
    deduped: list[str] = []
    for tok in tokens:
        cmp = re.sub(r"[^a-zA-Z0-9]+$", "", tok).lower()
        prev_cmp = re.sub(r"[^a-zA-Z0-9]+$", "", deduped[-1]).lower() if deduped else ""
        if cmp and cmp == prev_cmp:
            continue
        deduped.append(tok)
    out = " ".join(deduped).strip()
    # Trim trailing punctuation so prompts don't get awkward periods/commas
    # ("…focused on flexible solutions for every business model..").
    return out.rstrip(",;:.! ")


def _topic_passes_filters(s: str) -> bool:
    if not (_TOPIC_PHRASE_LEN_MIN <= len(s) <= _TOPIC_PHRASE_LEN_MAX):
        return False
    if s in _TOPIC_STOPLIST:
        return False
    first = s.split()[0] if s else ""
    if first in _TOPIC_BAD_FIRST_WORDS:
        return False
    # Require at least one substantive word (3+ alpha chars) — drops "10 new",
    # ":", emoji-only headings, etc.
    if not re.search(r"[a-z]{3,}", s):
        return False
    return True


def extract_page_topics(
    home_html: str,
    max_topics: int = 4,
    exclude_brand: str | None = None,
) -> list[str]:
    """Return up to N candidate topic phrases from H1/H2/H3 + nav anchor text.

    Used to interpolate site-specific phrases into prompt templates so the
    output reads contextual ("…focused on vacation rentals") rather than
    generic ("…focused on this category"). Phrases are normalized lower-case,
    deduplicated, filtered against a boilerplate stoplist, and ranked by a
    blend of frequency (more mentions = more central) and specificity (longer
    phrases break ties since they carry more signal than single words).

    ``exclude_brand`` filters out any phrase containing the brand name as a
    substring — Airbnb's homepage repeats "Homes on Airbnb" three times, but
    the long-tail prompt already mentions Airbnb, so it would read awkwardly
    as "…focused on homes on airbnb."
    """
    soup = BeautifulSoup(home_html or "", "html.parser")
    # We weight headings far more than nav anchors so that a site's footer/header
    # ("Help Center", "Become a host") repeating 5+ times can't outrank a single
    # H2 that captures the actual product ("Vacation Rentals"). Headings are
    # editorial; nav is mostly chrome.
    candidates: list[tuple[str, int]] = []

    # Headings — most authoritative source of "what this site is about". H1
    # is usually the hero; H2/H3 are section labels.
    heading_weight = {"h1": 5, "h2": 4, "h3": 3}
    for tag, weight in heading_weight.items():
        for el in soup.find_all(tag, limit=12):
            t = el.get_text(" ", strip=True)
            if t:
                candidates.append((t, weight))

    # Nav anchor text — captures category labels like "Stays" / "Experiences"
    # on Airbnb that don't appear in any heading. Cap by length so we skip
    # legal/footer copy and ad-style "Save 20% on your first order!" CTAs.
    for a in soup.find_all("a", limit=120):
        t = a.get_text(" ", strip=True)
        if t and 3 <= len(t) <= 40:
            candidates.append((t, 1))

    brand_lc = (exclude_brand or "").strip().lower()

    weighted: dict[str, int] = {}
    for raw, weight in candidates:
        norm = _normalize_topic(raw).lower()
        if not _topic_passes_filters(norm):
            continue
        if brand_lc and brand_lc in norm:
            continue
        weighted[norm] = weighted.get(norm, 0) + weight

    ranked = sorted(weighted.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [t for t, _ in ranked[:max_topics]]


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


def generate_prompts(
    category_slug: str,
    brand: str,
    topics: list[str] | None = None,
) -> list[TestPrompt]:
    """Render the four prompt angles for the given category.

    ``topics`` are site-specific topic phrases extracted from the homepage
    (see :func:`extract_page_topics`). When supplied, the strongest topic is
    woven into the long-tail prompt so it reads site-specific instead of
    template-y. We deliberately don't interpolate into ``use_case`` or
    ``category`` — those are deliberately written as universal queries an AI
    engine would actually receive from a generic shopper, and stuffing
    site-specific phrasing into them would defeat the test (we want to see
    if the engine cites the user's site for a *neutral* query). The
    long-tail prompt, by contrast, is meant to be specific — that's where
    topic interpolation adds signal.
    """
    cat = get_category(category_slug)
    brand = (brand or "").strip() or "this site"
    art = _indef(cat.descriptor)
    primary_topic = (topics or [None])[0] if (topics and category_slug != "generic") else None

    if primary_topic:
        long_tail_text = (
            f"Recommend {art} {cat.descriptor} for {cat.long_tail_persona} "
            f"focused on {primary_topic}."
        )
    else:
        long_tail_text = f"Recommend {art} {cat.descriptor} for {cat.long_tail_persona}."

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
            long_tail_text,
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
    topics = extract_page_topics(home_html, exclude_brand=brand)
    prompts = generate_prompts(detected.slug, brand, topics=topics)
    return TestPromptsBundle(
        detected_category=detected,
        brand=brand,
        prompts=prompts,
        all_categories=list_categories(),
    )
