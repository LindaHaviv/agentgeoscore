"""Shared helpers for citation probes."""
from __future__ import annotations

from urllib.parse import urlparse


def host_matches(url: str, host: str) -> bool:
    """Return True iff `url`'s host is `host` or a subdomain of it.

    Uses real URL parsing — NOT substring containment — so scanning
    `box.com` doesn't falsely match `dropbox.com`, `ai.com` doesn't match
    `openai.com`, etc. `www.` is stripped from both sides.

    Falsy inputs return False.
    """
    if not url or not host:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    url_host = (parsed.netloc or "").lower().split(":", 1)[0].removeprefix("www.")
    host_norm = host.lower().removeprefix("www.")
    if not url_host or not host_norm:
        return False
    return url_host == host_norm or url_host.endswith("." + host_norm)
