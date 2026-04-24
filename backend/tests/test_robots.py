"""Tests for robots.txt parsing + AI-bot access detection."""
from __future__ import annotations

import pytest
import respx
from httpx import Response

from app.fetcher import Fetcher
from app.models import CheckStatus
from app.scanners.agent_access import check_agent_access, is_agent_blocked, parse_robots
from app.targets import WebsiteTarget


def test_blocks_specific_agent():
    robots = """
User-agent: GPTBot
Disallow: /

User-agent: *
Allow: /
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is True
    assert is_agent_blocked(groups, "ClaudeBot") is False  # falls through to *


def test_blocks_all_via_wildcard():
    robots = """
User-agent: *
Disallow: /
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is True
    assert is_agent_blocked(groups, "ClaudeBot") is True


def test_allow_overrides_disallow():
    robots = """
User-agent: GPTBot
Disallow: /
Allow: /
"""
    groups = parse_robots(robots)
    # Last rule wins in our simple parser
    assert is_agent_blocked(groups, "GPTBot") is False


def test_empty_disallow_means_allow():
    robots = """
User-agent: GPTBot
Disallow:
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is False


def test_comments_and_blank_lines_ignored():
    robots = """
# AgentGEOScore test fixture
User-agent: GPTBot   # block OpenAI
Disallow: /

# another block
User-agent: *
Disallow:
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is True
    assert is_agent_blocked(groups, "ClaudeBot") is False


def test_grouped_user_agents_share_rules():
    robots = """
User-agent: GPTBot
User-agent: ClaudeBot
Disallow: /

User-agent: *
Disallow:
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is True
    assert is_agent_blocked(groups, "ClaudeBot") is True
    assert is_agent_blocked(groups, "PerplexityBot") is False


def test_case_insensitive_agent_matching():
    robots = """
User-agent: gptbot
Disallow: /
"""
    groups = parse_robots(robots)
    assert is_agent_blocked(groups, "GPTBot") is True


def test_partial_disallow_is_not_full_block():
    robots = """
User-agent: GPTBot
Disallow: /admin
"""
    groups = parse_robots(robots)
    # Our is_agent_blocked checks for full-root `Disallow: /` only
    assert is_agent_blocked(groups, "GPTBot") is False


def test_no_robots_file_means_unblocked():
    groups = parse_robots("")
    assert is_agent_blocked(groups, "GPTBot") is False


# ---------------------------------------------------------------------------
# check_agent_access end-to-end: 404 vs non-404 fetch failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_robots_404_is_permissive():
    """404 = no robots.txt = permissive by default. WARN on existence check,
    PASS on ai_bots_allowed (since nothing is blocked)."""
    respx.get("https://example.com/robots.txt").mock(return_value=Response(404))
    async with Fetcher() as fetcher:
        results = await check_agent_access(WebsiteTarget.from_url("https://example.com"), fetcher)

    by_id = {r.id: r for r in results}
    assert by_id["robots_exists"].status == CheckStatus.WARN
    assert by_id["robots_exists"].score == 0.8
    assert by_id["ai_bots_allowed"].status == CheckStatus.PASS
    assert by_id["ai_bots_allowed"].score == 1.0


@pytest.mark.asyncio
@respx.mock
async def test_robots_500_does_not_falsely_pass():
    """Regression: a 500 / connection error on robots.txt used to silently
    mark `robots_exists` as PASS with score=1.0, inflating the Agent Access
    category. Now it must WARN with a lower score, and `ai_bots_allowed`
    must SKIP (we can't determine AI-bot access if robots.txt won't load)."""
    respx.get("https://example.com/robots.txt").mock(return_value=Response(500))
    async with Fetcher() as fetcher:
        results = await check_agent_access(WebsiteTarget.from_url("https://example.com"), fetcher)

    by_id = {r.id: r for r in results}
    assert by_id["robots_exists"].status == CheckStatus.WARN
    assert by_id["robots_exists"].score == 0.4
    # Previously this was PASS with score 1.0 — the bug Devin Review caught.
    assert by_id["robots_exists"].status != CheckStatus.PASS

    assert by_id["ai_bots_allowed"].status == CheckStatus.SKIP
    assert by_id["ai_bots_allowed"].score == 0.0
