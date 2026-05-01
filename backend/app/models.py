"""Pydantic models for scan requests and reports."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class CheckResult(BaseModel):
    """A single atomic check."""

    id: str
    label: str
    status: CheckStatus
    score: float = Field(ge=0, le=1, description="Normalized 0–1 score for this check")
    weight: float = Field(ge=0, description="Weight within its category")
    detail: str = ""
    evidence: dict | None = None


class CategoryId(StrEnum):
    AGENT_ACCESS = "agent_access"
    DISCOVERABILITY = "discoverability"
    STRUCTURED_DATA = "structured_data"
    CONTENT_CLARITY = "content_clarity"
    CITATION_PROBE = "citation_probe"


class CategoryResult(BaseModel):
    id: CategoryId
    label: str
    weight: float = Field(ge=0, le=1)
    score: int = Field(ge=0, le=100)
    checks: list[CheckResult]
    summary: str = ""


class Fix(BaseModel):
    """An actionable recommendation derived from a failing or warning check.

    Richer than a plain Recommendation: it includes an effort estimate, an
    expected score-lift (so users can triage high-leverage fixes first), and
    an optional copy-pasteable snippet (JSON-LD, <meta> tags, robots.txt lines…).
    """

    severity: Literal["critical", "important", "minor"]
    category: CategoryId
    title: str
    detail: str
    score_lift: int = Field(ge=0, le=100, description="Estimated overall-score delta if fixed")
    effort: Literal["low", "medium", "high"] = "low"
    snippet: str | None = None
    snippet_language: str | None = None
    docs_url: str | None = None


class ScanRequest(BaseModel):
    url: HttpUrl
    include_probe: bool = True


class DetectedCategory(BaseModel):
    """Auto-detected vertical for the scanned site.

    The user can override this from the UI; the override is round-tripped
    through ``GET /api/test-prompts`` and the resulting bundle has
    ``confidence == "high"`` and ``signals == ["user override"]``.
    """

    slug: str
    label: str
    persona: str
    confidence: Literal["high", "medium", "low"]
    signals: list[str] = Field(default_factory=list)


class PromptDeepLinks(BaseModel):
    """Pre-filled deep-link URLs for each AI search platform."""

    chatgpt: str
    perplexity: str
    claude: str
    google_ai: str


class TestPrompt(BaseModel):
    """A single AI-search prompt to test the site's visibility."""

    angle: Literal["category", "use_case", "comparison", "long_tail"]
    label: str
    text: str
    rationale: str
    deep_links: PromptDeepLinks


class TestPromptsBundle(BaseModel):
    """Bundle of AI-search test prompts attached to every scan report."""

    detected_category: DetectedCategory
    brand: str
    prompts: list[TestPrompt]
    all_categories: list[dict] = Field(default_factory=list)


class Report(BaseModel):
    url: str
    normalized_url: str
    domain: str
    scanned_at: datetime
    duration_ms: int
    score: int = Field(ge=0, le=100)
    grade: Literal["A", "B", "C", "D", "F"]
    categories: list[CategoryResult]
    fixes: list[Fix]
    test_prompts: TestPromptsBundle | None = None
    errors: list[str] = Field(default_factory=list)
