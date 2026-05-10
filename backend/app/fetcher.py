"""HTTP fetcher with sensible timeouts and caching within a single scan."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import urljoin

import httpx

from .url_safety import is_public_http_url

USER_AGENT = (
    "AgentGEOScoreBot/0.1 (+https://github.com/LindaHaviv/agentgeoscore) "
    "Mozilla/5.0 (compatible; AgentGEOScore)"
)
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Bounded redirect depth + bounded response body size to prevent abuse
# (zip-bomb-style endpoints, infinite redirect chains, etc.).
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5 MiB — generous for any real homepage


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
    """Async HTTP client with per-URL memoization for a single scan.

    All outbound URLs (including redirect targets) are validated by
    :func:`app.url_safety.is_public_http_url` to prevent SSRF — see
    ``url_safety.py`` for the threat model + mitigation details.
    """

    def __init__(self, timeout: httpx.Timeout | None = None):
        # ``Accept-Language`` is set explicitly so geolocation-aware sites
        # (Stripe, Airbnb, large e-commerce) don't redirect us to a localized
        # subpath like ``/nl/`` based on the egress IP of our host. When that
        # happens, sampled headings/nav arrive in another language and leak
        # into category detection + topic extraction (we previously got
        # phrases like "lees het verhaal" surfaced as topics for stripe.com
        # because the Fly app egresses from Amsterdam).
        #
        # ``follow_redirects`` is intentionally OFF — we follow manually so
        # we can re-validate every redirect target (SSRF redirect bypass).
        self._client = httpx.AsyncClient(
            timeout=timeout or DEFAULT_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=False,
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
            result = await self._fetch_with_redirects(url)
            self._cache[url] = result
            return result

    async def _fetch_with_redirects(self, original_url: str) -> FetchResult:
        """Manual redirect loop with per-hop SSRF validation + body cap."""
        import time

        start = time.perf_counter()
        current = original_url

        for hop in range(MAX_REDIRECTS + 1):
            ok, reason = await is_public_http_url(current)
            if not ok:
                elapsed = int((time.perf_counter() - start) * 1000)
                return FetchResult(
                    url=original_url,
                    status=0,
                    text="",
                    elapsed_ms=elapsed,
                    error=f"refused: {reason}",
                )

            try:
                # Stream so we can enforce a hard byte cap before loading
                # the whole body into memory.
                async with self._client.stream("GET", current) as resp:
                    if 300 <= resp.status_code < 400 and "location" in resp.headers:
                        if hop >= MAX_REDIRECTS:
                            elapsed = int(
                                (time.perf_counter() - start) * 1000
                            )
                            return FetchResult(
                                url=original_url,
                                status=resp.status_code,
                                text="",
                                elapsed_ms=elapsed,
                                error=(
                                    "too many redirects "
                                    f"(>{MAX_REDIRECTS})"
                                ),
                            )
                        current = urljoin(current, resp.headers["location"])
                        continue

                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            elapsed = int(
                                (time.perf_counter() - start) * 1000
                            )
                            return FetchResult(
                                url=original_url,
                                status=resp.status_code,
                                text="",
                                final_url=str(resp.url),
                                elapsed_ms=elapsed,
                                error=(
                                    f"response exceeds "
                                    f"{MAX_RESPONSE_BYTES} bytes"
                                ),
                            )
                        chunks.append(chunk)

                    body = b"".join(chunks)
                    encoding = resp.encoding or "utf-8"
                    try:
                        text = body.decode(encoding, errors="replace")
                    except (LookupError, TypeError):
                        text = body.decode("utf-8", errors="replace")

                    elapsed = int((time.perf_counter() - start) * 1000)
                    return FetchResult(
                        url=original_url,
                        status=resp.status_code,
                        text=text,
                        headers=dict(resp.headers),
                        final_url=str(resp.url),
                        elapsed_ms=elapsed,
                    )
            except httpx.HTTPError as e:
                elapsed = int((time.perf_counter() - start) * 1000)
                return FetchResult(
                    url=original_url,
                    status=0,
                    text="",
                    elapsed_ms=elapsed,
                    error=str(e),
                )

        # Fall-through (shouldn't reach with the loop bound, but be safe).
        elapsed = int((time.perf_counter() - start) * 1000)
        return FetchResult(
            url=original_url,
            status=0,
            text="",
            elapsed_ms=elapsed,
            error="redirect loop exited unexpectedly",
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Fetcher:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
