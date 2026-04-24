"""Tests for robots.txt parsing + AI-bot access detection."""
from __future__ import annotations

from app.scanners.agent_access import is_agent_blocked, parse_robots


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
