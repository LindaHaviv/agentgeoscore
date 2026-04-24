"""Google Gemini probe — free tier with Google Search grounding returns citations.

Docs: https://ai.google.dev/gemini-api/docs/google-search
Get a key (free): https://aistudio.google.com/apikey
"""
from __future__ import annotations

import os

import httpx

from ..models import CheckResult, CheckStatus

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


async def probe_gemini(queries: list[str], target_host: str) -> CheckResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return CheckResult(
            id="probe_gemini",
            label="Google Gemini citations",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="GEMINI_API_KEY not set — skipping Gemini probe. Get a free key at https://aistudio.google.com/apikey.",
        )

    hits = 0
    cited_urls: list[str] = []
    errors: list[str] = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        for query in queries:
            try:
                resp = await client.post(
                    GEMINI_URL.format(model=GEMINI_MODEL),
                    params={"key": api_key},
                    json={
                        "contents": [{"parts": [{"text": query}]}],
                        "tools": [{"google_search": {}}],
                    },
                )
                if resp.status_code != 200:
                    errors.append(f"{query!r}: HTTP {resp.status_code}")
                    continue
                data = resp.json()
                urls = _extract_citation_urls(data)
                cited_urls.extend(urls)
                if any(_host_matches(u, target_host) for u in urls):
                    hits += 1
            except httpx.HTTPError as e:
                errors.append(f"{query!r}: {e}")

    return _build_result(
        "probe_gemini", "Google Gemini citations", queries, hits, cited_urls, errors
    )


def _extract_citation_urls(data: dict) -> list[str]:
    """Walk the Gemini response and pull out grounding citation URLs."""
    urls: list[str] = []
    for cand in data.get("candidates", []) or []:
        meta = cand.get("groundingMetadata") or {}
        for chunk in meta.get("groundingChunks", []) or []:
            web = chunk.get("web") or {}
            uri = web.get("uri")
            if uri:
                urls.append(uri)
        for sa in meta.get("searchEntryPoint", {}).get("renderedContent", []) or []:
            if isinstance(sa, dict) and sa.get("uri"):
                urls.append(sa["uri"])
    return urls


def _host_matches(url: str, host: str) -> bool:
    if not url or not host:
        return False
    # Cheap containment check — works for both direct URLs and Google-wrapped redirects
    host_lower = host.lower().removeprefix("www.")
    return host_lower in url.lower()


def _build_result(
    check_id: str,
    label: str,
    queries: list[str],
    hits: int,
    cited_urls: list[str],
    errors: list[str],
) -> CheckResult:
    total = len(queries)
    if total == 0:
        return CheckResult(
            id=check_id,
            label=label,
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="No queries to run.",
        )
    if errors and hits == 0 and len(errors) == total:
        return CheckResult(
            id=check_id,
            label=label,
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail=f"Probe unavailable: {errors[0]}",
        )
    score = hits / total
    if hits == total:
        status = CheckStatus.PASS
    elif hits > 0:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL
    detail = (
        f"Cited in {hits}/{total} queries. "
        + (f"Errors: {len(errors)}. " if errors else "")
        + (f"Sample cited URLs: {', '.join(cited_urls[:3])}." if cited_urls else "No citations returned for target domain.")
    )
    return CheckResult(
        id=check_id,
        label=label,
        status=status,
        score=score,
        weight=1.0,
        detail=detail,
        evidence={"hits": hits, "queries": total, "cited_sample": cited_urls[:5]},
    )
