"""Groq probe — mocked HTTP tests."""
from __future__ import annotations

import respx
from httpx import Response

from app.models import CheckStatus
from app.probes.groq import probe_groq


async def test_groq_skip_without_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = await probe_groq(["q"], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "GROQ_API_KEY" in r.detail


@respx.mock
async def test_groq_counts_citations(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "See https://example.com/docs for details.",
                            "executed_tools": [
                                {
                                    "output": [
                                        {"url": "https://example.com/a"},
                                        {"url": "https://other.com/b"},
                                    ]
                                }
                            ],
                        }
                    }
                ]
            },
        )
    )
    r = await probe_groq(["what is example"], "example.com")
    assert r.status == CheckStatus.PASS
    assert r.score == 1.0
    assert r.evidence["hits"] == 1


@respx.mock
async def test_groq_no_hit(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "No mention of the target.",
                            "executed_tools": [
                                {"output": [{"url": "https://other.com/b"}]}
                            ],
                        }
                    }
                ]
            },
        )
    )
    r = await probe_groq(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.FAIL
    assert r.score == 0.0
