"""Tests for the optional LLM polish layer over template prompts.

The polish pass is allowed to fail in any number of ways (no key, timeout,
HTTP error, malformed JSON, validation failure). Every failure mode must
return the original template bundle unchanged so scans never block on
external infrastructure.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.models import (
    DetectedCategory,
    PromptDeepLinks,
    TestPrompt,
    TestPromptsBundle,
)
from app.test_prompts_llm import (
    MAX_PROMPT_LEN,
    MIN_PROMPT_LEN,
    _validate,
    polish_prompts,
)


def _draft_prompt(angle: str, label: str, text: str) -> TestPrompt:
    return TestPrompt(
        angle=angle,  # type: ignore[arg-type]
        label=label,
        text=text,
        rationale="rationale",
        deep_links=PromptDeepLinks(
            chatgpt="https://chatgpt.com/?q=",
            perplexity="https://www.perplexity.ai/?q=",
            claude="https://claude.ai/new?q=",
            google_ai="https://www.google.com/search?q=",
        ),
    )


def _bundle(brand: str = "Stripe") -> TestPromptsBundle:
    return TestPromptsBundle(
        detected_category=DetectedCategory(
            slug="fintech-payments",
            label="payments / fintech",
            persona="developers integrating payments",
            confidence="high",
            signals=["test-fixture"],
        ),
        brand=brand,
        prompts=[
            _draft_prompt(
                "category",
                "Category recommendation",
                "What's the best payment processor for developers in 2026?",
            ),
            _draft_prompt(
                "use_case",
                "Use-case discovery",
                "How do I accept credit cards on my website?",
            ),
            _draft_prompt(
                "comparison",
                "Comparison",
                "Stripe vs alternatives — which is best for developers?",
            ),
            _draft_prompt(
                "long_tail",
                "Long-tail / persona",
                "Recommend a payment processor for a SaaS founder focused on subscription billing.",
            ),
        ],
        all_categories=[],
    )


def _mock_groq_transport(
    polished_texts: list[str] | None = None,
    *,
    raw_content: str | None = None,
    status_code: int = 200,
    raise_exc: Exception | None = None,
) -> httpx.MockTransport:
    """Build an httpx MockTransport returning a Groq-shaped chat response."""

    def handler(request: httpx.Request) -> httpx.Response:
        if raise_exc is not None:
            raise raise_exc
        if raw_content is not None:
            content = raw_content
        else:
            content = json.dumps({"prompts": polished_texts or []})
        body = {
            "choices": [
                {"message": {"content": content, "role": "assistant"}}
            ]
        }
        return httpx.Response(status_code, json=body)

    return httpx.MockTransport(handler)


# ---- Happy path ------------------------------------------------------------


async def test_polish_prompts_replaces_prompt_text_when_groq_returns_valid_json():
    polished = [
        "Which payment processor handles subscription billing best in 2026?",
        "How can I add Apple Pay and credit cards to my SaaS checkout flow?",
        "Stripe vs Adyen vs Braintree — which fits a developer-led startup?",
        "Which payments API is friendliest to a Y Combinator SaaS founder doing recurring billing?",
    ]
    transport = _mock_groq_transport(polished)
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert [p.text for p in out.prompts] == polished
    # Angles, labels, rationales preserved.
    assert [p.angle for p in out.prompts] == [p.angle for p in bundle.prompts]
    assert [p.label for p in out.prompts] == [p.label for p in bundle.prompts]
    # Deep-link URL gets re-encoded with the new text.
    assert "subscription+billing" in out.prompts[0].deep_links.chatgpt.replace(
        "%20", "+"
    ) or "subscription%20billing" in out.prompts[0].deep_links.chatgpt


# ---- Fail-open paths -------------------------------------------------------


async def test_polish_prompts_fails_open_when_api_key_missing(monkeypatch):
    """No GROQ_API_KEY in env → return bundle unchanged, no HTTP call."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    bundle = _bundle()

    def boom(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be called when key is missing")

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        out = await polish_prompts(bundle, api_key=None, client=client)
    assert out is bundle or out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_on_timeout():
    transport = _mock_groq_transport(raise_exc=httpx.ReadTimeout("slow"))
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_on_429():
    transport = _mock_groq_transport(
        raise_exc=httpx.HTTPStatusError(
            "429",
            request=httpx.Request("POST", "https://api.groq.com"),
            response=httpx.Response(429),
        )
    )
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_on_500_status():
    transport = _mock_groq_transport(status_code=500, raw_content="oops")
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_on_unparseable_json():
    transport = _mock_groq_transport(raw_content="this is not json")
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_when_groq_returns_wrong_count():
    transport = _mock_groq_transport(["only one prompt of decent length here please"])
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_when_brand_dropped_from_comparison():
    """Comparison prompt must keep the brand name. If the LLM drops it,
    we don't trust the rewrite and return the template version."""
    polished = [
        "Which payment processor is best for SaaS in 2026?",
        "How do I accept credit cards online as a developer?",
        # Brand "Stripe" deliberately removed here — should trigger fallback.
        "Compared to Adyen or Braintree — which fits a startup best?",
        "Recommend a payments API for subscription billing at a Y Combinator startup.",
    ]
    transport = _mock_groq_transport(polished)
    bundle = _bundle(brand="Stripe")
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_when_prompts_too_short():
    polished = ["short", "tiny", "Stripe wins", "x" * 5]  # all below MIN_PROMPT_LEN
    transport = _mock_groq_transport(polished)
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


async def test_polish_prompts_fails_open_when_duplicates_returned():
    same = "Which payments tool is best for developers in 2026?"
    polished = [same, same, "Stripe vs alternatives in 2026?", same]
    transport = _mock_groq_transport(polished)
    bundle = _bundle()
    async with httpx.AsyncClient(transport=transport) as client:
        out = await polish_prompts(bundle, api_key="test-key", client=client)
    assert out.model_dump() == bundle.model_dump()


# ---- Validation unit ------------------------------------------------------


def test_validate_accepts_four_distinct_brand_preserving_prompts():
    texts = [
        "Which payment processor handles subscription billing best in 2026?",
        "How can I add Apple Pay and cards to my SaaS checkout?",
        "Stripe vs Adyen vs Braintree — which is best for a developer-led startup?",
        "Recommend a payments API for a YC SaaS founder doing recurring billing.",
    ]
    assert _validate(texts, brand="Stripe") is True


def test_validate_rejects_when_comparison_loses_brand():
    texts = [
        "x" * (MIN_PROMPT_LEN + 5),
        "y" * (MIN_PROMPT_LEN + 5),
        "Compared to others which is best?",  # brand absent
        "z" * (MIN_PROMPT_LEN + 5),
    ]
    assert _validate(texts, brand="Stripe") is False


def test_validate_rejects_when_prompt_exceeds_max_length():
    long_text = "Stripe " + "x" * (MAX_PROMPT_LEN + 10)
    texts = [
        "x" * (MIN_PROMPT_LEN + 5),
        "y" * (MIN_PROMPT_LEN + 5),
        long_text,
        "z" * (MIN_PROMPT_LEN + 5),
    ]
    assert _validate(texts, brand="Stripe") is False


def test_validate_skips_brand_check_when_brand_is_placeholder():
    """When extract_brand falls back to 'this site', we don't enforce the
    presence-in-comparison check (there's no brand to enforce)."""
    texts = [
        "x" * (MIN_PROMPT_LEN + 5),
        "y" * (MIN_PROMPT_LEN + 5),
        "How does this site compare to its competitors?",
        "z" * (MIN_PROMPT_LEN + 5),
    ]
    assert _validate(texts, brand="this site") is True


# ---- maybe_polish wrapper -------------------------------------------------


async def test_maybe_polish_prompts_returns_bundle_when_key_missing(monkeypatch):
    from app.test_prompts_llm import maybe_polish_prompts

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    bundle = _bundle()
    out = await maybe_polish_prompts(bundle, home_html="<html></html>")
    assert out is bundle


@pytest.mark.parametrize(
    "raw,expected_substring",
    [
        ('"Wrapped in quotes"', "Wrapped in quotes"),
        ("1. Numbered prefix here that is long enough", "Numbered prefix"),
        ("\u201cSmart quotes\u201d", "Smart quotes"),
    ],
)
def test_clean_prompt_text_strips_common_llm_artifacts(raw, expected_substring):
    from app.test_prompts_llm import _clean_prompt_text

    out = _clean_prompt_text(raw)
    assert expected_substring in out
    assert not out.startswith(('"', "'", "1.", "\u201c"))
