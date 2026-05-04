"""Tests for the hreflang / international SEO scanner."""
from __future__ import annotations

import pytest

from app.models import CheckStatus
from app.scanners.hreflang import (
    _extract_hreflang_links,
    _is_valid_bcp47,
    _looks_multilingual,
    check_hreflang,
)

# ---- Fixtures -------------------------------------------------------------


def _page(head: str = "", body: str = "", html_lang: str = "en") -> str:
    return (
        f'<!doctype html><html lang="{html_lang}"><head>{head}</head>'
        f"<body>{body}</body></html>"
    )


def _alt(hreflang: str, href: str) -> str:
    return f'<link rel="alternate" hreflang="{hreflang}" href="{href}" />'


# ---- _is_valid_bcp47 ------------------------------------------------------


@pytest.mark.parametrize(
    "code,expected",
    [
        ("en", True),
        ("fr", True),
        ("zh", True),
        ("EN", True),  # Case-insensitive primary tag is allowed
        ("en-US", True),
        ("en-GB", True),
        ("fr-CA", True),
        ("zh-Hans", True),
        ("zh-Hans-CN", True),
        ("es-419", True),  # 3-digit UN region code
        ("x-default", True),
        ("", False),
        ("english", False),  # 4 letters in primary
        ("en-USA", False),  # 3-letter region
        ("en-12", False),  # 2-digit region
        ("en_US", False),  # underscore separator
    ],
)
def test_is_valid_bcp47(code: str, expected: bool) -> None:
    assert _is_valid_bcp47(code) is expected


# ---- _looks_multilingual --------------------------------------------------


def test_monolingual_english_site_does_not_look_multilingual() -> None:
    html = _page(
        body='<a href="/about">About</a><a href="/blog">Blog</a>',
        html_lang="en",
    )
    is_multi, signals = _looks_multilingual(html)
    assert is_multi is False
    assert signals == []


def test_html_lang_non_english_is_multilingual_signal() -> None:
    html = _page(html_lang="fr")
    is_multi, signals = _looks_multilingual(html)
    assert is_multi is True
    assert any('lang="fr"' in s for s in signals)


def test_localized_url_paths_in_links_are_multilingual_signal() -> None:
    html = _page(
        body=(
            '<a href="/fr/produits">Français</a>'
            '<a href="/de/produkte">Deutsch</a>'
            '<a href="/about">About</a>'
        ),
        html_lang="en",
    )
    is_multi, signals = _looks_multilingual(html)
    assert is_multi is True
    assert any("fr" in s for s in signals)


# ---- _extract_hreflang_links ----------------------------------------------


def test_extract_hreflang_skips_non_alternate_links() -> None:
    html = _page(
        head=(
            '<link rel="canonical" href="https://x.com/" />'
            '<link rel="alternate" hreflang="fr" href="https://x.com/fr/" />'
            '<link rel="stylesheet" href="/x.css" />'
        )
    )
    links = _extract_hreflang_links(html)
    assert len(links) == 1
    assert links[0]["hreflang"] == "fr"


def test_extract_hreflang_ignores_alternate_without_hreflang_attr() -> None:
    """A `<link rel="alternate" type="application/rss+xml">` is a feed
    declaration, not an hreflang declaration. Don't count it."""
    html = _page(
        head=(
            '<link rel="alternate" type="application/rss+xml" href="/feed.xml" />'
            '<link rel="alternate" hreflang="en" href="https://x.com/" />'
        )
    )
    links = _extract_hreflang_links(html)
    assert len(links) == 1
    assert links[0]["hreflang"] == "en"


# ---- check_hreflang end-to-end --------------------------------------------


def test_skip_when_monolingual_with_no_alternates() -> None:
    html = _page(
        body='<a href="/about">About</a>',
        html_lang="en",
    )
    result = check_hreflang(html)
    assert result.status == CheckStatus.SKIP
    assert "monolingual" in result.detail.lower()
    assert result.score == 0.0


def test_fail_when_multilingual_signals_but_no_hreflang() -> None:
    """The most common real failure: site has /fr/ /de/ paths in nav but
    forgot to declare hreflang. Localized variants compete with each other
    for the same keywords in Google's index."""
    html = _page(
        body=(
            '<a href="/fr/produits">FR</a>'
            '<a href="/de/produkte">DE</a>'
            '<a href="/es/productos">ES</a>'
        ),
        html_lang="en",
    )
    result = check_hreflang(html)
    assert result.status == CheckStatus.FAIL
    assert result.score == pytest.approx(0.2)
    assert "no hreflang" in result.detail.lower()
    assert result.evidence is not None
    assert result.evidence["i18n_signals"]


def test_pass_with_complete_hreflang_set_including_x_default() -> None:
    head = (
        _alt("en", "https://x.com/")
        + _alt("fr", "https://x.com/fr/")
        + _alt("de", "https://x.com/de/")
        + _alt("x-default", "https://x.com/")
    )
    result = check_hreflang(_page(head=head))
    assert result.status == CheckStatus.PASS
    assert result.score == pytest.approx(1.0)
    assert result.evidence is not None
    assert result.evidence["has_x_default"] is True


def test_pass_at_85_when_x_default_missing() -> None:
    head = (
        _alt("en", "https://x.com/")
        + _alt("fr", "https://x.com/fr/")
        + _alt("de", "https://x.com/de/")
    )
    result = check_hreflang(_page(head=head))
    assert result.status == CheckStatus.PASS
    assert result.score == pytest.approx(0.85)
    assert "x-default" in result.detail.lower()


def test_warn_when_only_one_alternate_declared() -> None:
    head = _alt("fr", "https://x.com/fr/")
    result = check_hreflang(_page(head=head))
    assert result.status == CheckStatus.WARN
    assert "only one" in result.detail.lower()


def test_warn_when_invalid_bcp47_codes_present() -> None:
    head = (
        _alt("en", "https://x.com/")
        + _alt("english", "https://x.com/en/")  # bogus code
        + _alt("de_DE", "https://x.com/de/")  # underscore not allowed
        + _alt("x-default", "https://x.com/")
    )
    result = check_hreflang(_page(head=head))
    assert result.status == CheckStatus.WARN
    assert result.evidence is not None
    assert set(result.evidence["invalid_codes"]) == {"english", "de_DE"}


def test_warn_when_alternates_use_relative_urls() -> None:
    """The spec allows relative hrefs but Google strongly recommends
    absolute. Warn rather than fail."""
    head = (
        _alt("en", "/")
        + _alt("fr", "/fr/")
        + _alt("de", "/de/")
        + _alt("x-default", "/")
    )
    result = check_hreflang(_page(head=head))
    assert result.status == CheckStatus.WARN
    assert result.evidence is not None
    assert len(result.evidence["relative_hrefs"]) == 4


def test_protocol_relative_hreflang_urls_are_treated_as_absolute() -> None:
    """`//example.com/x` is protocol-relative — browsers and crawlers treat
    it as absolute. Don't flag as relative."""
    head = (
        _alt("en", "//x.com/")
        + _alt("fr", "//x.com/fr/")
        + _alt("x-default", "//x.com/")
    )
    result = check_hreflang(_page(head=head))
    assert result.evidence is not None
    assert result.evidence["relative_hrefs"] == []


def test_x_default_is_not_counted_as_a_language_variant() -> None:
    """Detail should report N language variants + x-default, not N+1
    variants. Verifies the human-readable copy doesn't mislead."""
    head = (
        _alt("en", "https://x.com/")
        + _alt("fr", "https://x.com/fr/")
        + _alt("x-default", "https://x.com/")
    )
    result = check_hreflang(_page(head=head))
    assert "2 language variant" in result.detail
    assert "+ x-default" in result.detail
