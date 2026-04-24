"""Target abstraction. v1: websites. v2: app stores, etc.

Targets normalize the input (a URL, an app id, etc.) and provide a standard
interface that scanners + probes can query. Adding new target types in v2
doesn't require touching the scoring engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse


@dataclass
class WebsiteTarget:
    """A public website identified by its origin URL."""

    raw_url: str
    url: str  # normalized
    origin: str  # scheme://host
    host: str

    @classmethod
    def from_url(cls, raw_url: str) -> WebsiteTarget:
        raw = raw_url.strip()
        if not raw:
            raise ValueError("URL is empty")
        if "://" not in raw:
            raw = "https://" + raw
        parsed = urlparse(raw)
        if not parsed.netloc:
            raise ValueError(f"Invalid URL: {raw_url}")
        scheme = parsed.scheme or "https"
        # Strip default ports, lowercase host
        host = parsed.hostname or ""
        netloc = host
        if parsed.port and not (
            (scheme == "https" and parsed.port == 443)
            or (scheme == "http" and parsed.port == 80)
        ):
            netloc = f"{host}:{parsed.port}"
        path = parsed.path or "/"
        normalized = urlunparse((scheme, netloc, path, "", parsed.query, ""))
        origin = f"{scheme}://{netloc}"
        return cls(raw_url=raw_url, url=normalized, origin=origin, host=host)

    def absolute(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.origin}{path}"
