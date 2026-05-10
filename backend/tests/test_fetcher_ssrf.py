"""End-to-end SSRF guard tests for the Fetcher.

These run *without* mocking ``url_safety`` — we want to confirm the live
guard wired into ``Fetcher.get`` actually refuses the canonical bypass
patterns.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.fetcher import Fetcher


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://localhost/",  # resolves to 127.0.0.1
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "ftp://example.com/etc/passwd",
        "file:///etc/passwd",
        "http://example.com:22/",
    ],
)
async def test_fetcher_refuses_ssrf_targets(url: str) -> None:
    """Each of these is a textbook SSRF bypass attempt."""
    async with Fetcher() as fetcher:
        result = await fetcher.get(url)
    assert result.ok is False
    assert result.status == 0
    assert result.error is not None
    assert "refused" in result.error


@pytest.mark.asyncio
async def test_fetcher_refuses_redirect_to_private_ip() -> None:
    """A public URL that 302s to localhost must NOT be followed."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://public.example/":
            return httpx.Response(
                302, headers={"Location": "http://127.0.0.1/admin"}
            )
        return httpx.Response(200, text="should-not-fetch")

    transport = httpx.MockTransport(handler)

    async with Fetcher() as fetcher:
        # Patch DNS so "public.example" looks routable.
        with patch(
            "app.url_safety._resolve_all_ips", return_value=["8.8.8.8"]
        ):
            # Replace the underlying client's transport with our mock.
            fetcher._client._transport = transport
            result = await fetcher.get("https://public.example/")

    assert result.ok is False
    assert "refused" in (result.error or "")
    assert "127.0.0.1" in (result.error or "") or "literal private" in (
        result.error or ""
    )


@pytest.mark.asyncio
async def test_fetcher_caps_response_body() -> None:
    """Bodies larger than MAX_RESPONSE_BYTES return an error, not the body."""
    import httpx

    from app.fetcher import MAX_RESPONSE_BYTES

    big_body = b"a" * (MAX_RESPONSE_BYTES + 1024)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=big_body)

    transport = httpx.MockTransport(handler)

    async with Fetcher() as fetcher:
        with patch(
            "app.url_safety._resolve_all_ips", return_value=["8.8.8.8"]
        ):
            fetcher._client._transport = transport
            result = await fetcher.get("https://big.example/")

    assert result.ok is False
    assert "exceeds" in (result.error or "")
