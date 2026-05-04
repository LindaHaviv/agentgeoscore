"""Tests for the Core Web Vitals scanner.

These tests stub the PageSpeed Insights HTTP call via httpx's MockTransport
so they're deterministic, hermetic, and don't depend on a live API key.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.models import CheckStatus
from app.scanners.core_web_vitals import (
    PSI_URL,
    _classify_metric,
    _extract_field_metrics,
    _extract_lab_metrics,
    check_core_web_vitals,
)
from app.targets import WebsiteTarget

# ---- Fixtures -------------------------------------------------------------


def _target(host: str = "example.com") -> WebsiteTarget:
    return WebsiteTarget.from_url(f"https://{host}")


def _psi_response_with_field(lcp_ms: float, cls_x100: float, inp_ms: float) -> dict:
    """Build a PSI response shaped like the real API for CrUX field data.

    PSI returns CLS as integer-percentile *100, hence cls_x100.
    """
    return {
        "loadingExperience": {
            "metrics": {
                "LARGEST_CONTENTFUL_PAINT_MS": {"percentile": lcp_ms},
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": {"percentile": cls_x100},
                "INTERACTION_TO_NEXT_PAINT": {"percentile": inp_ms},
            }
        },
        "lighthouseResult": {"audits": {}},
    }


def _psi_response_lab_only(lcp_ms: float, cls: float, tbt_ms: float) -> dict:
    """Build a PSI response with no CrUX field data, only lab metrics."""
    return {
        # Empty / missing loadingExperience block — typical for low-traffic sites.
        "lighthouseResult": {
            "audits": {
                "largest-contentful-paint": {"numericValue": lcp_ms},
                "cumulative-layout-shift": {"numericValue": cls},
                "total-blocking-time": {"numericValue": tbt_ms},
            }
        },
    }


def _patch_psi(monkeypatch: pytest.MonkeyPatch, *, payload: dict | None = None,
               status: int = 200, raise_exc: Exception | None = None) -> None:
    """Replace ``httpx.AsyncClient`` with one that returns ``payload`` for PSI.

    Works by intercepting the `.get(PSI_URL, params=...)` call and returning
    a canned ``httpx.Response``. Other calls would raise (we never make any
    in this scanner).
    """
    payload = payload or {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        assert str(request.url).startswith(PSI_URL), f"Unexpected URL: {request.url}"
        return httpx.Response(status, content=json.dumps(payload))

    transport = httpx.MockTransport(handler)

    # Wrap AsyncClient so the scanner's `async with httpx.AsyncClient()` block
    # gets our mocked transport.
    real_async_client = httpx.AsyncClient

    def mocked(*args, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    monkeypatch.setattr("app.scanners.core_web_vitals.httpx.AsyncClient", mocked)


# ---- _classify_metric -----------------------------------------------------


@pytest.mark.parametrize(
    "value,good,poor,expected",
    [
        (1.5, 2.5, 4.0, "good"),
        (2.5, 2.5, 4.0, "good"),  # boundary inclusive on the good side
        (3.0, 2.5, 4.0, "needs_improvement"),
        (4.0, 2.5, 4.0, "needs_improvement"),  # poor cutoff is exclusive
        (4.5, 2.5, 4.0, "poor"),
        (0.0, 0.10, 0.25, "good"),
        (0.05, 0.10, 0.25, "good"),
        (0.30, 0.10, 0.25, "poor"),
    ],
)
def test_classify_metric_buckets(
    value: float, good: float, poor: float, expected: str
) -> None:
    assert _classify_metric(value, good, poor) == expected


# ---- _extract_field_metrics / _extract_lab_metrics ------------------------


def test_extract_field_metrics_pulls_all_three_signals() -> None:
    data = _psi_response_with_field(lcp_ms=1800, cls_x100=5, inp_ms=120)
    field = _extract_field_metrics(data)
    assert field is not None
    assert field["lcp_s"] == pytest.approx(1.8)
    assert field["cls"] == pytest.approx(0.05)
    assert field["inp_ms"] == pytest.approx(120.0)


def test_extract_field_metrics_returns_none_when_no_crux_data() -> None:
    data = {"lighthouseResult": {"audits": {}}}
    assert _extract_field_metrics(data) is None


def test_extract_field_metrics_returns_none_when_metrics_block_empty() -> None:
    data = {"loadingExperience": {"metrics": {}}}
    assert _extract_field_metrics(data) is None


def test_extract_lab_metrics_uses_lighthouse_audits() -> None:
    data = _psi_response_lab_only(lcp_ms=2200, cls=0.07, tbt_ms=180)
    lab = _extract_lab_metrics(data)
    assert lab is not None
    assert lab["lcp_s"] == pytest.approx(2.2)
    assert lab["cls"] == pytest.approx(0.07)
    assert lab["tbt_ms"] == pytest.approx(180.0)


def test_extract_lab_metrics_returns_none_when_no_audits() -> None:
    assert _extract_lab_metrics({}) is None


# ---- check_core_web_vitals end-to-end -------------------------------------


@pytest.mark.asyncio
async def test_skip_when_api_key_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PAGESPEED_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.SKIP
    assert result.id == "core_web_vitals"
    assert "PAGESPEED_API_KEY not set" in result.detail


@pytest.mark.asyncio
async def test_field_data_pass_when_all_metrics_good(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    _patch_psi(monkeypatch, payload=_psi_response_with_field(
        lcp_ms=1800, cls_x100=5, inp_ms=120
    ))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.PASS
    assert result.score == pytest.approx(1.0)
    assert result.evidence is not None
    assert result.evidence["source"].startswith("field")
    assert "LCP 1.8s" in result.detail
    assert "CLS 0.05" in result.detail
    assert "INP 120 ms" in result.detail


@pytest.mark.asyncio
async def test_field_data_warn_when_one_metric_needs_improvement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    # LCP 3.2s = needs_improvement; CLS + INP good.
    _patch_psi(monkeypatch, payload=_psi_response_with_field(
        lcp_ms=3200, cls_x100=5, inp_ms=120
    ))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.WARN
    assert "LCP needs improvement" in result.detail


@pytest.mark.asyncio
async def test_field_data_fail_when_any_metric_poor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    # CLS = 0.30 → poor; LCP + INP good.
    _patch_psi(monkeypatch, payload=_psi_response_with_field(
        lcp_ms=1800, cls_x100=30, inp_ms=120
    ))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.FAIL
    assert "CLS is poor" in result.detail


@pytest.mark.asyncio
async def test_falls_back_to_lab_when_no_field_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    _patch_psi(monkeypatch, payload=_psi_response_lab_only(
        lcp_ms=2200, cls=0.07, tbt_ms=150
    ))
    result = await check_core_web_vitals(_target())
    # Lab data only has LCP + CLS in scope (no INP). Both good → PASS.
    assert result.status == CheckStatus.PASS
    assert result.evidence is not None
    assert result.evidence["source"].startswith("lab")
    assert "Synthetic Lighthouse run" in result.detail


@pytest.mark.asyncio
async def test_lab_data_warn_when_metric_is_poor_not_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lab data is noisier than field data, so poor lab → WARN, not FAIL.

    Field data corresponds to real users; a poor field number is reliable.
    A single Lighthouse run can vary ±20% per device load, so we don't
    want to FAIL a site on lab numbers alone.
    """
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    _patch_psi(monkeypatch, payload=_psi_response_lab_only(
        lcp_ms=5000, cls=0.05, tbt_ms=400
    ))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.WARN
    assert "(lab)" in result.detail


@pytest.mark.asyncio
async def test_skip_on_psi_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    _patch_psi(monkeypatch, status=429, payload={"error": "Quota exceeded"})
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.SKIP
    assert "HTTP 429" in result.detail


@pytest.mark.asyncio
async def test_skip_on_psi_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    _patch_psi(monkeypatch, raise_exc=httpx.TimeoutException("psi too slow"))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.SKIP
    assert "PageSpeed Insights fetch failed" in result.detail


@pytest.mark.asyncio
async def test_skip_when_psi_returns_no_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAGESPEED_API_KEY", "fake-key")
    # 200 response, but no loadingExperience and no lighthouseResult — PSI
    # genuinely couldn't load the URL.
    _patch_psi(monkeypatch, payload={})
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.SKIP
    assert "no usable field or lab metrics" in result.detail


@pytest.mark.asyncio
async def test_google_api_key_env_var_also_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Some users already have GOOGLE_API_KEY set for other Google APIs; we
    accept either to reduce friction. PAGESPEED_API_KEY takes precedence."""
    monkeypatch.delenv("PAGESPEED_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "fallback-key")
    _patch_psi(monkeypatch, payload=_psi_response_with_field(
        lcp_ms=1800, cls_x100=5, inp_ms=120
    ))
    result = await check_core_web_vitals(_target())
    assert result.status == CheckStatus.PASS
