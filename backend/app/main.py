"""FastAPI entrypoint for AgentGEOScore."""
from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .fetcher import Fetcher
from .llms_suggest import generate_llms_txt
from .models import CategoryId, Report, ScanRequest
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

load_dotenv()

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
