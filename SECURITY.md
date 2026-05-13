# Security Policy

Thanks for helping keep AgentGEOScore (and its users) safe.

## Supported versions

This is a single-branch project — only the latest commit on `main` is
supported. There are no LTS releases.

## Reporting a vulnerability

**Please do not file public GitHub issues for security problems.**

Email `linda.haviv@gmail.com` with:

1. A short description of the issue
2. Steps to reproduce (URL, payload, expected vs actual behaviour)
3. Your assessment of impact

I'll acknowledge within 5 business days, ship a fix on a private branch,
and credit you in the release notes (unless you prefer to stay
anonymous).

If a public exploit already exists or the issue is being actively
abused, mark the email subject `[URGENT]` and I'll respond within 24h.

## Threat model — what's in scope

AgentGEOScore is a public-facing web service that:

- Accepts URLs from anonymous users via `POST /api/scan` and
  `POST /api/compare`.
- Fetches those URLs server-side (this is the SSRF surface) plus a
  small number of secondary URLs (sitemap, internal links sampled from
  the homepage).
- Calls a handful of third-party APIs (PageSpeed, Groq, Gemini, Brave)
  with server-held keys.

In-scope vulnerabilities:

- **SSRF / fetcher bypasses.** The fetcher rejects requests to private
  IP ranges, loopback, link-local, multicast, reserved, and CGNAT
  addresses. Re-validation runs on every redirect hop. If you can make
  the backend fetch (or expose response bodies from)
  `127.0.0.0/8`, RFC 1918 ranges, `169.254.0.0/16`, `*.fly.internal`,
  or any other internal network from a public input — that's a bug.
  See [`backend/app/url_safety.py`](backend/app/url_safety.py).
- **Secret leakage.** Any path that exposes the contents of API keys
  set via `*_API_KEY` env vars (PageSpeed, Groq, Gemini, Brave,
  Mistral) in responses, error messages, share cards, or logs.
- **Rate-limit bypasses.** Any way to evade the per-IP slowapi limits
  on `/api/scan`, `/api/compare`, `/api/test-prompts`, `/api/og`.
- **XSS / HTML injection** in `/share`, `/api/og`, or any frontend
  component that renders user-supplied content (domain names, scan
  errors, etc.).
- **Resource exhaustion** beyond the documented response-size cap
  (5 MiB) — e.g. zip-bomb-style decompression, parser DoS via
  malformed JSON-LD or HTML.

Out of scope:

- Findings against a fork or self-hosted deploy that has explicitly
  opted out of the SSRF guard (e.g. `ALLOWED_ORIGINS=*` plus a custom
  fetcher).
- Self-XSS that requires the user to paste attacker-controlled content
  into their own browser console.
- Vulnerabilities in upstream libraries that have not yet been
  released — please report those upstream first.
- Best-practice notes that aren't exploitable (missing `X-XSS-Protection`
  header, etc.).

## Known limitations

These are documented residual risks that we accept rather than fix:

- **DNS rebinding.** The SSRF guard resolves the hostname once and
  rejects if any returned IP is private. An attacker who controls a
  DNS server with a very low TTL could in theory return a public IP
  at validation time and a private IP at fetch time. The bulletproof
  fix is to pin the resolved IP through to the HTTP connection (custom
  transport). For a public-internet GEO auditor we accept the residual
  risk; if you have a working PoC against `api.agentgeoscore.com`
  we'd love to see it.
- **Free-tier quota exhaustion.** A determined attacker hitting
  `/api/scan` from a botnet of distinct IPs can still burn through our
  PageSpeed / Groq / Gemini free-tier quotas (each scan = 1 query per
  service). The probes degrade to `skip` when quotas are exhausted, so
  the app keeps working — just with reduced signal. Fly itself
  rate-limits per source IP at the edge.

## Coordinated disclosure timeline

If we agree on a fix, the typical timeline is:

| Day | Step |
|----|----|
| 0  | You email a report. |
| 1–5 | I acknowledge and triage. |
| 5–14 | Fix lands on a private branch, tests added. |
| 14–30 | Fix deploys to prod; PR opens publicly with a brief writeup. |
| 30+ | Disclosure window opens — feel free to publish a writeup, with credit. |

For trivially fixable issues (a one-line patch), we collapse the
timeline aggressively. For cross-cutting issues we'll discuss before
publishing.

Thanks again — security reports keep this project honest.
