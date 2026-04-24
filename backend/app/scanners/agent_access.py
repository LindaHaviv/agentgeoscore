"""Agent Access scanner — does robots.txt let AI crawlers in?

AI crawlers we check for (user-agent tokens as documented by each vendor):
- GPTBot (OpenAI)
- ChatGPT-User (OpenAI - user actions)
- OAI-SearchBot (OpenAI search)
- ClaudeBot (Anthropic)
- Claude-Web (Anthropic)
- PerplexityBot (Perplexity)
- Perplexity-User (Perplexity - user actions)
- Google-Extended (Google Gemini training)
- GoogleOther (Google general)
- Bytespider (ByteDance / Doubao)
- Applebot-Extended (Apple Intelligence)
- Amazonbot (Amazon Rufus / Alexa)
- cohere-ai (Cohere)
- Meta-ExternalAgent (Meta)
- DuckAssistBot (DuckDuckGo)
- YouBot (You.com)
- FacebookBot (Meta)
"""
from __future__ import annotations

from ..fetcher import Fetcher
from ..models import CheckResult, CheckStatus
from ..targets import WebsiteTarget

AI_BOTS = [
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "ClaudeBot",
    "Claude-Web",
    "PerplexityBot",
    "Perplexity-User",
    "Google-Extended",
    "GoogleOther",
    "Bytespider",
    "Applebot-Extended",
    "Amazonbot",
    "cohere-ai",
    "Meta-ExternalAgent",
    "DuckAssistBot",
    "YouBot",
    "FacebookBot",
]

# Core bots whose blocking is most costly. Used for "critical" scoring tier.
CORE_AI_BOTS = {
    "GPTBot",
    "ClaudeBot",
    "PerplexityBot",
    "Google-Extended",
    "Applebot-Extended",
    "OAI-SearchBot",
    "ChatGPT-User",
}


def parse_robots(text: str) -> dict[str, list[str]]:
    """Minimal robots.txt parser returning {user_agent_lower: [rule_entries]}.

    Semantics:
    - A *group* is one or more contiguous `User-agent` lines followed by rule lines.
    - A blank line OR a new `User-agent` line after rules starts a new group.
    - Rule lines (`Allow`, `Disallow`) apply to *all* User-agents in the current group.
    - Comments (`#`) and unknown directives are ignored.
    """
    groups: dict[str, list[str]] = {}
    current_agents: list[str] = []
    in_rules = False  # True once we've seen a rule line for the current group
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            # Blank line ends the current group
            current_agents = []
            in_rules = False
            continue
        if ":" not in line:
            continue
        field, _, value = line.partition(":")
        field = field.strip().lower()
        value = value.strip()
        if field == "user-agent":
            if in_rules:
                # Rule lines already seen → this UA starts a brand-new group
                current_agents = []
                in_rules = False
            current_agents.append(value.lower())
            groups.setdefault(value.lower(), [])
        elif field in ("disallow", "allow"):
            in_rules = True
            entry = f"{field}:{value}"
            for agent in current_agents:
                groups.setdefault(agent, []).append(entry)
    return groups


def is_agent_blocked(groups: dict[str, list[str]], agent: str) -> bool:
    """True if robots.txt fully disallows `agent` from the site root.

    We apply the specific agent group if present; otherwise fall back to `*`.
    A bot is "blocked" if there is a `Disallow: /` line active for it and no
    overriding `Allow: /` later in the same group.
    """
    agent_key = agent.lower()
    # Note: `[]` is falsy in Python — don't use `or` here, otherwise a bot
    # with its own empty group would incorrectly fall through to the `*`
    # wildcard rules. Per the robots.txt spec, an empty specific group means
    # "no restrictions for this bot".
    specific = groups.get(agent_key)
    rules = specific if specific is not None else (groups.get("*") or [])
    blocked = False
    for entry in rules:
        field, _, value = entry.partition(":")
        value = value.strip()
        if field == "disallow":
            if value == "/":
                blocked = True
            elif value == "":
                # Empty Disallow means allow all
                blocked = False
        elif field == "allow":
            if value == "/" or value == "":
                blocked = False
    return blocked


async def check_agent_access(target: WebsiteTarget, fetcher: Fetcher) -> list[CheckResult]:
    """Fetch /robots.txt and check each AI bot's access."""
    results: list[CheckResult] = []
    robots_url = target.absolute("/robots.txt")
    fetch = await fetcher.get(robots_url)

    if not fetch.ok or fetch.status == 404:
        is_404 = fetch.status == 404
        # No robots.txt = permissive by default. That's actually good for agents.
        # A non-404 failure (5xx, timeout, network error) is a real problem —
        # AI crawlers will also fail to fetch it, and we can't know the policy.
        results.append(
            CheckResult(
                id="robots_exists",
                label="robots.txt reachable",
                status=CheckStatus.WARN,
                score=0.8 if is_404 else 0.4,
                weight=0.5,
                detail=(
                    "No robots.txt found (that's fine — means all bots allowed by default). "
                    "Consider adding one with explicit AI-bot allows so your intent is clear."
                    if is_404
                    else f"robots.txt fetch failed: {fetch.error or fetch.status}"
                ),
            )
        )
        # 404 = no rules, permissive by default. Non-404 failure = unknown.
        results.append(
            CheckResult(
                id="ai_bots_allowed",
                label="Major AI bots allowed",
                status=CheckStatus.PASS if is_404 else CheckStatus.SKIP,
                score=1.0 if is_404 else 0.0,
                weight=2.0,
                detail=(
                    "No robots.txt → all AI crawlers allowed."
                    if is_404
                    else "Couldn't fetch robots.txt — AI-bot access undetermined."
                ),
                evidence={"blocked": [], "allowed": AI_BOTS} if is_404 else None,
            )
        )
        return results

    results.append(
        CheckResult(
            id="robots_exists",
            label="robots.txt reachable",
            status=CheckStatus.PASS,
            score=1.0,
            weight=0.5,
            detail=f"robots.txt served at {robots_url}",
        )
    )

    groups = parse_robots(fetch.text)
    blocked_bots = [b for b in AI_BOTS if is_agent_blocked(groups, b)]
    core_blocked = [b for b in blocked_bots if b in CORE_AI_BOTS]
    allowed_bots = [b for b in AI_BOTS if b not in blocked_bots]

    # Core bots check — heaviest weight
    if core_blocked:
        core_status = CheckStatus.FAIL
        core_score = max(0.0, 1 - len(core_blocked) / len(CORE_AI_BOTS))
        core_detail = (
            f"Blocking core AI agents: {', '.join(core_blocked)}. "
            f"These power ChatGPT, Claude, Perplexity, Gemini and Apple Intelligence — "
            f"blocking them removes your site from those assistants' citations."
        )
    else:
        core_status = CheckStatus.PASS
        core_score = 1.0
        core_detail = "All core AI crawlers (GPTBot, ClaudeBot, PerplexityBot, Google-Extended, Applebot-Extended) are allowed."
    results.append(
        CheckResult(
            id="core_ai_bots",
            label="Core AI crawlers allowed",
            status=core_status,
            score=core_score,
            weight=3.0,
            detail=core_detail,
            evidence={"blocked": core_blocked, "core_set": sorted(CORE_AI_BOTS)},
        )
    )

    # Broader AI-bot coverage
    broad_blocked = [b for b in blocked_bots if b not in CORE_AI_BOTS]
    if broad_blocked:
        broad_status = CheckStatus.WARN if len(broad_blocked) <= 3 else CheckStatus.FAIL
        broad_score = max(0.0, 1 - len(broad_blocked) / (len(AI_BOTS) - len(CORE_AI_BOTS)))
        broad_detail = f"Also blocking: {', '.join(broad_blocked)}."
    else:
        broad_status = CheckStatus.PASS
        broad_score = 1.0
        broad_detail = "No additional AI bots are blocked beyond the core set."
    results.append(
        CheckResult(
            id="broad_ai_bots",
            label="Long-tail AI crawlers allowed",
            status=broad_status,
            score=broad_score,
            weight=1.0,
            detail=broad_detail,
            evidence={"blocked": broad_blocked, "allowed": allowed_bots},
        )
    )

    # Explicit AI-bot rules (vs. just relying on wildcard) — bonus for intent
    explicit_agents = [a for a in groups.keys() if a != "*" and a != ""]
    has_explicit_ai_rule = any(b.lower() in groups for b in AI_BOTS)
    results.append(
        CheckResult(
            id="explicit_ai_rules",
            label="Explicit AI-bot rules in robots.txt",
            status=CheckStatus.PASS if has_explicit_ai_rule else CheckStatus.WARN,
            score=1.0 if has_explicit_ai_rule else 0.5,
            weight=0.5,
            detail=(
                f"Found explicit rules for: {', '.join(sorted(set(explicit_agents)))}."
                if has_explicit_ai_rule
                else "No named AI bots in robots.txt — you're relying on wildcard defaults. "
                "Add explicit `User-agent: GPTBot` etc. entries to make intent clear."
            ),
        )
    )

    return results
