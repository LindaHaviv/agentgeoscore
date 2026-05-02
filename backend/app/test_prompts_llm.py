"""Optional LLM rewrite pass for AI-search test prompts.

The base templates in ``test_prompts.generate_prompts`` are deterministic and
free, but every site in a vertical reads identically — *"Recommend a travel
option for a family planning a vacation in a new city focused on …"* — and
when the page-topic interpolation pulls in something like a marketing campaign
name the result can be grammatically awkward (*"…focused on the a'ja wilson
show"*).

This module rewrites the four template prompts through Groq's free-tier
``llama-3.3-70b-versatile`` so they sound natural and site-specific while
keeping the four prompt angles, the brand, and the category descriptor
intact. The call is wrapped in a tight timeout and **fails open** — if the
key is missing, the request times out, the JSON doesn't parse, or the
returned prompts fail validation, we silently return the original template
bundle. Scans never block on this.

Cost / latency budget:
- Groq llama-3.3-70b is well under the per-scan latency budget (typical
  ~0.4-0.8s end-to-end for 4 short prompts).
- Free tier rate limits are 30 req/min, more than enough for current scan
  volume.
- Worst-case extra latency on a scan: ``TIMEOUT_SEC`` (currently 2.5s).
"""
from __future__ import annotations

import asyncio
import json
import os

import httpx

from .models import TestPrompt, TestPromptsBundle

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

# Total wall-clock budget for the polish pass. Picked so a Groq slowdown can
# never make a scan visibly slower; if it ever does, we just ship the
# template version.
TIMEOUT_SEC = 2.5

# Sanity bounds on a single polished prompt. Anything outside these is
# treated as a parse failure and we fall back to the template.
MIN_PROMPT_LEN = 15
MAX_PROMPT_LEN = 240


async def maybe_polish_prompts(
    bundle: TestPromptsBundle,
    home_html: str,
    *,
    timeout: float = TIMEOUT_SEC,
    client: httpx.AsyncClient | None = None,
    api_key: str | None = None,
) -> TestPromptsBundle:
    """Polish the bundle's prompts via Groq if a key is configured.

    Re-extracts page topics from ``home_html`` so we can hand the LLM the
    same site-specific signal the template layer used. Cheap (a single
    BeautifulSoup parse).
    """
    api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
    if not api_key:
        return bundle

    # Local import dodges the circular dependency between this module and
    # ``test_prompts`` (which imports the bundle / prompt models).
    from .test_prompts import extract_page_topics

    topics = extract_page_topics(home_html, exclude_brand=bundle.brand)
    return await polish_prompts(
        bundle,
        topics=topics,
        timeout=timeout,
        client=client,
        api_key=api_key,
    )


async def polish_prompts(
    bundle: TestPromptsBundle,
    *,
    topics: list[str] | None = None,
    api_key: str | None = None,
    timeout: float = TIMEOUT_SEC,
    client: httpx.AsyncClient | None = None,
) -> TestPromptsBundle:
    """Rewrite ``bundle.prompts`` through Groq, falling back to the input.

    The function never raises; any failure path returns ``bundle`` unchanged
    so the scan can always complete with at least the template prompts.
    """
    api_key = api_key if api_key is not None else os.getenv("GROQ_API_KEY")
    if not api_key:
        return bundle
    if len(bundle.prompts) != 4:
        return bundle

    drafts = [p.text for p in bundle.prompts]

    try:
        polished = await asyncio.wait_for(
            _call_groq(
                brand=bundle.brand,
                category_label=bundle.detected_category.label,
                topics=topics or [],
                drafts=drafts,
                api_key=api_key,
                timeout=timeout,
                client=client,
            ),
            timeout=timeout,
        )
    except (TimeoutError, httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        return bundle
    except Exception:
        # Belt-and-suspenders. We never want to fail a scan because the
        # *optional* polish pass blew up.
        return bundle

    if not _validate(polished, brand=bundle.brand):
        return bundle

    # Local import dodges the circular dependency.
    from .test_prompts import _deep_links

    new_prompts = [
        TestPrompt(
            angle=original.angle,
            label=original.label,
            text=new_text,
            rationale=original.rationale,
            deep_links=_deep_links(new_text),
        )
        for original, new_text in zip(bundle.prompts, polished, strict=True)
    ]
    return bundle.model_copy(update={"prompts": new_prompts})


async def _call_groq(
    *,
    brand: str,
    category_label: str,
    topics: list[str],
    drafts: list[str],
    api_key: str,
    timeout: float,
    client: httpx.AsyncClient | None,
) -> list[str]:
    """Send the prompts to Groq and return four polished strings."""
    if len(drafts) != 4:
        raise ValueError("expected exactly 4 draft prompts")

    topics_line = ""
    if topics:
        topics_line = f"\nReal homepage topics (from H1/H2/H3): {', '.join(topics[:5])}"

    user_prompt = (
        f"Site / brand: {brand}\n"
        f"Category: {category_label}{topics_line}\n\n"
        "Draft AI-search test prompts (in this order — category-recommendation, "
        "use-case discovery, comparison, long-tail / persona):\n"
        f"  1. {drafts[0]}\n"
        f"  2. {drafts[1]}\n"
        f"  3. {drafts[2]}\n"
        f"  4. {drafts[3]}\n\n"
        "Rewrite each so it sounds like something a real person would actually "
        "type into ChatGPT, Perplexity, Claude, or Google's AI Mode when they're "
        "shopping or researching this category. Keep the four prompts in the "
        "same order and angle — do not merge, drop, or add prompts.\n\n"
        f'Hard constraints:\n'
        f'  - Prompt #3 (comparison) must mention "{brand}" by name.\n'
        f'  - Prompt #1 (category) must NOT mention "{brand}" by name '
        '(it should be a neutral category query).\n'
        '  - No preambles ("Here are…"), no numbering inside the prompt text, '
        'no quote marks around prompts.\n'
        '  - Each prompt 15-240 characters.\n\n'
        'Reply with JSON only: {"prompts": ["...", "...", "...", "..."]}'
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You polish AI-search test prompts so they sound natural "
                    "and site-specific without changing their structure. "
                    "Reply with JSON only."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    own_client = client is None
    if own_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=2.0))
    try:
        resp = await client.post(GROQ_URL, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if own_client and client is not None:
            await client.aclose()

    content = data["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    prompts = parsed.get("prompts")
    if not isinstance(prompts, list) or len(prompts) != 4:
        raise ValueError("Groq returned non-conforming prompts payload")
    return [_clean_prompt_text(str(p)) for p in prompts]


def _clean_prompt_text(s: str) -> str:
    """Strip wrapping quotes / leading numbering the LLM sometimes adds."""
    s = s.strip()
    # Remove a single layer of wrapping quotes.
    for pair in (('"', '"'), ("'", "'"), ("\u201c", "\u201d"), ("\u2018", "\u2019")):
        if s.startswith(pair[0]) and s.endswith(pair[1]) and len(s) >= 2:
            s = s[1:-1].strip()
            break
    # Drop any "1. ", "2) " prefix the LLM may slip in despite the instruction.
    if len(s) >= 3 and s[0].isdigit() and s[1] in {".", ")"} and s[2] == " ":
        s = s[3:].strip()
    return s


def _validate(texts: list[str], *, brand: str) -> bool:
    """Reject obviously broken polish output."""
    if len(texts) != 4:
        return False
    seen_lower: set[str] = set()
    for t in texts:
        if not isinstance(t, str):
            return False
        clean = t.strip()
        if not (MIN_PROMPT_LEN <= len(clean) <= MAX_PROMPT_LEN):
            return False
        key = clean.lower()
        if key in seen_lower:
            return False
        seen_lower.add(key)
    # Comparison (index 2) must still mention the brand. We deliberately
    # don't enforce that brand is *absent* from the category prompt (#0)
    # because some brands are also category nouns ("Apple" → fruit) and
    # rewriting could legitimately keep the brand if it reads naturally.
    if brand and brand.strip().lower() not in {"this site", ""}:
        if brand.lower() not in texts[2].lower():
            return False
    return True
