"""Duck.ai probe — full coverage of the SSE chat flow and _parse_sse."""
from __future__ import annotations

import httpx
import respx
from httpx import Response

from app.models import CheckStatus
from app.probes.duck_ai import (
    DUCK_CHAT_URL,
    DUCK_STATUS_URL,
    _parse_sse,
    probe_duck_ai,
)


def _sse(*messages: str) -> str:
    """Format a list of message strings as an SSE-encoded body."""
    out: list[str] = []
    for m in messages:
        out.append(f'data: {{"message": "{m}"}}')
    out.append("data: [DONE]")
    return "\n".join(out) + "\n"


@respx.mock
async def test_duck_ai_status_endpoint_raises(monkeypatch):
    """The status fetch raising an HTTPError → SKIP with the error message."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(side_effect=httpx.ConnectError("boom"))
    r = await probe_duck_ai(["q"], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "Duck.ai unreachable" in r.detail


@respx.mock
async def test_duck_ai_all_queries_cite_target_pass(monkeypatch):
    """Every query mentions the target → PASS with score 1.0."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    respx.post(DUCK_CHAT_URL).mock(
        return_value=Response(
            200,
            headers={"content-type": "text/event-stream"},
            text=_sse("Try ", "https://example.com/docs", " for more."),
        )
    )
    r = await probe_duck_ai(["query 1", "query 2"], "example.com")
    assert r.status == CheckStatus.PASS
    assert r.score == 1.0
    assert r.evidence["hits"] == 2
    assert r.evidence["queries"] == 2


@respx.mock
async def test_duck_ai_no_citations_fail(monkeypatch):
    """Queries return URLs but none match the target → FAIL."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    respx.post(DUCK_CHAT_URL).mock(
        return_value=Response(200, text=_sse("See https://other.com/page only."))
    )
    r = await probe_duck_ai(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.FAIL
    assert r.score == 0.0
    # The non-matching URL is still captured in evidence for debugging.
    assert any("other.com" in u for u in r.evidence["cited_sample"])


@respx.mock
async def test_duck_ai_partial_citation_warn(monkeypatch):
    """One of two queries cites the target → WARN with score 0.5."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    responses = [
        Response(200, text=_sse("https://example.com/a")),
        Response(200, text=_sse("https://other.com/b")),
    ]
    respx.post(DUCK_CHAT_URL).mock(side_effect=responses)
    r = await probe_duck_ai(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.WARN
    assert r.score == 0.5
    assert r.evidence["hits"] == 1


@respx.mock
async def test_duck_ai_chat_non_200_adds_error(monkeypatch):
    """Chat endpoint 429 is recorded as an error and the query is skipped."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    respx.post(DUCK_CHAT_URL).mock(return_value=Response(429, text=""))
    r = await probe_duck_ai(["q1"], "example.com")
    # All queries errored → probe SKIPs as "unavailable".
    assert r.status == CheckStatus.SKIP
    assert "Probe unavailable" in r.detail or "HTTP 429" in r.detail


@respx.mock
async def test_duck_ai_chat_raises_httperror(monkeypatch):
    """Chat endpoint network error is recorded as an error."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    respx.post(DUCK_CHAT_URL).mock(side_effect=httpx.ReadTimeout("timed out"))
    r = await probe_duck_ai(["q1"], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "Probe unavailable" in r.detail


@respx.mock
async def test_duck_ai_refreshes_vqd_token_between_queries(monkeypatch):
    """When chat responds with a new x-vqd-4 header, the probe rotates the token."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    # Two-query batch: first response rotates the token to tok-2.
    responses = [
        Response(
            200,
            headers={"x-vqd-4": "tok-2"},
            text=_sse("https://example.com/x"),
        ),
        Response(200, text=_sse("https://example.com/y")),
    ]
    respx.post(DUCK_CHAT_URL).mock(side_effect=responses)
    r = await probe_duck_ai(["q1", "q2"], "example.com")
    assert r.status == CheckStatus.PASS
    # Second call used the rotated token.
    calls = respx.routes[1].calls
    assert calls[1].request.headers.get("x-vqd-4") == "tok-2"


@respx.mock
async def test_duck_ai_empty_query_list(monkeypatch):
    """Zero queries → SKIP with "no queries" detail."""
    monkeypatch.delenv("DISABLE_DUCK_AI", raising=False)
    respx.get(DUCK_STATUS_URL).mock(
        return_value=Response(200, headers={"x-vqd-4": "tok-1"})
    )
    r = await probe_duck_ai([], "example.com")
    assert r.status == CheckStatus.SKIP
    assert "no queries" in r.detail


def test_parse_sse_concatenates_message_payloads():
    body = (
        'data: {"message": "Hello, "}\n'
        'data: {"message": "world"}\n'
        "data: [DONE]\n"
    )
    assert _parse_sse(body) == "Hello, world"


def test_parse_sse_skips_done_sentinel_and_empty_payloads():
    body = (
        'data: {"message": "a"}\n'
        "data: \n"
        "data: [DONE]\n"
        'data: {"message": "b"}\n'
    )
    assert _parse_sse(body) == "ab"


def test_parse_sse_ignores_invalid_json():
    body = (
        'data: {"message": "real"}\n'
        "data: <not json>\n"
        'data: {"message": "still real"}\n'
    )
    assert _parse_sse(body) == "realstill real"


def test_parse_sse_ignores_non_data_lines():
    body = (
        "event: ping\n"
        'data: {"message": "kept"}\n'
        ": comment line\n"
        'data: {"message": "also kept"}\n'
    )
    assert _parse_sse(body) == "keptalso kept"


def test_parse_sse_returns_empty_when_no_data():
    assert _parse_sse("") == ""
    assert _parse_sse("event: ping\n") == ""


def test_parse_sse_handles_message_missing_field():
    """An SSE row with valid JSON but no ``message`` field contributes nothing."""
    body = (
        'data: {"event": "ack"}\n'
        'data: {"message": "real"}\n'
    )
    assert _parse_sse(body) == "real"
