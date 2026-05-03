"""Tests for the competitor-baseline endpoint and report cache."""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.compare import (
    _ReportCache,
    normalize_competitor_input,
    report_cache,
    run_cached_scan,
    run_compare,
)
from app.main import app
from app.models import (
    CategoryId,
    CategoryResult,
    CheckResult,
    CheckStatus,
    Report,
)
from app.targets import WebsiteTarget


def _fake_report(domain: str = "example.com", score: int = 80, grade: str = "B") -> Report:
    """Build a minimal valid Report for cache/summary tests."""
    return Report(
        url=f"https://{domain}",
        normalized_url=f"https://{domain}/",
        domain=domain,
        scanned_at=datetime.now(UTC),
        duration_ms=42,
        score=score,
        grade=grade,  # type: ignore[arg-type]
        categories=[
            CategoryResult(
                id=CategoryId.AGENT_ACCESS,
                label="Agent Access",
                weight=0.25,
                score=score,
                checks=[
                    CheckResult(
                        id="x",
                        label="x",
                        status=CheckStatus.PASS,
                        score=1.0,
                        weight=1.0,
                        detail="",
                    )
                ],
                summary="",
            ),
            CategoryResult(
                id=CategoryId.DISCOVERABILITY,
                label="Discoverability",
                weight=0.25,
                score=score - 5,
                checks=[],
                summary="",
            ),
        ],
        fixes=[],
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Each test gets a clean module-level cache."""
    report_cache.clear()


# ---- normalize_competitor_input ------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_present",
    [
        ("stripe.com", True),
        ("https://stripe.com", True),
        ("HTTPS://Stripe.COM/", True),
        # Empty / scheme-only inputs are rejected. Other malformed input
        # passes through here intentionally — the scan will fail-open and
        # surface a per-row error, which is friendlier than a 422.
        ("", False),
        ("   ", False),
        ("https://", False),
    ],
)
def test_normalize_competitor_input(raw: str, expected_present: bool) -> None:
    out = normalize_competitor_input(raw)
    assert (out is not None) is expected_present


# ---- _ReportCache --------------------------------------------------------


def test_report_cache_set_and_get() -> None:
    c = _ReportCache()
    r = _fake_report("a.com", score=90, grade="A")
    c.set("https://a.com/", r)
    got = c.get("https://a.com/")
    assert got is not None
    assert got.domain == "a.com"
    assert got.score == 90


def test_report_cache_returns_none_for_missing_key() -> None:
    c = _ReportCache()
    assert c.get("https://nope.com/") is None


def test_report_cache_evicts_lru_at_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.compare._CACHE_MAX_ENTRIES", 3)
    c = _ReportCache()
    for i in range(5):
        c.set(f"https://site{i}.com/", _fake_report(f"site{i}.com"))
    # Only the 3 most recent survive — site0 and site1 evicted.
    assert c.get("https://site0.com/") is None
    assert c.get("https://site1.com/") is None
    assert c.get("https://site4.com/") is not None


def test_report_cache_lazy_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    """A stale entry returns None and gets dropped on read."""
    # Pin TTL to something we can step past with a small monkeypatched clock.
    monkeypatch.setattr("app.compare._CACHE_TTL_SECONDS", 100)
    fake_now = {"t": 1000.0}
    monkeypatch.setattr("app.compare.time.time", lambda: fake_now["t"])
    c = _ReportCache()
    c.set("https://a.com/", _fake_report("a.com"))
    fake_now["t"] = 1000.0 + 200  # well past TTL
    assert c.get("https://a.com/") is None
    assert c.size == 0


# ---- run_cached_scan -----------------------------------------------------


@pytest.mark.asyncio
async def test_run_cached_scan_caches_after_first_call() -> None:
    runner = AsyncMock(return_value=_fake_report("stripe.com", score=90, grade="A"))
    first = await run_cached_scan("stripe.com", runner)
    second = await run_cached_scan("stripe.com", runner)
    assert first.cached is False
    assert second.cached is True
    assert runner.await_count == 1  # second call hit cache, not the runner
    assert first.score == second.score == 90


@pytest.mark.asyncio
async def test_run_cached_scan_returns_error_row_on_invalid_input() -> None:
    runner = AsyncMock()
    summary = await run_cached_scan("   ", runner)
    assert summary.error == "Invalid domain or URL"
    assert summary.score == 0
    assert summary.grade == "?"
    runner.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_cached_scan_returns_error_row_on_runner_exception() -> None:
    async def boom(*args: object, **kwargs: object) -> Report:
        raise RuntimeError("dns nope")
    summary = await run_cached_scan("brokensite.invalid", boom)
    assert summary.error is not None
    assert "dns nope" in summary.error
    assert summary.score == 0


# ---- run_compare ---------------------------------------------------------


@pytest.mark.asyncio
async def test_run_compare_dedupes_competitor_inputs() -> None:
    runner = AsyncMock(side_effect=lambda target, _probe: _fake_report(target.host))
    target_summary, competitors = await run_compare(
        "https://stripe.com",
        ["square.com", "https://square.com", "  square.com/  "],
        runner,
    )
    assert target_summary.domain == "stripe.com"
    # All three competitor inputs normalized to the same square.com — only one scan.
    assert len(competitors) == 1
    assert competitors[0].domain == "square.com"


@pytest.mark.asyncio
async def test_run_compare_runs_in_parallel_and_returns_each_summary() -> None:
    runner = AsyncMock(side_effect=lambda target, _probe: _fake_report(target.host, score=70))
    target_summary, competitors = await run_compare(
        "https://target.com",
        ["a.com", "b.com", "c.com"],
        runner,
    )
    assert target_summary.domain == "target.com"
    assert [c.domain for c in competitors] == ["a.com", "b.com", "c.com"]
    # Target + 3 competitors = 4 runner invocations.
    assert runner.await_count == 4


@pytest.mark.asyncio
async def test_run_compare_drops_competitor_when_it_matches_target() -> None:
    """PR #17 review regression: pasting the target as a competitor must not
    cause two concurrent scans of the same site (both racing past the cache
    miss). The duplicated competitor row should be dropped from the
    competitors list entirely.
    """
    runner = AsyncMock(side_effect=lambda target, _probe: _fake_report(target.host))
    target_summary, competitors = await run_compare(
        "https://stripe.com",
        # 1st competitor matches the target — should be filtered out.
        # 2nd is a real different domain.
        ["stripe.com", "square.com"],
        runner,
    )
    assert target_summary.domain == "stripe.com"
    assert [c.domain for c in competitors] == ["square.com"]
    # Target + 1 unique competitor = 2 runner calls (NOT 3).
    assert runner.await_count == 2


@pytest.mark.asyncio
async def test_run_compare_keeps_failed_rows_alongside_successes() -> None:
    async def runner(target: WebsiteTarget, _probe: bool) -> Report:
        if target.host == "broken.com":
            raise RuntimeError("connection refused")
        return _fake_report(target.host, score=85)

    target_summary, competitors = await run_compare(
        "https://target.com",
        ["good.com", "broken.com"],
        runner,
    )
    assert target_summary.error is None
    assert competitors[0].domain == "good.com"
    assert competitors[0].error is None
    assert competitors[1].domain == "broken.com"
    assert competitors[1].error is not None


# ---- /api/compare endpoint -----------------------------------------------


def test_compare_endpoint_validation_rejects_no_competitors() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/compare",
        json={"target": "https://stripe.com", "competitors": []},
    )
    assert resp.status_code == 422


def test_compare_endpoint_validation_rejects_more_than_three() -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/compare",
        json={
            "target": "https://stripe.com",
            "competitors": ["a.com", "b.com", "c.com", "d.com"],
        },
    )
    assert resp.status_code == 422


def test_compare_endpoint_returns_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: monkey-patch the scan runner so we don't hit the network."""

    async def fake_scan(target: WebsiteTarget, include_probe: bool) -> Report:
        return _fake_report(target.host, score=88, grade="A")

    monkeypatch.setattr("app.main._run_full_scan", fake_scan)
    client = TestClient(app)
    resp = client.post(
        "/api/compare",
        json={"target": "https://stripe.com", "competitors": ["square.com", "adyen.com"]},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target"]["domain"] == "stripe.com"
    assert body["target"]["score"] == 88
    assert body["target"]["grade"] == "A"
    assert len(body["competitors"]) == 2
    assert {c["domain"] for c in body["competitors"]} == {"square.com", "adyen.com"}
    assert all(c["score"] == 88 for c in body["competitors"])
    # The categories list should be populated and lean (no checks/details).
    assert body["target"]["categories"], "should have at least one category"
    assert "checks" not in body["target"]["categories"][0]
