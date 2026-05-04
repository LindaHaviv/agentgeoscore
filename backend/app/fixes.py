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
ROBOTS_ALLOW_SNIPPET = """# Explicitly allow AI crawlers
User-agent: GPTBot
Allow: /

User-agent: ChatGPT-User
Allow: /

User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Allow: /

User-agent: Claude-Web
Allow: /

User-agent: anthropic-ai
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: Perplexity-User
Allow: /

User-agent: Google-Extended
Allow: /

User-agent: Applebot-Extended
Allow: /

User-agent: Bytespider
Allow: /

User-agent: cohere-ai
Allow: /

User-agent: Meta-ExternalAgent
Allow: /

User-agent: Amazonbot
Allow: /

User-agent: DuckAssistBot
Allow: /

User-agent: Diffbot
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

JSONLD_PERSON_SNIPPET = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Person",
  "name": "Jane Doe",
  "url": "https://example.com/author/jane-doe",
  "jobTitle": "Senior Engineer",
  "worksFor": { "@type": "Organization", "name": "Your Org" },
  "sameAs": [
    "https://www.linkedin.com/in/janedoe",
    "https://github.com/janedoe",
    "https://twitter.com/janedoe"
  ]
}
</script>"""

JSONLD_ARTICLE_DATEMODIFIED_SNIPPET = """<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "Your article title",
  "datePublished": "2025-01-15T08:00:00+00:00",
  "dateModified": "2026-04-20T10:30:00+00:00",
  "author": {
    "@type": "Person",
    "name": "Jane Doe",
    "url": "https://example.com/author/jane-doe"
  }
}
</script>
<!-- Plus a visible date line in your article body: -->
<p class="byline">
  By <a rel="author" href="/author/jane-doe">Jane Doe</a> ·
  <time datetime="2026-04-20">Updated April 2026</time>
</p>"""

BYLINE_LINK_SNIPPET = """<!-- Make every byline a real link to a credentialed author page -->
<p class="byline">
  By <a rel="author" href="/author/jane-doe">Jane Doe</a>
  · <time datetime="2026-04-20">April 20, 2026</time>
</p>

<!-- And populate /author/jane-doe with a real bio + sameAs Person schema. -->"""

OUTBOUND_CITATIONS_SNIPPET = """<!-- Cite credible external sources inline; AI engines weight these heavily. -->
<p>
  According to a
  <a href="https://www.example-research.org/study">2025 longitudinal study</a>,
  …
</p>

<!-- Or use a footnote-style reference list at the end: -->
<section aria-label="References">
  <h2>References</h2>
  <ol>
    <li><a href="https://arxiv.org/abs/2311.09735">Aggarwal et al., GEO: Generative Engine Optimization (2024)</a></li>
    <li><a href="https://schema.org/Person">schema.org Person spec</a></li>
  </ol>
</section>"""

QUOTATION_SNIPPET = """<!-- Direct quotations from credible sources are cited disproportionately. -->
<blockquote cite="https://www.example.com/source">
  <p>"The single highest-leverage technical signal that determines AI citation
  eligibility is well-formed structured data."</p>
  <footer>— <cite><a href="https://www.example.com/source">Original source</a></cite></footer>
</blockquote>"""

FANOUT_H2_SNIPPET = """<!-- Each H2/H3 question becomes a separate retrieval surface for AI engines. -->
<h2>What is generative engine optimization?</h2>
<p>One concise paragraph that answers the question directly…</p>

<h2>How is GEO different from SEO?</h2>
<p>Direct answer in 1–3 sentences, then expand…</p>

<h2>Which AI engines should I optimize for first?</h2>
<p>…</p>"""

TRANSCRIPT_SNIPPET = """<!-- Option A: <track> on a self-hosted <video> -->
<video controls>
  <source src="/media/episode-12.mp4" type="video/mp4">
  <track kind="captions" src="/media/episode-12.vtt" srclang="en" label="English">
</video>

<!-- Option B: a visible transcript section adjacent to the embed -->
<details>
  <summary>Read the full transcript</summary>
  <article>
    <p><strong>Host:</strong> Welcome back to the show…</p>
    <p><strong>Guest:</strong> Thanks for having me…</p>
  </article>
</details>"""

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

MULTIPAGE_DEPTH_SNIPPET = """<!-- Pick one or two content pages your homepage links to (blog index, /about,
     /pricing, a flagship case study) and bring them up to the same standard
     as the homepage. Below is a minimum on-page checklist for any content URL: -->

<!-- 1. A single, descriptive <h1> + a meta description -->
<title>How we cut onboarding time by 40% — Acme blog</title>
<meta name="description" content="Concrete steps Acme took to reduce new-customer onboarding from 12 days to 7." />

<!-- 2. A real dateModified, machine-readable -->
<time datetime="2026-04-20" itemprop="dateModified">April 20, 2026</time>

<!-- 3. JSON-LD describing the page (Article / AboutPage / Product / FAQPage) -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "How we cut onboarding time by 40%",
  "datePublished": "2026-04-20",
  "dateModified": "2026-04-20",
  "author": { "@type": "Person", "name": "Jane Doe", "url": "https://example.com/author/jane-doe" }
}
</script>

<!-- 4. Substantive body copy — aim for ~800-1500 words on the pages
     AI engines are most likely to surface (about / pricing / flagship posts).
     Princeton GEO 2024 found 1500-2500 words to be the cited-content sweet spot. -->"""

CONTENT_DEPTH_SNIPPET = """<!-- Princeton's GEO 2024 study found content in the 1500–2500-word band gets
     cited disproportionately by AI engines. The shape that consistently lifts
     citations: a focused intro that answers the question directly, then 4–8
     question-shaped H2s with concrete sub-answers, and a recap. -->

<article>
  <h1>How to migrate from Stripe to Square (and when not to)</h1>
  <p class="lede">
    A 1900-word, decision-focused guide. Direct answer in the first paragraph,
    then concrete steps and trade-offs.
  </p>

  <h2>Should you actually migrate?</h2>
  <p>Direct answer in 1–3 sentences, then expand…</p>

  <h2>What does the migration actually involve?</h2>
  <p>Concrete steps with code/CLI examples…</p>

  <h2>How long does it take?</h2>
  <p>Real numbers from a real migration, not estimates…</p>

  <h2>What breaks?</h2>
  <p>Specific gotchas with the workaround for each…</p>

  <h2>When should you stay?</h2>
  <p>Honest about the cases where the migration isn't worth it…</p>
</article>

<!-- Aim for: 1500–2500 words total, at least 4 H2/H3 sub-headings, every
     sub-heading phrased as a question your readers actually ask. Each H2
     answer becomes an independently-citable surface for AI engines. -->"""

JSONLD_VALIDITY_SNIPPET = """// Minimum valid JSON-LD for the four types that matter most for AI citation.
// Google Rich Results (and most AI crawlers that parse structured data) will
// silently drop a block that's missing any REQUIRED property — your schema
// effectively doesn't exist for ranking purposes.

// 1. Article / BlogPosting / NewsArticle — required: headline, author, datePublished
{
  "@context": "https://schema.org",
  "@type": "Article",
  "headline": "How we cut onboarding time by 40%",
  "author": { "@type": "Person", "name": "Jane Doe", "url": "https://example.com/author/jane-doe" },
  "datePublished": "2026-04-20",
  "dateModified": "2026-04-22",
  "image": "https://example.com/og/onboarding.jpg",
  "publisher": {
    "@type": "Organization",
    "name": "Acme",
    "logo": { "@type": "ImageObject", "url": "https://example.com/logo.png" }
  }
}

// 2. Product — required: name (plus offers/review/aggregateRating for rich results)
{
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "Acme Pro",
  "image": "https://example.com/pro.jpg",
  "description": "The flagship plan with everything included.",
  "brand": { "@type": "Brand", "name": "Acme" },
  "offers": {
    "@type": "Offer",
    "price": "99.00",
    "priceCurrency": "USD",
    "availability": "https://schema.org/InStock"
  }
}

// 3. FAQPage — required: mainEntity as non-empty list of Questions,
//    each with name + acceptedAnswer.text
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "How long does onboarding take?",
      "acceptedAnswer": { "@type": "Answer", "text": "Most teams finish in 3–5 days." }
    },
    {
      "@type": "Question",
      "name": "Do you support SSO?",
      "acceptedAnswer": { "@type": "Answer", "text": "Yes — SAML and OIDC on every plan." }
    }
  ]
}

// 4. Organization — required: name, url (plus logo for Google knowledge panels)
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "Acme",
  "url": "https://example.com",
  "logo": "https://example.com/logo.png",
  "sameAs": [
    "https://www.linkedin.com/company/acme",
    "https://twitter.com/acme"
  ]
}"""

JS_RENDERING_SNIPPET = """// Next.js — opt the route into static / server rendering
// app/page.tsx
export const dynamic = 'force-static';   // or 'force-dynamic' for SSR
export default async function Page() {
  const data = await getData();          // fetched at build- or request-time
  return <Hero data={data} />;
}

// Nuxt — useAsyncData runs server-side by default; just don't gate hero copy on
// browser-only APIs (`window`, `document`, `localStorage`).

// Plain SPA — pre-render with a build-time crawler. Vite-React example:
//   npm i -D vite-plugin-prerender
//   plugins: [prerender({ routes: ['/', '/pricing', '/about'] })]

// Last resort — proxy crawler UAs through a service like prerender.io."""


HREFLANG_SNIPPET = """<!-- Declare every language version of this page in <head>. Each version
     should declare the SAME set of alternates pointing back to all the
     others (reciprocity is enforced by Google). Always include x-default
     as the geo-fallback for users whose locale doesn't match any
     declared variant.

     Codes follow BCP 47: lang ("en"), or lang-region ("en-GB"), or
     lang-script-region ("zh-Hans-CN"). Region codes are ISO 3166-1
     alpha-2 (uppercase) — they are NOT country names. -->

<link rel="alternate" hreflang="en"        href="https://example.com/" />
<link rel="alternate" hreflang="en-GB"     href="https://example.com/uk/" />
<link rel="alternate" hreflang="fr"        href="https://example.com/fr/" />
<link rel="alternate" hreflang="fr-CA"     href="https://example.com/ca/fr/" />
<link rel="alternate" hreflang="de"        href="https://example.com/de/" />
<link rel="alternate" hreflang="es-419"    href="https://example.com/latam/" />
<link rel="alternate" hreflang="zh-Hans"   href="https://example.com/cn/" />
<link rel="alternate" hreflang="x-default" href="https://example.com/" />

<!-- Verify with:
       https://search.google.com/test/rich-results?url=...
     or Bing Webmaster Tools' International Targeting report. -->"""


CORE_WEB_VITALS_SNIPPET = """// Core Web Vitals are part of Google's ranking signal — and Google AI
// Overviews inherits from that index. Below is the Lighthouse-recommended
// stack of fixes for the three CWV metrics, ordered by typical impact.

// 1. LCP (Largest Contentful Paint) — target < 2.5s on mobile
//    Almost always: hero image / hero font is too heavy or fetched late.
//    Fixes:
//      - <link rel="preload" as="image" href="/hero.webp" fetchpriority="high">
//      - Convert hero images to AVIF/WebP, target < 100 KB above the fold.
//      - Self-host or use <link rel="preconnect"> on Google Fonts.
//      - Move blocking <script> tags out of <head> or add `defer`.
//      - For Next.js: import { Image } with priority=true on hero images.

// 2. CLS (Cumulative Layout Shift) — target < 0.10
//    Almost always: images, ads, or fonts that arrive late and shove the
//    layout. Fixes:
//      - Always specify width + height on <img> and <video>.
//      - Reserve space for ads / embeds with a fixed-size container.
//      - Use `font-display: optional` instead of `swap` to avoid late-FOIT shifts.

// 3. INP (Interaction to Next Paint) — target < 200 ms
//    Heavy main-thread work blocking input handlers. Fixes:
//      - Code-split the homepage bundle (Next.js does this automatically).
//      - Defer hydration of below-the-fold components.
//      - Use `requestIdleCallback` for non-critical work.
//      - Audit third-party scripts (analytics, chat widgets) — many are
//        synchronous and block input by 100+ ms.

// Verify with:
//   npx unlighthouse --site https://example.com
//   or PageSpeed Insights: https://pagespeed.web.dev/?url=https://example.com"""


INTERNAL_LINKING_SNIPPET = """<!-- Anchor text is a primary topic signal for AI crawlers. Replace generic
     phrases with text that describes the destination page in 2–6 words.
     The closer the anchor text matches the headline of the linked page,
     the cleaner the link graph reads to GPTBot / ClaudeBot / Perplexity. -->

<!-- Bad — tells the crawler nothing about where the link goes -->
<a href="/blog/how-we-saved-100k-on-aws">Click here</a>
<a href="/pricing">Read more</a>
<a href="/about">https://example.com/about</a>
<a href="/cases/acme"></a>

<!-- Good — anchor text describes the target -->
<a href="/blog/how-we-saved-100k-on-aws">How we cut our AWS bill by $100k</a>
<a href="/pricing">View pricing for Pro and Enterprise plans</a>
<a href="/about">About our team and mission</a>
<a href="/cases/acme">Case study: Acme reduced support tickets 40%</a>

<!-- Image-only links: give them an accessible name so the link graph
     stays readable to crawlers that don't render images. -->
<a href="/blog">
  <img src="/icons/blog.svg" alt="Engineering blog">
</a>
<!-- or -->
<a href="/blog" aria-label="Engineering blog">
  <img src="/icons/blog.svg" alt="">
</a>

<!-- Make sure your top-nav links are real <a href> elements in the
     initial HTML, not React/Vue onClick handlers. AI crawlers without
     JS execution walk the link graph from server-rendered anchors only. -->"""


FIX_LIBRARY: dict[str, FixTemplate] = {
    # Discoverability ---------------------------------------------------------
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
    "js_rendering": {
        "severity_on_fail": "critical",
        "severity_on_warn": "important",
        "effort": "high",
        "score_lift_fail": 8,
        "score_lift_warn": 4,
        "title_fail": "Server-render or pre-render your homepage HTML",
        "title_warn": "Move more of your homepage out of client-side JS",
        "snippet": JS_RENDERING_SNIPPET,
        "snippet_language": "javascript",
        "docs_url": "https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics",
    },
    "multipage_depth": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 5,
        "score_lift_warn": 2,
        "title_fail": "Bring your inner pages up to the same standard as the homepage",
        "title_warn": "Make depth consistent across your top content pages",
        "snippet": MULTIPAGE_DEPTH_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://developers.google.com/search/docs/appearance/structured-data/article",
    },
    "content_depth": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Grow your flagship content into the 1500\u20132500-word citation band",
        "title_warn": "Tighten your flagship content toward the 1500\u20132500-word band",
        "snippet": CONTENT_DEPTH_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://arxiv.org/abs/2311.09735",
    },
    "jsonld_validity": {
        "severity_on_fail": "critical",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 6,
        "score_lift_warn": 2,
        "title_fail": "Fill in required properties on your JSON-LD blocks",
        "title_warn": "Add the recommended fields to your JSON-LD blocks",
        "snippet": JSONLD_VALIDITY_SNIPPET,
        "snippet_language": "javascript",
        "docs_url": "https://developers.google.com/search/docs/appearance/structured-data",
    },
    "internal_linking": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Rewrite generic anchor text with descriptive labels",
        "title_warn": "Tighten anchor-text quality on your internal links",
        "snippet": INTERNAL_LINKING_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://developers.google.com/search/docs/crawling-indexing/links-crawlable",
    },
    "core_web_vitals": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "high",
        "score_lift_fail": 5,
        "score_lift_warn": 2,
        "title_fail": "Get LCP, CLS, and INP into Google's 'good' tier",
        "title_warn": "Push borderline Core Web Vitals into the 'good' tier",
        "snippet": CORE_WEB_VITALS_SNIPPET,
        "snippet_language": "javascript",
        "docs_url": "https://web.dev/articles/vitals",
    },
    "hreflang": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Declare hreflang alternates for every language version",
        "title_warn": "Tighten your hreflang declarations",
        "snippet": HREFLANG_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://developers.google.com/search/docs/specialized/international/localized-versions",
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
    "core_ai_bots": {
        "severity_on_fail": "critical",
        "severity_on_warn": "important",
        "effort": "low",
        "score_lift_fail": 6,
        "score_lift_warn": 3,
        "title_fail": "Unblock core AI crawlers (GPTBot, ClaudeBot, PerplexityBot)",
        "title_warn": "Unblock the remaining core AI crawlers in robots.txt",
        "snippet": ROBOTS_ALLOW_SNIPPET,
        "snippet_language": "text",
        "docs_url": "https://platform.openai.com/docs/bots",
    },
    "broad_ai_bots": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 2,
        "title_warn": "Allow the long tail of AI crawlers (Applebot-Extended, Amazonbot, …)",
        "snippet": ROBOTS_ALLOW_SNIPPET,
        "snippet_language": "text",
        "docs_url": "https://platform.openai.com/docs/bots",
    },
    "explicit_ai_rules": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 2,
        "title_warn": "Add explicit AI-bot rules to robots.txt (don't rely on wildcards)",
        "snippet": ROBOTS_ALLOW_SNIPPET,
        "snippet_language": "text",
        "docs_url": "https://platform.openai.com/docs/bots",
    },
    "ai_bots_allowed": {
        "severity_on_fail": "critical",
        "severity_on_warn": "important",
        "effort": "low",
        "score_lift_fail": 6,
        "score_lift_warn": 3,
        "title_fail": "Stop blocking AI crawlers in robots.txt",
        "title_warn": "Review your robots.txt — some AI crawlers are being blocked",
        "snippet": ROBOTS_ALLOW_SNIPPET,
        "snippet_language": "text",
        "docs_url": "https://platform.openai.com/docs/bots",
    },
    "html_lang": {
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_warn": 1,
        "title_warn": 'Declare a language on your <html> tag',
        "snippet": '<html lang="en">',
        "snippet_language": "html",
        "docs_url": "https://developer.mozilla.org/docs/Web/HTML/Global_attributes/lang",
    },
    "html_reachable": {
        "severity_on_fail": "critical",
        "effort": "medium",
        "score_lift_fail": 10,
        "title_fail": "Make your homepage reachable (current request failed)",
    },
    "response_speed": {
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_warn": 1,
        "title_warn": "Speed up your homepage TTFB (AI crawlers time out sooner than humans)",
        "docs_url": "https://web.dev/articles/ttfb",
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
    "twitter_card": {
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
    "text_extractable": {
        "severity_on_fail": "critical",
        "effort": "high",
        "score_lift_fail": 6,
        "title_fail": "Render meaningful text server-side (avoid JS-only content)",
        "docs_url": "https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics",
    },
    # Citability — Princeton GEO 2024 + E-E-A-T ----------------------------
    "outbound_citations": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 5,
        "score_lift_warn": 2,
        "title_fail": "Cite authoritative external sources inside your content",
        "title_warn": "Add a few more outbound citations to credible sources",
        "snippet": OUTBOUND_CITATIONS_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://arxiv.org/abs/2311.09735",
    },
    "statistics_density": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Add concrete numbers and statistics to your content",
        "title_warn": "Add a few more concrete statistics or data points",
        "docs_url": "https://arxiv.org/abs/2311.09735",
    },
    "quotation_density": {
        "severity_on_fail": "minor",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Quote credible sources directly using <blockquote> / <q>",
        "title_warn": "Add 1–2 more direct quotations from credible sources",
        "snippet": QUOTATION_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://arxiv.org/abs/2311.09735",
    },
    "fanout_h2_questions": {
        "severity_on_fail": "minor",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 2,
        "score_lift_warn": 1,
        "title_fail": "Phrase your H2/H3 subheads as questions readers actually ask",
        "title_warn": "Convert more H2/H3 subheads into question form",
        "snippet": FANOUT_H2_SNIPPET,
        "snippet_language": "html",
    },
    "freshness_visible_updated": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Show a visible \"Updated [date]\" line on every article",
        "title_warn": "Pair your <time> element with a human-readable \"Updated …\" line",
        "snippet": JSONLD_ARTICLE_DATEMODIFIED_SNIPPET,
        "snippet_language": "html",
    },
    "byline_links": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Link every byline to a real author page",
        "title_warn": "Improve your author byline with rel=author + a credentialed page",
        "snippet": BYLINE_LINK_SNIPPET,
        "snippet_language": "html",
    },
    "transcripts_for_media": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "medium",
        "score_lift_fail": 4,
        "score_lift_warn": 2,
        "title_fail": "Publish transcripts for your video / audio content",
        "title_warn": "Make sure every video / podcast has a discoverable transcript",
        "snippet": TRANSCRIPT_SNIPPET,
        "snippet_language": "html",
    },
    "person_schema_sameas": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Add Person JSON-LD with sameAs profile links for every author",
        "title_warn": "Add more sameAs links to your author Person schema",
        "snippet": JSONLD_PERSON_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://schema.org/Person",
    },
    "freshness_datemodified": {
        "severity_on_fail": "important",
        "severity_on_warn": "minor",
        "effort": "low",
        "score_lift_fail": 3,
        "score_lift_warn": 1,
        "title_fail": "Add datePublished + dateModified to your Article JSON-LD",
        "title_warn": "Add dateModified alongside your existing datePublished",
        "snippet": JSONLD_ARTICLE_DATEMODIFIED_SNIPPET,
        "snippet_language": "html",
        "docs_url": "https://schema.org/Article",
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
