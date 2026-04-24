"""HTTP fetcher with sensible timeouts and caching within a single scan."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import httpx

USER_AGENT = (
    "AgentGEOScoreBot/0.1 (+https://github.com/LindaHaviv/agentgeoscore) "
    "Mozilla/5.0 (compatible; AgentGEOScore)"
)
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@dataclass
class FetchResult:
    url: str
    status: int
    text: str
    headers: dict[str, str] = field(default_factory=dict)
    final_url: str = ""
    elapsed_ms: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400


class Fetcher:
    """Async HTTP client with per-URL memoization for a single scan."""

    def __init__(self, timeout: httpx.Timeout | None = None):
        self._client = httpx.AsyncClient(
            timeout=timeout or DEFAULT_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
            http2=False,
        )
        self._cache: dict[str, FetchResult] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def get(self, url: str) -> FetchResult:
        if url in self._cache:
            return self._cache[url]
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            if url in self._cache:
                return self._cache[url]
            import time

            start = time.perf_counter()
            try:
                resp = await self._client.get(url)
                elapsed = int((time.perf_counter() - start) * 1000)
                result = FetchResult(
                    url=url,
                    status=resp.status_code,
                    text=resp.text,
                    headers=dict(resp.headers),
                    final_url=str(resp.url),
                    elapsed_ms=elapsed,
                )
            except httpx.HTTPError as e:
                elapsed = int((time.perf_counter() - start) * 1000)
                result = FetchResult(
                    url=url, status=0, text="", elapsed_ms=elapsed, error=str(e)
                )
            self._cache[url] = result
            return result

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
