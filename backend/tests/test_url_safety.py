"""Tests for the SSRF URL guard.

The fetcher exposes ``Fetcher.get(url)`` to user-supplied URLs. ``url_safety``
is the gate that decides whether a URL is safe to GET. The cases below
correspond to documented bypass attempts; if any of them ever start passing
(returning ``ok=True``), that's an SSRF regression.
"""
from __future__ import annotations

import ipaddress
import socket
from unittest.mock import patch

import pytest

from app.url_safety import (
    _is_blocked_ip,
    _validate_scheme_and_port,
    is_public_http_url,
)


def _addrinfo(*ips: str) -> list[tuple]:
    """Build the 5-tuple list ``getaddrinfo`` returns from a flat list of IPs."""
    return [
        (socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))
        for ip in ips
    ]


# ---- scheme + port checks (sync layer) --------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<script>",
        "gopher://example.com/",
    ],
)
def test_validate_scheme_rejects_non_http(url: str) -> None:
    host, reason = _validate_scheme_and_port(url)
    assert host == ""
    assert reason


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:22/",
        "http://example.com:25/",
        "http://example.com:6379/",
        "http://example.com:11211/",
        "https://example.com:8080/",
    ],
)
def test_validate_scheme_rejects_non_default_ports(url: str) -> None:
    host, reason = _validate_scheme_and_port(url)
    assert host == ""
    assert "port" in reason


def test_validate_scheme_accepts_default_ports() -> None:
    host, reason = _validate_scheme_and_port("http://example.com/")
    assert host == "example.com" and reason == ""
    host, reason = _validate_scheme_and_port("https://example.com:443/")
    assert host == "example.com" and reason == ""


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://169.254.169.254/",  # cloud metadata
        "http://[::1]/",
        "http://0.0.0.0/",
    ],
)
def test_validate_scheme_rejects_literal_private_ips(url: str) -> None:
    host, reason = _validate_scheme_and_port(url)
    assert host == ""
    assert "literal private IP" in reason or "missing hostname" in reason


# ---- DNS-based block (async layer) ------------------------------------------


@pytest.mark.asyncio
async def test_is_public_http_url_blocks_private_resolution() -> None:
    """Hostname that resolves to a private IP is blocked."""
    with patch("app.url_safety._resolve_all_ips", return_value=["10.0.0.5"]):
        ok, reason = await is_public_http_url("https://internal.example.com/")
    assert ok is False
    assert "non-public" in reason


@pytest.mark.asyncio
async def test_is_public_http_url_blocks_loopback_resolution() -> None:
    with patch("app.url_safety._resolve_all_ips", return_value=["127.0.0.1"]):
        ok, _ = await is_public_http_url("https://localhost-alias.example/")
    assert ok is False


@pytest.mark.asyncio
async def test_is_public_http_url_blocks_metadata_resolution() -> None:
    """169.254.169.254 (cloud metadata) reachable via a public hostname."""
    with patch(
        "app.url_safety._resolve_all_ips", return_value=["169.254.169.254"]
    ):
        ok, reason = await is_public_http_url("https://meta.example.com/")
    assert ok is False
    assert "169.254.169.254" in reason


@pytest.mark.asyncio
async def test_is_public_http_url_blocks_cgnat() -> None:
    with patch("app.url_safety._resolve_all_ips", return_value=["100.64.1.1"]):
        ok, _ = await is_public_http_url("https://cgnat.example.com/")
    assert ok is False


@pytest.mark.asyncio
async def test_is_public_http_url_blocks_mixed_resolution() -> None:
    """Even one private IP among many makes the URL unsafe (DNS rebinding sympathy)."""
    with patch(
        "app.url_safety._resolve_all_ips",
        return_value=["8.8.8.8", "10.0.0.1"],
    ):
        ok, _ = await is_public_http_url("https://mixed.example.com/")
    assert ok is False


@pytest.mark.asyncio
async def test_is_public_http_url_accepts_public_resolution() -> None:
    with patch("app.url_safety._resolve_all_ips", return_value=["8.8.8.8"]):
        ok, reason = await is_public_http_url("https://public.example.com/")
    assert ok is True
    assert reason == ""


@pytest.mark.asyncio
async def test_is_public_http_url_handles_dns_failure() -> None:
    with patch("app.url_safety._resolve_all_ips", return_value=[]):
        ok, reason = await is_public_http_url("https://nope.invalid/")
    assert ok is False
    assert "DNS" in reason


# ---- _is_blocked_ip unit cases ----------------------------------------------


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.1",
        "192.168.0.1",
        "172.16.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
        "100.64.0.5",
        "0.0.0.0",
        "224.0.0.1",  # multicast
    ],
)
def test_is_blocked_ip_blocks(ip: str) -> None:
    assert _is_blocked_ip(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize(
    "ip",
    [
        "8.8.8.8",
        "1.1.1.1",
        "151.101.1.1",
        "2606:4700:4700::1111",
    ],
)
def test_is_blocked_ip_allows(ip: str) -> None:
    assert _is_blocked_ip(ipaddress.ip_address(ip)) is False
