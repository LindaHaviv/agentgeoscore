"""Unit tests for the scoring engine."""
from __future__ import annotations

from app.models import CategoryId, CheckResult, CheckStatus
from app.scoring import (
    build_category,
    build_fixes,
    grade_for,
    overall_score,
    score_category,
)


def _mk(score: float, weight: float = 1.0, status: CheckStatus = CheckStatus.PASS) -> CheckResult:
    return CheckResult(id="x", label="x", score=score, weight=weight, status=status)


def test_score_category_weighted_average():
    checks = [_mk(1.0, 2.0), _mk(0.0, 2.0), _mk(0.5, 4.0)]
    # weighted sum = 2 + 0 + 2 = 4; total weight = 8; 100 * 4/8 = 50
    assert score_category(checks) == 50


def test_score_category_skipped_excluded():
    checks = [
        _mk(1.0, 1.0, status=CheckStatus.PASS),
        _mk(0.0, 1.0, status=CheckStatus.SKIP),  # ignored
    ]
    assert score_category(checks) == 100


def test_score_category_all_skipped_is_zero():
    checks = [_mk(1.0, 1.0, status=CheckStatus.SKIP)]
    assert score_category(checks) == 0


def test_score_category_zero_weight_safe():
    checks = [_mk(1.0, 0.0, status=CheckStatus.PASS)]
    assert score_category(checks) == 0


def test_score_category_empty():
    assert score_category([]) == 0


def test_overall_score_weighted():
    cats = [
        build_category(CategoryId.AGENT_ACCESS, [_mk(1.0, 1.0)]),          # 100, weight .25
        build_category(CategoryId.DISCOVERABILITY, [_mk(0.5, 1.0)]),        # 50,  weight .20
        build_category(CategoryId.STRUCTURED_DATA, [_mk(0.0, 1.0)]),        # 0,   weight .20
        build_category(CategoryId.CONTENT_CLARITY, [_mk(1.0, 1.0)]),        # 100, weight .15
        build_category(CategoryId.CITATION_PROBE, [_mk(0.5, 1.0)]),         # 50,  weight .20
    ]
    # weighted: 100*.25 + 50*.20 + 0*.20 + 100*.15 + 50*.20 = 25 + 10 + 0 + 15 + 10 = 60
    assert overall_score(cats) == 60


def test_overall_score_renormalizes_without_probe():
    # Drop citation_probe; scoring engine should renormalize
    cats = [
        build_category(CategoryId.AGENT_ACCESS, [_mk(1.0, 1.0)]),          # 100, .25
        build_category(CategoryId.DISCOVERABILITY, [_mk(1.0, 1.0)]),        # 100, .20
        build_category(CategoryId.STRUCTURED_DATA, [_mk(1.0, 1.0)]),        # 100, .20
        build_category(CategoryId.CONTENT_CLARITY, [_mk(1.0, 1.0)]),        # 100, .15
    ]
    # Without probe, total weight = .80; all 100 → overall 100
    assert overall_score(cats) == 100


def test_overall_score_excludes_fully_skipped_category():
    # Citation Probe present but all checks are SKIP (no API keys). It MUST
    # NOT drag down the overall score as a 0 — it should be excluded and the
    # remaining weights re-normalized.
    cats = [
        build_category(CategoryId.AGENT_ACCESS, [_mk(1.0, 1.0)]),                           # 100
        build_category(CategoryId.DISCOVERABILITY, [_mk(1.0, 1.0)]),                         # 100
        build_category(CategoryId.STRUCTURED_DATA, [_mk(1.0, 1.0)]),                         # 100
        build_category(CategoryId.CONTENT_CLARITY, [_mk(1.0, 1.0)]),                         # 100
        build_category(CategoryId.CITATION_PROBE, [_mk(0.0, 1.0, status=CheckStatus.SKIP)]),  # skipped
    ]
    assert overall_score(cats) == 100


def test_overall_score_empty():
    assert overall_score([]) == 0


def test_grade_boundaries():
    assert grade_for(100) == "A"
    assert grade_for(90) == "A"
    assert grade_for(89) == "B"
    assert grade_for(75) == "B"
    assert grade_for(74) == "C"
    assert grade_for(60) == "C"
    assert grade_for(59) == "D"
    assert grade_for(40) == "D"
    assert grade_for(39) == "F"
    assert grade_for(0) == "F"


def test_fixes_prioritizes_critical():
    cats = [
        build_category(
            CategoryId.AGENT_ACCESS,
            [
                CheckResult(
                    id="fail1", label="Critical fail", weight=3, score=0, status=CheckStatus.FAIL, detail="fix me"
                ),
                CheckResult(
                    id="warn1", label="Small warn", weight=1, score=0.5, status=CheckStatus.WARN
                ),
            ],
        ),
        build_category(
            CategoryId.CONTENT_CLARITY,  # weight 0.15 → "important" not "critical"
            [CheckResult(id="fail2", label="Non-core fail", weight=1, score=0, status=CheckStatus.FAIL)],
        ),
    ]
    fixes = build_fixes(cats)
    # Critical from high-weight category first
    assert fixes[0].severity == "critical"
    assert fixes[0].category == CategoryId.AGENT_ACCESS
    # Severities are sorted critical → important → minor
    severities = [f.severity for f in fixes]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "important": 1, "minor": 2}[s])
    # Every fix exposes a non-negative score_lift (used by the UI for triage)
    assert all(f.score_lift >= 0 for f in fixes)


def test_fixes_snippet_rewrites_example_com_to_target_host():
    cats = [
        build_category(
            CategoryId.STRUCTURED_DATA,
            [
                CheckResult(
                    id="jsonld_present",
                    label="schema.org JSON-LD present",
                    weight=3.0,
                    score=0,
                    status=CheckStatus.FAIL,
                    detail="no JSON-LD",
                )
            ],
        )
    ]
    fixes = build_fixes(cats, target_host="mysite.io")
    jsonld_fix = next(f for f in fixes if "JSON-LD" in f.title)
    assert jsonld_fix.snippet is not None
    assert "mysite.io" in jsonld_fix.snippet
    assert "example.com" not in jsonld_fix.snippet
