"""Loop runner — orchestrates test execution + review iterations."""

import asyncio
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from kestrel_eye.config import EyeConfig
from kestrel_eye.models import ReviewReport
from kestrel_eye.providers.base import VisionProvider
from kestrel_eye.report import (
    format_failure_summary,
    generate_json_report,
    generate_markdown_report,
    print_iteration_summary,
)
from kestrel_eye.reviewer import DemoReviewer

logger = logging.getLogger(__name__)


@dataclass
class RunnerConfig:
    """Configuration for the runner."""

    eye_config: EyeConfig
    max_iterations: int = 10
    interactive: bool = False
    file_issues: bool = False
    output_dir: Optional[Path] = None

    @property
    def screenshot_dir(self) -> Path:
        return Path(self.eye_config.screenshot_dir)

    @property
    def report_dir(self) -> Path:
        return self.output_dir or self.screenshot_dir


class EyeRunner:
    """Orchestrates test execution + review loop."""

    def __init__(self, config: RunnerConfig, provider: VisionProvider):
        self.config = config
        self.provider = provider
        self.reviewer = DemoReviewer(config.eye_config, provider)
        self.iteration = 0
        self.history: list[ReviewReport] = []

    async def run_tests(self) -> bool:
        """Execute test_cmd from eye.toml via subprocess.

        Returns:
            True if screenshot_dir contains PNG files after execution.
        """
        test_cmd = self.config.eye_config.test_cmd
        if not test_cmd:
            logger.warning("No test_cmd configured — skipping test execution")
            return self._has_screenshots()

        logger.info("Running: %s", test_cmd)
        try:
            proc = await asyncio.create_subprocess_shell(
                test_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            timeout = self.config.eye_config.model.timeout
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            if proc.returncode != 0:
                logger.warning(
                    "test_cmd exited with code %d (may still have screenshots)",
                    proc.returncode,
                )
                if stderr:
                    logger.debug("test_cmd stderr: %s", stderr.decode()[:500])

        except asyncio.TimeoutError:
            logger.error("test_cmd timed out after %ds", timeout)
            return self._has_screenshots()
        except Exception as e:
            logger.error("Failed to run test_cmd: %s", e)
            return self._has_screenshots()

        return self._has_screenshots()

    async def run_review(self) -> ReviewReport:
        """Review current screenshots, comparing to previous iteration."""
        previous = self.history[-1] if self.history else None
        return await self.reviewer.review_all(
            iteration=self.iteration,
            previous_report=previous,
        )

    async def run_once(self) -> ReviewReport:
        """Single pass: run tests -> review -> generate reports.

        This is what talon calls via quality gate.
        """
        self.iteration += 1

        has_screenshots = await self.run_tests()
        if not has_screenshots:
            logger.error("No screenshots found in %s", self.config.screenshot_dir)
            return ReviewReport(
                timestamp="",
                model_used=getattr(self.provider, "model", "unknown"),
                iteration=self.iteration,
            )

        report = await self.run_review()
        self.history.append(report)
        self._generate_reports(report)
        return report

    async def run_loop(self) -> ReviewReport:
        """Interactive loop: run_once -> print summary -> wait -> repeat.

        This is what developers use standalone.
        """
        report = ReviewReport(timestamp="", model_used="", iteration=0)

        while self.iteration < self.config.max_iterations:
            report = await self.run_once()
            print_iteration_summary(report)

            if report.failed == 0 and report.warnings == 0:
                print("\n✓ All screenshots pass!")
                return report

            if not self.config.interactive:
                return report

            try:
                input("\nPress Enter after fixing issues to re-run...")
            except (KeyboardInterrupt, EOFError):
                print("\nStopped.")
                return report

        print(f"\nMax iterations ({self.config.max_iterations}) reached.")
        return report

    async def run_review_only(self) -> ReviewReport:
        """Skip test execution, review existing screenshots."""
        self.iteration += 1

        if not self._has_screenshots():
            logger.error("No screenshots found in %s", self.config.screenshot_dir)
            return ReviewReport(
                timestamp="",
                model_used=getattr(self.provider, "model", "unknown"),
                iteration=self.iteration,
            )

        report = await self.run_review()
        self.history.append(report)
        self._generate_reports(report)
        return report

    def _has_screenshots(self) -> bool:
        """Check if screenshot_dir has any PNG files."""
        screenshot_dir = self.config.screenshot_dir
        if not screenshot_dir.exists():
            return False
        return any(screenshot_dir.glob("*.png"))

    def _generate_reports(self, report: ReviewReport) -> None:
        """Generate JSON and Markdown reports."""
        report_dir = self.config.report_dir
        generate_json_report(report, report_dir / "review.json")
        generate_markdown_report(
            report,
            self.config.eye_config.name,
            report_dir / "review.md",
        )

    def get_exit_code(self, report: ReviewReport) -> int:
        """Determine exit code from report.

        Returns:
            0 = all pass, 1 = failures, 2 = no screenshots.
        """
        if report.total_screenshots == 0:
            return 2
        if report.failed > 0 or report.warnings > 0:
            return 1
        return 0
