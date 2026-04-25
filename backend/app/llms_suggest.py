"""Generate a starter `llms.txt` for a scanned site.

The llmstxt.org spec asks for a Markdown file at `/llms.txt` with:

    # <Site name>
    > <One-line summary>
    Optional context paragraph.
    ## <Section>
    - [link title](/link): description

We don't have access to the full site graph, so we build a minimal-but-valid
starter from the homepage. Quality matters here — the file is what users
copy-paste into their site, so we work hard to:

  * Pick a real brand name (og:site_name, schema.org Organization, or the
    branded half of <title>) instead of the H1 — H1s on marketing homepages
    are usually hero taglines like "Be the next big thing".
  * Pick a real summary (meta description / og:description / twitter:description)
    and reject CTA-style fragments.
  * Pick real key pages (/about, /pricing, /docs, …) instead of every <a>
    on the homepage in DOM order, which on big marketing sites yields hero
    card links with sentence-long labels.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .probes._util import host_matches

# Path prefixes that we always skip — these are auth/legal/utility surfaces,
# not pages a model should cite to understand the site.
_PATH_BLOCKLIST = (
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/register",
    "/auth",
    "/oauth",
    "/sso",
    "/account",
    "/cart",
    "/checkout",
    "/legal",
    "/privacy",
    "/terms",
    "/tos",
    "/cookies",
    "/cookie-policy",
    "/dpa",
    "/gdpr",
    "/ccpa",
    "/sitemap",
    "/search",
    "/logout",
)

# Substrings that, if they appear anywhere in the path, mark a link as
# legal/policy boilerplate — covers things like /website-terms,
# /enterprise-tos, /acceptable-use-policy that don't sit under a /legal prefix.
_PATH_SUBSTRING_BLOCKLIST = (
    "terms-of",
    "terms-",
    "-terms",
    "-tos",
    "privacy-policy",
    "acceptable-use",
    "code-of-conduct",
    "data-processing",
)

# Path segments that are good "section" pages — links matching these get
# bumped to the top of the Key pages list.
_PRIORITY_PATHS = (
    "/about",
    "/product",
    "/products",
    "/feature",
    "/features",
    "/pricing",
    "/plans",
    "/enterprise",
    "/customers",
    "/case-studies",
    "/case-study",
    "/docs",
    "/documentation",
    "/api",
    "/developers",
    "/blog",
    "/learn",
    "/guides",
    "/research",
    "/company",
    "/team",
)

_MAX_LABEL_LEN = 50
_MAX_LINKS = 7


def generate_llms_txt(home_html: str, origin: str, host: str) -> str:
    """Return a starter llms.txt Markdown body."""
    if not home_html:
        return _empty_skeleton(origin, host)

    soup = BeautifulSoup(home_html, "lxml")

    name = _extract_name(soup, host)
    summary = _extract_summary(soup, name)
    context = _extract_context(soup, summary)
    links = _collect_internal_links(soup, origin, host)

    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append(f"> {summary}")
    lines.append("")

    if context:
        lines.append(context)
        lines.append("")

    if links:
        lines.append("## Key pages")
        for href, label, hint in links:
            if hint:
                lines.append(f"- [{label}]({href}): {hint}")
            else:
                lines.append(f"- [{label}]({href})")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _empty_skeleton(origin: str, host: str) -> str:
    return (
        f"# {_host_to_name(host)}\n"
        f"> (add a one-line description of your site here)\n\n"
        f"## Key pages\n"
        f"- [Home]({origin}/): main landing page\n"
    )


def _extract_name(soup: BeautifulSoup, host: str) -> str:
    """Pick a brand name. Strong signals first; H1 is a last-resort fallback."""
    og_site = soup.find("meta", attrs={"property": "og:site_name"})
    if og_site and og_site.get("content"):
        cand = _clean(og_site["content"])
        if cand:
            return cand

    schema_name = _name_from_jsonld(soup)
    if schema_name:
        return schema_name

    title_tag = soup.find("title")
    if title_tag:
        cand = _branded_segment(title_tag.get_text() or "")
        if cand and not _is_generic_page_word(cand):
            return cand

    # H1 only as a fallback, and only if it's short enough to plausibly be
    # a brand rather than a campaign tagline.
    h1 = soup.find("h1")
    if h1:
        h1_text = _one_line(h1.get_text(" ", strip=True), limit=40)
        if h1_text and len(h1_text) <= 30 and not _looks_like_cta(h1_text):
            return h1_text

    return _host_to_name(host)


_GENERIC_PAGE_WORDS = {"home", "homepage", "index", "welcome", "page", "untitled"}


def _is_generic_page_word(s: str) -> bool:
    return s.strip().lower() in _GENERIC_PAGE_WORDS


def _name_from_jsonld(soup: BeautifulSoup) -> str:
    """Pull the brand name from a schema.org Organization / WebSite block."""
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_jsonld_nodes(data):
            if not isinstance(node, dict):
                continue
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(x in ("Organization", "Corporation", "WebSite", "LocalBusiness") for x in types if isinstance(x, str)):
                name = node.get("name")
                if isinstance(name, str):
                    cand = _clean(name)
                    if cand:
                        return cand
    return ""


def _iter_jsonld_nodes(data: object):
    if isinstance(data, list):
        for item in data:
            yield from _iter_jsonld_nodes(item)
    elif isinstance(data, dict):
        yield data
        graph = data.get("@graph")
        if isinstance(graph, list):
            for item in graph:
                yield from _iter_jsonld_nodes(item)


def _extract_summary(soup: BeautifulSoup, name: str) -> str:
    for selector in (
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
        ("meta", {"name": "twitter:description"}),
    ):
        tag = soup.find(*selector)
        if tag and tag.get("content"):
            cand = _one_line(tag["content"], limit=240)
            if cand and not _looks_like_cta(cand):
                return cand

    schema_desc = _description_from_jsonld(soup)
    if schema_desc:
        return schema_desc

    return f"{name} — add a one-line summary here."


def _description_from_jsonld(soup: BeautifulSoup) -> str:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            continue
        for node in _iter_jsonld_nodes(data):
            if isinstance(node, dict):
                desc = node.get("description")
                if isinstance(desc, str):
                    cand = _one_line(desc, limit=240)
                    if cand and not _looks_like_cta(cand):
                        return cand
    return ""


def _extract_context(soup: BeautifulSoup, summary: str) -> str:
    """Pick a short context paragraph that adds info beyond the summary."""
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if not text or len(text) < 60:
            continue
        cand = _one_line(text, limit=240)
        # Don't repeat the summary back; reject trivially-similar leading text.
        if summary and cand[:80].lower() == summary[:80].lower():
            continue
        if _looks_like_cta(cand):
            continue
        return cand
    return ""


def _collect_internal_links(
    soup: BeautifulSoup, origin: str, host: str
) -> list[tuple[str, str, str]]:
    """Return up to _MAX_LINKS (href, label, hint) tuples for the Key pages section.

    Strategy:
      * Walk all <a href> in DOM order.
      * Reject off-host, hash-only, mailto/tel, and homepage self-links.
      * Reject auth/legal/utility paths via _PATH_BLOCKLIST.
      * Clean each label: prefer aria-label/title attrs over multi-line link
        content; truncate long sentence-style hero CTAs.
      * Score each remaining link: priority paths first, then DOM order.
    """
    candidates: list[tuple[int, int, str, str]] = []  # (score, dom_pos, href, label)
    seen: set[str] = set()

    for pos, a in enumerate(soup.find_all("a", href=True)):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        abs_url = urljoin(origin + "/", href)
        parsed = urlparse(abs_url)
        if not parsed.netloc:
            continue
        if not host_matches(abs_url, host):
            continue

        path = parsed.path or "/"
        # Skip the *scanned* homepage self-link, but allow a subdomain root
        # (e.g. https://docs.acme.example/) — it points somewhere different.
        scanned_netloc = urlparse(origin).netloc.lower()
        if path in ("", "/") and parsed.netloc.lower() == scanned_netloc:
            continue
        # Compare against blocklists / priority paths case-insensitively so
        # `/Login` and `/About` are treated the same as `/login` and `/about`.
        path_lower = path.lower()
        if _path_blocked(path_lower):
            continue
        if any(sub in path_lower for sub in _PATH_SUBSTRING_BLOCKLIST):
            continue

        norm = abs_url.split("#", 1)[0].split("?", 1)[0].rstrip("/") or abs_url
        if norm in seen:
            continue
        seen.add(norm)

        label = _label_from_anchor(a)
        if not label or _looks_like_cta(label):
            continue

        score = _path_priority(path_lower)
        candidates.append((score, pos, norm, label))

        if len(candidates) >= _MAX_LINKS * 4:
            # Bound the scan — even huge homepages don't need exhaustive walks.
            break

    # Sort: lower score wins (0 = priority page, 1 = generic), then DOM order.
    candidates.sort(key=lambda x: (x[0], x[1]))

    out: list[tuple[str, str, str]] = []
    for _score, _pos, href, label in candidates[:_MAX_LINKS]:
        hint = _slug_to_hint(href, label)
        out.append((href, label, hint))
    return out


def _label_from_anchor(a) -> str:
    """Extract a short, clean label from an <a> tag.

    Prefer (in order): aria-label/title, a heading child (h1-h6), a strong/b
    child — these are usually the "title" half of a hero card. Fall back to
    the full visible text, but reject anything that smells like multiple
    concatenated sentences (e.g. "Title. Description." with no whitespace).
    """
    aria = (a.get("aria-label") or "").strip()
    if aria and len(aria) <= _MAX_LABEL_LEN:
        return _one_line(aria, limit=_MAX_LABEL_LEN)
    title_attr = (a.get("title") or "").strip()
    if title_attr and len(title_attr) <= _MAX_LABEL_LEN:
        return _one_line(title_attr, limit=_MAX_LABEL_LEN)

    # Hero cards typically wrap a heading + description in one <a>. If the
    # anchor has a heading-like child, that's the cleanest label.
    for tag_name in ("h1", "h2", "h3", "h4", "h5", "h6", "strong", "b"):
        child = a.find(tag_name)
        if child:
            child_text = re.sub(r"\s+", " ", child.get_text(" ", strip=True)).strip()
            if child_text and len(child_text) <= _MAX_LABEL_LEN and not _has_internal_sentence_break(child_text):
                return child_text

    full = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).strip()
    if not full:
        return ""

    # If the anchor's collapsed text is two distinct phrases (title +
    # description), the first leaf string is usually the title. Use it iff
    # it's *materially* shorter than the full text — otherwise keep full.
    # Skip leading badge tokens like "NEW", "BETA", "BADGE" used as visual
    # decorators on hero cards.
    pieces = [re.sub(r"\s+", " ", p).strip() for p in a.stripped_strings]
    pieces = [p for p in pieces if p and not _looks_like_badge(p)]
    if len(pieces) >= 2:
        first = pieces[0]
        if first and len(first) <= _MAX_LABEL_LEN and len(first) < len(full) * 0.7:
            if not _has_internal_sentence_break(first):
                return first

    # Reject "Title. Description." style labels — they read as ad copy and
    # produce ugly llms.txt entries.
    if _has_internal_sentence_break(full):
        return ""

    if len(full) > _MAX_LABEL_LEN:
        return ""

    return full


_BADGE_WORDS = {"new", "beta", "alpha", "pro", "free", "trial", "live", "soon", "hot", "demo"}


def _looks_like_badge(s: str) -> bool:
    """True if `s` is a short status/decorator word like 'NEW' or 'BETA'."""
    stripped = s.strip()
    if not stripped:
        return True
    # Single short ALL-CAPS word with no spaces.
    if len(stripped) <= 6 and stripped == stripped.upper() and " " not in stripped:
        return stripped.lower().rstrip("!.,") in _BADGE_WORDS
    return False


def _has_internal_sentence_break(text: str) -> bool:
    """True if text contains sentence-ending punctuation that isn't the very
    last char — i.e. multiple sentences glued together."""
    stripped = text.rstrip(".!?")
    return bool(re.search(r"[.!?]\s+\S", stripped))


def _path_blocked(path: str) -> bool:
    """True if the path matches any blocklist prefix at a segment boundary.

    Bare `path.startswith("/auth")` would erroneously block `/author`,
    `/authors`, `/authority`, `/accounting`, etc. Match only at `/` or `.`
    boundaries (or whole-path equality) so legitimate pages survive.
    """
    for prefix in _PATH_BLOCKLIST:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "."):
            return True
    return False


def _path_priority(path: str) -> int:
    """Lower numbers sort first. 0 = canonical section page, 1 = other."""
    for prio in _PRIORITY_PATHS:
        if path == prio or path.startswith(prio + "/") or path.startswith(prio + "."):
            return 0
    return 1


def _slug_to_hint(url: str, label: str) -> str:
    """Generate a short hint for the link, or empty string if redundant."""
    path = urlparse(url).path or "/"
    last = [p for p in path.split("/") if p]
    if not last:
        return ""
    slug = last[-1].replace("-", " ").replace("_", " ").lower()
    # Pure-number slugs (e.g. "1" from /blog/1) are just IDs — useless.
    if slug.replace(" ", "").isdigit():
        return ""
    if len(slug) <= 1:
        return ""
    # If the slug just repeats words from the label, the hint adds nothing.
    label_lower = label.lower()
    if slug in label_lower:
        return ""
    slug_words = [w for w in slug.split() if w]
    if slug_words and all(w in label_lower for w in slug_words):
        return ""
    return slug


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _branded_segment(title: str) -> str:
    """Return the brand-side segment of a separator-delimited title.

    Both `Brand | Tagline` and `Tagline — Brand` show up in the wild. The
    brand half is almost always the *shorter* segment, so when we see two
    halves we pick the shorter — falling back to the first if they tie.
    """
    s = re.sub(r"\s+", " ", title).strip()
    if not s:
        return ""
    parts = [p.strip() for p in re.split(r"\s+[\|·•—\-–:]\s+", s) if p.strip()]
    if not parts:
        return s
    if len(parts) == 1:
        return parts[0][:60]
    shortest = min(parts, key=len)
    return shortest[:60]


def _host_to_name(host: str) -> str:
    h = host.lower()
    if h.startswith("www."):
        h = h[4:]
    base = h.split(".")[0]
    if not base:
        return host
    return base[:1].upper() + base[1:]


_CTA_PATTERNS = re.compile(
    r"^(get started|start (free|today|now)|try (it )?(free|now)|sign up|sign in|"
    r"learn more|see (more|how)|read more|contact (us|sales)|book (a |your )?demo|"
    r"buy now|shop now|view (more|all)|explore now|join (now|today))\b",
    re.IGNORECASE,
)


def _looks_like_cta(s: str) -> bool:
    return bool(_CTA_PATTERNS.match(s.strip()))


def _one_line(s: str, limit: int = 200) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s
