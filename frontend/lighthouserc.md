# Lighthouse CI config rationale

This doc explains every audit disabled in `lighthouserc.json`. The default
`lighthouse:recommended` preset enables ~80 individual audit assertions on
top of the 4 category scores. Many don't apply to a static SPA SEO shell
that consumes a backend hosted on a different origin. Each disable below
has a one-line justification — if you re-enable one, expect it to fail
unless that justification has stopped being true.

## Category-score thresholds (enforced)

| Category | Threshold | Notes |
|---|---|---|
| Performance | ≥ 0.80 | Throttled-mobile, 4G; desktop scores are much higher |
| Accessibility | ≥ 0.90 | Real a11y signal — tightening to 0.95 once stable |
| Best Practices | ≥ 0.90 | Catches DOM XSS patterns, console errors, etc. |
| SEO | ≥ 0.95 | Highest bar — this is our brand promise |
| PWA | off | Not building a PWA |

## Disabled audits (with rationale)

### Image audits — no image-based LCP / hero images in the SPA shell

- **`prioritize-lcp-image`** — returns NaN when no image LCP exists; static
  shell's LCP is a text block
- **`lcp-lazy-loaded`** — same; NaN with no image LCP
- **`uses-responsive-images`** — no `<img>` tags in the static shell
- **`modern-image-formats`** — no images to convert
- **`offscreen-images`** — no images, period
- **`preload-fonts`** — we already preload the 2 critical woff2 fonts; the
  audit's heuristics don't recognise our setup

If hero / content images are ever added, re-enable all of the above and
adopt the `<picture>` + `srcset` + `loading="lazy"` pattern.

### PWA audits — `pwa` category is off

- **`service-worker`** — not registering one
- **`installable-manifest`** — manifest.json is present but the site isn't
  an installable app
- **`themed-omnibox`**, **`splash-screen`**, **`maskable-icon`**,
  **`apple-touch-icon`** — PWA install-prompt UX, not in scope
- **`content-width`** — passes anyway but the audit's heuristic flags some
  vh-based layouts

### Backend / host responsibilities — controlled via FastAPI middleware

The lhci run tests the static dist served by a static-file server.
These audits are about HTTP response headers / host config that don't
apply to the frontend bundle in isolation:

- **`csp-xss`** — CSP is set on FastAPI responses
  (`SecurityHeadersMiddleware` in `backend/app/main.py`), not on the static
  frontend; the host (Fly / devinapps / new domain) controls the static
  response CSP
- **`uses-http2`**, **`uses-rel-preconnect`**,
  **`uses-text-compression`**, **`uses-long-cache-ttl`** — all host config
- **`redirects-http`**, **`is-on-https`** — host enforces HTTPS
- **`geolocation-on-start`**, **`notification-on-start`** — we don't use
  those APIs

### CI-environment false positives

- **`valid-source-maps`** — we deliberately don't ship source maps to prod
  (Vite default: drop sourceMappingURL); exposing source paths is a leak
- **`no-vulnerable-libraries`** — noisy, uses an outdated CVE database
  (npm audit is the source of truth, see dependabot.yml)
- **`errors-in-console`** — the lhci runner serves the static dist without
  a backend; React tries to fetch `/api/...` at lhci's static server which
  has no backend → console errors that don't happen in prod
- **`inspector-issues`** — same: CI-only runtime mismatches that don't
  exist with a real backend

### Tree-shaking / minification — covered by Vite

- **`unminified-javascript`**, **`unminified-css`** — Vite minifies in prod
  by default
- **`unused-javascript`** — warn-only with `maxLength: 2`; React StrictMode
  wrappers and Router internals carry some unused code that's standard
- **`unused-css-rules`** — warn-only with `maxLength: 2`; Tailwind JIT
  tree-shakes but some preflight rules may flag

### Per-metric performance — relaxed warn thresholds

The category Performance ≥ 0.80 floor catches real overall regressions.
Individual metrics warn-only at thresholds calibrated to the observed
throttled-mobile reality:

- **`first-contentful-paint`** — warn at 0.75 (observed: 0.81)
- **`largest-contentful-paint`** — warn at 0.60 (observed: 0.69)

These should tighten 5-10% above observed floor once we have a few
baseline runs in CI.

## What stays enforced

The 70+ audits not listed above are still asserted at their preset
defaults. Notable ones:

- **`tap-targets`** — interactive targets ≥ 48×48 CSS px on mobile
- **`color-contrast`** — WCAG AA contrast ratios
- **`image-alt`**, **`label`**, **`link-name`**, **`button-name`** — a11y
  accessible-name checks
- **`label-content-name-mismatch`** — visible text ≠ aria-label
  (caught the home-link bug we fixed)
- **`meta-viewport`** — mobile viewport meta
- **`no-document-write`** — anti-pattern
- **`bf-cache`** — back/forward cache compatibility
- **`heading-order`** — h1 → h2 → h3 hierarchy
- **`html-lang-valid`**, **`document-title`**, **`meta-description`**,
  **`canonical`**, **`robots-txt`**, **`structured-data`** — SEO basics

## When to revisit this config

- Image-based hero is added → re-enable the image audits
- PWA support is added → re-enable PWA audits + flip the category
- Backend moves to the same origin as the frontend → reconsider CSP / host
  audits
- After 5+ baseline runs → tighten per-metric performance warn thresholds
