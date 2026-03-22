"""Tests for GitHub issue reporter with mocked gh CLI."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from kestrel_eye.models import (
    ReviewReport,
    ScreenshotFinding,
    ScreenshotReview,
)
from kestrel_eye.reporter import GitHubReporter


def _make_review(name: str, act: str, status: str = "pass") -> ScreenshotReview:
    return ScreenshotReview(
        screenshot_name=name,
        act=act,
        overall_status=status,
        findings=[
            ScreenshotFinding(
                element="elem", status=status,
                description=f"elem is {status}", confidence=0.9,
            )
        ],
        layout_assessment="ok",
        readability_score=4,
        summary=f"{name} is {status}",
    )


def _make_report(reviews: list[ScreenshotReview]) -> ReviewReport:
    passed = sum(1 for r in reviews if r.overall_status == "pass")
    failed = sum(1 for r in reviews if r.overall_status == "fail")
    return ReviewReport(
        timestamp="t", model_used="m", iteration=1,
        total_screenshots=len(reviews),
        passed=passed, failed=failed,
        reviews=reviews,
    )


class TestGitHubReporter:
    @pytest.mark.asyncio
    async def test_no_issues_when_all_pass(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._check_gh = lambda: True
        reporter._run_gh = AsyncMock(return_value="")
        reporter._find_issue = AsyncMock(return_value=None)

        report = _make_report([
            _make_review("a.png", "Act 1"),
            _make_review("b.png", "Act 2"),
        ])

        urls = await reporter.report(report, "Test")
        # Should not create any issues
        assert all("closed" not in u for u in urls if u)

    @pytest.mark.asyncio
    async def test_creates_issue_for_failing_act(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._check_gh = lambda: True
        reporter._find_issue = AsyncMock(return_value=None)
        reporter._run_gh = AsyncMock(return_value="https://github.com/owner/repo/issues/1")

        report = _make_report([
            _make_review("a.png", "Act 1", "fail"),
            _make_review("b.png", "Act 2"),
        ])

        urls = await reporter.report(report, "Test")
        assert len(urls) >= 1
        # Verify issue create was called
        create_calls = [
            c for c in reporter._run_gh.call_args_list
            if c.args[0] == "issue" and c.args[1] == "create"
        ]
        assert len(create_calls) == 1

    @pytest.mark.asyncio
    async def test_groups_failures_by_act(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._check_gh = lambda: True
        reporter._find_issue = AsyncMock(return_value=None)
        reporter._run_gh = AsyncMock(return_value="https://github.com/owner/repo/issues/1")

        report = _make_report([
            _make_review("a.png", "Act 1", "fail"),
            _make_review("b.png", "Act 1", "fail"),
            _make_review("c.png", "Act 2"),
        ])

        urls = await reporter.report(report, "Test")
        # Should create one issue for Act 1 (not two)
        create_calls = [
            c for c in reporter._run_gh.call_args_list
            if c.args[0] == "issue" and c.args[1] == "create"
        ]
        assert len(create_calls) == 1

    @pytest.mark.asyncio
    async def test_comments_on_existing_issue(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._check_gh = lambda: True
        reporter._find_issue = AsyncMock(return_value=42)  # Existing issue
        reporter._run_gh = AsyncMock(return_value="")

        report = _make_report([
            _make_review("a.png", "Act 1", "fail"),
        ])

        await reporter.report(report, "Test")
        comment_calls = [
            c for c in reporter._run_gh.call_args_list
            if c.args[0] == "issue" and c.args[1] == "comment"
        ]
        assert len(comment_calls) == 1
        assert "42" in comment_calls[0].args

    @pytest.mark.asyncio
    async def test_closes_fixed_issues(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._check_gh = lambda: True
        reporter._find_issue = AsyncMock(return_value=42)
        reporter._run_gh = AsyncMock(return_value="")

        report = _make_report([
            _make_review("a.png", "Act 1"),  # Now passes
        ])

        urls = await reporter.report(report, "Test")
        close_calls = [
            c for c in reporter._run_gh.call_args_list
            if c.args[0] == "issue" and c.args[1] == "close"
        ]
        assert len(close_calls) == 1

    @pytest.mark.asyncio
    async def test_gh_not_available(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        reporter._gh_available = False

        report = _make_report([_make_review("a.png", "Act 1", "fail")])
        urls = await reporter.report(report, "Test")
        assert urls == []

    def test_issue_body_format(self):
        reporter = GitHubReporter("owner/repo", ["kestrel-eye"])
        body = reporter._format_issue_body(
            "Act 1: Test",
            [_make_review("a.png", "Act 1", "fail")],
            iteration=2,
            project_name="My Project",
        )
        assert "kestrel-eye Visual Review Failure" in body
        assert "My Project" in body
        assert "a.png" in body
        assert "kestrel-talon" in body
