"""Discoverability scanner — llms.txt, sitemap, HTTPS, response speed."""
from __future__ import annotations

from bs4 import BeautifulSoup

from ..fetcher import Fetcher
from ..models import CheckResult, CheckStatus
from ..targets import WebsiteTarget


async def check_discoverability(
    target: WebsiteTarget, fetcher: Fetcher, home_html: str | None = None
) -> list[CheckResult]:
    results: list[CheckResult] = []

    # 1. llms.txt — the emerging standard (https://llmstxt.org) for AI-friendly content maps
    llms_url = target.absolute("/llms.txt")
    llms_fetch = await fetcher.get(llms_url)
    if llms_fetch.ok and llms_fetch.status == 200 and llms_fetch.text.strip():
        # Light validation: should start with a H1 per spec
        first_line = next(
            (ln for ln in llms_fetch.text.splitlines() if ln.strip()), ""
        )
        well_formed = first_line.startswith("# ")
        results.append(
            CheckResult(
                id="llms_txt",
                label="llms.txt present",
                status=CheckStatus.PASS if well_formed else CheckStatus.WARN,
                score=1.0 if well_formed else 0.7,
                weight=2.0,
                detail=(
                    f"Found llms.txt ({len(llms_fetch.text)} bytes)."
                    if well_formed
                    else "Found llms.txt but it doesn't start with a `# Heading` line per the llmstxt.org spec."
                ),
            )
        )
        # Bonus: llms-full.txt (full-content variant)
        llms_full = await fetcher.get(target.absolute("/llms-full.txt"))
        results.append(
            CheckResult(
                id="llms_full_txt",
                label="llms-full.txt present",
                status=CheckStatus.PASS if llms_full.ok and llms_full.status == 200 else CheckStatus.WARN,
                score=1.0 if llms_full.ok and llms_full.status == 200 else 0.3,
                weight=0.5,
                detail=(
                    f"Found llms-full.txt ({len(llms_full.text)} bytes)."
                    if llms_full.ok and llms_full.status == 200
                    else "Optional: add /llms-full.txt with full-content Markdown for richer AI grounding."
                ),
            )
        )
    else:
        results.append(
            CheckResult(
                id="llms_txt",
                label="llms.txt present",
                status=CheckStatus.FAIL,
                score=0.0,
                weight=2.0,
                detail=(
                    "No /llms.txt found. This is the emerging standard (llmstxt.org) that tells "
                    "AI assistants which Markdown-formatted pages best represent your site. "
                    "Adding one is the single highest-leverage thing you can do."
                ),
            )
        )

    # 2. sitemap.xml — check direct path + robots.txt Sitemap directive
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

    # 3. HTTPS
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

    # 4. Canonical URL on homepage
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

    # 5. Homepage response speed
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
