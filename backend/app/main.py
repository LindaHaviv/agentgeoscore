"""FastAPI entrypoint for AgentGEOScore."""
from __future__ import annotations

import asyncio
import html
import os
import time
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response

from .fetcher import Fetcher
from .llms_suggest import generate_llms_txt
from .models import CategoryId, Report, ScanRequest
from .og import render_brand_card, render_share_card
from .probes import (
    derive_queries,
    probe_brave,
    probe_duck_ai,
    probe_gemini,
    probe_groq,
    probe_mistral,
)
from .scanners import (
    check_agent_access,
    check_content_clarity,
    check_discoverability,
    check_structured_data,
)
from .scoring import build_category, build_fixes, grade_for, overall_score
from .targets import WebsiteTarget

# Populate os.environ from .env *before* reading any config values below, so
# a local .env can override production defaults without needing real OS env
# vars.
load_dotenv()

# Frontend origin to redirect humans to from the /share route.
# Override via FRONTEND_ORIGIN env var in deploy config.
FRONTEND_ORIGIN = os.environ.get(
    "FRONTEND_ORIGIN", "https://dist-olcivbch.devinapps.com"
).rstrip("/")

# Public backend origin used when composing absolute URLs in crawler-facing
# HTML (og:image). Derived from request headers by default, but pinning it via
# env avoids trusting a spoofable Host header for any embed that runs through
# a social-media image proxy. Leave unset to fall back to request-derived.
BACKEND_ORIGIN = os.environ.get("BACKEND_ORIGIN", "").rstrip("/")

app = FastAPI(
    title="AgentGEOScore API",
    description=(
        "Generative Engine Optimization — score any URL for how well AI agents "
        "find, read, and cite it."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
@app.get("/api/")
async def root() -> dict:
    return {
        "name": "AgentGEOScore",
        "version": "0.1.0",
        "tagline": "Generative Engine Optimization, graded.",
        "endpoints": {
            "POST /api/scan": "Run a GEO scan on a URL",
            "GET /api/healthz": "Health check",
        },
    }


@app.get("/api/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/api/scan", response_model=Report)
async def scan(req: ScanRequest) -> Report:
    try:
        target = WebsiteTarget.from_url(str(req.url))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    started = time.perf_counter()
    errors: list[str] = []

    async with Fetcher() as fetcher:
        # Fetch homepage once and reuse
        home = await fetcher.get(target.url)
        if not home.ok:
            errors.append(f"Homepage fetch failed: {home.error or home.status}")
            home_html = ""
        else:
            home_html = home.text

        # Run synchronous-friendly scanners in parallel
        agent_access_task = check_agent_access(target, fetcher)
        discoverability_task = check_discoverability(target, fetcher, home_html)
        structured_data_checks = check_structured_data(home_html)
        content_checks = check_content_clarity(home_html)

        # Live probes in parallel
        probe_tasks: list = []
        if req.include_probe:
            queries = derive_queries(home_html, target.host)
            probe_tasks = [
                probe_gemini(queries, target.host),
                probe_mistral(queries, target.host),
                probe_brave(queries, target.host),
                probe_duck_ai(queries, target.host),
                probe_groq(queries, target.host),
            ]

        results = await asyncio.gather(
            agent_access_task,
            discoverability_task,
            *probe_tasks,
            return_exceptions=True,
        )

    # Unpack (first two are scanner lists, rest are probe CheckResults)
    agent_access_checks = _unwrap(results[0], errors, "agent_access")
    discoverability_checks = _unwrap(results[1], errors, "discoverability")
    probe_checks = []
    for res in results[2:]:
        probe_checks.append(_unwrap_single(res, errors, "probe"))

    categories = [
        build_category(CategoryId.AGENT_ACCESS, agent_access_checks or []),
        build_category(CategoryId.DISCOVERABILITY, discoverability_checks or []),
        build_category(CategoryId.STRUCTURED_DATA, structured_data_checks),
        build_category(CategoryId.CONTENT_CLARITY, content_checks),
    ]
    probe_checks_clean = [c for c in probe_checks if c is not None]
    if probe_checks_clean:
        categories.append(build_category(CategoryId.CITATION_PROBE, probe_checks_clean))

    score = overall_score(categories)
    grade = grade_for(score)
    fixes = build_fixes(categories, target.host)
    suggested_llms_txt = generate_llms_txt(home_html, target.origin, target.host)

    return Report(
        url=str(req.url),
        normalized_url=target.url,
        domain=target.host,
        scanned_at=datetime.now(UTC),
        duration_ms=int((time.perf_counter() - started) * 1000),
        score=score,
        grade=grade,
        categories=categories,
        fixes=fixes,
        suggested_llms_txt=suggested_llms_txt,
        errors=errors,
    )


_ALLOWED_GRADES = {"A", "B", "C", "D", "F"}


def _sanitize_domain(raw: str) -> str:
    """Accept the domain query param, strip scheme/path, keep it printable.

    Kept intentionally loose — this is a display parameter, not a DB key, and
    rendering an ugly string is better than 400-ing share embeds.
    """
    d = (raw or "").strip().lower()
    if d.startswith(("http://", "https://")):
        d = d.split("://", 1)[1]
    d = d.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    d = d.removeprefix("www.")
    # Reject anything that's not a plausible host-ish string.
    return "".join(c for c in d if c.isalnum() or c in ".-:_")[:120] or "site"


def _sanitize_grade(raw: str) -> str:
    g = (raw or "").strip().upper()[:1]
    return g if g in _ALLOWED_GRADES else "?"


def _sanitize_score(raw: int) -> int:
    return max(0, min(100, int(raw)))


@app.get("/api/og", response_class=Response)
async def og_image(
    d: str | None = Query(default=None, description="Target domain"),
    s: int = Query(default=0, ge=0, le=100),
    g: str = Query(default="?", min_length=0, max_length=2),
    brand: int = Query(default=0, ge=0, le=1),
) -> Response:
    """Render an OG share-card PNG.

    - `brand=1` → render the homepage/brand card (no score).
    - otherwise → render a per-report card with domain + score + grade.
    """
    if brand:
        png = render_brand_card()
    else:
        if not d:
            raise HTTPException(status_code=400, detail="missing domain (d=)")
        png = render_share_card(
            domain=_sanitize_domain(d),
            score=_sanitize_score(s),
            grade=_sanitize_grade(g),
        )
    return Response(
        content=png,
        media_type="image/png",
        headers={
            # Cache on CDNs / Slack / Twitter's image cache for an hour.
            "Cache-Control": "public, max-age=3600, s-maxage=3600",
        },
    )


@app.get("/share", response_class=HTMLResponse)
@app.get("/share/", response_class=HTMLResponse)
async def share_page(
    request: Request,
    d: str | None = Query(default=None, description="Target domain"),
    s: int = Query(default=0, ge=0, le=100),
    g: str = Query(default="?", max_length=2),
) -> HTMLResponse:
    """HTML shell that crawlers read for OG tags; humans 302 to the SPA.

    Generating a bot-visible HTML page on the backend is the only reliable way
    to get OG/Twitter cards for a Vite SPA — putting og:* tags inside React
    won't work because crawlers don't execute JS.
    """
    if not d:
        raise HTTPException(status_code=400, detail="missing domain (d=)")
    domain = _sanitize_domain(d)
    score = _sanitize_score(s)
    grade = _sanitize_grade(g)

    # Absolute URL to the OG image. Slack/Twitter bots want absolute URLs, and
    # some (Slack) reject http:// images even when the site is served over
    # https. Prefer an explicit BACKEND_ORIGIN env var (set in prod), else
    # derive from the request. Fly's edge terminates TLS and forwards
    # X-Forwarded-Proto=https but uvicorn isn't started with --proxy-headers
    # in the default deploy, so request.url.scheme comes back as "http" —
    # honour the forwarded scheme when falling back to request-derived base.
    if BACKEND_ORIGIN:
        base = BACKEND_ORIGIN
    else:
        scheme = (
            request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
            or request.url.scheme
            or "https"
        )
        host = request.headers.get("host") or request.url.netloc
        base = f"{scheme}://{host}"
    og_image_path = f"{base}/api/og?d={domain}&s={score}&g={grade}"
    report_url = f"{FRONTEND_ORIGIN}/report/{domain}"

    title = f"{domain} scored {score}/100 ({grade}) — AgentGEOScore"
    description = (
        f"How well AI agents (ChatGPT, Claude, Gemini, Perplexity, Groq) find "
        f"and cite {domain}. Grade {grade} · Score {score}/100."
    )

    # Escape everything that lands in HTML attributes / text.
    title_e = html.escape(title, quote=True)
    desc_e = html.escape(description, quote=True)
    report_e = html.escape(report_url, quote=True)
    og_e = html.escape(og_image_path, quote=True)
    domain_e = html.escape(domain, quote=True)

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title_e}</title>
<meta name="description" content="{desc_e}" />
<link rel="canonical" href="{report_e}" />
<meta property="og:type" content="website" />
<meta property="og:title" content="{title_e}" />
<meta property="og:description" content="{desc_e}" />
<meta property="og:url" content="{report_e}" />
<meta property="og:image" content="{og_e}" />
<meta property="og:image:width" content="1200" />
<meta property="og:image:height" content="630" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title_e}" />
<meta name="twitter:description" content="{desc_e}" />
<meta name="twitter:image" content="{og_e}" />
<meta http-equiv="refresh" content="0; url={report_e}" />
</head>
<body>
<p>Redirecting to the AgentGEOScore report for <a href="{report_e}">{domain_e}</a>…</p>
<script>window.location.replace({report_e!r});</script>
</body>
</html>
"""
    return HTMLResponse(
        content=body,
        headers={"Cache-Control": "public, max-age=300"},
    )


def _unwrap(res, errors: list[str], label: str):
    if isinstance(res, Exception):
        errors.append(f"{label}: {res}")
        return []
    return res


def _unwrap_single(res, errors: list[str], label: str):
    if isinstance(res, Exception):
        errors.append(f"{label}: {res}")
        return None
    return res
