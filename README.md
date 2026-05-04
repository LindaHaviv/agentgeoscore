# AgentGEOScore

> Generative Engine Optimization — score & grade any site for AI-agent visibility.

Paste a URL, get:

- a **0–100 score** + letter grade **A–F**
- a **category breakdown** across 5 axes (agent access, discoverability, structured data, content clarity, citation probe)
- a **ranked fix list** — what to do first, with copy-pasteable HTML snippets and expected score-lift per fix
- a **head-to-head comparison** against any competitor URL — same scoring grid, side-by-side
- **AI-search test prompts** auto-generated for the site's category, with deep-links to ChatGPT / Perplexity / Claude / Google AI Mode (so you can verify visibility in the field, not just on paper)
- a **dynamic OG share card** for every report

GEO is what SEO becomes when the readers are LLMs. This is the field study and the toolkit that came out of it.

**Live**: https://dist-olcivbch.devinapps.com/
**Backend**: https://agentgeoscore-1ei53w.fly.dev (Fly.io, region `ams`, auto-stops idle machines)

---

## What's actually measured

The score blends 5 weighted categories (40 individual checks). Each check is grounded in a citation from the AI-search literature or a documented platform behavior — none of it is vibes.

| Category          | Weight | Sample checks |
|-------------------|:------:|---------------|
| Agent Access      | 25%    | robots.txt exists, AI-bot rules, CDN AI gating, HTTPS, redirects clean |
| Discoverability   | 20%    | sitemap.xml, canonical URL, homepage TTFB, **SPA / JS-rendering detection**, **multipage depth sample** |
| Structured Data   | 20%    | JSON-LD presence, `@type` coverage, microdata, **JSON-LD validator-conformance per @type**, **hreflang correctness** |
| Content Clarity   | 15%    | title + meta length, exactly one `<h1>`, semantic landmarks, text:HTML ratio, **content-depth signal (Princeton 1500–2500 word band)**, **internal-linking quality** |
| Citation Probe    | 20%    | % of LLMs that cite the domain (Gemini, Mistral, Brave, Duck.ai, Groq) + **Core Web Vitals via PageSpeed Insights** |

**Grade bands**: A ≥ 90 · B ≥ 75 · C ≥ 60 · D ≥ 40 · else F.

The newer signals (in **bold** above) shipped as eight evidence-backed gap PRs:

1. **SPA / JS-rendering detection** — flags client-rendered shells most AI crawlers can't read
2. **Multipage sample audit** — fetches 5–10 internal pages and checks per-page signal coverage so a single polished homepage can't carry the whole score
3. **Competitor baseline** — `/api/compare` endpoint + side-by-side card
4. **Content-depth signal** — scores deepest sampled page against the Princeton 1500–2500 word band
5. **JSON-LD validator-conformance** — verifies required props per `@type` (Article needs `headline`, `Product` needs `offers`, etc.)
6. **Internal linking** — anchor-text quality + orphan detection
7. **Core Web Vitals** — Google PageSpeed Insights API integration
8. **hreflang / i18n** — return-tag pairs, x-default presence, language-tag validity

## Stack

- **Backend**: FastAPI + httpx, typed with Pydantic. Managed with [`uv`](https://docs.astral.sh/uv/).
- **Frontend**: Vite + React + TypeScript + Tailwind.
- **Tests**: `pytest` + `respx` (backend, 445 tests), `vitest` + `@testing-library/react` (frontend unit), Playwright + `@axe-core/playwright` (e2e + a11y).
- **CI**: GitHub Actions — lint, typecheck, unit, build, e2e.
- **Deploy**: Backend → Fly.io (auto-deploys on push to `main` from `Dockerfile`). Frontend → static bundle on devinapps.com (S3).

## Project layout

```
agentgeoscore/
├── backend/
│   ├── app/
│   │   ├── main.py              # POST /api/scan, POST /api/compare, GET /api/share/og
│   │   ├── models.py            # Pydantic
│   │   ├── scoring.py           # category + overall scoring, fix ranking
│   │   ├── compare.py           # head-to-head competitor scoring
│   │   ├── fixes.py             # check_id → Fix (severity / effort / score_lift / snippet)
│   │   ├── fetcher.py           # async httpx client; sets Accept-Language: en-US
│   │   ├── test_prompts.py      # category lexicon + AI-search prompt generation
│   │   ├── test_prompts_llm.py  # optional Groq llama-3.3-70b polish pass
│   │   ├── og.py                # dynamic OG share-card SVG → PNG
│   │   ├── llms_suggest.py      # llms.txt off-page recommendation generator
│   │   ├── scanners/            # agent_access, discoverability, structured_data, content_clarity
│   │   │                        # (each gap above is a scanner module)
│   │   └── probes/              # gemini, mistral, brave, duck_ai, groq, pagespeed
│   └── tests/                   # pytest + respx mocks
├── frontend/
│   ├── src/
│   │   ├── pages/               # HomePage, ReportPage, NotFoundPage
│   │   ├── components/          # URLInput, ScoreCard, CategoryBreakdown, FixList,
│   │   │                        # CompareCard, TestPromptsCard, RecommendationsCard
│   │   ├── api.ts, types.ts, brand.ts
│   └── tests/e2e/               # Playwright + axe
├── Dockerfile, fly.toml         # Fly deploy config
└── .agents/skills/deploy/       # operational runbook for redeploys
```

## Getting started

### Backend

```bash
cd backend
uv sync --extra dev
uv run --extra dev uvicorn app.main:app --reload --port 8000
```

- `GET  /api/healthz` — liveness check
- `POST /api/scan` — `{ "url": "https://stripe.com" }` → full `Report`
- `POST /api/compare` — `{ "url": "...", "competitor_url": "..." }` → side-by-side scoring
- `GET  /api/share/og?url=...` — dynamic OG share card (PNG)

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` to `http://localhost:8000` — run the backend in parallel.

## Optional API keys

All probes degrade gracefully when their key is missing — the row reports a clean "skip" with a link to the free-tier signup, and the rest of the report still renders.

| Env var               | What it powers |
|-----------------------|----------------|
| `GEMINI_API_KEY`      | Gemini 2.5-flash citation probe (Google Search grounded) |
| `MISTRAL_API_KEY`     | Mistral citation probe |
| `BRAVE_API_KEY`       | Brave Search citation probe (Perplexity-adjacent signal) |
| `GROQ_API_KEY`        | Groq `compound-beta` citation probe **and** the optional LLM-polish pass over AI-search test prompts (`llama-3.3-70b-versatile`). Polish falls back to template prompts if missing or the call fails. |
| `PAGESPEED_API_KEY`   | Core Web Vitals scanner (gap #7) — Google PageSpeed Insights |
| _(none)_              | Duck.ai best-effort browser-less probe always runs |

All keys are server-side. End users never see, paste, or know about them.

## Scripts

| Path     | Command                            | What it does                              |
|----------|------------------------------------|-------------------------------------------|
| backend  | `uv run --extra dev pytest -q`     | Unit + integration tests (`respx` mocked) |
| backend  | `uv run --extra dev ruff check .`  | Lint                                      |
| frontend | `npm run lint`                     | ESLint                                    |
| frontend | `npm run typecheck`                | `tsc --noEmit`                            |
| frontend | `npm test -- --run`                | Vitest                                    |
| frontend | `npm run build`                    | Production bundle                         |
| frontend | `npm run test:e2e`                 | Playwright + axe (auto-starts Vite)       |

## Privacy

- No scan results are persisted server-side (history tracking is on the roadmap as gap #9, opt-in and cookie-free).
- No auth, no cookies, no third-party tracking.
- Probe API keys never leave the backend.

---

## Contributing

PRs welcome. The ground rules below keep the project legible and the score honest.

### Getting set up

1. Fork + clone.
2. Backend: `cd backend && uv sync --extra dev && uv run --extra dev uvicorn app.main:app --reload --port 8000`.
3. Frontend (separate terminal): `cd frontend && npm install && npm run dev`.
4. Run the full test suite before opening a PR — it's fast (~3s pytest, ~5s vitest).
5. Pre-commit hooks aren't required; CI will run them for you.

### Adding a new gap scanner

If you've found an evidence-backed signal that AI engines actually use, here's the checklist for adding it as a 9th, 10th, … gap:

1. **Cite the evidence first.** Open an issue with a link to the paper, blog post, or platform doc that motivates the signal. Subjective signals get rejected; observable, testable ones get merged.
2. **Pick a scanner module.** Add the heuristic to the appropriate file under `backend/app/scanners/` (agent_access / discoverability / structured_data / content_clarity). If the signal needs an external API call, put it in `backend/app/probes/`.
3. **Define the check.** Each check returns a `CheckResult` with `id`, `status` (`pass` / `warn` / `fail` / `skip` / `error`), `score` (0–100), and `detail`. Use existing scanners as templates.
4. **Add a fix.** Wire `check_id → Fix` in `backend/app/fixes.py` with a severity, effort estimate, expected score lift, and a copy-pasteable HTML snippet. The snippet should be runnable as-is; placeholder copy is fine but the markup must be valid.
5. **Test against real HTML.** Drop a fixture in `backend/tests/` and assert pass/warn/fail boundaries. Mock all HTTP via `respx` — no live network calls in the test suite.
6. **Add the row to the frontend.** The category breakdown auto-renders any new `CheckResult`, but if your check needs custom UI (e.g., a side-by-side card like `CompareCard`), add it under `frontend/src/components/`.
7. **Open a PR.** In the description: cite the evidence, summarize the heuristic, paste a screenshot of the row in the report, and include before/after scores on a representative real site.

### Adding a category

The category lexicon lives in `backend/app/test_prompts.py` as a tuple of `CategoryDef` records. To add a vertical:

1. Append a new `CategoryDef` with `slug`, `label`, `descriptor`, `persona`, `use_case`, `long_tail_persona`, plus optional `schema_types`, `keywords`, `strong_keywords`, and `path_hints`.
2. Add a detection test in `backend/tests/test_test_prompts.py` against realistic HTML for that vertical.
3. Avoid keyword overlaps with existing categories — if a token is shared, lean on stronger signals (schema_types, strong_keywords, path_hints) for differentiation. Run the full test suite to catch regressions; existing tests pin known-good detection on real homepages (Stripe, Devin, Mayo Clinic, IKEA, Airbnb).

### Code style

- Follow the existing patterns. Type hints everywhere. Pydantic for any cross-boundary data. Async httpx for fetches. No new top-level dependencies without a clear rationale.
- Backend lint: `ruff` (config in `pyproject.toml`). Frontend lint: ESLint + `tsc --noEmit`.
- Tests are required for any new check or scanner. Don't modify existing tests to make them pass — fix the code instead.
- No emoji in code, comments, or commit messages.
- Comments describe the *why*, not the *what*. Don't comment the diff.

### Opening a PR

- Branch from `main`. Use a short descriptive name (e.g. `add-author-bio-scanner`).
- Title: imperative + scope (e.g. "Add author-bio scanner to content-clarity").
- Body: cite the evidence (paper / doc / platform behavior), summarize the heuristic, include before/after scores on a real site if scoring changes.
- CI must be green before review.

### Operational notes

- Production backend is on Fly.io, region `ams`. The Dockerfile builds the FastAPI app with `uv` and runs uvicorn.
- Pushing to `main` triggers an auto-deploy via Fly's GitHub integration. There's no separate staging environment yet; small changes ship straight to prod after CI + review.
- Secrets live in Fly's secret store (not in the repo, not in the Devin secret store — they're separate platforms). Use `fly secrets set` or the Fly dashboard at https://fly.io/apps/agentgeoscore-1ei53w/secrets to add or rotate keys.
- See `.agents/skills/deploy/SKILL.md` for the full redeploy runbook.

## License

MIT. See [`LICENSE`](LICENSE) if present, otherwise treat this repo as MIT-licensed.

## Acknowledgements

The scoring methodology pulls from the GEO literature — most directly from Princeton's GEO benchmark paper (Aggarwal et al., 2024) for the content-depth and citability signals. The category lexicon was hand-curated from a sample of ~200 real homepages across verticals; pull requests to expand it are very welcome.
