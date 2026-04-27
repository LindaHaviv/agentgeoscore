"""Citability scanner — content-level signals correlated with AI-agent citations.

Most checks here are grounded in the Princeton/IIT-Delhi *Generative Engine
Optimization* paper (Aggarwal et al., KDD 2024, arXiv:2311.09735), which
empirically tested 9 content modifications on a 10K-query benchmark and on
Perplexity. The high-impact verified modifications were:

  - Cite Sources         → outbound citations to authoritative external content
  - Quotation Addition   → use blockquotes / inline quotations
  - Statistics Addition  → numbers with units in body content

Vendor-confirmed gates / E-E-A-T signals layered on top:

  - Visible "Updated [date]" line  → Schema.org / Google AI Overviews freshness
  - Author byline that links out   → Google E-E-A-T canonical (author authority)
  - Transcripts on video/audio     → media is otherwise unindexable by LLMs
  - Question-as-H2 "fan-out"       → aligns with RAG chunking (weak evidence; minor)

Each check SKIPs on pages where it doesn't apply (e.g. transcripts SKIP if no
media is present, byline-links SKIPs if no byline indicator) so a marketing
homepage isn't penalized for not being a blog post.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ..models import CheckResult, CheckStatus

# Tunable thresholds — kept conservative so we don't punish legit sites.
_MIN_CITATIONS_PASS = 3
_MIN_CITATIONS_WARN = 1
_MIN_STATS_PASS = 4
_MIN_STATS_WARN = 1
_MIN_QUESTION_HEADINGS_PASS = 2
_MIN_QUESTION_HEADINGS_WARN = 1
_MIN_BODY_WORDS_FOR_DENSITY_CHECKS = 80

# Numbers we consider "statistics": digits attached to a unit, percent, currency,
# multiplier suffix, or year/date pattern. Bare digits (e.g. an address number)
# don't count.
_STAT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d+(?:\.\d+)?\s?%"),                           # 12% / 12.5 %
    re.compile(r"[$€£¥]\s?\d[\d,]*(?:\.\d+)?(?:[KMB]| ?(?:billion|million|thousand))?", re.I),
    re.compile(r"\d+(?:\.\d+)?\s?(?:K|M|B)\b"),                 # 5K, 1.2M, 3B
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:billion|million|thousand|trillion)\b", re.I),
    re.compile(r"\b\d+x\b", re.I),                              # 10x
    re.compile(r"\b(?:19|20)\d{2}\b"),                          # year tokens
    re.compile(r"\b\d{1,3}(?:,\d{3})+\b"),                      # 1,234,567
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:ms|s|min|hr|hours?|days?|years?|months?|weeks?)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s?(?:GB|MB|KB|TB|PB|Hz|MHz|GHz|kg|lb|m|km|mi|ft)\b", re.I),
)

_QUESTION_WORDS = ("how", "what", "why", "when", "where", "who", "which", "can", "should", "is", "are", "do", "does", "will")

_UPDATED_LINE = re.compile(
    r"\b(?:last\s+updated|updated|last\s+modified|modified|revised|"
    r"edited|last\s+edited|published)\s*[:.\-]?\s*"
    r"(?:on\s+)?"
    r"(?:"
    r"[A-Za-z]+\s+\d{1,2},?\s+\d{4}"          # April 22, 2026
    r"|\d{1,2}\s+[A-Za-z]+\s+\d{4}"           # 22 April 2026 (Wikipedia, EU)
    r"|\d{4}-\d{2}-\d{2}"                      # 2026-04-22
    r"|\d{1,2}/\d{1,2}/\d{2,4}"                # 4/22/2026
    r")",
    re.I,
)

_TRANSCRIPT_HINT = re.compile(r"\b(?:transcript|captions?|subtitles?)\b", re.I)

_MEDIA_HOSTS = ("youtube.com", "youtu.be", "vimeo.com", "wistia.com", "loom.com", "spotify.com", "anchor.fm", "soundcloud.com")


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
    except (ValueError, TypeError):
        return ""
    return host.lower().lstrip(".")


def _registered(host: str) -> str:
    """Best-effort registered-domain extractor (last two labels).

    Avoids treating ``docs.example.com`` and ``example.com`` as different
    domains for outbound-citation counting.
    """
    if not host:
        return ""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    return ".".join(parts[-2:])


def _main_container(soup: BeautifulSoup) -> Tag:
    """Pick the substantive content container.

    Prefer ``<article>``, fall back to ``<main>``, then ``<body>``. Heuristic:
    article-shaped content usually lives in those tags; counting outbound
    citations across an entire homepage's nav/footer would inflate scores.
    """
    article = soup.find("article")
    if article and len(article.get_text(strip=True)) > 200:
        return article
    main = soup.find("main")
    if main and len(main.get_text(strip=True)) > 200:
        return main
    body = soup.find("body")
    return body or soup


def _has_article_jsonld(jsonld_blocks: list[dict]) -> bool:
    """Walk the entire JSON-LD graph for any Article-type node.

    Articles are commonly nested (CMS pattern: ``{"@type":"WebPage",
    "mainEntity":{"@type":"Article",...}}``). Top-level-only checks would
    incorrectly miss those and SKIP the freshness check downstream.
    """
    article_types = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "ScholarlyArticle", "Report"}

    def walk(node) -> bool:
        if isinstance(node, dict):
            t = node.get("@type")
            if isinstance(t, str) and t in article_types:
                return True
            if isinstance(t, list) and any(x in article_types for x in t):
                return True
            return any(walk(v) for v in node.values())
        if isinstance(node, list):
            return any(walk(item) for item in node)
        return False

    return any(walk(block) for block in jsonld_blocks)


def _find_persons(jsonld_blocks: list[dict]) -> list[dict]:
    """Return all Person nodes present anywhere in the JSON-LD graph."""
    out: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            t = node.get("@type")
            if t == "Person" or (isinstance(t, list) and "Person" in t):
                out.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for block in jsonld_blocks:
        walk(block)
    return out


def _sameas_count(person: dict) -> int:
    sa = person.get("sameAs")
    if isinstance(sa, list):
        return len([x for x in sa if isinstance(x, str) and x.strip()])
    if isinstance(sa, str) and sa.strip():
        return 1
    return 0


def _date_modified_strings(jsonld_blocks: list[dict]) -> list[str]:
    out: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for key in ("dateModified", "datePublished"):
                v = node.get(key)
                if isinstance(v, str) and v.strip():
                    out.append(v.strip())
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for block in jsonld_blocks:
        walk(block)
    return out


def _byline_anchor(soup: BeautifulSoup) -> Tag | None:
    """Return an ``<a>`` element that looks like a byline link, or None."""
    # rel=author is the canonical signal
    a = soup.find("a", attrs={"rel": "author"})
    if a:
        return a
    # itemprop=author with an inner anchor
    for el in soup.find_all(attrs={"itemprop": "author"}):
        inner = el.find("a") if isinstance(el, Tag) else None
        if inner and inner.get("href"):
            return inner
        if isinstance(el, Tag) and el.name == "a" and el.get("href"):
            return el
    # Common class names — kept tight to avoid false positives
    selectors = (
        ".byline a[href]",
        ".author a[href]",
        ".post-author a[href]",
        ".article-author a[href]",
        "a.author[href]",
        "a.byline[href]",
    )
    for sel in selectors:
        try:
            found = soup.select_one(sel)
        except (ValueError, NotImplementedError):
            continue
        if found:
            return found
    return None


def _has_byline_text(soup: BeautifulSoup) -> bool:
    """True if the page mentions a byline anywhere (even if not linked)."""
    if soup.find(attrs={"itemprop": "author"}):
        return True
    if soup.find(class_=re.compile(r"\bbyline\b", re.I)):
        return True
    if soup.find(class_=re.compile(r"\bauthor\b", re.I)):
        return True
    if soup.find("meta", attrs={"name": re.compile(r"^author$", re.I)}):
        return True
    if soup.find("meta", attrs={"property": "article:author"}):
        return True
    return False


def _detect_media(soup: BeautifulSoup) -> list[str]:
    """Return labels of detected video/audio elements (for evidence)."""
    found: list[str] = []
    for tag in soup.find_all(["video", "audio"]):
        found.append(tag.name)
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src") or ""
        host = _domain_of(src)
        if any(host.endswith(h) for h in _MEDIA_HOSTS):
            found.append(host)
    return found


def _has_transcript(soup: BeautifulSoup, container: Tag) -> bool:
    """Heuristic: does this page provide a transcript for its media?

    Signals (any one is sufficient):
      1. ``<track kind="captions">`` or ``kind="subtitles"`` on a ``<video>``
      2. A link/heading whose visible text contains "transcript"
      3. A ``<details>`` block with summary mentioning "transcript"
    """
    for track in soup.find_all("track"):
        kind = (track.get("kind") or "").lower()
        if kind in ("captions", "subtitles"):
            return True
    # Anchor / heading / button labelled "transcript"
    for tag in container.find_all(["a", "h2", "h3", "h4", "button", "summary"]):
        text = tag.get_text(" ", strip=True)
        if text and _TRANSCRIPT_HINT.search(text):
            return True
    return False


def check_citability(html: str, jsonld_blocks: list[dict]) -> list[CheckResult]:
    """Run the citability checks. Pass already-parsed JSON-LD to avoid reparsing."""
    results: list[CheckResult] = []
    if not html:
        return results

    soup = BeautifulSoup(html, "lxml")
    # Strip script/style/noscript so they don't inflate stats counts.
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    container = _main_container(soup)
    body_text = container.get_text(" ", strip=True)
    word_count = len(body_text.split())
    page_host = _registered(_domain_of(_first_canonical(soup) or ""))

    # 1. Outbound citations density (Princeton paper: "Cite Sources" — top winner)
    results.append(_check_outbound_citations(container, page_host, word_count))

    # 2. Statistics density (Princeton: "Statistics Addition")
    results.append(_check_statistics(body_text, word_count))

    # 3. Quotation density (Princeton: "Quotation Addition")
    results.append(_check_quotations(container, word_count))

    # 4. Fan-out H2 questions (RAG chunking proxy)
    results.append(_check_fanout_questions(soup))

    # 5. Visible "Updated …" line
    results.append(_check_visible_updated(soup, body_text, jsonld_blocks))

    # 6. Author byline links to a real author page
    results.append(_check_byline_links(soup, jsonld_blocks))

    # 7. Transcripts for video/audio
    results.append(_check_transcripts(soup, container))

    return results


def _first_canonical(soup: BeautifulSoup) -> str:
    can = soup.find("link", rel="canonical")
    if can and can.get("href"):
        return can["href"]
    og_url = soup.find("meta", attrs={"property": "og:url"})
    if og_url and og_url.get("content"):
        return og_url["content"]
    return ""


def _check_outbound_citations(container: Tag, page_host: str, word_count: int) -> CheckResult:
    if word_count < _MIN_BODY_WORDS_FOR_DENSITY_CHECKS:
        return CheckResult(
            id="outbound_citations",
            label="Outbound citations to authoritative sources",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=1.5,
            detail="Page has too little body text to evaluate citation density (try a blog post or article URL).",
        )
    seen: set[str] = set()
    examples: list[str] = []
    for a in container.find_all("a", href=True):
        href = a["href"].strip()
        if not href.startswith(("http://", "https://")):
            continue
        host = _domain_of(href)
        if not host:
            continue
        reg = _registered(host)
        if not reg or (page_host and reg == page_host):
            continue
        if reg in seen:
            continue
        seen.add(reg)
        if len(examples) < 5:
            examples.append(reg)
    count = len(seen)

    if count >= _MIN_CITATIONS_PASS:
        status = CheckStatus.PASS
        score = min(1.0, count / 6)
        detail = f"{count} distinct outbound citations (e.g. {', '.join(examples[:3])}). Princeton GEO study found this is the #1 lever for AI citation visibility."
    elif count >= _MIN_CITATIONS_WARN:
        status = CheckStatus.WARN
        score = 0.5
        detail = f"Only {count} outbound citation(s). Aim for {_MIN_CITATIONS_PASS}+ links to credible external sources within your main content."
    else:
        status = CheckStatus.FAIL
        score = 0.1
        detail = "No outbound citations in main content. AI engines weight content with credible external references far higher (Princeton GEO 2024)."

    return CheckResult(
        id="outbound_citations",
        label="Outbound citations to authoritative sources",
        status=status,
        score=score,
        weight=1.5,
        detail=detail,
        evidence={"count": count, "examples": examples},
    )


def _check_statistics(body_text: str, word_count: int) -> CheckResult:
    if word_count < _MIN_BODY_WORDS_FOR_DENSITY_CHECKS:
        return CheckResult(
            id="statistics_density",
            label="Statistics and quantitative claims",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=1.0,
            detail="Page has too little body text to evaluate statistics density.",
        )
    matches: set[str] = set()
    for pat in _STAT_PATTERNS:
        for m in pat.findall(body_text):
            if isinstance(m, tuple):
                m = " ".join(x for x in m if x)
            matches.add(m.strip())

    count = len(matches)
    examples = sorted(matches, key=len)[:5]

    if count >= _MIN_STATS_PASS:
        status = CheckStatus.PASS
        score = min(1.0, count / 6)
        detail = f"{count} distinct quantitative claims (e.g. {', '.join(examples[:3])}). Statistics-rich content is cited ~30% more often (Princeton GEO 2024)."
    elif count >= _MIN_STATS_WARN:
        status = CheckStatus.WARN
        score = 0.5
        detail = f"Only {count} quantitative claim(s). Adding concrete numbers (percentages, counts, dates) raises citation likelihood."
    else:
        status = CheckStatus.FAIL
        score = 0.2
        detail = "No quantitative claims detected. AI engines preferentially cite content with specific numbers (Princeton GEO 2024)."

    return CheckResult(
        id="statistics_density",
        label="Statistics and quantitative claims",
        status=status,
        score=score,
        weight=1.0,
        detail=detail,
        evidence={"count": count, "examples": examples},
    )


def _check_quotations(container: Tag, word_count: int) -> CheckResult:
    if word_count < _MIN_BODY_WORDS_FOR_DENSITY_CHECKS:
        return CheckResult(
            id="quotation_density",
            label="Direct quotations and citations",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.8,
            detail="Page has too little body text to evaluate quotation usage.",
        )
    blocks = container.find_all("blockquote")
    qs = container.find_all("q")
    cites = container.find_all("cite")
    total = len(blocks) + len(qs) + len(cites)

    if total >= 2:
        status = CheckStatus.PASS
        score = 1.0
        detail = f"{total} quotation/citation element(s) ({len(blocks)} blockquote, {len(qs)} q, {len(cites)} cite). Princeton GEO study found this is a top citation-driver."
    elif total == 1:
        status = CheckStatus.WARN
        score = 0.6
        detail = "Only one quotation element. Adding 1–2 more direct quotes from credible sources raises citation likelihood."
    else:
        status = CheckStatus.FAIL
        score = 0.2
        detail = "No <blockquote>, <q>, or <cite> elements. Quoting credible sources raises AI citation rate by ~40% (Princeton GEO 2024)."

    return CheckResult(
        id="quotation_density",
        label="Direct quotations and citations",
        status=status,
        score=score,
        weight=0.8,
        detail=detail,
        evidence={"blockquote": len(blocks), "q": len(qs), "cite": len(cites)},
    )


def _check_fanout_questions(soup: BeautifulSoup) -> CheckResult:
    questions: list[str] = []
    for tag in soup.find_all(["h2", "h3"]):
        text = tag.get_text(" ", strip=True)
        if not text:
            continue
        if text.endswith("?"):
            questions.append(text[:80])
            continue
        # Also count "How to X" style headings — common Q&A fan-out pattern
        first = text.split()[0].lower() if text.split() else ""
        if first in _QUESTION_WORDS and len(text.split()) >= 3 and len(questions) < 8:
            # Be conservative: only count if the heading reads like a question.
            # Skip "What's new" / generic marketing tags.
            if any(text.lower().startswith(q + " ") for q in ("how to", "what is", "what are", "why does", "why do", "when should", "where to")):
                questions.append(text[:80])

    count = len(questions)
    if count >= _MIN_QUESTION_HEADINGS_PASS:
        status = CheckStatus.PASS
        score = min(1.0, count / 4)
        detail = f"{count} question-shaped subhead(s) (e.g. \"{questions[0]}\"). AI retrievers chunk by subhead — each one is a separate citation surface."
    elif count == _MIN_QUESTION_HEADINGS_WARN:
        status = CheckStatus.WARN
        score = 0.5
        detail = f"One question-shaped subhead. Aim for ≥{_MIN_QUESTION_HEADINGS_PASS} so multiple sub-queries can match your content."
    else:
        status = CheckStatus.WARN
        score = 0.3
        detail = "No question-shaped subheads (H2/H3 ending in '?'). Each sub-question your content answers is a separate AI-citation opportunity."

    return CheckResult(
        id="fanout_h2_questions",
        label="Question-shaped subheads (fan-out)",
        status=status,
        score=score,
        weight=0.6,
        detail=detail,
        evidence={"count": count, "examples": questions[:5]},
    )


def _check_visible_updated(soup: BeautifulSoup, body_text: str, jsonld_blocks: list[dict]) -> CheckResult:
    has_article = _has_article_jsonld(jsonld_blocks) or soup.find("article") is not None
    if not has_article:
        return CheckResult(
            id="freshness_visible_updated",
            label="Visible \"Updated\" date on article content",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.7,
            detail="Page doesn't appear to be an article; rescan an article URL for this check.",
        )

    matched = _UPDATED_LINE.search(body_text)
    has_time = soup.find("time", attrs={"datetime": True}) is not None

    if matched and has_time:
        status = CheckStatus.PASS
        score = 1.0
        detail = f"Found visible date line: \"{matched.group()[:80]}\" + <time> element. Strong freshness signal."
    elif matched:
        status = CheckStatus.PASS
        score = 0.85
        detail = f"Found visible date line: \"{matched.group()[:80]}\". Pair with a <time datetime=\"…\"> element for full strength."
    elif has_time:
        status = CheckStatus.WARN
        score = 0.6
        detail = "<time> element present, but no human-readable \"Updated …\" line. Sites with both are cited ~34% more (Seenos audit, 2026)."
    else:
        status = CheckStatus.FAIL
        score = 0.2
        detail = "No visible \"Updated …\" date and no <time> element. AI engines treat undated content as stale (Perplexity / AI Overviews freshness gate)."

    return CheckResult(
        id="freshness_visible_updated",
        label="Visible \"Updated\" date on article content",
        status=status,
        score=score,
        weight=0.7,
        detail=detail,
    )


def _check_byline_links(soup: BeautifulSoup, jsonld_blocks: list[dict]) -> CheckResult:
    has_byline = _has_byline_text(soup) or bool(_find_persons(jsonld_blocks))
    if not has_byline:
        return CheckResult(
            id="byline_links",
            label="Author byline links to a credentialed page",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.8,
            detail="No byline detected on this page; rescan an article URL for this check.",
        )

    anchor = _byline_anchor(soup)
    if not anchor:
        return CheckResult(
            id="byline_links",
            label="Author byline links to a credentialed page",
            status=CheckStatus.FAIL,
            score=0.1,
            weight=0.8,
            detail="Byline detected but it doesn't link anywhere. Bare-text bylines are invisible to AI engines — link them to a /about or /author/<name> page.",
        )

    href = (anchor.get("href") or "").strip()
    label = anchor.get_text(" ", strip=True)[:80]
    return CheckResult(
        id="byline_links",
        label="Author byline links to a credentialed page",
        status=CheckStatus.PASS,
        score=1.0,
        weight=0.8,
        detail=f"Byline links out: \"{label}\" → {href[:80]}. Pair with a Person JSON-LD block + sameAs links for full E-E-A-T credit.",
        evidence={"href": href, "label": label},
    )


def _check_transcripts(soup: BeautifulSoup, container: Tag) -> CheckResult:
    media = _detect_media(soup)
    if not media:
        return CheckResult(
            id="transcripts_for_media",
            label="Transcripts present for video / audio",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.6,
            detail="No video or audio detected on this page.",
        )

    if _has_transcript(soup, container):
        status = CheckStatus.PASS
        score = 1.0
        detail = f"Media detected ({', '.join(sorted(set(media))[:3])}) and a transcript / captions are present. AI engines can index this content."
    else:
        status = CheckStatus.FAIL
        score = 0.2
        detail = f"Media detected ({', '.join(sorted(set(media))[:3])}) but no transcript / captions. Without one, the content is invisible to LLMs."

    return CheckResult(
        id="transcripts_for_media",
        label="Transcripts present for video / audio",
        status=status,
        score=score,
        weight=0.6,
        detail=detail,
        evidence={"media": sorted(set(media))},
    )
