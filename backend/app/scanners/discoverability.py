"""Discoverability scanner — sitemap, HTTPS, canonical, response speed.

Note: We intentionally do NOT score `/llms.txt` or `/llms-full.txt`. The
llmstxt.org proposal is unadopted by every major AI engine (OpenAI,
Anthropic, Google AI Overviews, Perplexity) at the time of writing — no
vendor doc or peer-reviewed study confirms it influences citations.
Scoring it would punish sites for not adopting an unproven spec, which
contradicts our evidence-backed framing. It's mentioned as an off-page
recommendation instead (see RecommendationsCard on the frontend).
"""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import CheckResult, CheckStatus
from ..targets import WebsiteTarget


async def check_discoverability(
    target: WebsiteTarget, fetcher: Fetcher, home_html: str | None = None
) -> list[CheckResult]:
    results: list[CheckResult] = []

    # 1. sitemap.xml — check direct path + robots.txt Sitemap directive
    sitemap_url = target.absolute("/sitemap.xml")
    sitemap = await fetcher.get(sitemap_url)
    robots = await fetcher.get(target.absolute("/robots.txt"))
    sitemap_in_robots = False
    if robots.ok:
        for line in robots.text.splitlines():
            if line.strip().lower().startswith("sitemap:"):
                sitemap_in_robots = True
                break
    has_sitemap = (sitemap.ok and sitemap.status == 200) or sitemap_in_robots
    results.append(
        CheckResult(
            id="sitemap",
            label="Sitemap available",
            status=CheckStatus.PASS if has_sitemap else CheckStatus.FAIL,
            score=1.0 if has_sitemap else 0.0,
            weight=1.5,
            detail=(
                "sitemap.xml found"
                + (" (declared in robots.txt)" if sitemap_in_robots else "")
                + "."
                if has_sitemap
                else "No sitemap.xml found. AI crawlers use sitemaps to find content efficiently."
            ),
        )
    )

    # 2. HTTPS
    is_https = target.origin.startswith("https://")
    results.append(
        CheckResult(
            id="https",
            label="HTTPS enabled",
            status=CheckStatus.PASS if is_https else CheckStatus.FAIL,
            score=1.0 if is_https else 0.0,
            weight=1.5,
            detail="Site served over HTTPS."
            if is_https
            else "Site is HTTP-only. Most AI crawlers deprioritize or skip insecure sites.",
        )
    )

    # 3. Canonical URL on homepage
    canonical_present = False
    if home_html:
        soup = BeautifulSoup(home_html, "lxml")
        link = soup.find("link", attrs={"rel": "canonical"})
        canonical_present = bool(link and link.get("href"))
    results.append(
        CheckResult(
            id="canonical",
            label="Canonical URL declared",
            status=CheckStatus.PASS if canonical_present else CheckStatus.WARN,
            score=1.0 if canonical_present else 0.3,
            weight=0.8,
            detail=(
                "Homepage declares a canonical URL."
                if canonical_present
                else "No <link rel=\"canonical\"> on homepage. This helps AI agents dedupe content."
            ),
        )
    )

    # 4. Homepage response speed
    home_fetch = await fetcher.get(target.url)
    if home_fetch.ok:
        ms = home_fetch.elapsed_ms
        if ms <= 800:
            status, score, detail = CheckStatus.PASS, 1.0, f"Fast response ({ms} ms)."
        elif ms <= 2500:
            status, score, detail = CheckStatus.WARN, 0.6, f"Moderate response time ({ms} ms). Aim for <800 ms."
        else:
            status, score, detail = CheckStatus.FAIL, 0.2, f"Slow response ({ms} ms). AI crawlers may timeout or deprioritize."
    else:
        status, score, detail = CheckStatus.FAIL, 0.0, f"Homepage failed to load: {home_fetch.error or home_fetch.status}"
    results.append(
        CheckResult(
            id="response_speed",
            label="Homepage response speed",
            status=status,
            score=score,
            weight=0.7,
            detail=detail,
        )
    )

    return results
