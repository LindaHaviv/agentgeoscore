"""Content Clarity scanner — semantic HTML, headings, meta description, title."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..models import CheckResult, CheckStatus


def check_content_clarity(html: str) -> list[CheckResult]:
    results: list[CheckResult] = []
    if not html:
        return [
            CheckResult(
                id="html_reachable",
                label="Homepage HTML reachable",
                status=CheckStatus.FAIL,
                score=0.0,
                weight=5.0,
                detail="Couldn't fetch homepage HTML.",
            )
        ]
    soup = BeautifulSoup(html, "lxml")

    # 1. <title> quality
    title_tag = soup.find("title")
    title_text = (title_tag.get_text() if title_tag else "").strip()
    if not title_text:
        status, score, detail = CheckStatus.FAIL, 0.0, "No <title> tag."
    elif 10 <= len(title_text) <= 70:
        status, score, detail = CheckStatus.PASS, 1.0, f"Title: \"{title_text[:70]}\" ({len(title_text)} chars)."
    else:
        status, score, detail = (
            CheckStatus.WARN,
            0.6,
            f"Title length {len(title_text)} chars (ideal 10–70).",
        )
    results.append(
        CheckResult(
            id="title_quality", label="<title> quality", status=status, score=score, weight=1.5, detail=detail
        )
    )

    # 2. Meta description
    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc_content = (meta_desc.get("content") if meta_desc else "") or ""
    desc_content = desc_content.strip()
    if not desc_content:
        status, score, detail = CheckStatus.FAIL, 0.0, "No meta description."
    elif 50 <= len(desc_content) <= 170:
        status, score, detail = CheckStatus.PASS, 1.0, f"Description: {len(desc_content)} chars."
    else:
        status, score, detail = (
            CheckStatus.WARN,
            0.5,
            f"Description length {len(desc_content)} chars (ideal 50–170).",
        )
    results.append(
        CheckResult(
            id="meta_description",
            label="Meta description",
            status=status,
            score=score,
            weight=1.2,
            detail=detail,
        )
    )

    # 3. Single H1
    h1s = soup.find_all("h1")
    if len(h1s) == 1:
        status, score, detail = CheckStatus.PASS, 1.0, f"Single H1: \"{h1s[0].get_text(strip=True)[:80]}\""
    elif len(h1s) == 0:
        status, score, detail = CheckStatus.FAIL, 0.0, "No H1 on homepage."
    else:
        status, score, detail = CheckStatus.WARN, 0.5, f"{len(h1s)} H1 tags — ideally just one."
    results.append(
        CheckResult(
            id="h1_single",
            label="Exactly one H1",
            status=status,
            score=score,
            weight=1.0,
            detail=detail,
        )
    )

    # 4. Semantic HTML landmarks
    landmarks = ["header", "main", "nav", "footer", "article"]
    present = [tag for tag in landmarks if soup.find(tag)]
    frac = len(present) / len(landmarks)
    if frac >= 0.8:
        status, score, detail = CheckStatus.PASS, 1.0, f"Semantic landmarks: {', '.join(present)}."
    elif frac >= 0.4:
        status, score, detail = CheckStatus.WARN, 0.6, f"Some landmarks missing. Present: {', '.join(present) or 'none'}."
    else:
        status, score, detail = CheckStatus.FAIL, 0.2, "Few/no semantic HTML landmarks — hard for AI to parse structure."
    results.append(
        CheckResult(
            id="semantic_html",
            label="Semantic HTML landmarks",
            status=status,
            score=score,
            weight=1.5,
            detail=detail,
            evidence={"present": present, "expected": landmarks},
        )
    )

    # 5. Heading hierarchy (H2+ exists and reasonable distribution)
    headings = {f"h{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)}
    if headings["h2"] > 0 or headings["h3"] > 0:
        status, score, detail = CheckStatus.PASS, 1.0, f"Heading counts: {headings}."
    else:
        status, score, detail = CheckStatus.WARN, 0.4, "No H2/H3 headings — content may lack structure for AI."
    results.append(
        CheckResult(
            id="heading_hierarchy",
            label="Heading hierarchy",
            status=status,
            score=score,
            weight=0.8,
            detail=detail,
            evidence=headings,
        )
    )

    # 6. Text extractability — text-to-HTML ratio, skip noscript fallbacks
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible_text = soup.get_text(" ", strip=True)
    text_len = len(visible_text)
    html_len = len(html)
    ratio = text_len / html_len if html_len else 0
    word_count = len(visible_text.split())
    if word_count < 50:
        status, score, detail = (
            CheckStatus.FAIL,
            0.1,
            f"Only {word_count} words of visible text — likely a client-rendered SPA. AI agents can't read JS-only content.",
        )
    elif ratio < 0.05:
        status, score, detail = (
            CheckStatus.WARN,
            0.5,
            f"Low text-to-HTML ratio ({ratio:.1%}, {word_count} words). Could be markup-heavy.",
        )
    else:
        status, score, detail = (
            CheckStatus.PASS,
            1.0,
            f"Good text density: {word_count} words, {ratio:.1%} text-to-HTML ratio.",
        )
    results.append(
        CheckResult(
            id="text_extractable",
            label="Text content extractable",
            status=status,
            score=score,
            weight=2.0,
            detail=detail,
            evidence={"word_count": word_count, "ratio": round(ratio, 4)},
        )
    )

    # 7. Lang attribute
    html_tag = soup.find("html")
    lang = html_tag.get("lang") if html_tag else None
    results.append(
        CheckResult(
            id="html_lang",
            label="<html lang> set",
            status=CheckStatus.PASS if lang else CheckStatus.WARN,
            score=1.0 if lang else 0.5,
            weight=0.4,
            detail=f"lang=\"{lang}\"" if lang else "No lang attribute on <html>.",
        )
    )

    return results
