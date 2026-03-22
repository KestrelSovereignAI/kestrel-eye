"""Tests for Pydantic models and iteration diff computation."""

import pytest

from kestrel_eye.models import (
    GitHubIssueSpec,
    ReviewReport,
    ScreenshotFinding,
    ScreenshotReview,
    compute_iteration_diff,
)


def _make_review(name: str, status: str = "pass") -> ScreenshotReview:
    """Helper to create a ScreenshotReview."""
    return ScreenshotReview(
        screenshot_name=name,
        act="Act 1",
        overall_status=status,
        findings=[
            ScreenshotFinding(
                element="test element",
                status=status,
                description="test description",
                confidence=0.9,
            )
        ],
        layout_assessment="test layout",
        readability_score=4,
        summary=f"Screenshot {name} is {status}",
    )


def _make_report(reviews: list[ScreenshotReview], iteration: int = 1) -> ReviewReport:
    """Helper to create a ReviewReport."""
    passed = sum(1 for r in reviews if r.overall_status == "pass")
    failed = sum(1 for r in reviews if r.overall_status == "fail")
    warnings = sum(1 for r in reviews if r.overall_status == "warning")
    return ReviewReport(
        timestamp="2026-03-22T00:00:00Z",
        model_used="test-model",
        iteration=iteration,
        total_screenshots=len(reviews),
        passed=passed,
        failed=failed,
        warnings=warnings,
        reviews=reviews,
    )


class TestScreenshotReview:
    def test_serialization_roundtrip(self):
        review = _make_review("test.png")
        data = review.model_dump()
        restored = ScreenshotReview.model_validate(data)
        assert restored.screenshot_name == "test.png"
        assert restored.overall_status == "pass"

    def test_json_roundtrip(self):
        review = _make_review("test.png", "fail")
        json_str = review.model_dump_json()
        restored = ScreenshotReview.model_validate_json(json_str)
        assert restored.overall_status == "fail"

    def test_finding_confidence_bounds(self):
        with pytest.raises(Exception):
            ScreenshotFinding(
                element="x", status="pass",
                description="x", confidence=1.5,
            )
        with pytest.raises(Exception):
            ScreenshotFinding(
                element="x", status="pass",
                description="x", confidence=-0.1,
            )

    def test_readability_bounds(self):
        with pytest.raises(Exception):
            _make_review("x.png")
            ScreenshotReview(
                screenshot_name="x", act="Act", overall_status="pass",
                findings=[], layout_assessment="", readability_score=0,
                summary="",
            )
        with pytest.raises(Exception):
            ScreenshotReview(
                screenshot_name="x", act="Act", overall_status="pass",
                findings=[], layout_assessment="", readability_score=6,
                summary="",
            )


class TestReviewReport:
    def test_empty_report(self):
        report = ReviewReport(
            timestamp="2026-01-01", model_used="test", iteration=1
        )
        assert report.total_screenshots == 0
        assert report.passed == 0
        assert report.reviews == []

    def test_json_roundtrip(self):
        report = _make_report([_make_review("a.png"), _make_review("b.png", "fail")])
        json_str = report.model_dump_json()
        restored = ReviewReport.model_validate_json(json_str)
        assert restored.total_screenshots == 2
        assert restored.passed == 1
        assert restored.failed == 1


class TestComputeIterationDiff:
    def test_no_previous(self):
        current = _make_report([_make_review("a.png")])
        fixed, regressed = compute_iteration_diff(current, None)
        assert fixed == []
        assert regressed == []

    def test_all_pass_both(self):
        prev = _make_report([_make_review("a.png"), _make_review("b.png")])
        curr = _make_report([_make_review("a.png"), _make_review("b.png")])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == []
        assert regressed == []

    def test_some_fixed(self):
        prev = _make_report([
            _make_review("a.png", "fail"),
            _make_review("b.png", "fail"),
            _make_review("c.png", "pass"),
        ])
        curr = _make_report([
            _make_review("a.png", "pass"),
            _make_review("b.png", "fail"),
            _make_review("c.png", "pass"),
        ])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == ["a.png"]
        assert regressed == []

    def test_some_regressed(self):
        prev = _make_report([
            _make_review("a.png", "pass"),
            _make_review("b.png", "pass"),
        ])
        curr = _make_report([
            _make_review("a.png", "fail"),
            _make_review("b.png", "pass"),
        ])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == []
        assert regressed == ["a.png"]

    def test_mixed_fixed_and_regressed(self):
        prev = _make_report([
            _make_review("a.png", "fail"),
            _make_review("b.png", "pass"),
            _make_review("c.png", "warning"),
        ])
        curr = _make_report([
            _make_review("a.png", "pass"),
            _make_review("b.png", "fail"),
            _make_review("c.png", "pass"),
        ])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == ["a.png", "c.png"]
        assert regressed == ["b.png"]

    def test_warning_to_pass_is_fixed(self):
        prev = _make_report([_make_review("a.png", "warning")])
        curr = _make_report([_make_review("a.png", "pass")])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == ["a.png"]

    def test_pass_to_warning_is_regressed(self):
        prev = _make_report([_make_review("a.png", "pass")])
        curr = _make_report([_make_review("a.png", "warning")])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert regressed == ["a.png"]

    def test_new_screenshot_in_current(self):
        """New screenshot in current (not in previous) is not counted."""
        prev = _make_report([_make_review("a.png")])
        curr = _make_report([_make_review("a.png"), _make_review("b.png", "fail")])
        fixed, regressed = compute_iteration_diff(curr, prev)
        assert fixed == []
        assert regressed == []


class TestGitHubIssueSpec:
    def test_defaults(self):
        spec = GitHubIssueSpec(title="test", body="body")
        assert spec.severity == "critical"
        assert spec.labels == []
        assert spec.screenshots_affected == []
