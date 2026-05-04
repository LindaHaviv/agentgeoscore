"""Core Web Vitals — performance signals AI engines and search inherit.

Why this matters for GEO:
- Google AI Overviews is grafted onto traditional Google Search, which
  uses Core Web Vitals (LCP, CLS, INP) as a ranking factor. A page that
  fails CWV is deprioritized in the underlying search index and therefore
  less likely to surface in AI Overviews.
- Bing / Copilot uses similar perf signals (Bing's documentation:
  https://blogs.bing.com/webmaster/october-2023/Bing-Search-Engine-Optimization-Best-Practices).
- AI crawlers themselves time out on slow pages; a page that never
  finishes streaming above-the-fold content within a few seconds is
  likely to be partially-extracted by GPTBot/ClaudeBot.

We call the Google PageSpeed Insights v5 API (free tier — 25,000 req/day
with key, 4 req/min keyless). Mobile strategy is the default since
Google ranks on mobile-first. We surface:

- **Field data** (real users, from CrUX) when available — Google only
  publishes CrUX percentiles for sites with sufficient traffic.
- **Lab data** (single Lighthouse run) as a fallback for low-traffic
  sites without CrUX coverage.

Thresholds are Google's official Core Web Vitals tiers
(https://web.dev/articles/vitals):

| Metric | Good   | Needs improvement | Poor   |
|--------|--------|-------------------|--------|
| LCP    | ≤2.5s  | 2.5–4.0s          | >4.0s  |
| CLS    | ≤0.10  | 0.10–0.25         | >0.25  |
| INP    | ≤200ms | 200–500ms         | >500ms |

We fail-open: if the API key is unset, the request times out, or PSI
returns a non-200, the row SKIPs with an explanatory detail rather than
dragging the score down. The presence of CWV data is a positive signal,
not its absence.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

from ..models import CheckResult, CheckStatus
from ..targets import WebsiteTarget

# Google PageSpeed Insights v5 endpoint.
# Docs: https://developers.google.com/speed/docs/insights/v5/get-started
PSI_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

# 30s ceiling — PSI runs Lighthouse server-side and can take 15–25s on
# slow sites. 5s connect cap so DNS / TLS issues fail fast.
PSI_TIMEOUT = httpx.Timeout(30.0, connect=5.0)

# Strategy. Google ranks on mobile-first; we mirror that.
PSI_STRATEGY = "mobile"

# Google's Core Web Vitals thresholds.
_LCP_GOOD_S = 2.5
_LCP_POOR_S = 4.0
_CLS_GOOD = 0.10
_CLS_POOR = 0.25
_INP_GOOD_MS = 200
_INP_POOR_MS = 500


def _classify_metric(value: float, good: float, poor: float) -> str:
    """Return ``"good"`` | ``"needs_improvement"`` | ``"poor"``."""
    if value <= good:
        return "good"
    if value <= poor:
        return "needs_improvement"
    return "poor"


def _format_lcp(seconds: float) -> str:
    return f"{seconds:.1f}s"


def _format_cls(value: float) -> str:
    return f"{value:.2f}"


def _format_inp(ms: float) -> str:
    return f"{int(round(ms))} ms"


def _extract_field_metrics(data: dict) -> dict[str, float] | None:
    """Pull CrUX field data (real users) when PSI returns it.

    Returns ``{"lcp_s": ..., "cls": ..., "inp_ms": ...}`` or ``None`` if no
    CrUX data is available (typical for low-traffic sites).
    """
    loading = data.get("loadingExperience") or {}
    metrics = loading.get("metrics") or {}
    if not metrics:
        return None
    out: dict[str, float] = {}
    lcp = metrics.get("LARGEST_CONTENTFUL_PAINT_MS") or {}
    if "percentile" in lcp:
        out["lcp_s"] = lcp["percentile"] / 1000.0
    cls = metrics.get("CUMULATIVE_LAYOUT_SHIFT_SCORE") or {}
    if "percentile" in cls:
        # PSI returns CLS *100 as int — divide back to spec units.
        out["cls"] = cls["percentile"] / 100.0
    inp = metrics.get("INTERACTION_TO_NEXT_PAINT") or {}
    if "percentile" in inp:
        out["inp_ms"] = float(inp["percentile"])
    return out or None


def _extract_lab_metrics(data: dict) -> dict[str, float] | None:
    """Pull Lighthouse lab data — single synthetic run, always present.

    We use Total Blocking Time (TBT) as the lab proxy for INP; INP itself
    is a field metric and not measured in lab. ``numericValue`` is the
    raw measurement (ms for time-based, unitless for CLS).
    """
    audits = (data.get("lighthouseResult") or {}).get("audits") or {}
    if not audits:
        return None
    out: dict[str, float] = {}
    lcp = audits.get("largest-contentful-paint") or {}
    if "numericValue" in lcp:
        out["lcp_s"] = lcp["numericValue"] / 1000.0
    cls = audits.get("cumulative-layout-shift") or {}
    if "numericValue" in cls:
        out["cls"] = cls["numericValue"]
    tbt = audits.get("total-blocking-time") or {}
    if "numericValue" in tbt:
        out["tbt_ms"] = tbt["numericValue"]
    return out or None


def _score_field_metrics(metrics: dict[str, float]) -> tuple[CheckStatus, float, list[str]]:
    """Score CrUX field metrics. Returns (status, score, violation_summaries).

    Field data is the gold standard — real-user percentiles. We FAIL if any
    metric is poor, WARN if any is needs-improvement, PASS if all good.
    """
    classes = {
        "LCP": _classify_metric(metrics.get("lcp_s", 0.0), _LCP_GOOD_S, _LCP_POOR_S)
        if "lcp_s" in metrics else None,
        "CLS": _classify_metric(metrics.get("cls", 0.0), _CLS_GOOD, _CLS_POOR)
        if "cls" in metrics else None,
        "INP": _classify_metric(metrics.get("inp_ms", 0.0), _INP_GOOD_MS, _INP_POOR_MS)
        if "inp_ms" in metrics else None,
    }
    poor = [k for k, v in classes.items() if v == "poor"]
    ni = [k for k, v in classes.items() if v == "needs_improvement"]
    if poor:
        return CheckStatus.FAIL, 0.25, [f"{m} is poor" for m in poor] + [
            f"{m} needs improvement" for m in ni
        ]
    if ni:
        return CheckStatus.WARN, 0.6, [f"{m} needs improvement" for m in ni]
    return CheckStatus.PASS, 1.0, []


def _score_lab_metrics(metrics: dict[str, float]) -> tuple[CheckStatus, float, list[str]]:
    """Lab data is noisier than field data — be more lenient.

    A single Lighthouse run can vary ±20% from device load. Treat poor as
    WARN (not FAIL) and needs-improvement as a softer pass with notes.
    """
    classes = {
        "LCP": _classify_metric(metrics.get("lcp_s", 0.0), _LCP_GOOD_S, _LCP_POOR_S)
        if "lcp_s" in metrics else None,
        "CLS": _classify_metric(metrics.get("cls", 0.0), _CLS_GOOD, _CLS_POOR)
        if "cls" in metrics else None,
    }
    poor = [k for k, v in classes.items() if v == "poor"]
    ni = [k for k, v in classes.items() if v == "needs_improvement"]
    if poor:
        return CheckStatus.WARN, 0.5, [f"{m} is poor (lab)" for m in poor] + [
            f"{m} needs improvement (lab)" for m in ni
        ]
    if ni:
        return CheckStatus.PASS, 0.8, [f"{m} needs improvement (lab)" for m in ni]
    return CheckStatus.PASS, 0.95, []


def _build_field_detail(metrics: dict[str, float], summaries: list[str]) -> str:
    parts: list[str] = []
    if "lcp_s" in metrics:
        parts.append(f"LCP {_format_lcp(metrics['lcp_s'])}")
    if "cls" in metrics:
        parts.append(f"CLS {_format_cls(metrics['cls'])}")
    if "inp_ms" in metrics:
        parts.append(f"INP {_format_inp(metrics['inp_ms'])}")
    metric_str = ", ".join(parts) if parts else "(no metrics)"
    base = (
        f"Real-user data (Google CrUX, mobile p75): {metric_str}. "
        f"Google AI Overviews and traditional Google Search both use Core "
        f"Web Vitals as a ranking signal — failing pages are deprioritized "
        f"regardless of content quality."
    )
    if summaries:
        base += " Violations: " + "; ".join(summaries) + "."
    return base


def _build_lab_detail(metrics: dict[str, float], summaries: list[str]) -> str:
    parts: list[str] = []
    if "lcp_s" in metrics:
        parts.append(f"LCP {_format_lcp(metrics['lcp_s'])}")
    if "cls" in metrics:
        parts.append(f"CLS {_format_cls(metrics['cls'])}")
    if "tbt_ms" in metrics:
        parts.append(f"TBT {_format_inp(metrics['tbt_ms'])} (lab proxy for INP)")
    metric_str = ", ".join(parts) if parts else "(no metrics)"
    base = (
        f"Synthetic Lighthouse run (mobile, lab data — no CrUX field "
        f"history available): {metric_str}. Lab numbers vary ±20% per run, "
        f"so this is directional. To get authoritative percentiles, drive "
        f"enough mobile traffic that the URL appears in the Chrome User "
        f"Experience Report."
    )
    if summaries:
        base += " Notes: " + "; ".join(summaries) + "."
    return base


def _skip(detail: str) -> CheckResult:
    return CheckResult(
        id="core_web_vitals",
        label="Core Web Vitals",
        status=CheckStatus.SKIP,
        score=0.0,
        weight=1.5,
        detail=detail,
        evidence=None,
    )


async def check_core_web_vitals(target: WebsiteTarget) -> CheckResult:
    """Score the homepage's Core Web Vitals via Google PageSpeed Insights.

    Falls back to SKIP cleanly when:
    - ``PAGESPEED_API_KEY`` (or ``GOOGLE_API_KEY``) is unset
    - PSI returns non-200 or times out
    - PSI returns no usable metrics for either field or lab data

    We always emit the row so users see WHY CWV wasn't scored, not just
    that it's missing.
    """
    api_key = os.getenv("PAGESPEED_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    if not api_key:
        return _skip(
            "PAGESPEED_API_KEY not set — skipping Core Web Vitals. Google AI "
            "Overviews and traditional Google Search both weight CWV; failing "
            "pages are deprioritized regardless of content quality. Get a free "
            "key at https://developers.google.com/speed/docs/insights/v5/get-started "
            "(25,000 req/day, no card required) and set it as PAGESPEED_API_KEY."
        )

    params = {
        "url": target.url,
        "key": api_key,
        "strategy": PSI_STRATEGY,
        "category": "PERFORMANCE",
    }

    try:
        async with httpx.AsyncClient(timeout=PSI_TIMEOUT) as client:
            resp = await client.get(PSI_URL, params=params)
    except httpx.HTTPError as exc:
        return _skip(
            f"PageSpeed Insights fetch failed ({exc.__class__.__name__}: "
            f"{str(exc)[:120]}). Will retry on next scan."
        )

    if resp.status_code != 200:
        # Common non-200s: 400 (bad URL), 403 (key invalid / quota), 429
        # (rate-limited), 500 (PSI internal). All are transient or
        # configuration-level — don't drag the user's score down.
        body = (resp.text or "")[:200]
        return _skip(
            f"PageSpeed Insights returned HTTP {resp.status_code}. This usually "
            f"means the key is invalid, the daily quota is exhausted, or PSI "
            f"can't reach your URL. Body: {body!r}"
        )

    try:
        data: dict[str, Any] = resp.json()
    except ValueError:
        return _skip(
            "PageSpeed Insights returned non-JSON. Likely a transient PSI "
            "outage — try again in a minute."
        )

    field = _extract_field_metrics(data)
    if field is not None:
        status, score, summaries = _score_field_metrics(field)
        return CheckResult(
            id="core_web_vitals",
            label="Core Web Vitals",
            status=status,
            score=round(score, 3),
            weight=1.5,
            detail=_build_field_detail(field, summaries),
            evidence={
                "source": "field (CrUX, mobile p75)",
                "strategy": PSI_STRATEGY,
                **field,
            },
        )

    lab = _extract_lab_metrics(data)
    if lab is not None:
        status, score, summaries = _score_lab_metrics(lab)
        return CheckResult(
            id="core_web_vitals",
            label="Core Web Vitals",
            status=status,
            score=round(score, 3),
            weight=1.5,
            detail=_build_lab_detail(lab, summaries),
            evidence={
                "source": "lab (single Lighthouse run, mobile)",
                "strategy": PSI_STRATEGY,
                **lab,
            },
        )

    return _skip(
        "PageSpeed Insights returned a 200 but no usable field or lab "
        "metrics were found in the response. This is rare — usually means "
        "PSI couldn't load the URL (timeout, blocked by robots.txt, or a "
        "redirect loop)."
    )
