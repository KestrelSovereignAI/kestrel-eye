"""Tests for the reviewer engine with mocked provider."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from kestrel_eye.config import EyeConfig, ModelConfig, ScreenshotExpectation
from kestrel_eye.models import (
    ReviewReport,
    ScreenshotFinding,
    ScreenshotReview,
)
from kestrel_eye.reviewer import DemoReviewer


def _make_config(screenshot_dir: str, screenshots: list[ScreenshotExpectation]) -> EyeConfig:
    return EyeConfig(
        name="Test",
        screenshot_dir=screenshot_dir,
        model=ModelConfig(),
        screenshots=screenshots,
    )


def _make_expectation(name: str) -> ScreenshotExpectation:
    return ScreenshotExpectation(
        name=name,
        act="Act 1",
        expected=["element1", "element2"],
        layout="test layout",
    )


def _make_passing_review(name: str) -> ScreenshotReview:
    return ScreenshotReview(
        screenshot_name=name,
        act="Act 1",
        overall_status="pass",
        findings=[
            ScreenshotFinding(
                element="element1", status="pass",
                description="found", confidence=0.95,
            )
        ],
        layout_assessment="good",
        readability_score=5,
        summary="All good",
    )


def _make_failing_review(name: str) -> ScreenshotReview:
    return ScreenshotReview(
        screenshot_name=name,
        act="Act 1",
        overall_status="fail",
        findings=[
            ScreenshotFinding(
                element="element1", status="fail",
                description="not found", confidence=0.9,
            )
        ],
        layout_assessment="broken",
        readability_score=2,
        summary="Missing elements",
    )


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model = "test-model"
    provider.review_screenshot = AsyncMock()
    return provider


class TestReviewAll:
    @pytest.mark.asyncio
    async def test_all_pass(self, mock_provider, tmp_path):
        # Create fake screenshots
        (tmp_path / "a.png").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")

        config = _make_config(str(tmp_path), [
            _make_expectation("a.png"),
            _make_expectation("b.png"),
        ])

        mock_provider.review_screenshot.side_effect = [
            _make_passing_review("a.png"),
            _make_passing_review("b.png"),
        ]

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.total_screenshots == 2
        assert report.passed == 2
        assert report.failed == 0
        assert report.warnings == 0
        assert mock_provider.review_screenshot.call_count == 2

    @pytest.mark.asyncio
    async def test_concurrent_reviews(self, mock_provider, tmp_path):
        """review_all uses asyncio.gather for concurrent execution."""
        import asyncio

        names = [f"{i}.png" for i in range(5)]
        for name in names:
            (tmp_path / name).write_bytes(b"fake")

        config = _make_config(str(tmp_path), [_make_expectation(n) for n in names])

        call_order = []

        async def _track_review(**kwargs):
            call_order.append(kwargs["screenshot_name"])
            await asyncio.sleep(0)
            return _make_passing_review(kwargs["screenshot_name"])

        mock_provider.review_screenshot.side_effect = _track_review

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.total_screenshots == 5
        assert report.passed == 5
        assert mock_provider.review_screenshot.call_count == 5

    @pytest.mark.asyncio
    async def test_mixed_results(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")

        config = _make_config(str(tmp_path), [
            _make_expectation("a.png"),
            _make_expectation("b.png"),
        ])

        mock_provider.review_screenshot.side_effect = [
            _make_passing_review("a.png"),
            _make_failing_review("b.png"),
        ]

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.passed == 1
        assert report.failed == 1
        assert report.total_screenshots == 2

    @pytest.mark.asyncio
    async def test_missing_screenshot(self, mock_provider, tmp_path):
        """Missing screenshot file handled gracefully."""
        config = _make_config(str(tmp_path), [
            _make_expectation("missing.png"),
        ])

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.total_screenshots == 1
        assert report.failed == 1
        assert report.reviews[0].overall_status == "fail"
        assert "not found" in report.reviews[0].summary
        # Provider should NOT be called for missing files
        mock_provider.review_screenshot.assert_not_called()

    @pytest.mark.asyncio
    async def test_provider_error(self, mock_provider, tmp_path):
        """Provider error handled gracefully."""
        (tmp_path / "a.png").write_bytes(b"fake")

        config = _make_config(str(tmp_path), [
            _make_expectation("a.png"),
        ])

        mock_provider.review_screenshot.side_effect = RuntimeError("API error")

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.total_screenshots == 1
        assert report.failed == 1
        assert "Provider error" in report.reviews[0].summary

    @pytest.mark.asyncio
    async def test_empty_config(self, mock_provider, tmp_path):
        """Empty screenshots list produces valid empty report."""
        config = _make_config(str(tmp_path), [])
        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all()

        assert report.total_screenshots == 0
        assert report.passed == 0

    @pytest.mark.asyncio
    async def test_iteration_diff(self, mock_provider, tmp_path):
        """Previous report enables fixed/regressed computation."""
        (tmp_path / "a.png").write_bytes(b"fake")
        (tmp_path / "b.png").write_bytes(b"fake")

        config = _make_config(str(tmp_path), [
            _make_expectation("a.png"),
            _make_expectation("b.png"),
        ])

        # Previous: a=fail, b=pass
        prev = ReviewReport(
            timestamp="t", model_used="m", iteration=1,
            total_screenshots=2, passed=1, failed=1,
            reviews=[
                _make_failing_review("a.png"),
                _make_passing_review("b.png"),
            ],
        )

        # Current: a=pass, b=pass
        mock_provider.review_screenshot.side_effect = [
            _make_passing_review("a.png"),
            _make_passing_review("b.png"),
        ]

        reviewer = DemoReviewer(config, mock_provider)
        report = await reviewer.review_all(iteration=2, previous_report=prev)

        assert report.fixed_since_last == ["a.png"]
        assert report.regressed_since_last == []
        assert report.iteration == 2

    @pytest.mark.asyncio
    async def test_correct_args_passed_to_provider(self, mock_provider, tmp_path):
        """Provider called with correct image path and expectations."""
        (tmp_path / "test.png").write_bytes(b"fake")

        exp = ScreenshotExpectation(
            name="test.png",
            act="Act 2: Test",
            expected=["elem1", "elem2"],
            layout="test layout desc",
        )
        config = _make_config(str(tmp_path), [exp])

        mock_provider.review_screenshot.return_value = _make_passing_review("test.png")

        reviewer = DemoReviewer(config, mock_provider)
        await reviewer.review_all()

        call_kwargs = mock_provider.review_screenshot.call_args
        assert call_kwargs.kwargs["image_path"] == tmp_path / "test.png"
        assert call_kwargs.kwargs["screenshot_name"] == "test.png"
        assert call_kwargs.kwargs["act"] == "Act 2: Test"
        assert call_kwargs.kwargs["expected_elements"] == ["elem1", "elem2"]
        assert call_kwargs.kwargs["layout_description"] == "test layout desc"
