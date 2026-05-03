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

    # Validator-conformance: are the JSON-LD blocks that DO exist structurally
    # complete per schema.org / Google Rich Results requirements? Invalid
    # blocks silently fail for AI crawlers the same way missing ones do.
    if jsonld:
        results.append(_check_jsonld_validity(jsonld))

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


# ---- JSON-LD validator-conformance (gap #5) -------------------------------
#
# Schema.org-published types are only useful to AI crawlers if they parse —
# Google Rich Results, Perplexity's crawler, and Schema.org's own validator
# silently *drop* blocks that are missing required properties. A common
# failure mode we see in the wild: `@type: "Article"` with no `headline`,
# `@type: "Product"` with no `offers`, `@type: "FAQPage"` with malformed
# `mainEntity` arrays. Presence ≠ validity; this check is presence-of-required.
#
# Required / recommended props below encode Google's rich-results requirements
# (https://developers.google.com/search/docs/appearance/structured-data) for
# the 6 types that matter most for AI citation surfacing. We deliberately
# don't try to be a full JSON schema validator — just the required-field gate
# that makes or breaks rich-result inclusion.
_REQUIRED_BY_TYPE: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    # type: (required, recommended)
    "Article":       (("headline", "author", "datePublished"), ("dateModified", "image", "publisher")),
    "BlogPosting":   (("headline", "author", "datePublished"), ("dateModified", "image", "publisher")),
    "NewsArticle":   (("headline", "author", "datePublished"), ("dateModified", "image", "publisher")),
    "Product":       (("name",), ("image", "description", "offers", "aggregateRating", "review", "brand")),
    "FAQPage":       (("mainEntity",), ()),
    "Organization":  (("name", "url"), ("logo", "sameAs", "description")),
    "Person":        (("name",), ("sameAs", "url", "jobTitle")),
}


def _has_prop(node: dict, prop: str) -> bool:
    """True if ``node[prop]`` is present and not an empty/blank value."""
    v = node.get(prop)
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def _node_types(node: dict) -> list[str]:
    t = node.get("@type")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    return []


def _validate_faqpage_mainentity(node: dict) -> list[str]:
    """FAQPage needs ``mainEntity`` to be a non-empty list of valid Questions.

    Each Question item must have ``name`` (the question text) and an
    ``acceptedAnswer`` with a non-empty ``text``. Returns a list of
    human-readable problems, empty if the block is valid.
    """
    me = node.get("mainEntity")
    if me is None:
        return ["mainEntity missing"]
    items = me if isinstance(me, list) else [me]
    if not items:
        return ["mainEntity is empty"]
    problems: list[str] = []
    for i, q in enumerate(items):
        if not isinstance(q, dict):
            problems.append(f"mainEntity[{i}] is not an object")
            continue
        q_types = _node_types(q)
        if q_types and "Question" not in q_types:
            problems.append(f"mainEntity[{i}] @type is not Question")
        if not _has_prop(q, "name"):
            problems.append(f"mainEntity[{i}] missing name")
        accepted = q.get("acceptedAnswer")
        if not isinstance(accepted, dict):
            problems.append(f"mainEntity[{i}] missing acceptedAnswer")
            continue
        if not _has_prop(accepted, "text"):
            problems.append(f"mainEntity[{i}].acceptedAnswer missing text")
    return problems


def _validate_block(node: dict) -> tuple[str | None, list[str], list[str]]:
    """Inspect one JSON-LD node.

    Returns ``(matched_type, missing_required, missing_recommended)`` where
    ``matched_type`` is the first known schema.org type we found (or ``None``
    if the node's @type isn't one we validate). ``missing_required`` non-empty
    means the block is structurally broken for rich-result purposes.
    """
    types = _node_types(node)
    for t in types:
        if t not in _REQUIRED_BY_TYPE:
            continue
        required, recommended = _REQUIRED_BY_TYPE[t]
        missing_required: list[str] = []
        if t == "FAQPage":
            # FAQPage has structural rules inside mainEntity — delegate.
            faq_problems = _validate_faqpage_mainentity(node)
            if faq_problems:
                missing_required.extend(faq_problems)
        else:
            for prop in required:
                if not _has_prop(node, prop):
                    missing_required.append(prop)
        missing_recommended = [p for p in recommended if not _has_prop(node, p)]
        return t, missing_required, missing_recommended
    return None, [], []


def _check_jsonld_validity(jsonld: list[dict]) -> CheckResult:
    """Verify that each present JSON-LD block has the properties its @type requires.

    Only emitted when at least one block exists (the jsonld_present check
    owns the "no JSON-LD at all" messaging).
    """
    validated: list[dict] = []
    total_validated = 0
    blocks_with_broken_required = 0
    blocks_with_missing_recommended = 0
    # Only validate *top-level* JSON-LD blocks, not nested support nodes.
    # extract_jsonld already flattens @graph children into this list, so
    # `jsonld` is the canonical set of stand-alone entities. Nested
    # ``publisher`` / ``author`` / ``mainEntity`` sub-nodes are governed by
    # their parent type's rules (e.g. FAQPage validates its Questions via
    # ``_validate_faqpage_mainentity``) and must not be re-validated as
    # if they were independent top-level entities.
    for node in jsonld:
        matched, missing_required, missing_recommended = _validate_block(node)
        if matched is None:
            continue
        total_validated += 1
        entry = {
            "type": matched,
            "missing_required": missing_required,
            "missing_recommended": missing_recommended,
        }
        # Capture a stable handle for the block so the evidence list is
        # user-debuggable — preferred order: name, headline, url, @id.
        for handle in ("name", "headline", "url", "@id"):
            v = node.get(handle)
            if isinstance(v, str) and v.strip():
                entry["label"] = v.strip()[:80]
                break
        validated.append(entry)
        if missing_required:
            blocks_with_broken_required += 1
        elif missing_recommended:
            blocks_with_missing_recommended += 1

    if total_validated == 0:
        return CheckResult(
            id="jsonld_validity",
            label="JSON-LD validity (required properties)",
            status=CheckStatus.SKIP,
            score=0.0,
            weight=1.5,
            detail=(
                "JSON-LD is present, but none of the blocks declare a schema.org "
                "type we validate (Article / BlogPosting / NewsArticle / Product / "
                "FAQPage / Organization / Person). We can't check validity without "
                "a known @type — add one of those types so AI engines (and Google "
                "Rich Results) can actually use the data."
            ),
            evidence={"validated": 0, "types_checked": sorted(_REQUIRED_BY_TYPE)},
        )

    evidence = {
        "validated": total_validated,
        "broken_required": blocks_with_broken_required,
        "missing_recommended": blocks_with_missing_recommended,
        "blocks": validated,
    }

    if blocks_with_broken_required:
        # Any block missing a required prop is invisible to validators →
        # invisible to the rich-result layer → treated as absent by AI
        # crawlers that check.
        sample = next(b for b in validated if b["missing_required"])
        return CheckResult(
            id="jsonld_validity",
            label="JSON-LD validity (required properties)",
            status=CheckStatus.FAIL,
            score=0.2,
            weight=1.5,
            detail=(
                f"{blocks_with_broken_required}/{total_validated} JSON-LD block(s) are "
                f"missing required properties — e.g. a {sample['type']} block missing "
                f"{', '.join(sample['missing_required'][:3])}. Google Rich Results and "
                f"AI crawlers silently drop invalid blocks, so these count as absent."
            ),
            evidence=evidence,
        )
    if blocks_with_missing_recommended:
        sample = next(b for b in validated if b["missing_recommended"])
        return CheckResult(
            id="jsonld_validity",
            label="JSON-LD validity (required properties)",
            status=CheckStatus.WARN,
            score=0.75,
            weight=1.5,
            detail=(
                f"All {total_validated} JSON-LD block(s) declare their required "
                f"properties. But some recommended fields are missing — e.g. a "
                f"{sample['type']} block without {', '.join(sample['missing_recommended'][:3])}. "
                f"Optional for rich-result validity, but strong citation signals."
            ),
            evidence=evidence,
        )
    return CheckResult(
        id="jsonld_validity",
        label="JSON-LD validity (required properties)",
        status=CheckStatus.PASS,
        score=1.0,
        weight=1.5,
        detail=(
            f"All {total_validated} JSON-LD block(s) declare every required and "
            f"recommended property we check. AI crawlers and Google Rich Results "
            f"can parse these blocks cleanly."
        ),
        evidence=evidence,
    )
