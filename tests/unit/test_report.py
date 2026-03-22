"""Tests for report generation."""

import json
import pytest
from pathlib import Path

from kestrel_eye.models import (
    ReviewReport,
    ScreenshotFinding,
    ScreenshotReview,
)
from kestrel_eye.report import (
    format_failure_summary,
    generate_json_report,
    generate_markdown_report,
    print_iteration_summary,
)


def _make_review(name: str, status: str = "pass") -> ScreenshotReview:
    finding_status = status if status != "warning" else "warning"
    return ScreenshotReview(
        screenshot_name=name,
        act="Act 1: Test",
        overall_status=status,
        findings=[
            ScreenshotFinding(
                element="element1",
                status=finding_status,
                description=f"element1 is {status}",
                confidence=0.9,
            )
        ],
        layout_assessment="test layout",
        readability_score=4,
        summary=f"{name} is {status}",
    )


def _make_report(**kwargs) -> ReviewReport:
    defaults = dict(
        timestamp="2026-03-22T00:00:00Z",
        model_used="claude-haiku-4-5-20251001",
        iteration=1,
        total_screenshots=2,
        passed=1,
        failed=1,
        reviews=[_make_review("a.png"), _make_review("b.png", "fail")],
    )
    defaults.update(kwargs)
    return ReviewReport(**defaults)


class TestJsonReport:
    def test_roundtrip(self, tmp_path):
        report = _make_report()
        path = tmp_path / "review.json"
        generate_json_report(report, path)

        loaded = ReviewReport.model_validate_json(path.read_text())
        assert loaded.total_screenshots == report.total_screenshots
        assert loaded.passed == report.passed
        assert loaded.failed == report.failed
        assert len(loaded.reviews) == len(report.reviews)

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "review.json"
        generate_json_report(_make_report(), path)
        assert path.exists()


class TestMarkdownReport:
    def test_contains_summary_table(self, tmp_path):
        report = _make_report()
        path = tmp_path / "review.md"
        generate_markdown_report(report, "Test Project", path)
        content = path.read_text()

        assert "| Pass | 1 |" in content
        assert "| Fail | 1 |" in content
        assert "Test Project" in content

    def test_fixed_section(self, tmp_path):
        report = _make_report(fixed_since_last=["a.png"])
        path = tmp_path / "review.md"
        generate_markdown_report(report, "Test", path)
        content = path.read_text()

        assert "Fixed this iteration" in content
        assert "a.png" in content

    def test_regressed_section(self, tmp_path):
        report = _make_report(regressed_since_last=["b.png"])
        path = tmp_path / "review.md"
        generate_markdown_report(report, "Test", path)
        content = path.read_text()

        assert "Regressed this iteration" in content
        assert "b.png" in content

    def test_per_screenshot_sections(self, tmp_path):
        report = _make_report()
        path = tmp_path / "review.md"
        generate_markdown_report(report, "Test", path)
        content = path.read_text()

        assert "Pass — a.png" in content
        assert "Fail — b.png" in content

    def test_empty_report(self, tmp_path):
        report = ReviewReport(
            timestamp="t", model_used="m", iteration=1,
        )
        path = tmp_path / "review.md"
        generate_markdown_report(report, "Test", path)
        assert path.exists()


class TestPrintIterationSummary:
    def test_all_pass(self, capsys):
        report = _make_report(passed=5, failed=0, total_screenshots=5, reviews=[])
        print_iteration_summary(report)
        captured = capsys.readouterr()
        assert "5/5 pass" in captured.out
        assert "0 fail" in captured.out

    def test_with_fixed(self, capsys):
        report = _make_report(fixed_since_last=["a.png", "b.png"])
        print_iteration_summary(report)
        captured = capsys.readouterr()
        assert "Fixed: 2" in captured.out


class TestFormatFailureSummary:
    def test_basic_format(self):
        report = _make_report()
        summary = format_failure_summary(report, "output/review.md")
        assert "1/2 pass" in summary
        assert "1 fail" in summary
        assert "FAILURES:" in summary
        assert "b.png" in summary
        assert "output/review.md" in summary

    def test_no_report_path(self):
        report = _make_report()
        summary = format_failure_summary(report)
        assert "Full report:" not in summary

    def test_all_pass_no_failures_section(self):
        report = _make_report(
            passed=2, failed=0, warnings=0,
            reviews=[_make_review("a.png"), _make_review("b.png")],
        )
        summary = format_failure_summary(report)
        assert "FAILURES:" not in summary
