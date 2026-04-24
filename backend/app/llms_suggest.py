"""Generate a starter `llms.txt` for a scanned site.

The llmstxt.org spec asks for a Markdown file at `/llms.txt` with:

    # <Site name>
    > <One-line summary>
    Optional context paragraph.
    ## <Section>
    - [link title](/link): description

We don't have access to the full site graph, so we build a minimal-but-valid
starter from the homepage: title → H1, meta description → summary, OG/schema
metadata → context, internal nav links → a "Key pages" section.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def generate_llms_txt(home_html: str, origin: str, host: str) -> str:
    """Return a starter llms.txt Markdown body."""
    if not home_html:
        return (
            f"# {host}\n"
            f"> (add a one-line description of your site here)\n\n"
            f"## Key pages\n"
            f"- [Home]({origin}/): main landing page\n"
        )
    soup = BeautifulSoup(home_html, "lxml")

    title_tag = soup.find("title")
    title = _clean((title_tag.get_text() if title_tag else "").strip()) or host
    h1 = soup.find("h1")
    h1_text = h1.get_text(" ", strip=True) if h1 else ""
    name = h1_text or title

    meta = soup.find("meta", attrs={"name": "description"})
    summary = (meta.get("content") if meta else "") or ""
    summary = _one_line(summary)
    if not summary:
        og_desc = soup.find("meta", attrs={"property": "og:description"})
        if og_desc:
            summary = _one_line(og_desc.get("content") or "")
    if not summary:
        summary = f"{name} — add a one-line summary here."

    internal_links = _collect_internal_links(soup, origin, host)

    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append(f"> {summary}")
    lines.append("")

    # Optional context paragraph — picked from the first meaningful <p>
    first_p = _first_meaningful_paragraph(soup)
    if first_p:
        lines.append(first_p)
        lines.append("")

    if internal_links:
        lines.append("## Key pages")
        for href, label in internal_links:
            lines.append(f"- [{label}]({href}): {_slug_to_hint(href)}")
        lines.append("")

    lines.append("## About")
    lines.append(
        f"- [Home]({origin}/): main landing page"
    )

    return "\n".join(lines).rstrip() + "\n"


def _clean(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # Strip branding tails ("Foo | Bar" → "Foo")
    s = re.split(r"\s[\|·•—\-]\s", s, maxsplit=1)[0]
    return s.strip()


def _one_line(s: str, limit: int = 200) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) > limit:
        s = s[: limit - 1].rstrip() + "…"
    return s


def _collect_internal_links(
    soup: BeautifulSoup, origin: str, host: str, limit: int = 6
) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    host_lc = host.lower().removeprefix("www.")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue
        abs_url = urljoin(origin + "/", href)
        parsed = urlparse(abs_url)
        if not parsed.netloc:
            continue
        if host_lc not in parsed.netloc.lower():
            continue
        # Normalize trailing slash for dedup
        norm = abs_url.split("#", 1)[0].rstrip("/") or abs_url
        if norm in seen:
            continue
        seen.add(norm)
        label = a.get_text(" ", strip=True) or parsed.path
        label = re.sub(r"\s+", " ", label)[:60]
        if not label:
            continue
        out.append((norm, label))
        if len(out) >= limit:
            break
    return out


def _slug_to_hint(url: str) -> str:
    path = urlparse(url).path or "/"
    if path in ("", "/"):
        return "landing page"
    last = [p for p in path.split("/") if p]
    if not last:
        return "page"
    return last[-1].replace("-", " ").replace("_", " ")


def _first_meaningful_paragraph(soup: BeautifulSoup) -> str:
    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text and len(text) >= 40:
            return _one_line(text, limit=240)
    return ""
