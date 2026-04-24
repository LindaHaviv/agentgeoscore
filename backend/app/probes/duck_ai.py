"""Duck.ai probe — DuckDuckGo's free AI chat (best-effort, no API key).

DuckDuckGo exposes a public chat endpoint that proxies small LLMs (GPT-4o-mini,
Claude, Llama, Mistral). It's unofficial — they throttle and occasionally break
clients. We mark results as 'best-effort' in the UI.

For scoring, we don't rely on citation metadata (Duck.ai doesn't return
structured citations) — we ask the model for URLs and grep the response for
the target domain.
"""
from __future__ import annotations

import os
import re

import httpx

from ..models import CheckResult, CheckStatus
from ._util import host_matches

DUCK_STATUS_URL = "https://duckduckgo.com/duckchat/v1/status"
DUCK_CHAT_URL = "https://duckduckgo.com/duckchat/v1/chat"
DUCK_UA = "Mozilla/5.0 (X11; Linux x86_64) AgentGEOScore/0.1"
DUCK_MODEL = "gpt-4o-mini"


async def probe_duck_ai(queries: list[str], target_host: str) -> CheckResult:
    # Allow opt-out (CI / privacy-sensitive users)
    if os.getenv("DISABLE_DUCK_AI") == "1":
        return CheckResult(
            id="probe_duck_ai",
            label="Duck.ai citations (best-effort)",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="Duck.ai probe disabled via DISABLE_DUCK_AI=1.",
        )

    hits = 0
    cited_urls: list[str] = []
    errors: list[str] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
        # Step 1: get x-vqd-4 token from status endpoint
        try:
            status_resp = await client.get(
                DUCK_STATUS_URL,
                headers={"User-Agent": DUCK_UA, "x-vqd-accept": "1"},
            )
            vqd = status_resp.headers.get("x-vqd-4")
            if not vqd:
                return CheckResult(
                    id="probe_duck_ai",
                    label="Duck.ai citations (best-effort)",
                    status=CheckStatus.SKIP,
                    score=0.0,
                    weight=0.0,
                    detail="Couldn't obtain Duck.ai session token (expected — they rotate often).",
                )
        except httpx.HTTPError as e:
            return CheckResult(
                id="probe_duck_ai",
                label="Duck.ai citations (best-effort)",
                status=CheckStatus.SKIP,
                score=0.0,
                weight=0.0,
                detail=f"Duck.ai unreachable: {e}",
            )

        for query in queries:
            try:
                prompt = (
                    f"{query}\n\nList the top 3 websites for this, each on its own line "
                    f"with a full https:// URL."
                )
                resp = await client.post(
                    DUCK_CHAT_URL,
                    headers={
                        "User-Agent": DUCK_UA,
                        "Accept": "text/event-stream",
                        "Content-Type": "application/json",
                        "x-vqd-4": vqd,
                    },
                    json={
                        "model": DUCK_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                # Refresh token for next request if server rotated it
                new_vqd = resp.headers.get("x-vqd-4")
                if new_vqd:
                    vqd = new_vqd
                if resp.status_code != 200:
                    errors.append(f"{query!r}: HTTP {resp.status_code}")
                    continue
                text = _parse_sse(resp.text)
                urls = re.findall(r"https?://[^\s\)\]\"<>]+", text)
                cited_urls.extend(urls)
                if any(host_matches(u, target_host) for u in urls):
                    hits += 1
            except httpx.HTTPError as e:
                errors.append(f"{query!r}: {e}")

    total = len(queries)
    if total == 0 or (errors and hits == 0 and len(errors) == total):
        return CheckResult(
            id="probe_duck_ai",
            label="Duck.ai citations (best-effort)",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail=f"Probe unavailable: {errors[0] if errors else 'no queries'}",
        )

    score = hits / total
    status = (
        CheckStatus.PASS if hits == total
        else CheckStatus.WARN if hits > 0
        else CheckStatus.FAIL
    )
    return CheckResult(
        id="probe_duck_ai",
        label="Duck.ai citations (best-effort)",
        status=status,
        score=score,
        weight=0.5,  # Lower weight since unofficial
        detail=(
            f"Cited in {hits}/{total} Duck.ai queries. "
            f"This probe is best-effort (no official API). "
            + (f"Sample URLs: {', '.join(cited_urls[:3])}." if cited_urls else "")
        ),
        evidence={"hits": hits, "queries": total, "cited_sample": cited_urls[:5]},
    )


def _parse_sse(body: str) -> str:
    """Concatenate `message` fields from an SSE response."""
    out: list[str] = []
    for line in body.splitlines():
        if line.startswith("data: "):
            payload = line[len("data: "):]
            if payload.strip() in ("[DONE]", ""):
                continue
            try:
                import json

                obj = json.loads(payload)
                msg = obj.get("message") or ""
                out.append(msg)
            except json.JSONDecodeError:
                continue
    return "".join(out)
