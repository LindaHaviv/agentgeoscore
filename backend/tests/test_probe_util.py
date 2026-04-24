"""Tests for probes._util.host_matches — guards against the substring false
positive (e.g. `box.com` matching `dropbox.com`) caught by Devin Review."""
from __future__ import annotations

import pytest

from app.probes._util import host_matches


@pytest.mark.parametrize("url, host, expected", [
    # Exact host match
    ("https://box.com/page", "box.com", True),
    ("https://box.com/page", "BOX.COM", True),
    ("https://box.com/page", "www.box.com", True),
    ("https://www.box.com/page", "box.com", True),
    # Subdomain matches
    ("https://blog.box.com/post", "box.com", True),
    ("https://a.b.box.com/x", "box.com", True),
    # The false-positives we want to reject
    ("https://dropbox.com/page", "box.com", False),
    ("https://openai.com/docs", "ai.com", False),
    ("https://snapchat.com/x", "chat.com", False),
    ("https://notbox.com/x", "box.com", False),
    # Different TLD
    ("https://box.co/page", "box.com", False),
    ("https://box.com.evil.com/", "box.com", False),
    # Path/query containing the host name shouldn't match either
    ("https://google.com/search?q=box.com", "box.com", False),
    ("https://google.com/url?u=https://box.com/", "box.com", False),
    # Malformed / falsy
    ("", "box.com", False),
    ("https://box.com", "", False),
    ("not a url", "box.com", False),
])
def test_host_matches(url: str, host: str, expected: bool) -> None:
    assert host_matches(url, host) is expected
