"""Scoring engine — combines check results into category and overall scores."""
from __future__ import annotations

from .fixes import build_fix_for_check
from .models import (
    CategoryId,
    CategoryResult,
    CheckResult,
    CheckStatus,
    Fix,
)

# Category weights — must sum to 1.0
CATEGORY_WEIGHTS: dict[CategoryId, float] = {
    CategoryId.AGENT_ACCESS: 0.25,
    CategoryId.DISCOVERABILITY: 0.20,
    CategoryId.STRUCTURED_DATA: 0.20,
    CategoryId.CONTENT_CLARITY: 0.15,
    CategoryId.CITATION_PROBE: 0.20,
}

CATEGORY_LABELS: dict[CategoryId, str] = {
    CategoryId.AGENT_ACCESS: "Agent Access",
    CategoryId.DISCOVERABILITY: "Discoverability",
    CategoryId.STRUCTURED_DATA: "Structured Data",
    CategoryId.CONTENT_CLARITY: "Content Clarity",
    CategoryId.CITATION_PROBE: "Citation Probe",
}


def score_category(checks: list[CheckResult]) -> int:
    """Weighted average of per-check scores, returned as int 0-100."""
    active = [c for c in checks if c.status != CheckStatus.SKIP and c.weight > 0]
    if not active:
        return 0
    total_weight = sum(c.weight for c in active)
    if total_weight <= 0:
        return 0
    weighted = sum(c.score * c.weight for c in active)
    return round(100 * weighted / total_weight)


def build_category(
    category_id: CategoryId, checks: list[CheckResult], summary: str = ""
) -> CategoryResult:
    return CategoryResult(
        id=category_id,
        label=CATEGORY_LABELS[category_id],
        weight=CATEGORY_WEIGHTS[category_id],
        score=score_category(checks),
        checks=checks,
        summary=summary,
    )


def overall_score(categories: list[CategoryResult]) -> int:
    """Weighted composite 0-100.

    A category is excluded from the overall score if every one of its checks is
    SKIP (e.g. the Citation Probe category when no LLM API keys are configured).
    The remaining category weights are re-normalized so the overall reflects
    only the signals we actually measured.
    """
    if not categories:
        return 0
    active = [
        c for c in categories
        if c.checks and any(ch.status != CheckStatus.SKIP for ch in c.checks)
    ]
    if not active:
        return 0
    total_weight = sum(c.weight for c in active)
    if total_weight <= 0:
        return 0
    weighted = sum(c.score * c.weight for c in active)
    return round(weighted / total_weight)


def grade_for(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


_SEVERITY_ORDER = {"critical": 0, "important": 1, "minor": 2}
_EFFORT_ORDER = {"low": 0, "medium": 1, "high": 2}


def build_fixes(categories: list[CategoryResult], target_host: str = "") -> list[Fix]:
    """Turn failing/warning checks into ranked, actionable Fix objects.

    Ranking priority:
      1. severity (critical > important > minor)
      2. score_lift (higher first — more impact)
      3. effort     (low > medium > high)
    """
    fixes: list[Fix] = []
    for cat in categories:
        for check in cat.checks:
            if check.status in (CheckStatus.FAIL, CheckStatus.WARN):
                fix = build_fix_for_check(cat, check, target_host)
                if fix is not None:
                    fixes.append(fix)
    fixes.sort(
        key=lambda f: (
            _SEVERITY_ORDER[f.severity],
            -f.score_lift,
            _EFFORT_ORDER[f.effort],
        )
    )
    return fixes
