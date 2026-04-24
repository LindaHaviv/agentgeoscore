"""Groq probe — free tier `compound` model with built-in web search.

Groq's `compound` / `compound-mini` models are tool-use augmented LLMs that can
call the web on their own and return citations in the response metadata. The
free tier is generous enough to run a handful of queries per scan.

Docs: https://console.groq.com/docs/agentic-tooling
Get a key (free): https://console.groq.com/keys
"""
from __future__ import annotations

import os
import re

import httpx

from ..models import CheckResult, CheckStatus
from ._util import host_matches as _host_matches

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "compound-beta"


async def probe_groq(queries: list[str], target_host: str) -> CheckResult:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return CheckResult(
            id="probe_groq",
            label="Groq citations",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="GROQ_API_KEY not set — skipping Groq probe. Get a free key at https://console.groq.com/keys.",
        )

    hits = 0
    cited_urls: list[str] = []
    errors: list[str] = []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0)) as client:
        for query in queries:
            try:
                resp = await client.post(
                    GROQ_URL,
                    headers=headers,
                    json={
                        "model": GROQ_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are a helpful assistant. Use web search to find "
                                    "current information and cite the sources you used."
                                ),
                            },
                            {"role": "user", "content": query},
                        ],
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

    # Reuse the shared result-builder from gemini.py.
    from .gemini import _build_result
    return _build_result(
        "probe_groq", "Groq citations", queries, hits, cited_urls, errors
    )


def _extract_citation_urls(data: dict) -> list[str]:
    """Pull citation URLs out of a Groq compound chat response."""
    urls: list[str] = []
    for choice in data.get("choices", []) or []:
        msg = choice.get("message") or {}
        # Groq compound models expose executed_tools with web search results
        for tool in msg.get("executed_tools", []) or []:
            output = tool.get("output") or ""
            if isinstance(output, str):
                urls.extend(re.findall(r"https?://[^\s\)\]\"<>]+", output))
            elif isinstance(output, list):
                for item in output:
                    if isinstance(item, dict) and item.get("url"):
                        urls.append(item["url"])
        # Fallback: parse URLs from assistant content
        content = msg.get("content") or ""
        if isinstance(content, str):
            urls.extend(re.findall(r"https?://[^\s\)\]\"<>]+", content))
    return urls



