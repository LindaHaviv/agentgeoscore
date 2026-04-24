"""Fix library — map failing/warning checks to rich, actionable Fix objects.

Each check_id has an (optional) entry here that describes:
- the severity / effort of the fix
- expected score_lift (rough estimate — shown to users for triage)
- a copy-pasteable snippet where one makes sense
- a docs URL that explains the "why"

Checks without an entry still produce a generic Fix derived from the
CheckResult's label + detail, so the list stays comprehensive.
"""
from __future__ import annotations

from typing import Literal, TypedDict

from .models import CategoryResult, CheckResult, CheckStatus, Fix

Severity = Literal["critical", "important", "minor"]
Effort = Literal["low", "medium", "high"]


class FixTemplate(TypedDict, total=False):
    severity_on_fail: Severity
    severity_on_warn: Severity
    effort: Effort
    score_lift_fail: int
    score_lift_warn: int
    title_fail: str
    title_warn: str
    snippet: str
    snippet_language: str
    docs_url: str


# Snippets — standalone constants so tests can assert they exist / are non-empty.
LLMS_TXT_SNIPPET = """# <Your site name>
> One-line summary of what your site is and who it's for.

A paragraph of optional context that gives an LLM enough grounding to talk
about your product accurately.

## Key pages
- [/about](/about): who we are
- [/docs](/docs): developer documentation
- [/pricing](/pricing): plans and pricing
"""

ROBOTS_ALLOW_SNIPPET = """# Explicitly allow AI crawlers
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

Sitemap: https://example.com/sitemap.xml
"""

JSONLD_ORG_SNIPPET = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Your Org",
  "url": "https://example.com",
  "logo": "https://example.com/logo.png",
  "sameAs": [
    "https://twitter.com/yourorg",
    "https://www.linkedin.com/company/yourorg"
  ]
}
</script>"""

OG_META_SNIPPET = """<meta property="og:title" content="Your page title" />
<meta property="og:description" content="One-sentence summary of this page." />
<meta property="og:type" content="website" />
<meta property="og:url" content="https://example.com/" />
<meta property="og:image" content="https://example.com/og-image.png" />
<meta name="twitter:card" content="summary_large_image" />"""

CANONICAL_SNIPPET = '<link rel="canonical" href="https://example.com/current-page" />'

META_DESC_SNIPPET = (
    '<meta name="description" content="A 50–170 character summary of this page '
    'that describes what visitors (and AI agents) will find here." />'
)


FIX_LIBRARY: dict[str, FixTemplate] = {
    # Discoverability ---------------------------------------------------------
    "llms_txt": {
        "severity_on_fail": "critical",
        "severity_on_warn": "important",
        "effort": "low",
        "score_lift_fail": 8,
        "score_lift_warn": 3,
        "title_fail": "Publish an llms.txt at your site root",
        "title_warn": "Fix your llms.txt to match the llmstxt.org spec",
        "snippet": LLMS_TXT_SNIPPET,
        "snippet_language": "markdown",
        "docs_url": "https://llmstxt.org/",
    },
    "llms_full_txt": {
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_warn": 1,
        "title_warn": "Add an llms-full.txt with your full site content in Markdown",
        "docs_url": "https://llmstxt.org/",
    },
    "sitemap": {
        "severity_on_fail": "important",
        "effort": "low",
        "score_lift_fail": 4,
        "title_fail": "Publish a sitemap.xml and declare it in robots.txt",
        "snippet": "Sitemap: https://example.com/sitemap.xml",
        "snippet_language": "text",
        "docs_url": "https://www.sitemaps.org/protocol.html",
    },
    "https": {
        "severity_on_fail": "critical",
        "effort": "medium",
        "score_lift_fail": 5,
        "title_fail": "Serve your site over HTTPS",
        "docs_url": "https://letsencrypt.org/getting-started/",
    },
    "canonical": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 2,
        "title_warn": "Declare a canonical URL on your homepage",
        "snippet": CANONICAL_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://developers.google.com/search/docs/crawling-indexing/canonicalization",
    },
    # Agent Access ------------------------------------------------------------
    "robots_exists": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 2,
        "title_warn": "Add a robots.txt with explicit AI-bot allows",
        "snippet": ROBOTS_ALLOW_SNIPPET,
        "snippet_language": "text",
        "docs_url": "https://platform.openai.com/docs/bots",
    },
    # Structured Data --------------------------------------------------------
    "jsonld_present": {
        "severity_on_fail": "critical",
        "effort": "low",
        "score_lift_fail": 8,
        "title_fail": "Add schema.org JSON-LD to your homepage",
        "snippet": JSONLD_ORG_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://schema.org/docs/gs.html",
    },
    "jsonld_rich": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 2,
        "title_fail": "Use a rich schema.org @type (Organization, Article, Product, FAQPage…)",
        "title_warn": "Expand your schema.org coverage with more rich types",
        "snippet": JSONLD_ORG_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://developers.google.com/search/docs/appearance/structured-data/search-gallery",
    },
    "opengraph": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Add OpenGraph meta tags to your homepage",
        "title_warn": "Fill in the missing OpenGraph properties",
        "snippet": OG_META_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://ogp.me/",
    },
    "twitter_cards": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 1,
        "title_warn": "Add a Twitter card meta tag",
        "snippet": '<meta name="twitter:card" content="summary_large_image" />',
        "snippet_language": "html",
        "docs_url": "https://developer.twitter.com/en/docs/twitter-for-websites/cards/overview/summary-card-with-large-image",
    },
    # Content Clarity --------------------------------------------------------
    "title_quality": {
        "severity_on_fail": "critical",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 4,
        "score_lift_warn": 1,
        "title_fail": "Add a <title> to your homepage",
        "title_warn": "Tighten your <title> to 10–70 characters",
        "snippet": "<title>Your Product Name — One-line value proposition</title>",
        "snippet_language": "html",
    },
    "meta_description": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Add a meta description to your homepage",
        "title_warn": "Adjust your meta description to 50–170 characters",
        "snippet": META_DESC_SNIPPET,
        "snippet_language": "html",
    },
    "h1_single": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 2,
        "score_lift_warn": 1,
        "title_fail": "Add exactly one <h1> to your homepage",
        "title_warn": "Reduce to a single <h1> on your homepage",
    },
    "semantic_html": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Use semantic HTML landmarks (header, main, nav, footer, article)",
        "title_warn": "Add the missing semantic HTML landmarks",
    },
    "heading_hierarchy": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 1,
        "title_warn": "Add H2/H3 headings to structure your content",
    },
    "text_extractability": {
        "severity_on_fail": "critical",
        "effort": "high",
        "score_lift_fail": 6,
        "title_fail": "Render meaningful text server-side (avoid JS-only content)",
        "docs_url": "https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics",
    },
    # Citation probes -------------------------------------------------------
    "probe_gemini": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Earn citations from Gemini (Google Search grounding)",
        "title_warn": "Improve your citation rate in Gemini",
    },
    "probe_mistral": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Earn citations from Mistral web-search",
        "title_warn": "Improve your citation rate in Mistral",
    },
    "probe_brave": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Rank on Brave Search (powers many AI search layers)",
        "title_warn": "Improve your Brave Search ranking",
    },
    "probe_groq": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Earn citations from Groq compound (built-in web search)",
        "title_warn": "Improve your Groq citation rate",
    },
    "probe_duck_ai": {
        "severity_on_fail": "minor",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 1,
        "score_lift_warn": 1,
        "title_fail": "Earn citations from Duck.ai (GPT-4o-mini + Claude)",
        "title_warn": "Improve your Duck.ai citation rate",
    },
}


def build_fix_for_check(
    category: CategoryResult, check: CheckResult, target_host: str = ""
) -> Fix | None:
    """Build a Fix from a FAIL/WARN check. Returns None for PASS/SKIP."""
    if check.status not in (CheckStatus.FAIL, CheckStatus.WARN):
        return None

    tpl = FIX_LIBRARY.get(check.id, {})
    is_fail = check.status == CheckStatus.FAIL

    # Defaults — used when no template entry is defined for this check_id.
    default_severity: Severity = (
        "critical" if (is_fail and category.weight >= 0.2)
        else "important" if is_fail
        else "minor"
    )
    default_score_lift = max(1, round(category.weight * check.weight * 10))

    severity: Severity = (
        tpl.get("severity_on_fail", default_severity) if is_fail
        else tpl.get("severity_on_warn", "minor")
    )
    score_lift = (
        tpl.get("score_lift_fail", default_score_lift) if is_fail
        else tpl.get("score_lift_warn", max(1, default_score_lift // 2))
    )
    effort: Effort = tpl.get("effort", "low")
    title = (
        tpl.get("title_fail") if is_fail else tpl.get("title_warn")
    ) or (f"Fix: {check.label}" if is_fail else f"Improve: {check.label}")

    snippet = tpl.get("snippet")
    if snippet and target_host:
        snippet = snippet.replace("example.com", target_host)

    return Fix(
        severity=severity,
        category=category.id,
        title=title,
        detail=check.detail or "",
        score_lift=int(score_lift),
        effort=effort,
        snippet=snippet,
        snippet_language=tpl.get("snippet_language"),
        docs_url=tpl.get("docs_url"),
    )
