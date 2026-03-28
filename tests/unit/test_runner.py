"""Tests for the loop runner with mocked subprocess and reviewer."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from kestrel_eye.config import EyeConfig, ModelConfig, ScreenshotExpectation
from kestrel_eye.models import ReviewReport, ScreenshotFinding, ScreenshotReview
from kestrel_eye.runner import EyeRunner, RunnerConfig


def _make_config(screenshot_dir: str, test_cmd: str = "echo test") -> EyeConfig:
    return EyeConfig(
        name="Test",
        screenshot_dir=screenshot_dir,
        test_cmd=test_cmd,
        model=ModelConfig(),
        screenshots=[
            ScreenshotExpectation(
                name="a.png", act="Act 1",
                expected=["elem"], layout="layout",
            )
        ],
    )


def _make_report(passed: int = 1, failed: int = 0, iteration: int = 1) -> ReviewReport:
    reviews = []
    for i in range(passed):
        reviews.append(ScreenshotReview(
            screenshot_name=f"pass_{i}.png", act="Act 1", overall_status="pass",
            findings=[], layout_assessment="ok", readability_score=5, summary="ok",
        ))
    for i in range(failed):
        reviews.append(ScreenshotReview(
            screenshot_name=f"fail_{i}.png", act="Act 1", overall_status="fail",
            findings=[ScreenshotFinding(
                element="x", status="fail", description="missing", confidence=0.9,
            )],
            layout_assessment="bad", readability_score=2, summary="bad",
        ))
    return ReviewReport(
        timestamp="t", model_used="m", iteration=iteration,
        total_screenshots=passed + failed,
        passed=passed, failed=failed,
        reviews=reviews,
    )


@pytest.fixture
def mock_provider():
    provider = MagicMock()
    provider.model = "test-model"
    return provider


class TestRunTests:
    @pytest.mark.asyncio
    async def test_runs_test_cmd(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path), f"touch {tmp_path}/b.png")
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        result = await runner.run_tests()
        assert result is True

    @pytest.mark.asyncio
    async def test_no_test_cmd(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path), "")
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        result = await runner.run_tests()
        assert result is True

    @pytest.mark.asyncio
    async def test_no_screenshots_after_run(self, mock_provider, tmp_path):
        config = _make_config(str(tmp_path), "echo no_screenshots")
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        result = await runner.run_tests()
        assert result is False


class TestRunOnce:
    @pytest.mark.asyncio
    async def test_single_pass_all_pass(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)

        # Mock the reviewer
        runner.reviewer.review_all = AsyncMock(return_value=_make_report(passed=1))

        report = await runner.run_once()
        assert report.passed == 1
        assert runner.iteration == 1
        assert runner.get_exit_code(report) == 0

    @pytest.mark.asyncio
    async def test_single_pass_with_failures(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)

        runner.reviewer.review_all = AsyncMock(
            return_value=_make_report(passed=1, failed=1)
        )

        report = await runner.run_once()
        assert runner.get_exit_code(report) == 1

    @pytest.mark.asyncio
    async def test_no_screenshots_exit_code_2(self, mock_provider, tmp_path):
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)

        report = await runner.run_once()
        assert runner.get_exit_code(report) == 2


class TestRunLoop:
    @pytest.mark.asyncio
    async def test_exits_on_all_pass(self, mock_provider, tmp_path, capsys):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path))
        runner_config = RunnerConfig(eye_config=config, interactive=False)
        runner = EyeRunner(runner_config, mock_provider)

        runner.reviewer.review_all = AsyncMock(
            return_value=_make_report(passed=2, failed=0)
        )

        report = await runner.run_loop()
        assert report.passed == 2
        assert runner.iteration == 1
        captured = capsys.readouterr()
        assert "All screenshots pass" in captured.out

    @pytest.mark.asyncio
    async def test_non_interactive_exits_after_one(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path))
        runner_config = RunnerConfig(eye_config=config, interactive=False)
        runner = EyeRunner(runner_config, mock_provider)

        runner.reviewer.review_all = AsyncMock(
            return_value=_make_report(passed=1, failed=1)
        )

        report = await runner.run_loop()
        assert runner.iteration == 1  # Only one iteration in non-interactive

    @pytest.mark.asyncio
    async def test_history_tracks_reports(self, mock_provider, tmp_path):
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)

        runner.reviewer.review_all = AsyncMock(
            return_value=_make_report(passed=2)
        )

        await runner.run_once()
        assert len(runner.history) == 1
        assert runner.history[0].passed == 2


class TestConfigurableTimeout:
    @pytest.mark.asyncio
    async def test_uses_config_timeout(self, mock_provider, tmp_path):
        """Runner uses timeout from config, not hardcoded value."""
        (tmp_path / "a.png").write_bytes(b"fake")
        config = _make_config(str(tmp_path), "echo test")
        config.model.timeout = 60
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)

        with patch("kestrel_eye.runner.asyncio.wait_for", new_callable=AsyncMock) as mock_wait:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_wait.return_value = (b"", b"")

            with patch("kestrel_eye.runner.asyncio.create_subprocess_shell", new_callable=AsyncMock) as mock_sub:
                mock_sub.return_value = mock_proc
                mock_proc.communicate = AsyncMock(return_value=(b"", b""))
                await runner.run_tests()
                # Verify timeout kwarg passed to wait_for
                mock_wait.assert_called_once()
                call_kwargs = mock_wait.call_args
                assert call_kwargs.kwargs.get("timeout") == 60 or call_kwargs[1].get("timeout") == 60 or (len(call_kwargs[0]) > 1 and call_kwargs[0][1] == 60)


class TestExitCodes:
    def test_all_pass_is_0(self, mock_provider, tmp_path):
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        report = _make_report(passed=5, failed=0)
        assert runner.get_exit_code(report) == 0

    def test_failures_is_1(self, mock_provider, tmp_path):
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        report = _make_report(passed=3, failed=2)
        assert runner.get_exit_code(report) == 1

    def test_no_screenshots_is_2(self, mock_provider, tmp_path):
        config = _make_config(str(tmp_path))
        runner = EyeRunner(RunnerConfig(eye_config=config), mock_provider)
        report = ReviewReport(timestamp="t", model_used="m", iteration=1)
        assert runner.get_exit_code(report) == 2
