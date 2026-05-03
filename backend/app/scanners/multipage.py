"""Multi-page sample scanner — moves the audit beyond the homepage.

GEO health is fundamentally a multi-page property. A homepage might be a
beautifully-rendered marketing page while every blog post is a thin
client-rendered shell, or the About page lacks any author signal. A single
homepage fetch makes the scan a *sample*, not an *audit*.

This module fixes the worst of that gap without turning the scan into a
crawler. We:

1. Pick at most ``_SAMPLE_LIMIT`` (default 2) extra URLs from the homepage's
   own internal navigation, ranked by how content-rich they're likely to be
   (blog index > about > pricing > docs > everything else).
2. Fetch them in parallel with the existing ``Fetcher`` (which de-dupes and
   timeouts the same way the homepage fetch does).
3. Run a stripped-down per-page summary: word count, JSON-LD presence, a
   recent ``dateModified`` / ``<time>`` signal, and outbound-citation count.
4. Aggregate into a single ``multipage_depth`` ``CheckResult`` so the report
   doesn't get overwhelmed by per-page noise — one row in Content Clarity.

This is deliberately not a full crawl. We document that in the check
``detail`` so users know what they're getting: "we sampled N pages — a real
audit would crawl your top 20 by traffic." For multi-page comparisons across
competitors, that's gap #3 (competitor baseline), not this one.

Why pick at most 2:
- Each extra fetch adds 100–500 ms to total scan time. Two pages keeps p95
  scan time under ~3 s on real-world sites we tested.
- Two is enough to catch the most common case where the homepage is
  hand-tuned but the rest of the site isn't.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urldefrag, urljoin, urlparse

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import CheckResult, CheckStatus
from ..targets import WebsiteTarget

# Hard cap on extra fetches — see module docstring.
_SAMPLE_LIMIT = 2

# Per-page word-count thresholds. <300 visible words on a content URL is
# almost always either thin or JS-rendered.
_WORD_OK = 300
_WORD_THIN = 100

# Recency window for a page's "freshness" signal. AI engines (Perplexity,
# Google AI Overviews) demonstrably prefer recent content; >365 days is
# stale enough that we don't credit it.
_FRESHNESS_DAYS = 365

# File extensions / schemes we never sample.
_SKIP_EXTENSIONS = (
    ".pdf", ".zip", ".tar", ".gz", ".jpg", ".jpeg", ".png", ".gif", ".svg",
    ".webp", ".ico", ".mp4", ".mp3", ".webm", ".css", ".js", ".json", ".xml",
    ".rss", ".atom",
)
_SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:")

# Path patterns we never sample even when they're internal — these are
# transactional / navigational chrome, not content.
_SKIP_PATH_PATTERNS = re.compile(
    r"^/(?:login|signin|sign-in|signup|sign-up|register|cart|checkout|"
    r"account|profile|search|logout|api|cdn-cgi|wp-admin|wp-login|"
    r"_next|static|assets|media|images?)(?:/|$)",
    re.IGNORECASE,
)

# Priority tiers for sampled URLs. Higher score = more likely to be picked.
# A path *starts with* one of these prefixes (case-insensitive). The first
# match wins, so order matters.
_PATH_PRIORITY: tuple[tuple[re.Pattern[str], int, str], ...] = (
    # Tier 1: editorial / dated content — richest GEO signal.
    (re.compile(r"^/(?:blog|posts?|news|articles?|insights?|stories|journal|magazine)(?:/|$)", re.IGNORECASE), 100, "blog"),
    # Tier 2: who/why — E-E-A-T.
    (re.compile(r"^/(?:about|team|company|people|authors?)(?:/|$)", re.IGNORECASE), 80, "about"),
    # Tier 3: what — product/pricing pages.
    (re.compile(r"^/(?:pricing|plans?|products?|features?|solutions?)(?:/|$)", re.IGNORECASE), 60, "product"),
    # Tier 4: docs / guides — secondary content.
    (re.compile(r"^/(?:docs?|documentation|guides?|tutorials?|help|resources?|support|learn)(?:/|$)", re.IGNORECASE), 40, "docs"),
    # Tier 5: case studies / customers — narrative content.
    (re.compile(r"^/(?:cases?|case-stud(?:y|ies)|customers?|stories)(?:/|$)", re.IGNORECASE), 30, "cases"),
)


# Princeton GEO 2024 ("GEO: Generative Engine Optimization", arXiv:2311.09735)
# found a strong citation lift on content in roughly the 1500–2500-word band:
# below ~800 words AI engines treat the page as too thin to cite as a primary
# source; above ~4000 with no sub-headings becomes a wall-of-text that's hard
# to extract sub-claims from. Thresholds below encode that finding so we can
# warn on both ends.
_DEPTH_THIN = 800           # below this is FAIL — unlikely to be cited as primary source
_DEPTH_BELOW_SWEET = 1500   # below this is WARN — passable but under sweet spot
_DEPTH_ABOVE_SWEET = 2500   # above this transitions to "long" territory
_DEPTH_LONG = 4000          # above this requires sub-headings to stay parseable
_DEPTH_MIN_SUBHEADS = 3     # >_DEPTH_LONG with fewer subheads = wall-of-text WARN

# Average adult reading speed (words per minute). Used only to render a
# friendly "~N min read" hint in the detail string.
_READING_WPM = 230


@dataclass
class _PageStats:
    """What we extract from each sampled page."""

    url: str
    fetched: bool = False
    status: int = 0
    error: str | None = None
    word_count: int = 0
    has_jsonld: bool = False
    has_recent_date: bool = False
    outbound_citations: int = 0
    subheading_count: int = 0  # h2 + h3 — used by the content_depth check
    detected_topic: str = ""  # which priority tier matched

    @property
    def per_page_score(self) -> float:
        """Normalize this page's content quality to 0..1.

        Anchors:
        - word_count below ``_WORD_THIN`` → 0.1 (broken / SPA)
        - between ``_WORD_THIN`` and ``_WORD_OK`` → 0.4 (thin)
        - at or above ``_WORD_OK`` → 0.8 baseline
        - JSON-LD adds +0.1
        - recent date adds +0.1
        Capped at 1.0.
        """
        if not self.fetched or self.error:
            return 0.0
        if self.word_count < _WORD_THIN:
            base = 0.1
        elif self.word_count < _WORD_OK:
            base = 0.4
        else:
            base = 0.8
        if self.has_jsonld:
            base += 0.1
        if self.has_recent_date:
            base += 0.1
        return min(base, 1.0)


@dataclass
class _Candidate:
    """A scored URL we may sample."""

    url: str
    score: int
    topic: str
    anchor_text: str = ""
    nav_position: int = 0  # 0-based DOM order; ties broken by earliness


def _is_sampleable_href(href: str, base_host: str, base_url: str) -> tuple[bool, str]:
    """Check whether an href is a same-host, non-asset, non-chrome URL.

    Returns (sampleable, normalized_absolute_url).
    """
    if not href:
        return False, ""
    href_stripped = href.strip()
    if not href_stripped or href_stripped.startswith("#"):
        return False, ""
    lowered = href_stripped.lower()
    if lowered.startswith(_SKIP_SCHEMES):
        return False, ""
    # Resolve to absolute and strip the URL fragment so #anchor variants
    # collapse to the same path.
    absolute = urljoin(base_url, href_stripped)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return False, ""
    if parsed.hostname != base_host:
        return False, ""
    path = parsed.path or "/"
    if path == "/" or path == "":  # the homepage itself
        return False, ""
    if any(path.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
        return False, ""
    if _SKIP_PATH_PATTERNS.match(path):
        return False, ""
    # Drop the query string for ranking purposes — but keep it on the URL we
    # actually fetch, since it can carry meaningful state. Actually, since
    # most query-string-only variants are trackers, drop them.
    canonical = f"{parsed.scheme}://{parsed.netloc}{path}"
    return True, canonical


def _path_priority(path: str) -> tuple[int, str]:
    """Return ``(score, topic)`` for a URL path."""
    for pattern, score, topic in _PATH_PRIORITY:
        if pattern.match(path):
            return score, topic
    return 10, "other"  # any same-host non-chrome page is at least slightly worth sampling


def pick_sample_urls(home_html: str, target: WebsiteTarget, limit: int = _SAMPLE_LIMIT) -> list[_Candidate]:
    """Score the homepage's internal links and return the top ``limit`` candidates.

    Deduplicates by canonical URL (path-only). Stable within a tier — earlier
    DOM order wins ties to favor primary nav over footer.
    """
    if not home_html:
        return []
    soup = BeautifulSoup(home_html, "html.parser")
    seen: dict[str, _Candidate] = {}
    for idx, anchor in enumerate(soup.find_all("a", href=True)):
        href = anchor.get("href", "")
        ok, canonical = _is_sampleable_href(href, target.host, target.url)
        if not ok:
            continue
        path = urlparse(canonical).path or "/"
        score, topic = _path_priority(path)
        anchor_text = anchor.get_text(" ", strip=True)[:80]
        prev = seen.get(canonical)
        if prev is None or score > prev.score:
            seen[canonical] = _Candidate(
                url=canonical,
                score=score,
                topic=topic,
                anchor_text=anchor_text,
                nav_position=idx,
            )
    # Sort by (score desc, nav_position asc) and keep the top ``limit`` per
    # *topic* — we want diversity, not 2 blog index pages.
    ranked = sorted(seen.values(), key=lambda c: (-c.score, c.nav_position))
    picked: list[_Candidate] = []
    seen_topics: set[str] = set()
    for cand in ranked:
        if cand.topic in seen_topics and len(picked) >= 1:
            # Skip same-topic duplicates once we have at least one page picked.
            continue
        picked.append(cand)
        seen_topics.add(cand.topic)
        if len(picked) >= limit:
            break
    return picked


# Recognize a few common dateModified / time formats. We only care whether
# *any* parseable date within the freshness window exists on the page; we
# don't need full ISO 8601 coverage.
_DATE_PATTERN = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def _has_recent_date_signal(soup: BeautifulSoup) -> bool:
    """Scan the page for a recent ``dateModified`` / ``<time datetime=...>``.

    Looks at:
    - Any ``<time datetime="...">`` tag with a parseable YYYY-MM-DD value.
    - ``<meta property="article:modified_time">`` and friends.
    - Any inline JSON-LD that contains ``dateModified`` / ``datePublished``.

    Returns True if at least one date is within ``_FRESHNESS_DAYS`` of today.
    """
    cutoff = datetime.now(UTC) - timedelta(days=_FRESHNESS_DAYS)
    candidates: list[str] = []
    for tag in soup.find_all("time"):
        dt = tag.get("datetime")
        if dt:
            candidates.append(str(dt))
    for meta_property in (
        "article:modified_time",
        "article:published_time",
        "og:updated_time",
    ):
        for meta in soup.find_all("meta", attrs={"property": meta_property}):
            content = meta.get("content")
            if content:
                candidates.append(str(content))
    # Cheap JSON-LD scan — we don't need to parse, just check the raw text.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        body = script.string or ""
        if "dateModified" in body or "datePublished" in body:
            candidates.append(body)
    for candidate in candidates:
        match = _DATE_PATTERN.search(candidate)
        if not match:
            continue
        try:
            page_date = datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3)),
                tzinfo=UTC,
            )
        except ValueError:
            continue
        if page_date >= cutoff:
            return True
    return False


def _summarize_page(html: str, base_host: str) -> tuple[int, bool, bool, int, int]:
    """Return ``(word_count, has_jsonld, has_recent_date, outbound_citations, subheadings)``.

    ``subheadings`` is the count of ``<h2>`` + ``<h3>`` tags on the page, used
    by the content-depth check to decide whether a long page is structured
    enough that AI engines can extract sub-claims from it.
    """
    if not html:
        return 0, False, False, 0, 0
    soup = BeautifulSoup(html, "html.parser")
    has_jsonld = soup.find("script", attrs={"type": "application/ld+json"}) is not None
    has_recent = _has_recent_date_signal(soup)
    # Count sub-headings before stripping anything — these survive script/style
    # decomposition anyway, but we want the count to reflect the rendered DOM.
    subheadings = len(soup.find_all(["h2", "h3"]))
    # Strip script/style/noscript before counting visible words — same rule
    # as content_clarity / js_rendering for consistency.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(" ", strip=True)
    word_count = len(visible_text.split())
    # Outbound citations — links to a different host.
    outbound = 0
    for anchor in soup.find_all("a", href=True):
        href = anchor.get("href", "").strip()
        if not href or href.startswith(_SKIP_SCHEMES) or href.startswith("#"):
            continue
        try:
            host = urlparse(href).hostname
        except ValueError:
            continue
        if host and host != base_host:
            outbound += 1
    return word_count, has_jsonld, has_recent, outbound, subheadings


async def _fetch_and_summarize(
    candidate: _Candidate, fetcher: Fetcher, base_host: str
) -> _PageStats:
    """Fetch one sampled URL and extract its summary stats."""
    stats = _PageStats(url=candidate.url, detected_topic=candidate.topic)
    try:
        result = await fetcher.get(candidate.url)
    except Exception as exc:  # noqa: BLE001 — fail-open per scanner conventions
        stats.error = str(exc)[:160]
        return stats
    stats.status = result.status
    if not result.ok:
        stats.error = result.error or f"HTTP {result.status}"
        return stats
    stats.fetched = True
    word_count, has_jsonld, has_date, citations, subheads = _summarize_page(
        result.text, base_host
    )
    stats.word_count = word_count
    stats.has_jsonld = has_jsonld
    stats.has_recent_date = has_date
    stats.outbound_citations = citations
    stats.subheading_count = subheads
    return stats


def _build_check_from_stats(
    stats_list: list[_PageStats], picked: list[_Candidate]
) -> CheckResult:
    """Aggregate per-page stats into a single user-facing CheckResult."""
    if not picked:
        return CheckResult(
            id="multipage_depth",
            label="Content depth across sampled pages",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=1.5,
            detail=(
                "No internal content links found on the homepage to sample. Either "
                "the page is a single-page app whose nav is rendered client-side, "
                "or the only links are to external sites — both are signals worth "
                "investigating, but we can't audit page depth with no candidates."
            ),
            evidence={"sampled": []},
        )

    successful = [s for s in stats_list if s.fetched and not s.error]
    if not successful:
        # All sampled pages failed to fetch — distinct failure mode from "thin".
        return CheckResult(
            id="multipage_depth",
            label="Content depth across sampled pages",
            status=CheckStatus.FAIL,
            score=0.1,
            weight=1.5,
            detail=(
                f"Tried to sample {len(stats_list)} internal page(s) "
                f"({', '.join(_short_path(s.url) for s in stats_list)}) but every "
                "fetch failed. AI crawlers will hit the same errors. "
                "Check that internal links resolve, redirects don't loop, and the "
                "site doesn't block non-browser User-Agents."
            ),
            evidence={
                "sampled": [
                    {"url": s.url, "topic": s.detected_topic, "error": s.error or "fetch failed"}
                    for s in stats_list
                ]
            },
        )

    avg_score = sum(s.per_page_score for s in successful) / len(successful)
    n = len(successful)
    thin_pages = [s for s in successful if s.word_count < _WORD_OK]
    with_jsonld = [s for s in successful if s.has_jsonld]
    with_date = [s for s in successful if s.has_recent_date]
    no_jsonld = [s for s in successful if not s.has_jsonld]
    no_date = [s for s in successful if not s.has_recent_date]

    # ``signal_summary`` describes what we *actually* observed on these pages,
    # without overclaiming. avg_score >= 0.85 only guarantees "substantive on
    # average," not "every page has every signal" — see PR #15 review:
    # https://github.com/LindaHaviv/agentgeoscore/pull/15#discussion_r3178406411
    # So we report counts, not categorical claims like "all show ...".
    signal_summary = (
        f"{n - len(thin_pages)}/{n} substantive (\u2265{_WORD_OK} words), "
        f"{len(with_jsonld)}/{n} with JSON-LD, {len(with_date)}/{n} with a recent date"
    )

    if avg_score >= 0.85:
        status = CheckStatus.PASS
        detail = (
            f"Sampled {n} internal page(s) ({_describe_sample(successful)}). "
            f"{signal_summary}. AI crawlers will see depth across the site, "
            f"not just the homepage."
        )
    elif avg_score >= 0.4:
        status = CheckStatus.WARN
        gaps: list[str] = []
        if thin_pages:
            gaps.append(f"{len(thin_pages)}/{n} page(s) under {_WORD_OK} words")
        if no_jsonld:
            gaps.append(f"{len(no_jsonld)}/{n} page(s) without JSON-LD")
        if no_date:
            gaps.append(f"{len(no_date)}/{n} page(s) without a recent dateModified")
        detail = (
            f"Sampled {n} internal page(s) ({_describe_sample(successful)}). "
            f"The homepage may be polished, but depth is uneven: "
            f"{', '.join(gaps) if gaps else 'mixed signals'}. "
            f"AI engines weight site-wide consistency \u2014 invest in the same rigor "
            f"on content pages."
        )
    else:
        status = CheckStatus.FAIL
        detail = (
            f"Sampled {n} internal page(s) ({_describe_sample(successful)}) \u2014 "
            f"{signal_summary}. They're either very thin (<{_WORD_THIN} words) or "
            f"missing structured data and dates entirely. If your homepage is the "
            f"only substantive page, AI engines have nothing to cite beyond a "
            f"single URL. Heuristic \u2014 we sample at most {_SAMPLE_LIMIT} "
            f"page(s); a full audit would crawl your top 20 by traffic."
        )

    evidence = {
        "sampled": [
            {
                "url": s.url,
                "topic": s.detected_topic,
                "word_count": s.word_count,
                "has_jsonld": s.has_jsonld,
                "has_recent_date": s.has_recent_date,
                "outbound_citations": s.outbound_citations,
                **({"error": s.error} if s.error else {}),
            }
            for s in stats_list
        ],
        "avg_score": round(avg_score, 3),
    }

    return CheckResult(
        id="multipage_depth",
        label="Content depth across sampled pages",
        status=status,
        score=round(avg_score, 3),
        weight=1.5,
        detail=detail,
        evidence=evidence,
    )


def _short_path(url: str) -> str:
    """Render a URL as just its path for compact display."""
    try:
        return urlparse(url).path or url
    except ValueError:
        return url


def _describe_sample(stats: list[_PageStats]) -> str:
    return ", ".join(_short_path(s.url) for s in stats)


def _content_depth_skip(detail: str) -> CheckResult:
    """Skip-status placeholder for the content_depth row.

    Used when there's nothing meaningful to evaluate (no sampled pages, every
    sample failed, etc.). We still emit the row so users see *why* the signal
    is missing rather than wondering whether it ran at all.
    """
    return CheckResult(
        id="content_depth",
        label="Article-length signal on content pages",
        status=CheckStatus.SKIP,
        score=0.0,
        weight=1.5,
        detail=detail,
        evidence=None,
    )


def _build_content_depth_check(stats_list: list[_PageStats]) -> CheckResult:
    """Score the deepest sampled page against Princeton's word-count band.

    We pick the *longest* successfully-fetched page rather than averaging,
    because GEO citation behaviour rewards having at least one substantive
    page on the site — a thin homepage + one 1800-word blog post is enough
    to start getting cited. Averaging would punish that pattern.
    """
    successful = [s for s in stats_list if s.fetched and not s.error]
    if not successful:
        return _content_depth_skip(
            "No sampled content page was reachable, so we can't score article "
            "length yet. Fix the multi-page sample issue above first — once a "
            "content URL fetches cleanly we'll measure word count and "
            "sub-heading structure here."
        )

    deepest = max(successful, key=lambda s: s.word_count)
    words = deepest.word_count
    subheads = deepest.subheading_count
    minutes = max(1, round(words / _READING_WPM))
    where = _short_path(deepest.url)

    if words < _DEPTH_THIN:
        status = CheckStatus.FAIL
        score = 0.15
        detail = (
            f"Deepest sampled page ({where}) is only {words} words — below the "
            f"~{_DEPTH_THIN}-word floor where AI engines start treating a page "
            f"as a primary source. Princeton's GEO 2024 study found the "
            f"1500–2500-word band gets cited disproportionately. Aim to grow "
            f"your flagship content page to at least {_DEPTH_BELOW_SWEET} words "
            f"of substantive text (not boilerplate)."
        )
    elif words < _DEPTH_BELOW_SWEET:
        status = CheckStatus.WARN
        score = 0.55
        detail = (
            f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
            f"— readable but under Princeton's 1500–2500-word citation sweet "
            f"spot. Consider expanding flagship pages with concrete examples, "
            f"data, and answered sub-questions until they sit in that band."
        )
    elif words <= _DEPTH_ABOVE_SWEET:
        status = CheckStatus.PASS
        score = 1.0
        detail = (
            f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
            f"— inside Princeton's 1500–2500-word citation sweet spot. AI engines "
            f"are likeliest to cite pages in this depth band as primary sources."
        )
    elif words <= _DEPTH_LONG:
        # 2501–4000: long-but-not-yet-wall-of-text. Split on sub-heading
        # density the same way the >_DEPTH_LONG branch does — without H2/H3
        # structure even a 3500-word page is hard for AI engines to extract
        # sub-claims from, so don't claim it's "well-structured" if it isn't.
        if subheads >= _DEPTH_MIN_SUBHEADS:
            status = CheckStatus.PASS
            score = 0.85
            detail = (
                f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
                f"— above Princeton's 1500–2500-word sweet spot but still well-structured "
                f"with {subheads} sub-heading(s). AI engines can extract sub-claims as "
                f"long as the page stays scannable."
            )
        else:
            status = CheckStatus.WARN
            score = 0.55
            detail = (
                f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
                f"with only {subheads} sub-heading(s) — above Princeton's 1500–2500-word "
                f"sweet spot but lacking the H2/H3 structure that lets AI engines extract "
                f"discrete sub-claims. Add at least {_DEPTH_MIN_SUBHEADS} sub-headings, or "
                f"trim to land inside the sweet spot."
            )
    else:
        # > _DEPTH_LONG — split on subheading density.
        if subheads >= _DEPTH_MIN_SUBHEADS:
            status = CheckStatus.PASS
            score = 0.7
            detail = (
                f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
                f"— long-form, but {subheads} sub-headings keep it parseable. AI "
                f"engines can still extract sub-claims. Consider whether splitting "
                f"into a series would lift each piece into Princeton's 1500–2500-word "
                f"sweet spot."
            )
        else:
            status = CheckStatus.WARN
            score = 0.4
            detail = (
                f"Deepest sampled page ({where}) is {words} words (~{minutes} min read) "
                f"with only {subheads} sub-heading(s) — a wall-of-text. AI engines "
                f"struggle to extract discrete sub-claims from long pages without "
                f"H2/H3 structure. Add at least {_DEPTH_MIN_SUBHEADS} sub-headings, "
                f"or split into separate posts so each piece sits in Princeton's "
                f"1500–2500-word sweet spot."
            )

    evidence = {
        "deepest_url": deepest.url,
        "word_count": words,
        "subheading_count": subheads,
        "reading_minutes": minutes,
        "sweet_spot": [_DEPTH_BELOW_SWEET, _DEPTH_ABOVE_SWEET],
        "thin_threshold": _DEPTH_THIN,
        "long_threshold": _DEPTH_LONG,
        "sampled_word_counts": [
            {"url": s.url, "word_count": s.word_count, "subheadings": s.subheading_count}
            for s in successful
        ],
    }
    return CheckResult(
        id="content_depth",
        label="Article-length signal on content pages",
        status=status,
        score=round(score, 3),
        weight=1.5,
        detail=detail,
        evidence=evidence,
    )


async def check_multipage_depth(
    target: WebsiteTarget, fetcher: Fetcher, home_html: str
) -> list[CheckResult]:
    """Run the multi-page sample audit. Returns the depth row + content_depth row.

    The content-depth check shares the multi-page sampler's fetches — it
    inspects the deepest of the same pages — so we don't pay for any extra
    HTTP traffic to add the article-length signal.
    """
    if not home_html:
        return [
            CheckResult(
                id="multipage_depth",
                label="Content depth across sampled pages",
                status=CheckStatus.SKIP,
                score=0.0,
                weight=1.5,
                detail="Homepage fetch failed; can't sample internal pages.",
                evidence=None,
            ),
            _content_depth_skip(
                "Homepage fetch failed; can't measure article length on inner pages."
            ),
        ]
    picked = pick_sample_urls(home_html, target)
    if not picked:
        return [
            _build_check_from_stats([], []),
            _content_depth_skip(
                "No sampled content page available — see the multi-page row above. "
                "Article length is measured on the same pages we sample for depth."
            ),
        ]
    stats = await asyncio.gather(
        *(_fetch_and_summarize(c, fetcher, target.host) for c in picked),
        return_exceptions=False,
    )
    stats_list = list(stats)
    return [
        _build_check_from_stats(stats_list, picked),
        _build_content_depth_check(stats_list),
    ]
