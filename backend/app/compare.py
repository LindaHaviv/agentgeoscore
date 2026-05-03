"""Competitor baseline — runs the existing scan pipeline for the target plus
1-3 competitor domains in parallel and returns a lean side-by-side summary.

Why a separate endpoint instead of N independent ``/api/scan`` calls from the
frontend:

- We want to share a single in-memory TTL cache across both the regular scan
  flow and compare flow, so a competitor that's already been compared (or
  scanned today) returns instantly on subsequent comparisons. A frontend-driven
  approach would either need its own duplicate cache or make redundant
  network round-trips.
- We can collapse the response to a much smaller payload (overall score +
  per-category score per domain) than 4 full ``Report`` objects. Network +
  parse cost matters when the user is comparing 4 sites.
- Errors (e.g. one competitor TLD bounces) get reported per-row instead of
  taking down the whole compare.

Score calls always run with ``include_probe=False``: live citation probes
add 5-15 s per scan and cost money. The user can re-run the *target* with
probes on from the regular report flow if they want them.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import TYPE_CHECKING

from .models import (
    CategorySummary,
    CompareSummary,
    Report,
)
from .targets import WebsiteTarget

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

# How long a cached scan stays fresh. AI-engine signals don't change minute
# to minute; an hour is a reasonable trade-off between freshness and not
# hammering competitor sites on every compare.
_CACHE_TTL_SECONDS = 60 * 60  # 1 hour
# Hard cap on entries — bounded to keep memory predictable on the small
# Fly machine. LRU eviction once we hit the cap.
_CACHE_MAX_ENTRIES = 256


class _ReportCache:
    """In-memory TTL cache keyed by normalized URL. Process-local.

    On Fly we run a single backend instance, so a process-local cache hits
    every request. If we ever scale horizontally, swap this for a Redis-
    backed cache without touching call sites.
    """

    def __init__(self) -> None:
        self._entries: OrderedDict[str, tuple[float, Report]] = OrderedDict()

    def get(self, key: str) -> Report | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        ts, report = entry
        if time.time() - ts > _CACHE_TTL_SECONDS:
            # Lazy expiry — drop the stale entry the moment we observe it.
            self._entries.pop(key, None)
            return None
        # Bump LRU recency on read.
        self._entries.move_to_end(key)
        return report

    def set(self, key: str, report: Report) -> None:
        self._entries[key] = (time.time(), report)
        self._entries.move_to_end(key)
        while len(self._entries) > _CACHE_MAX_ENTRIES:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        """Used in tests to reset state between cases."""
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


# Module-level singleton — the FastAPI app shares it across all requests.
report_cache = _ReportCache()


def _summarize(report: Report, *, cached: bool = False) -> CompareSummary:
    """Project a full ``Report`` down to the lean ``CompareSummary`` shape."""
    return CompareSummary(
        domain=report.domain,
        url=report.normalized_url,
        score=report.score,
        grade=report.grade,
        categories=[
            CategorySummary(id=c.id, label=c.label, score=c.score)
            for c in report.categories
        ],
        duration_ms=report.duration_ms,
        error=None,
        cached=cached,
    )


def _error_summary(raw_input: str, error: str) -> CompareSummary:
    """Build a placeholder summary for a competitor whose scan failed.

    We still return a row so the UI can render "couldn't reach this site"
    instead of silently dropping it. ``score=0`` / ``grade='?'`` make it
    visually distinct from a real low score.
    """
    # Best-effort host extraction — if even normalization fails, fall back
    # to whatever the user typed.
    try:
        target = WebsiteTarget.from_url(
            raw_input if "://" in raw_input else f"https://{raw_input}"
        )
        domain, url = target.host, target.url
    except ValueError:
        domain = raw_input.strip()[:120] or "?"
        url = ""
    return CompareSummary(
        domain=domain,
        url=url,
        score=0,
        grade="?",
        categories=[],
        duration_ms=0,
        error=error[:240],
        cached=False,
    )


def normalize_competitor_input(raw: str) -> str | None:
    """Accept domain-or-URL input and return a normalized https URL, or None.

    Trims whitespace, prepends ``https://`` when missing, drops obvious
    junk (empty / scheme-only / spaces). Used by the endpoint to dedupe
    competitor inputs before kicking off scans.
    """
    if not raw:
        return None
    cleaned = raw.strip()
    if not cleaned or cleaned in {"http://", "https://"}:
        return None
    if "://" not in cleaned:
        cleaned = "https://" + cleaned
    try:
        target = WebsiteTarget.from_url(cleaned)
    except ValueError:
        return None
    return target.url


async def run_cached_scan(
    raw_input: str,
    scan_runner: Callable[[WebsiteTarget, bool], Awaitable[Report]],
    *,
    include_probe: bool = False,
) -> CompareSummary:
    """Run a scan for ``raw_input`` (domain or URL), with caching + error handling.

    Returns a ``CompareSummary``. Never raises — fail-open per scanner
    conventions: a bad input or unreachable site produces an
    ``error`` row, not a 5xx.
    """
    normalized = normalize_competitor_input(raw_input)
    if normalized is None:
        return _error_summary(raw_input, "Invalid domain or URL")

    cached = report_cache.get(normalized)
    if cached is not None:
        return _summarize(cached, cached=True)

    try:
        target = WebsiteTarget.from_url(normalized)
        report = await scan_runner(target, include_probe)
    except Exception as exc:  # noqa: BLE001 — fail-open; surface as row error
        return _error_summary(raw_input, f"{type(exc).__name__}: {exc}"[:240])

    report_cache.set(normalized, report)
    return _summarize(report, cached=False)


async def run_compare(
    target_url: str,
    competitor_inputs: list[str],
    scan_runner: Callable[[WebsiteTarget, bool], Awaitable[Report]],
) -> tuple[CompareSummary, list[CompareSummary]]:
    """Run target + competitors in parallel, dedupe trivial duplicates."""
    # Drop empty entries up front and dedupe by normalized URL so the user
    # doesn't accidentally pay for "stripe.com" + "https://stripe.com" twice.
    # Also seed `seen` with the target itself so a user pasting the target
    # domain as a competitor doesn't trigger two concurrent scans of the same
    # site (both would race past the cache check before either could write
    # back). Bug from PR #17 review.
    seen: set[str] = set()
    target_normalized = normalize_competitor_input(target_url)
    if target_normalized is not None:
        seen.add(target_normalized)
    cleaned_competitors: list[str] = []
    for raw in competitor_inputs:
        normalized = normalize_competitor_input(raw)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        cleaned_competitors.append(raw)

    target_summary, *competitor_summaries = await asyncio.gather(
        run_cached_scan(target_url, scan_runner, include_probe=False),
        *(run_cached_scan(c, scan_runner, include_probe=False) for c in cleaned_competitors),
    )
    return target_summary, list(competitor_summaries)
