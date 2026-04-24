"""Unit tests for URL/target normalization."""
from __future__ import annotations

import pytest

from app.targets import WebsiteTarget


def test_adds_https_scheme():
    t = WebsiteTarget.from_url("example.com")
    assert t.url.startswith("https://example.com")
    assert t.origin == "https://example.com"
    assert t.host == "example.com"


def test_preserves_http():
    t = WebsiteTarget.from_url("http://example.com")
    assert t.origin == "http://example.com"


def test_preserves_subdomain_and_path():
    t = WebsiteTarget.from_url("https://blog.example.com/post/1")
    assert t.host == "blog.example.com"
    assert "/post/1" in t.url


def test_strips_default_ports():
    t = WebsiteTarget.from_url("https://example.com:443/foo")
    assert ":443" not in t.origin
    t2 = WebsiteTarget.from_url("http://example.com:80")
    assert ":80" not in t2.origin


def test_preserves_custom_port():
    t = WebsiteTarget.from_url("http://localhost:8080")
    assert t.origin == "http://localhost:8080"


def test_rejects_empty():
    with pytest.raises(ValueError):
        WebsiteTarget.from_url("")


def test_rejects_no_host():
    with pytest.raises(ValueError):
        WebsiteTarget.from_url("https:///nohost")


def test_absolute_builds_url():
    t = WebsiteTarget.from_url("https://example.com")
    assert t.absolute("/robots.txt") == "https://example.com/robots.txt"
    assert t.absolute("robots.txt") == "https://example.com/robots.txt"
