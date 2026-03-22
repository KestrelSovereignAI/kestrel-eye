"""Pydantic models for structured review output."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScreenshotFinding(BaseModel):
    """A single finding from reviewing one expected element."""

    element: str = Field(description="The expected element that was checked")
    status: Literal["pass", "fail", "warning", "unclear"] = Field(
        description="Result of the check"
    )
    description: str = Field(description="What was found or missing")
    confidence: float = Field(
        ge=0.0, le=1.0, description="Confidence in this finding (0.0-1.0)"
    )


class ScreenshotReview(BaseModel):
    """Complete review of a single screenshot."""

    screenshot_name: str = Field(description="Filename of the screenshot")
    act: str = Field(description="Logical grouping (e.g. 'Act 1: Cryptographic Identity')")
    overall_status: Literal["pass", "fail", "warning"] = Field(
        description="Overall status: pass if all elements found, fail if any critical missing"
    )
    findings: list[ScreenshotFinding] = Field(
        description="Per-element findings"
    )
    layout_assessment: str = Field(
        description="Free-text assessment of layout and composition"
    )
    readability_score: int = Field(
        ge=1, le=5, description="Readability rating: 1=broken, 5=crisp and clear"
    )
    summary: str = Field(description="One-line summary of the review")


class ReviewReport(BaseModel):
    """Aggregated report across all screenshots for one iteration."""

    timestamp: str
    model_used: str
    iteration: int = 1
    total_screenshots: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    reviews: list[ScreenshotReview] = []
    fixed_since_last: list[str] = []
    regressed_since_last: list[str] = []


class GitHubIssueSpec(BaseModel):
    """Specification for a GitHub issue to file."""

    title: str
    body: str
    labels: list[str] = []
    severity: Literal["critical", "warning"] = "critical"
    screenshots_affected: list[str] = []


def compute_iteration_diff(
    current: ReviewReport,
    previous: Optional[ReviewReport],
) -> tuple[list[str], list[str]]:
    """Compare two reports and return (fixed, regressed) screenshot names.

    fixed: was fail/warning in previous, now pass in current
    regressed: was pass in previous, now fail/warning in current

    Returns:
        Tuple of (fixed_since_last, regressed_since_last).
    """
    if previous is None:
        return [], []

    prev_status = {
        r.screenshot_name: r.overall_status for r in previous.reviews
    }
    curr_status = {
        r.screenshot_name: r.overall_status for r in current.reviews
    }

    fixed = []
    regressed = []

    for name, curr in curr_status.items():
        prev = prev_status.get(name)
        if prev is None:
            continue
        if prev in ("fail", "warning") and curr == "pass":
            fixed.append(name)
        elif prev == "pass" and curr in ("fail", "warning"):
            regressed.append(name)

    return sorted(fixed), sorted(regressed)
