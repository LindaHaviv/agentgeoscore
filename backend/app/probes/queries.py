"""Derive probe queries from a target's homepage HTML.

We don't want to just ask the LLM "what is example.com". We want to ask natural
topical questions in the domain of the site, then check if AI cites the site.
That's the real signal for "would an AI agent recommend me?".

Strategy:
1. Extract title, meta description, and H1/H2 text.
2. Combine into 2-3 natural search queries like "best tool for X" or
   "how to Y" based on the extracted vocabulary.
"""
from __future__ import annotations

import re

from bs4 import BeautifulSoup


def derive_queries(html: str, host: str, max_queries: int = 3) -> list[str]:
    """Produce natural-language queries likely to surface this kind of site."""
    if not html:
        return [f"{host} review"]

    soup = BeautifulSoup(html, "lxml")
    title = (soup.find("title").get_text() if soup.find("title") else "").strip()
    meta = soup.find("meta", attrs={"name": "description"})
    desc = (meta.get("content") if meta else "") or ""
    h1 = soup.find("h1")
    h1_text = (h1.get_text(" ", strip=True) if h1 else "")
    h2s = [h.get_text(" ", strip=True) for h in soup.find_all("h2")[:3]]

    # Clean branding strings "Foo | Bar" → "Foo"
    def clean(s: str) -> str:
        s = re.sub(r"\s+", " ", s).strip()
        # Strip trailing brand separators
        s = re.split(r"\s[\|·•—\-]\s", s, maxsplit=1)[0]
        return s.strip()

    topic_title = clean(title) or h1_text or host
    topic_desc = clean(desc)

    queries: list[str] = []

    # Query 1: the descriptive query — what is the site about?
    if topic_desc:
        queries.append(f"{topic_desc[:180]}")
    elif topic_title:
        queries.append(f"what is {topic_title}")

    # Query 2: recommendation-style — surfaces sites AI agents actually cite
    keyword = _topic_keyword(topic_title, topic_desc, h2s)
    if keyword:
        queries.append(f"best {keyword} 2026")

    # Query 3: explicit domain mention — baseline check
    queries.append(f"{host} review and features")

    # Dedup + trim
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q.lower() not in seen:
            seen.add(q.lower())
            unique.append(q)
    return unique[:max_queries]


_STOPWORDS = {
    "the", "a", "an", "for", "and", "or", "to", "of", "with", "from",
    "by", "in", "on", "at", "is", "are", "your", "our", "my", "we",
    "you", "i", "it", "that", "this", "be", "can", "will", "all",
    "any", "more", "than", "as", "up", "out", "about", "best", "home",
    "welcome", "page",
}


def _topic_keyword(title: str, desc: str, h2s: list[str]) -> str:
    """Pick a short topical noun phrase from extracted text."""
    blob = " ".join([title, desc, *h2s]).lower()
    # Keep words with letters, drop stopwords and single-char tokens
    tokens = [t for t in re.findall(r"[a-z][a-z\-]{2,}", blob) if t not in _STOPWORDS]
    if not tokens:
        return ""
    # Use first 2-3 tokens as topic keyword
    return " ".join(tokens[:3])
