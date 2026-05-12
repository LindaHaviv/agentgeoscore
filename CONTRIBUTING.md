# Contributing to AgentGEOScore

Thanks for considering a contribution. The ground rules below keep the project
legible and the score honest.

## Getting set up

1. Fork + clone.
2. Backend: `cd backend && uv sync --extra dev && uv run --extra dev uvicorn app.main:app --reload --port 8000`
3. Frontend (separate terminal): `cd frontend && npm install && npm run dev`
4. Run the full test suite before opening a PR — it's fast (~3 s pytest, ~2 s vitest).
5. Pre-commit hooks aren't required; CI will run them for you.

## Adding a new gap scanner

If you've found an evidence-backed signal that AI engines actually use, here's
the checklist for adding it as a 9th, 10th, … gap:

1. **Cite the evidence first.** Open an issue with a link to the paper, blog
   post, or platform doc that motivates the signal. Subjective signals get
   rejected; observable, testable ones get merged.
2. **Pick a scanner module.** Add the heuristic to the appropriate file under
   `backend/app/scanners/` (`agent_access` / `discoverability` /
   `structured_data` / `content_clarity`). If the signal needs an external
   API call, put it in `backend/app/probes/`.
3. **Define the check.** Each check returns a `CheckResult` with `id`,
   `status` (`pass` / `warn` / `fail` / `skip` / `error`), `score` (0–100),
   and `detail`. Use existing scanners as templates.
4. **Add a fix.** Wire `check_id → Fix` in `backend/app/fixes.py` with a
   severity, effort estimate, expected score lift, and a copy-pasteable HTML
   snippet. The snippet should be runnable as-is; placeholder copy is fine
   but the markup must be valid.
5. **Test against real HTML.** Drop a fixture in `backend/tests/` and assert
   pass/warn/fail boundaries. Mock all HTTP via `respx` — no live network
   calls in the test suite.
6. **Add the row to the frontend.** The category breakdown auto-renders any
   new `CheckResult`, but if your check needs custom UI (e.g. a side-by-side
   card like `CompetitorCompareCard`), add it under
   `frontend/src/components/`.
7. **Open a PR.** In the description: cite the evidence, summarize the
   heuristic, paste a screenshot of the row in the report, and include
   before/after scores on a representative real site.

## Adding a category

The category lexicon lives in `backend/app/test_prompts.py` as a tuple of
`CategoryDef` records. To add a vertical:

1. Append a new `CategoryDef` with `slug`, `label`, `descriptor`, `persona`,
   `use_case`, `long_tail_persona`, plus optional `schema_types`, `keywords`,
   `strong_keywords`, and `path_hints`.
2. Add a detection test in `backend/tests/test_test_prompts.py` against
   realistic HTML for that vertical.
3. Avoid keyword overlaps with existing categories — if a token is shared,
   lean on stronger signals (`schema_types`, `strong_keywords`, `path_hints`)
   for differentiation. Run the full test suite to catch regressions;
   existing tests pin known-good detection on real homepages (Stripe, Devin,
   Mayo Clinic, IKEA, Airbnb).

## Code style

- Follow the existing patterns. Type hints everywhere. Pydantic for any
  cross-boundary data. Async httpx for fetches. No new top-level
  dependencies without a clear rationale.
- Backend lint: `ruff` (config in `pyproject.toml`). Frontend lint:
  ESLint + `tsc --noEmit`.
- Tests are required for any new check or scanner. Don't modify existing
  tests to make them pass — fix the code instead.
- No emoji in code, comments, or commit messages.
- Comments describe the *why*, not the *what*. Don't comment the diff.

## Editing the static SEO shell (`frontend/index.html`)

The pre-React HTML inside `<div id="root">` is the source of truth for how
AI crawlers see the homepage. If you change the markup there, run:

```
cd frontend && npm test -- --run src/test/seo-shell.test.ts
```

The regression guard parses `index.html` and asserts every JSON-LD block,
semantic landmark, byline anchor, citation density check, and FAQPage
validity. The companion backend test
`backend/tests/test_predict_self_score.py` runs the real `/api/scan`
pipeline against the rebuilt `dist/` and asserts the four addressable
categories all score 100. Both must stay green.

## Opening a PR

- Branch from `main`. Use a short descriptive name (e.g.
  `add-author-bio-scanner`).
- Title: imperative + scope (e.g. *"Add author-bio scanner to
  content-clarity"*).
- Body: cite the evidence (paper / doc / platform behavior), summarize the
  heuristic, include before/after scores on a real site if scoring changes.
- CI must be green before review.

## Operational notes

- Production backend is on Fly.io, region `ams`. The Dockerfile builds the
  FastAPI app with `uv` and runs uvicorn.
- Pushing to `main` triggers an auto-deploy via Fly's GitHub integration.
  There's no separate staging environment yet; small changes ship straight
  to prod after CI + review.
- Secrets live in Fly's secret store (not in the repo, not in the Devin
  secret store — they're separate platforms). Use `fly secrets set` or the
  Fly dashboard at https://fly.io/apps/agentgeoscore-1ei53w/secrets to add
  or rotate keys.
- See `.agents/skills/deploy/SKILL.md` for the full redeploy runbook.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). By
participating, you agree to abide by it.

## Security

Found a vulnerability? Please **don't** open a public issue — see
[`SECURITY.md`](SECURITY.md) for the disclosure process.

## License

By contributing, you agree your contributions will be licensed under the
project's [MIT license](LICENSE).
