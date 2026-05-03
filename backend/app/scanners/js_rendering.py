"""Heuristic detector for client-rendered SPAs that AI crawlers may not see.

The existing ``text_extractable`` check (in ``content_clarity``) flags pages
with very little visible text but conflates two genuinely-different problems:

  1. Thin content — a brochure landing page with 30 words.
  2. Client-rendered SPA — a Next.js / React / Vue / Angular shell whose
     real content lives in a JS bundle the AI crawler may or may not
     execute.

This module is the second one. It looks for SPA *shape*: a single empty
root mount-point (a div whose id is ``root`` / ``app`` / ``__next`` / etc.),
a framework bundle reference, and very little server-rendered visible
text. When all three line up, mainstream AI crawlers in non-browse mode
(GPTBot, ClaudeBot, PerplexityBot, ChatGPT-User without the agent loop) will
see almost nothing useful, even though a human with a browser sees a full
page.

Why heuristic and not Playwright:
- Adding a real headless browser to the production image would add ~300 MB,
  cold-start cost, and a class of flakiness we don't have today.
- A heuristic correctly classifies the long tail of common patterns
  (Next.js SSG vs CSR, Nuxt with `__NUXT__` payload, Vue+Vite, etc.) at
  zero runtime cost.
- We document the tradeoff in the check ``detail`` so the user knows the
  diagnosis is heuristic rather than authoritative.

References:
- ChatGPT bots and JS execution: https://platform.openai.com/docs/bots
- Bing/Bingbot rendering policy: https://blogs.bing.com/webmaster/2024/04/23/Bingbot-Rendering-Engine-Update
- Google's "two waves of indexing" on JS-heavy sites:
  https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..models import CheckResult, CheckStatus

# Element selectors that a *single* SPA mount point typically uses. The
# pattern is "one near-empty <div> at the top of <body> with a known id /
# attribute, and basically nothing else server-rendered."
_SPA_ROOT_SELECTORS: tuple[tuple[str, dict[str, str]], ...] = (
    ("div", {"id": "root"}),       # Create React App, Vite-React, generic
    ("div", {"id": "app"}),        # Vue 2/3, generic
    ("div", {"id": "__next"}),     # Next.js
    ("div", {"id": "__nuxt"}),     # Nuxt
    ("div", {"id": "___gatsby"}),  # Gatsby
    ("div", {"id": "svelte"}),     # SvelteKit (older)
    ("div", {"id": "sapper"}),     # Sapper (legacy)
    ("div", {"id": "main"}),       # Common, weaker signal
    ("app-root", {}),              # Angular default selector
    ("router-outlet", {}),         # Angular routing shell
)

# Substrings (case-insensitive) anywhere in the HTML that strongly imply a
# JS framework is responsible for rendering. We check the raw HTML to catch
# both ``<script src="…/react.production.min.js">`` and inline references
# inside hydration payloads.
_FRAMEWORK_FINGERPRINTS: tuple[str, ...] = (
    "/_next/static/",
    "__NEXT_DATA__",
    "/_nuxt/",
    "__NUXT__",
    "data-reactroot",
    "react-dom",
    "react.production.min.js",
    "react.development.js",
    "vue.global.js",
    "vue.runtime",
    "/runtime.js",       # Angular default chunk name (weaker — paired w/ shell)
    "/polyfills",
    "ng-version",
    "svelte-",
    "solid-js",
    "gatsby-app",
    "astro-island",
    "remix-run",
    "_buildManifest",
)

# A site that "looks like an SPA" but renders this much visible text is
# almost certainly fine for AI crawlers. Picked to comfortably accommodate
# Next.js SSG / Nuxt SSR / Astro-with-islands sites whose homepages render
# the full hero + nav + footer copy. Below this we want to look harder.
_TEXT_OK_THRESHOLD = 800

# Below this, even a server-rendered site is suspicious — content too thin
# to be useful to an AI engine. A real SPA shell is usually under ~200 chars
# of visible text (just the <noscript> fallback + nav skeleton).
_TEXT_SHELL_THRESHOLD = 200


def check_js_rendering(html: str) -> list[CheckResult]:
    """Return a single CheckResult diagnosing client-rendered-only homepages.

    The check is deliberately *one* result (not a category) so it can sit
    alongside the existing Discoverability checks without complicating the
    score model. Weight is moderate (2.0) — failing it doesn't tank the
    score on its own, but it stacks with ``text_extractable`` so a fully
    JS-only site visibly loses points in two places.
    """
    if not html or not html.strip():
        return [
            CheckResult(
                id="js_rendering",
                label="Server-rendered HTML",
                status=CheckStatus.SKIP,
                score=0.0,
                weight=0.0,
                detail="No homepage HTML available — skipping client-render check.",
            )
        ]

    soup = BeautifulSoup(html, "lxml")

    # Strip script/style/noscript before measuring "visible" text. We
    # intentionally keep <noscript> blocks *out* of the visible-text count
    # because AI crawlers in non-rendering mode do see them, but they
    # represent a fallback message to humans, not the real content. If we
    # counted them, sites would game the heuristic by stuffing prose into
    # <noscript>.
    body = soup.find("body")
    if body is None:
        # Pages with no <body> are weird; fall through with whole-doc text.
        text_source = soup
    else:
        text_source = body

    # Make a copy so we don't mutate ``soup`` (the caller may reuse it).
    text_copy = BeautifulSoup(str(text_source), "lxml")
    for tag in text_copy(["script", "style", "noscript", "template"]):
        tag.decompose()
    visible_text = text_copy.get_text(" ", strip=True)
    visible_chars = len(visible_text)

    # Detect a single near-empty SPA root mount point. We require that the
    # matched element is *actually empty* (or near-empty) of static text
    # to avoid false-positives on, say, a Vue ``app`` div that contains a
    # fully server-rendered tree (Vue with SSR, Astro hydration islands).
    spa_shell_id: str | None = None
    if body is not None:
        for tag_name, attrs in _SPA_ROOT_SELECTORS:
            for el in body.find_all(tag_name, attrs=attrs, limit=4):
                # `el.get_text` skips nested tags' text content. If the
                # element renders < 80 chars of static text, it's a shell.
                inner_text = (el.get_text(" ", strip=True) or "")
                if len(inner_text) < 80:
                    spa_shell_id = attrs.get("id") or tag_name
                    break
            if spa_shell_id:
                break

    # Detect framework presence anywhere in the raw HTML. Lower-cased once
    # so ``in`` checks are cheap.
    html_lower = html.lower()
    fingerprint_hits = [fp for fp in _FRAMEWORK_FINGERPRINTS if fp.lower() in html_lower]
    has_framework = bool(fingerprint_hits)

    # Decision tree. We prefer to be *forgiving* — false-positives erode
    # trust faster than false-negatives on this particular check.
    framework_label = _summarize_fingerprints(fingerprint_hits)
    evidence = {
        "visible_chars": visible_chars,
        "spa_shell": spa_shell_id,
        "framework_fingerprints": fingerprint_hits[:8],
    }

    if visible_chars >= _TEXT_OK_THRESHOLD:
        # Plenty of server-rendered text. Doesn't matter if the site is
        # also a Next.js SSG with a __next root — the content is in the
        # initial HTML and AI crawlers will see it.
        return [
            CheckResult(
                id="js_rendering",
                label="Server-rendered HTML",
                status=CheckStatus.PASS,
                score=1.0,
                weight=2.0,
                detail=(
                    f"Homepage ships {visible_chars:,} characters of visible text "
                    "in the initial HTML — AI crawlers without JS execution "
                    "(GPTBot, ClaudeBot, PerplexityBot in fetch mode) can read it."
                ),
                evidence=evidence,
            )
        ]

    if spa_shell_id and visible_chars < _TEXT_SHELL_THRESHOLD and has_framework:
        # Classic client-rendered SPA pattern: empty root + framework bundle
        # + almost no visible text. AI crawlers without JS exec see nothing.
        return [
            CheckResult(
                id="js_rendering",
                label="Server-rendered HTML",
                status=CheckStatus.FAIL,
                score=0.1,
                weight=2.0,
                detail=(
                    f"Homepage looks client-rendered ({framework_label}, "
                    f"{visible_chars} chars of visible text). AI crawlers "
                    "without JS execution will see almost nothing. "
                    "Render the initial HTML server-side (SSR), pre-render "
                    "(SSG / ISR), or use a service like Prerender.io. "
                    "Heuristic — confirm by fetching with `curl` and checking "
                    "for your hero copy."
                ),
                evidence=evidence,
            )
        ]

    if spa_shell_id and visible_chars < _TEXT_OK_THRESHOLD:
        # Has the SPA shape but at least some prose. Could be a partially
        # prerendered SSG site whose dynamic content (pricing, search
        # results, gated copy) lives in JS — or a thinly-prerendered SPA.
        return [
            CheckResult(
                id="js_rendering",
                label="Server-rendered HTML",
                status=CheckStatus.WARN,
                score=0.55,
                weight=2.0,
                detail=(
                    f"Homepage looks like a partially-rendered SPA "
                    f"({framework_label}, {visible_chars} chars of visible text "
                    f"in <body>, mount point `#{spa_shell_id}`). The visible "
                    "text is below 800 chars — anything dynamic (pricing, "
                    "search, personalised copy) probably won't be seen by AI "
                    "crawlers without JS execution. Heuristic — verify with "
                    "`curl -s <url> | wc -c` and inspect the HTML."
                ),
                evidence=evidence,
            )
        ]

    if visible_chars < _TEXT_SHELL_THRESHOLD:
        # No SPA shell detected, but still very little text. We don't fail
        # because that case is already caught by ``text_extractable`` in
        # content_clarity — warn quietly without double-penalising.
        return [
            CheckResult(
                id="js_rendering",
                label="Server-rendered HTML",
                status=CheckStatus.WARN,
                score=0.6,
                weight=2.0,
                detail=(
                    f"Homepage server-renders only {visible_chars} chars of "
                    "visible text. Doesn't look like a JS framework shell, "
                    "but the page may still be too thin for AI engines to "
                    "extract a useful answer."
                ),
                evidence=evidence,
            )
        ]

    return [
        CheckResult(
            id="js_rendering",
            label="Server-rendered HTML",
            status=CheckStatus.PASS,
            score=1.0,
            weight=2.0,
            detail=(
                f"Homepage server-renders {visible_chars} chars of visible "
                "text. AI crawlers without JS execution can read it."
            ),
            evidence=evidence,
        )
    ]


def _summarize_fingerprints(hits: list[str]) -> str:
    """Map raw framework hits to a human label for the check ``detail``."""
    if not hits:
        return "no JS framework detected"
    families: list[str] = []
    joined = " ".join(hits).lower()
    if "_next" in joined or "__next_data__" in joined or "_buildmanifest" in joined:
        families.append("Next.js")
    if "_nuxt" in joined or "__nuxt__" in joined:
        families.append("Nuxt")
    if any(re.search(r"react", h) for h in hits) or "data-reactroot" in joined:
        families.append("React")
    if "vue" in joined:
        families.append("Vue")
    if "ng-version" in joined or "/polyfills" in joined or "/runtime.js" in joined:
        families.append("Angular")
    if "svelte" in joined:
        families.append("Svelte")
    if "solid-js" in joined:
        families.append("Solid")
    if "gatsby" in joined:
        families.append("Gatsby")
    if "remix-run" in joined:
        families.append("Remix")
    if "astro-island" in joined:
        families.append("Astro")
    # Dedupe while preserving order, then format.
    seen: set[str] = set()
    families = [f for f in families if not (f in seen or seen.add(f))]
    if not families:
        return "JS framework bundle detected"
    if len(families) == 1:
        return f"{families[0]} bundle detected"
    return f"{'+'.join(families)} bundles detected"
