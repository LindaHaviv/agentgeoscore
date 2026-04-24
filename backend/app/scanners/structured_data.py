"""Structured Data scanner — schema.org JSON-LD, OpenGraph, Twitter cards."""
from __future__ import annotations

import json

from bs4 import BeautifulSoup

from ..models import CheckResult, CheckStatus


def extract_jsonld(html: str) -> list[dict]:
    """Return parsed JSON-LD objects from <script type='application/ld+json'> tags."""
    if not html:
        return []
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(parsed, dict):
            # Handle @graph wrapper
            if "@graph" in parsed and isinstance(parsed["@graph"], list):
                for item in parsed["@graph"]:
                    if isinstance(item, dict):
                        out.append(item)
            else:
                out.append(parsed)
    return out


def extract_og(html: str) -> dict[str, str]:
    """Extract og:* and article:* meta properties."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    props: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or ""
        content = meta.get("content") or ""
        if prop.startswith(("og:", "article:")):
            props[prop] = content
    return props


def extract_twitter(html: str) -> dict[str, str]:
    if not html:
        return {}
    soup = BeautifulSoup(html, "lxml")
    props: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        name = meta.get("name") or ""
        content = meta.get("content") or ""
        if name.startswith("twitter:"):
            props[name] = content
    return props


CORE_OG = ["og:title", "og:description", "og:type", "og:url", "og:image"]


def check_structured_data(html: str) -> list[CheckResult]:
    results: list[CheckResult] = []

    # JSON-LD
    jsonld = extract_jsonld(html)
    types = []
    for item in jsonld:
        t = item.get("@type")
        if isinstance(t, str):
            types.append(t)
        elif isinstance(t, list):
            types.extend(x for x in t if isinstance(x, str))
    if jsonld:
        results.append(
            CheckResult(
                id="jsonld_present",
                label="schema.org JSON-LD present",
                status=CheckStatus.PASS,
                score=1.0,
                weight=3.0,
                detail=f"Found {len(jsonld)} JSON-LD block(s): {', '.join(sorted(set(types))) or 'untyped'}.",
                evidence={"types": sorted(set(types)), "count": len(jsonld)},
            )
        )
        # Bonus for specific rich types
        rich_types = {
            "Organization", "WebSite", "Article", "NewsArticle", "Product",
            "Recipe", "Event", "Person", "BreadcrumbList", "FAQPage",
            "HowTo", "VideoObject", "SoftwareApplication", "LocalBusiness",
        }
        matched = rich_types.intersection(types)
        results.append(
            CheckResult(
                id="jsonld_rich",
                label="Rich schema.org types used",
                status=CheckStatus.PASS if matched else CheckStatus.WARN,
                score=min(1.0, len(matched) / 2) if matched else 0.3,
                weight=1.5,
                detail=(
                    f"Rich types detected: {', '.join(sorted(matched))}."
                    if matched
                    else "JSON-LD present but no rich schema.org types (Article, Product, Organization, FAQPage, etc.)."
                ),
            )
        )
    else:
        results.append(
            CheckResult(
                id="jsonld_present",
                label="schema.org JSON-LD present",
                status=CheckStatus.FAIL,
                score=0.0,
                weight=3.0,
                detail="No JSON-LD structured data on homepage. This is the single richest signal for AI agents.",
            )
        )
        results.append(
            CheckResult(
                id="jsonld_rich",
                label="Rich schema.org types used",
                status=CheckStatus.FAIL,
                score=0.0,
                weight=1.5,
                detail="Add rich types like Organization, Article, Product, or FAQPage.",
            )
        )

    # OpenGraph
    og = extract_og(html)
    og_missing = [k for k in CORE_OG if k not in og]
    if not og:
        results.append(
            CheckResult(
                id="opengraph",
                label="OpenGraph tags present",
                status=CheckStatus.FAIL,
                score=0.0,
                weight=2.0,
                detail="No OpenGraph meta tags. Add og:title, og:description, og:type, og:url, og:image.",
            )
        )
    elif og_missing:
        results.append(
            CheckResult(
                id="opengraph",
                label="OpenGraph tags present",
                status=CheckStatus.WARN,
                score=max(0.2, 1 - len(og_missing) / len(CORE_OG)),
                weight=2.0,
                detail=f"Missing OpenGraph tags: {', '.join(og_missing)}.",
                evidence={"present": sorted(og.keys())},
            )
        )
    else:
        results.append(
            CheckResult(
                id="opengraph",
                label="OpenGraph tags present",
                status=CheckStatus.PASS,
                score=1.0,
                weight=2.0,
                detail="All core OpenGraph tags present.",
                evidence={"present": sorted(og.keys())},
            )
        )

    # Twitter card
    twitter = extract_twitter(html)
    has_twitter = "twitter:card" in twitter
    results.append(
        CheckResult(
            id="twitter_card",
            label="Twitter/X card tags",
            status=CheckStatus.PASS if has_twitter else CheckStatus.WARN,
            score=1.0 if has_twitter else 0.4,
            weight=0.8,
            detail=(
                f"twitter:card = {twitter.get('twitter:card')}."
                if has_twitter
                else "No Twitter/X card meta tags. Add twitter:card, twitter:title, twitter:description."
            ),
        )
    )

    return results
