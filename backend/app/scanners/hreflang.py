"""hreflang / international SEO scanner.

Why this matters for GEO:
- Google's index (which AI Overviews inherits from) uses ``hreflang`` to
  pick the right localized version of a page for a user's geo + language.
  A multi-region site without hreflang will see the wrong version surface
  in non-English locales, fragmenting brand authority across duplicates.
- AI engines that paraphrase Google's results (Perplexity, Brave Search
  AI, Gemini citations) inherit the same locale-mismatch problem.
- Bing/Copilot uses similar locale signals.

Sources:
- Google Search Central — "Tell Google about localized versions of your
  page" (https://developers.google.com/search/docs/specialized/international/localized-versions)
- IETF BCP 47 — language tag syntax
  (https://www.rfc-editor.org/info/bcp47)

What we check:
1. Whether the site appears to be **multilingual at all**. If we see no
   alternates and no other i18n signals (no language switcher, no
   ``/fr/`` ``/de/`` paths, no Content-Language) we SKIP — most sites
   are monolingual and don't need hreflang.
2. If multilingual, whether each ``<link rel="alternate" hreflang>`` tag
   carries a syntactically valid BCP 47 code (``en``, ``en-US``,
   ``zh-Hans``, ``x-default``).
3. Whether the alternate set includes ``x-default`` when 2+ languages
   are declared (Google strongly recommends it as the geo-fallback).
4. Whether each alternate URL is well-formed and absolute (relative
   hreflangs are allowed by spec but cause confusion in practice — we
   WARN, don't FAIL).

We do not (yet) verify reciprocal hreflang because that requires fetching
each alternate URL and checking its `<head>` for a back-reference. That's
N extra HTTP calls and a multi-page audit; deferred to a later gap.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ..models import CheckResult, CheckStatus

# BCP 47 language tag — primary (2-3 letter), optional script (4-letter),
# optional region (2-letter or 3-digit). Plus the special token
# ``x-default``. We deliberately accept a *subset* of the full grammar
# because the long tail of valid BCP 47 (private-use subtags, extensions)
# is essentially never seen on real sites and tools that emit it.
_BCP47_RE = re.compile(
    r"^(?:"
    r"x-default"
    r"|"
    r"[A-Za-z]{2,3}"  # primary language: en, fr, zh, gsw…
    r"(?:-[A-Za-z]{4})?"  # script: Hans, Cyrl…
    r"(?:-(?:[A-Za-z]{2}|\d{3}))?"  # region: US, 419…
    r")$"
)

# Common URL path prefixes that imply localization. Used to detect
# "this site looks multilingual but has no hreflang at all" — a real
# failure mode where AI engines pick the wrong variant.
_LOCALE_PATH_HINTS: frozenset[str] = frozenset(
    {
        "/en/", "/en-us/", "/en-gb/",
        "/fr/", "/fr-fr/", "/fr-ca/",
        "/de/", "/de-de/",
        "/es/", "/es-es/", "/es-mx/", "/es-ar/",
        "/it/", "/pt/", "/pt-br/", "/pt-pt/",
        "/nl/", "/sv/", "/no/", "/da/", "/fi/", "/pl/",
        "/ja/", "/ja-jp/",
        "/zh/", "/zh-cn/", "/zh-tw/", "/zh-hans/", "/zh-hant/",
        "/ko/", "/ko-kr/",
        "/ru/", "/ar/", "/he/", "/hi/", "/tr/", "/th/", "/vi/",
    }
)


def _is_valid_bcp47(code: str) -> bool:
    """Permissive BCP 47 validator — covers the shapes real sites emit."""
    return bool(_BCP47_RE.match(code.strip()))


def _looks_multilingual(html: str) -> tuple[bool, list[str]]:
    """Heuristic: does this site *look* multilingual even without hreflang?

    Returns (looks_multilingual, signals_found). Signals are surfaced in
    the detail when we FAIL a site for missing hreflang — so the user
    sees *why* we're flagging them rather than just "missing tags."
    """
    if not html:
        return False, []
    signals: list[str] = []
    soup = BeautifulSoup(html, "html.parser")

    # Signal 1: <html lang="..."> set to something other than English.
    html_tag = soup.find("html")
    if isinstance(html_tag, Tag):
        lang = (html_tag.get("lang") or "").strip().lower()
        # ``en`` and ``en-*`` are the implicit default; anything else is a
        # localization signal worth surfacing.
        if lang and not lang.startswith("en"):
            signals.append(f'<html lang="{lang}">')

    # Signal 2: localized URLs in the homepage's <a href> set. Most i18n
    # sites have a country/language switcher in the header or footer.
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").lower()
        if not href:
            continue
        # Pull the path component — query strings and fragments confuse the
        # match. urlparse handles both relative and absolute forms.
        try:
            path = urlparse(href).path or ""
        except ValueError:
            continue
        # Match prefixes (lang at root) and "contains" (lang switcher links).
        for hint in _LOCALE_PATH_HINTS:
            if path.startswith(hint) or hint in path:
                signals.append(f"localized link path: {hint.strip('/')}")
                break
        if len(signals) >= 4:
            break  # cap so the detail stays readable

    # Dedupe while preserving order.
    seen: set[str] = set()
    deduped: list[str] = []
    for s in signals:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    return bool(deduped), deduped


def _extract_hreflang_links(html: str) -> list[dict[str, str]]:
    """Return a list of ``{"hreflang": ..., "href": ...}`` per alternate tag.

    Only ``<link rel="alternate" hreflang>`` tags inside ``<head>`` (or at
    the document root — many sites are sloppy about that) are counted.
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict[str, str]] = []
    for link in soup.find_all("link"):
        rel = link.get("rel") or []
        if isinstance(rel, str):
            rel = rel.split()
        rel = [r.lower() for r in rel]
        if "alternate" not in rel:
            continue
        hreflang = (link.get("hreflang") or "").strip()
        if not hreflang:
            continue
        href = (link.get("href") or "").strip()
        out.append({"hreflang": hreflang, "href": href})
    return out


def check_hreflang(html: str) -> CheckResult:
    """Score the homepage's hreflang declarations.

    Logic:
    - 0 hreflang tags AND no i18n signals → SKIP (monolingual site).
    - 0 hreflang tags AND i18n signals present → FAIL (declared
      localized but didn't tell crawlers).
    - 1 hreflang tag → WARN (single alternate is uncommon; usually
      means the implementation is incomplete).
    - 2+ tags, all valid, includes ``x-default`` → PASS.
    - 2+ tags, all valid, no ``x-default`` → PASS at 0.85 with note.
    - Any invalid BCP 47 codes → WARN with the bad codes named.
    - Relative ``href`` URLs → WARN at 0.7 with note.
    """
    alternates = _extract_hreflang_links(html)
    multilingual, signals = _looks_multilingual(html)

    if not alternates and not multilingual:
        return CheckResult(
            id="hreflang",
            label="International / hreflang",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.5,
            detail=(
                "No hreflang alternates and no localized-content signals "
                "detected — this looks like a monolingual site, where "
                "hreflang doesn't apply. Skipping."
            ),
            evidence=None,
        )

    if not alternates and multilingual:
        return CheckResult(
            id="hreflang",
            label="International / hreflang",
            status=CheckStatus.FAIL,
            score=0.2,
            weight=0.5,
            detail=(
                "Site appears multilingual ("
                + ", ".join(signals[:3])
                + ") but the homepage declares no hreflang alternates. "
                "AI engines and Google will pick a single variant for all "
                "locales, fragmenting your brand authority across "
                "duplicates. Add `<link rel=\"alternate\" hreflang>` tags "
                "in <head> for every language version, plus `x-default` "
                "for the geo-fallback."
            ),
            evidence={"i18n_signals": signals},
        )

    # We have alternates — validate them.
    invalid_codes: list[str] = []
    relative_hrefs: list[str] = []
    valid_codes: list[str] = []
    has_x_default = False
    for alt in alternates:
        code = alt["hreflang"]
        if code.lower() == "x-default":
            has_x_default = True
            valid_codes.append(code)
        elif _is_valid_bcp47(code):
            valid_codes.append(code)
        else:
            invalid_codes.append(code)
        href = alt["href"]
        if href and not href.startswith(("http://", "https://", "//")):
            relative_hrefs.append(href)

    total = len(alternates)

    if total == 1:
        return CheckResult(
            id="hreflang",
            label="International / hreflang",
            status=CheckStatus.WARN,
            score=0.5,
            weight=0.5,
            detail=(
                f"Only one hreflang alternate declared "
                f"({alternates[0]['hreflang']!r}) — a single alternate "
                f"can't tell crawlers what the *other* version is. "
                f"hreflang works as a set; declare every language version "
                f"plus an `x-default`."
            ),
            evidence={"alternates": alternates},
        )

    notes: list[str] = []
    score = 1.0
    status = CheckStatus.PASS

    if invalid_codes:
        status = CheckStatus.WARN
        score = min(score, 0.6)
        notes.append(
            f"{len(invalid_codes)} alternate(s) use invalid BCP 47 codes "
            f"(e.g. {', '.join(repr(c) for c in invalid_codes[:3])}) — "
            f"crawlers ignore non-conforming codes silently"
        )

    if not has_x_default:
        score = min(score, 0.85)
        notes.append(
            "missing `x-default` — Google strongly recommends it as the "
            "fallback for users whose locale doesn't match any declared "
            "alternate"
        )

    if relative_hrefs:
        status = (
            CheckStatus.WARN if status == CheckStatus.PASS else status
        )
        score = min(score, 0.7)
        notes.append(
            f"{len(relative_hrefs)} alternate(s) use relative URLs — "
            f"the spec allows it, but absolute URLs are unambiguous and "
            f"strongly recommended"
        )

    detail = (
        f"{total} hreflang alternates declared "
        f"({len(valid_codes) - (1 if has_x_default else 0)} language "
        f"variant(s)"
        + (" + x-default" if has_x_default else "")
        + ")."
    )
    if status == CheckStatus.PASS and not notes:
        detail += (
            " AI engines and Google can serve the right locale to each "
            "user."
        )
    if notes:
        # Uppercase only the first character so proper nouns and acronyms in
        # the notes (BCP 47, Google, URLs, x-default) survive intact.
        # ``str.capitalize()`` would lowercase all of them.
        joined = "; ".join(notes)
        detail += " " + joined[0].upper() + joined[1:] + "."

    return CheckResult(
        id="hreflang",
        label="International / hreflang",
        status=status,
        score=round(score, 3),
        weight=0.5,
        detail=detail,
        evidence={
            "alternates": alternates,
            "invalid_codes": invalid_codes,
            "relative_hrefs": relative_hrefs,
            "has_x_default": has_x_default,
        },
    )
