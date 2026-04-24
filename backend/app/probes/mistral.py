"""Mistral probe — free 'Experiment' tier with built-in websearch agent tool.

Docs: https://docs.mistral.ai/agents/tools/built-in/websearch
Get a key (free): https://console.mistral.ai/api-keys
"""
from __future__ import annotations

import os

import httpx

from ..models import CheckResult, CheckStatus

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"


async def probe_mistral(queries: list[str], target_host: str) -> CheckResult:
    api_key = os.getenv("MISTRAL_API_KEY")
    if not api_key:
        return CheckResult(
            id="probe_mistral",
            label="Mistral citations",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.0,
            detail="MISTRAL_API_KEY not set — skipping Mistral probe. Get a free key at https://console.mistral.ai/api-keys.",
        )

    hits = 0
    cited_urls: list[str] = []
    errors: list[str] = []
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=5.0)) as client:
        for query in queries:
            try:
                # Mistral's chat completions with the web_search tool
                resp = await client.post(
                    MISTRAL_URL,
                    headers=headers,
                    json={
                        "model": MISTRAL_MODEL,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a helpful assistant. Use the web search tool to find current information and always cite your sources.",
                            },
                            {"role": "user", "content": query},
                        ],
                        "tools": [{"type": "web_search"}],
                        "tool_choice": "auto",
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

    from .gemini import _build_result
    return _build_result(
        "probe_mistral", "Mistral citations", queries, hits, cited_urls, errors
    )


def _extract_citation_urls(data: dict) -> list[str]:
    urls: list[str] = []
    for choice in data.get("choices", []) or []:
        msg = choice.get("message") or {}
        # tool_calls with web_search results
        for tc in msg.get("tool_calls", []) or []:
            fn = tc.get("function") or {}
            args = fn.get("arguments") or ""
            # Citations often embedded in tool response content downstream
            _ = args
        # References array (Mistral citation format)
        for ref in msg.get("references", []) or []:
            if isinstance(ref, dict) and ref.get("url"):
                urls.append(ref["url"])
        # Fallback: parse URLs out of the raw assistant content
        content = msg.get("content") or ""
        if isinstance(content, str):
            import re
            urls.extend(re.findall(r"https?://[^\s\)\]\"<>]+", content))
    return urls


def _host_matches(url: str, host: str) -> bool:
    if not url or not host:
        return False
    return host.lower().removeprefix("www.") in url.lower()
