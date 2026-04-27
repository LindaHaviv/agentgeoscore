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

    # Author Person schema with sameAs (E-E-A-T canonical signal)
    results.append(_check_person_sameas(jsonld))

    # dateModified on Article-type schema (freshness signal)
    results.append(_check_jsonld_datemodified(jsonld))

    return results


_ARTICLE_TYPES = {"Article", "BlogPosting", "NewsArticle", "TechArticle", "ScholarlyArticle", "Report"}


def _walk_jsonld(blocks: list[dict]):
    """Yield every dict node anywhere in the JSON-LD graph (incl. nested)."""
    def walk(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)
    for block in blocks:
        yield from walk(block)


def _has_article_type(blocks: list[dict]) -> bool:
    for node in _walk_jsonld(blocks):
        t = node.get("@type")
        if isinstance(t, str) and t in _ARTICLE_TYPES:
            return True
        if isinstance(t, list) and any(x in _ARTICLE_TYPES for x in t):
            return True
    return False


def _find_persons(blocks: list[dict]) -> list[dict]:
    """Return Person nodes anywhere in the JSON-LD graph."""
    out: list[dict] = []
    for node in _walk_jsonld(blocks):
        t = node.get("@type")
        if t == "Person" or (isinstance(t, list) and "Person" in t):
            out.append(node)
    return out


def _sameas_links(person: dict) -> list[str]:
    sa = person.get("sameAs")
    if isinstance(sa, list):
        return [x for x in sa if isinstance(x, str) and x.strip()]
    if isinstance(sa, str) and sa.strip():
        return [sa.strip()]
    return []


def _check_person_sameas(jsonld: list[dict]) -> CheckResult:
    """Score Person schema + sameAs links — Google's canonical E-E-A-T signal."""
    persons = _find_persons(jsonld)
    if not persons:
        return CheckResult(
            id="person_schema_sameas",
            label="Author Person schema with sameAs links",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.8,
            detail="No Person JSON-LD on this page. If you publish bylined articles, add a Person block per author with sameAs links.",
        )

    best = max((len(_sameas_links(p)) for p in persons), default=0)
    named = next((p.get("name") for p in persons if isinstance(p.get("name"), str)), None)
    label_suffix = f" (e.g. {named})" if named else ""

    if best >= 2:
        return CheckResult(
            id="person_schema_sameas",
            label="Author Person schema with sameAs links",
            status=CheckStatus.PASS,
            score=1.0,
            weight=1.0,
            detail=f"Person schema with {best} sameAs link(s){label_suffix}. Strong E-E-A-T author-authority signal.",
            evidence={"sameAs_count": best},
        )
    if best == 1:
        return CheckResult(
            id="person_schema_sameas",
            label="Author Person schema with sameAs links",
            status=CheckStatus.WARN,
            score=0.5,
            weight=1.0,
            detail=f"Person schema present but only one sameAs link{label_suffix}. Add 2+ profile URLs (LinkedIn, X, GitHub, ORCID) for full E-E-A-T credit.",
            evidence={"sameAs_count": best},
        )
    return CheckResult(
        id="person_schema_sameas",
        label="Author Person schema with sameAs links",
        status=CheckStatus.WARN,
        score=0.3,
        weight=1.0,
        detail=f"Person schema present but no sameAs links{label_suffix}. Add LinkedIn, X, GitHub, or ORCID URLs so AI engines can verify authorship.",
        evidence={"sameAs_count": 0, "person_count": len(persons)},
    )


def _check_jsonld_datemodified(jsonld: list[dict]) -> CheckResult:
    """Score dateModified presence on Article-type schema (freshness gate)."""
    if not _has_article_type(jsonld):
        return CheckResult(
            id="freshness_datemodified",
            label="dateModified on Article schema",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=0.7,
            detail="No Article/BlogPosting/NewsArticle JSON-LD on this page. If this is a marketing homepage, that's fine — rescan an article URL for this check.",
        )

    has_modified = False
    has_published = False
    sample: str = ""
    for node in _walk_jsonld(jsonld):
        t = node.get("@type")
        is_article = (isinstance(t, str) and t in _ARTICLE_TYPES) or (
            isinstance(t, list) and any(x in _ARTICLE_TYPES for x in t)
        )
        if not is_article:
            continue
        dm = node.get("dateModified")
        dp = node.get("datePublished")
        if isinstance(dm, str) and dm.strip():
            has_modified = True
            sample = dm.strip()
        if isinstance(dp, str) and dp.strip():
            has_published = True
            if not sample:
                sample = dp.strip()

    if has_modified:
        return CheckResult(
            id="freshness_datemodified",
            label="dateModified on Article schema",
            status=CheckStatus.PASS,
            score=1.0,
            weight=0.7,
            detail=f"Article schema declares dateModified ({sample}). Strong freshness signal for AI ranking.",
        )
    if has_published:
        return CheckResult(
            id="freshness_datemodified",
            label="dateModified on Article schema",
            status=CheckStatus.WARN,
            score=0.6,
            weight=0.7,
            detail=f"datePublished present ({sample}) but no dateModified. Add dateModified so AI engines can tell when content was last refreshed.",
        )
    return CheckResult(
        id="freshness_datemodified",
        label="dateModified on Article schema",
        status=CheckStatus.FAIL,
        score=0.2,
        weight=0.7,
        detail="Article schema present but no dateModified or datePublished. Adding both lifts AI citation rate ~34% (Seenos audit, 2026).",
    )
