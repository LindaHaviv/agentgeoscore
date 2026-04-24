# AgentGEOScore

> Generative Engine Optimization — score & grade any site for AI-agent visibility.

Paste a URL, get:

- a **0–100 score** + letter grade **A–F**
- a **category breakdown** (agent access, discoverability, structured data, content clarity, citation probe)
- a **ranked fix list** — what to do first, with copy-pasteable snippets + expected score lift
- a **drop-in `llms.txt`** auto-generated from your homepage

GEO is what SEO becomes when the readers are LLMs. This is a field study + a toolkit.

## Stack

- **Backend**: FastAPI + httpx, typed with Pydantic. Managed with [`uv`](https://docs.astral.sh/uv/).
- **Frontend**: Vite + React + TypeScript + Tailwind.
- **Tests**: `pytest` + `respx` (backend), `vitest` + `@testing-library/react` (frontend unit), Playwright + `@axe-core/playwright` (e2e + a11y).
- **CI**: GitHub Actions — lint, typecheck, unit, build, e2e.

## Project layout

```
agentgeoscore/
├── backend/          # FastAPI app + scanners + probes + tests
│   ├── app/
│   │   ├── main.py              # POST /api/scan
│   │   ├── models.py            # Pydantic
│   │   ├── scoring.py           # category + overall scoring, fix ranking
│   │   ├── fixes.py             # check_id → Fix (severity/effort/score_lift/snippet)
│   │   ├── llms_suggest.py      # generates starter llms.txt from homepage
│   │   ├── scanners/            # agent_access, discoverability, structured_data, content_clarity
│   │   └── probes/              # gemini, mistral, brave, duck_ai, groq
│   └── tests/
└── frontend/
    ├── src/
    │   ├── pages/               # HomePage, ReportPage, NotFoundPage
    │   ├── components/          # URLInput, ScoreCard, CategoryBreakdown, FixList, LLMSTxtCard
    │   ├── api.ts
    │   ├── types.ts
    │   └── brand.ts
    └── tests/e2e/               # Playwright
```

## Getting started

### Backend

```bash
cd backend
uv sync --extra dev
uv run --extra dev uvicorn app.main:app --reload --port 8000
```

- `GET  /api/healthz` — liveness check
- `POST /api/scan` — `{ "url": "https://stripe.com" }` → `Report`

All LLM probes are **optional** and degrade gracefully when their key is missing. Supported keys (all free-tier):

| Env var           | Probe       |
|-------------------|-------------|
| `GEMINI_API_KEY`  | Gemini w/ Google Search grounding |
| `MISTRAL_API_KEY` | Mistral w/ web-search tool |
| `BRAVE_API_KEY`   | Brave Search API |
| `GROQ_API_KEY`    | Groq `compound-beta` w/ web search |
| _(none)_          | Duck.ai best-effort browser-less probe |

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
```

The dev server proxies `/api` to `http://localhost:8000` — run the backend in parallel.

## Scripts

| Path       | Command                        | What it does                              |
|------------|--------------------------------|-------------------------------------------|
| backend    | `uv run --extra dev pytest -q` | Unit + integration tests (`respx` mocked) |
| backend    | `uv run --extra dev ruff check .` | Lint                                   |
| frontend   | `npm run lint`                 | ESLint                                    |
| frontend   | `npm run typecheck`            | `tsc --noEmit`                            |
| frontend   | `npm test -- --run`            | Vitest                                    |
| frontend   | `npm run build`                | Production bundle                         |
| frontend   | `npm run test:e2e`             | Playwright + axe (auto-starts Vite)       |

## Scoring model

| Category          | Weight | What's checked |
|-------------------|:------:|----------------|
| Agent Access      | 25%    | robots.txt exists + AI-bot rules, CDN AI gating, HTTPS, HTTP status, redirects |
| Discoverability   | 20%    | `/llms.txt`, `/llms-full.txt`, `/sitemap.xml`, canonical URL, OG/Twitter cards |
| Structured Data   | 20%    | JSON-LD presence, schema.org `@type` coverage, microdata |
| Content Clarity   | 15%    | `<title>` + meta description length, exactly one `<h1>`, semantic landmarks, text-to-HTML ratio |
| Citation Probe    | 20%    | % of LLMs (Gemini, Mistral, Brave, Duck.ai, Groq) that cite the domain |

Grade bands: **A** ≥ 90, **B** ≥ 75, **C** ≥ 60, **D** ≥ 45, else **F**.

## Privacy

- No scan results are stored server-side.
- No auth, no cookies, no tracking.
- Probe API keys never leave the backend.

## License

MIT.
