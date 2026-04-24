"""Brave Search API probe — proxy for AI-search visibility.

Brave powers a significant chunk of AI-assistant search under the hood (and
their own Leo assistant). If Brave ranks your site, most LLM search layers
sitting on top of Brave will too.

Docs: https://api-dashboard.search.brave.com/app/documentation
Get a key (free tier: 2k queries/mo): https://api-dashboard.search.brave.com/
"""
from __future__ import annotations

import os

import httpx

from ..models import CheckResult, CheckStatus
from ._util import host_matches

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


async def probe_brave(queries: list[str], target_host: str) -> CheckResult:
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return CheckResult(
            id="probe_brave",
            label="Brave Search ranking",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="BRAVE_API_KEY not set — skipping Brave probe. Get a free key at https://brave.com/search/api/.",
        )

    hits = 0  # counts queries where target appears in top N
    ranks: list[int] = []
    errors: list[str] = []
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    TOP_N = 10

    async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
        for query in queries:
            try:
                resp = await client.get(
                    BRAVE_URL,
                    headers=headers,
                    params={"q": query, "count": TOP_N},
                )
                if resp.status_code != 200:
                    errors.append(f"{query!r}: HTTP {resp.status_code}")
                    continue
                data = resp.json()
                web_results = (data.get("web") or {}).get("results") or []
                rank = None
                for i, r in enumerate(web_results, start=1):
                    url = r.get("url") or ""
                    if host_matches(url, target_host):
                        rank = i
                        break
                if rank:
                    hits += 1
                    ranks.append(rank)
            except httpx.HTTPError as e:
                errors.append(f"{query!r}: {e}")

    total = len(queries)
    if total == 0 or (errors and hits == 0 and len(errors) == total):
        return CheckResult(
            id="probe_brave",
            label="Brave Search ranking",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail=f"Probe unavailable: {errors[0] if errors else 'no queries'}",
        )

    # Score rewards higher rankings more
    # rank 1 → 1.0, rank 10 → 0.1, no rank → 0
    per_query_scores = [max(0.0, (TOP_N + 1 - r) / TOP_N) for r in ranks]
    score = sum(per_query_scores) / total if total else 0.0
    if hits == total and all(r <= 3 for r in ranks):
        status = CheckStatus.PASS
    elif hits > 0:
        status = CheckStatus.WARN
    else:
        status = CheckStatus.FAIL

    rank_summary = (
        ", ".join([f"#{r}" for r in ranks]) if ranks else "not in top 10"
    )
    return CheckResult(
        id="probe_brave",
        label="Brave Search ranking",
        status=status,
        score=round(score, 3),
        weight=1.0,
        detail=f"Ranked in {hits}/{total} queries (top {TOP_N}). Positions: {rank_summary}.",
        evidence={"hits": hits, "queries": total, "ranks": ranks},
    )
