# Changelog

All notable changes to AgentGEOScore are documented here. The format
loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **Production domain cut over to `agentgeoscore.com`** (frontend, Cloudflare Pages) + `api.agentgeoscore.com` (backend, Fly). The legacy `dist-olcivbch.devinapps.com` preview URL is gone from the codebase entirely. (#45)
- Build-time guard in `vite.config.ts` now throws if either `VITE_FRONTEND_ORIGIN` or `VITE_API_BASE` is missing on production builds — protects against silent same-origin-fetch failures when host env vars aren't set. (#45)
- CORS allowlist default now includes `https://www.agentgeoscore.com` so the `www` subdomain isn't rejected. (#45)

### Added

- `og:image:secure_url` meta paired with `og:image` for Facebook OG Debugger hygiene. (#45)
- `frontend/vite-plugins/origin-and-freshness.ts` — new `DEFAULT_API_BASE` + `rewriteApiBase` helper. The OG image / Twitter image / SoftwareApplication JSON-LD `image` URLs in `index.html` are now rewritten at build time via `VITE_API_BASE`, matching how the frontend origin is already rewritten via `VITE_FRONTEND_ORIGIN`. (#45)
- `scripts/precheck-cutover.sh` — pre-merge gate script. Runs DNS resolution, TLS/reachability, OG endpoint (content-type + size + 1200×630 dimension check), and `/share` HTML validation. Exits non-zero if any prod endpoint fails its check — meant to catch the deploy-ordering hazard where DNS / Fly cert / OG endpoint aren't all live yet. (#45)
- `frontend/src/test/no-legacy-urls.test.ts` — regression guard that `git grep`s tracked source files for the legacy preview URL. Prevents accidental reintroduction. (#45)

## [0.1.0] – 2026-05-10 — Initial public release

This is the version that shipped to https://agentgeoscore.com/
when the repo went public (initially hosted at the devinapps preview
domain; cut over to the custom domain in #45). Everything below merged
through PRs #1–#28.

### Scoring engine

- 5-category, 40-check GEO scoring with weighted overall score (0–100,
  graded A–F). Categories: Agent Access (25%), Discoverability (20%),
  Structured Data (20%), Citation Probe (20%), Content Clarity (15%).
- Evidence-backed checks: AI bot allowlists, sitemap reachability,
  HTTPS, response speed, canonical tags, JSON-LD validity per
  `schema.org` type, OpenGraph + Twitter Card coverage, semantic HTML,
  H1 uniqueness, fan-out questions in subheads, byline + author Person
  schema, freshness signals.
- 8 evidence-backed gap scanners ported from the GEO literature:
  - **#1 SPA / JS-rendering detection** — flag when content is hidden
    behind a client render that AI crawlers won't execute.
  - **#2 Multipage sample depth** — sample sitemap URLs and score the
    deepest content page against the same checks.
  - **#3 Competitor baseline** — `/api/compare` runs the same pipeline
    against 1–3 competitor domains in parallel; 1-hour LRU cache.
  - **#4 Content depth (Princeton GEO 2024)** — score against the
    1,500–2,500-word "long-tail content" band.
  - **#5 JSON-LD validator-conformance** — verify required props per
    schema.org `@type` (Article, Organization, FAQPage, Recipe, etc.).
  - **#6 Internal linking** — anchor-text quality, orphan-page detection.
  - **#7 Core Web Vitals (PageSpeed Insights)** — real CrUX p75 LCP /
    CLS / INP.
  - **#8 hreflang / international SEO** — return-link symmetry, ISO
    code validity, x-default presence.

### Citation probes

Live LLM and search-engine queries that ask "do AI engines actually
cite this site?" Each probe fails open (returns `skip`) when its key
is missing.

- **Brave Search** — proxy for Perplexity's index.
- **Gemini** (Google AI with native web access) — Search Grounding.
- **Groq** (`llama-3.3-70b`) — proxy for "is this site in the
  open-weights training corpus?"
- **Mistral** — optional EU-region LLM coverage.
- **Duck.ai** (GPT-4o-mini + Claude) — DuckDuckGo's chat layer; key-free.

### Test prompts

- 27 vertical categories with hand-curated lexicons (schema_types,
  keywords, strong_keywords, path_hints) — auto-detection plus a
  user-override dropdown.
- 4 prompts per scan (category recommendation, use-case discovery,
  comparison, long-tail persona) with deep-link buttons to ChatGPT,
  Perplexity, Claude, and Google AI Mode.
- Optional LLM polish pass via Groq llama-3.3-70b rewrites the
  templated prompts into natural English.

### UI

- React + Vite + Tailwind, editorial paper-card aesthetic (warm
  surfaces, Fraunces display, ink-on-paper).
- Dynamic OG share cards rendered as PNGs by Pillow (per-report and
  brand variants).
- `/share/:domain` route for crawler-friendly social embeds.
- Competitor side-by-side card with score deltas.
- Off-page signals card (high-leverage levers we can't auto-score —
  documented with citations to the underlying research).

### Hardening (PR #28)

- **SSRF guard** ([`backend/app/url_safety.py`](backend/app/url_safety.py)) —
  every outbound URL (and every redirect hop) validated against
  private / loopback / link-local / multicast / reserved / CGNAT IPs.
- **Per-IP rate limits** via slowapi: `/api/scan` 10/min, `/api/compare`
  5/min, `/api/test-prompts` 30/min, `/api/og` 60/min, plus 120/min
  global default.
- **Bounded responses** — fetcher caps body size at 5 MiB, follows at
  most 5 redirects.
- **Tight CORS** — defaults to configured `FRONTEND_ORIGIN` plus
  localhost dev origins.
- **Defence-in-depth headers** — HSTS (1y, includeSubDomains),
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, strict
  CSP (`default-src 'none'`), `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy` denying camera/mic/geo/FLoC.
- **Non-root container** — Dockerfile drops to uid 10001.
- **Vulnerability disclosure** — [`SECURITY.md`](SECURITY.md), threat
  model, known limitations (DNS rebinding), coordinated-disclosure
  timeline.

### Project hygiene

- MIT license.
- Contributor Covenant 2.1.
- Issue + PR templates.
- `backend/.env.example` with every env var documented (free-tier
  signup links per provider).
- 500 backend tests + 23 frontend tests + Playwright e2e against the
  prod backend.

[Unreleased]: https://github.com/LindaHaviv/agentgeoscore/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/LindaHaviv/agentgeoscore/releases/tag/v0.1.0
