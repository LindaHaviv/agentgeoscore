"""Probe unit tests — all HTTP is mocked with respx so they run offline."""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.models import CheckStatus
from app.probes.brave import probe_brave
from app.probes.duck_ai import probe_duck_ai
from app.probes.gemini import probe_gemini
from app.probes.mistral import probe_mistral


@pytest.fixture
def unset_keys(monkeypatch):
    for k in ("GEMINI_API_KEY", "MISTRAL_API_KEY", "BRAVE_API_KEY"):
        monkeypatch.delenv(k, raising=False)


async def test_gemini_skip_without_key(unset_keys):
    r = await probe_gemini(["q"], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "GEMINI_API_KEY" in r.detail


@respx.mock
async def test_gemini_counts_citations(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {
                        "groundingMetadata": {
                            "groundingChunks": [
                                {"web": {"uri": "https://example.com/a"}},
                                {"web": {"uri": "https://other.com/b"}},
                            ]
                        }
                    }
                ]
            },
        )
    )
    r = await probe_gemini(["what is example"], "example.com")
    assert r.status == CheckStatus.PASS
    assert r.score == 1.0
    assert r.evidence["hits"] == 1


@respx.mock
async def test_gemini_no_hit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(
        return_value=Response(
            200,
            json={
                "candidates": [
                    {
                        "groundingMetadata": {
                            "groundingChunks": [
                                {"web": {"uri": "https://other.com/b"}},
                            ]
                        }
                    }
                ]
            },
        )
    )
    r = await probe_gemini(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.FAIL
    assert r.score == 0.0
    assert r.evidence["hits"] == 0


@respx.mock
async def test_gemini_all_errors_skip(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    ).mock(return_value=Response(500))
    r = await probe_gemini(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


async def test_mistral_skip_without_key(unset_keys):
    r = await probe_mistral(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


@respx.mock
async def test_mistral_extracts_urls_from_content(monkeypatch):
    monkeypatch.setenv("MISTRAL_API_KEY", "fake")
    respx.post("https://api.mistral.ai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "Sources: https://example.com/x and https://other.com/y",
                            "references": [{"url": "https://example.com/x"}],
                        }
                    }
                ]
            },
        )
    )
    r = await probe_mistral(["q"], "example.com")
    assert r.status == CheckStatus.PASS


async def test_brave_skip_without_key(unset_keys):
    r = await probe_brave(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


@respx.mock
async def test_brave_ranks_hit(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "fake")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=Response(
            200,
            json={
                "web": {
                    "results": [
                        {"url": "https://other.com/a"},
                        {"url": "https://example.com/b"},  # rank 2
                    ]
                }
            },
        )
    )
    r = await probe_brave(["q"], "example.com")
    assert r.evidence["ranks"] == [2]
    assert r.status in (CheckStatus.PASS, CheckStatus.WARN)


@respx.mock
async def test_brave_no_rank_fail(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "fake")
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=Response(200, json={"web": {"results": [{"url": "https://other.com"}]}})
    )
    r = await probe_brave(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.FAIL
    assert r.score == 0.0


async def test_duck_ai_skipped_by_env(monkeypatch):
    monkeypatch.setenv("DISABLE_DUCK_AI", "1")
    r = await probe_duck_ai(["q"], "example.com")
    assert r.status == CheckStatus.SKIP


@respx.mock
async def test_duck_ai_handles_no_vqd(monkeypatch):
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get("https://duckduckgo.com/duckchat/v1/status").mock(
        return_value=Response(200, headers={})  # no x-vqd-4
    )
    r = await probe_duck_ai(["q"], "example.com")
    assert r.status == CheckStatus.SKIP
