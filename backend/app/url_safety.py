"""URL safety helpers — SSRF guard.

The scan pipeline accepts URLs from the public internet (anyone hitting
``/api/scan`` can submit any URL). The fetcher then GETs that URL, follows
redirects, and exposes selected slices of the response body back through
the report. Without a guard, this is a textbook SSRF channel:

* ``http://localhost:8080/admin`` → reach internal services on the box
* ``http://169.254.169.254/`` → cloud-provider metadata services (Fly does
  not currently expose AWS-style metadata, but other deploy targets do)
* ``http://*.internal``, ``http://*.flycast`` → reach Fly's internal mesh
* ``http://10.0.0.5/`` / ``http://192.168.1.1/`` / ``http://127.0.0.1/``
  → RFC 1918, loopback
* a public 302 redirect → any of the above (redirect-based bypass)

We mitigate by:

1. Rejecting non ``http``/``https`` schemes outright.
2. Rejecting non-default ports (only 80/443 are allowed; we don't scan
   sites on weird ports as part of the GEO model anyway).
3. Resolving the hostname and rejecting if *any* returned IP is private,
   loopback, link-local, multicast, reserved, or in CGNAT space.
4. Re-running the same check on every redirect target before following.

Known limitation — DNS rebinding: an attacker who controls a DNS server
with a very short TTL could return a public IP at validation time and a
private IP at fetch time. Pinning the resolved IP through to the actual
HTTP connection (via custom transport) is the bulletproof fix; we note it
here and accept the residual risk for a public-internet GEO auditor.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

# 100.64.0.0/10 — Carrier-grade NAT (RFC 6598). Not flagged as ``is_private``
# by Python's ipaddress module on older versions, so we check explicitly.
_CGNAT_NETWORK_V4 = ipaddress.ip_network("100.64.0.0/10")

# Allowed ports per scheme. We never need anything else for a GEO scan.
_ALLOWED_HTTP_PORTS = {80}
_ALLOWED_HTTPS_PORTS = {443}


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if ``ip`` is in any range we refuse to fetch from."""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK_V4:
        return True
    return False


def _validate_scheme_and_port(url: str) -> tuple[bool, str]:
    """Sync part of the check. Returns ``(hostname, "")`` on pass, ``("", reason)`` on fail."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return "", "unparseable URL"

    if parsed.scheme not in ("http", "https"):
        return "", f"scheme {parsed.scheme!r} not allowed"

    hostname = parsed.hostname
    if not hostname:
        return "", "missing hostname"

    # Reject inputs that are bare IPs (literal v4/v6) — also caught by the
    # async DNS step below, but rejecting up-front gives a clearer error and
    # avoids a needless DNS round-trip for the most common bypass attempts
    # (``http://127.0.0.1``, ``http://[::1]``, etc.).
    try:
        as_ip = ipaddress.ip_address(hostname)
    except ValueError:
        as_ip = None
    if as_ip is not None and _is_blocked_ip(as_ip):
        return "", f"literal private IP {hostname!r}"

    port = parsed.port
    if port is not None:
        if parsed.scheme == "http" and port not in _ALLOWED_HTTP_PORTS:
            return "", f"port {port} not allowed for http"
        if parsed.scheme == "https" and port not in _ALLOWED_HTTPS_PORTS:
            return "", f"port {port} not allowed for https"

    return hostname, ""


async def _resolve_all_ips(hostname: str) -> list[str]:
    """Async DNS resolution. Returns all addresses (v4 + v6) for ``hostname``.

    Uses the running event loop's resolver so we don't block in async
    context. Returns ``[]`` if resolution fails.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        return []
    addrs: list[str] = []
    for info in infos:
        sockaddr = info[4]
        if sockaddr:
            addrs.append(sockaddr[0])
    return addrs


async def is_public_http_url(url: str) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ``ok=True`` means safe to fetch.

    On rejection, ``reason`` is a short human-readable string suitable for
    surfacing in error logs / FetchResult.error (does NOT need to be safe
    to round-trip back to the user verbatim — callers should not echo
    arbitrary URLs into HTML, but the share endpoint already sanitizes
    independently).
    """
    hostname, reason = _validate_scheme_and_port(url)
    if reason:
        return False, reason

    ips = await _resolve_all_ips(hostname)
    if not ips:
        return False, f"DNS resolution failed for {hostname!r}"

    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"unparseable resolved address {ip_str!r}"
        if _is_blocked_ip(ip):
            return False, f"hostname {hostname!r} resolves to non-public {ip_str}"

    return True, ""
