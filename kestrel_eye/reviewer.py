"""Core reviewer — reviews all screenshots against expectations."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from kestrel_eye.config import EyeConfig, ScreenshotExpectation
from kestrel_eye.models import (
    ReviewReport,
    ScreenshotFinding,
    ScreenshotReview,
    compute_iteration_diff,
)
from kestrel_eye.providers.base import VisionProvider

logger = logging.getLogger(__name__)


class DemoReviewer:
    """Reviews screenshots against expectations using a vision provider."""

    def __init__(self, config: EyeConfig, provider: VisionProvider):
        self.config = config
        self.provider = provider
        self._semaphore = asyncio.Semaphore(config.model.max_concurrency)

    async def review_all(
        self,
        iteration: int = 1,
        previous_report: Optional[ReviewReport] = None,
    ) -> ReviewReport:
        """Review all screenshots from config.

        Args:
            iteration: Current iteration number (1-indexed).
            previous_report: Previous iteration's report for diff computation.

        Returns:
            Complete ReviewReport with all findings.
        """

        async def _bounded_review(expectation: ScreenshotExpectation) -> ScreenshotReview:
            async with self._semaphore:
                return await self.review_single(expectation)

        reviews = await asyncio.gather(
            *[_bounded_review(exp) for exp in self.config.screenshots]
        )

        passed = sum(1 for r in reviews if r.overall_status == "pass")
        failed = sum(1 for r in reviews if r.overall_status == "fail")
        warnings = sum(1 for r in reviews if r.overall_status == "warning")

        report = ReviewReport(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_used=getattr(self.provider, "model", "unknown"),
            iteration=iteration,
            total_screenshots=len(reviews),
            passed=passed,
            failed=failed,
            warnings=warnings,
            reviews=reviews,
        )

        fixed, regressed = compute_iteration_diff(report, previous_report)
        report.fixed_since_last = fixed
        report.regressed_since_last = regressed

        return report

    async def review_single(
        self,
        expectation: ScreenshotExpectation,
    ) -> ScreenshotReview:
        """Review one screenshot against its expectations.

        Handles missing files and provider errors gracefully.
        """
        screenshot_dir = Path(self.config.screenshot_dir)
        image_path = screenshot_dir / expectation.name

        if not image_path.exists():
            logger.warning("Screenshot not found: %s", image_path)
            return ScreenshotReview(
                screenshot_name=expectation.name,
                act=expectation.act,
                overall_status="fail",
                findings=[
                    ScreenshotFinding(
                        element="screenshot file",
                        status="fail",
                        description=f"Screenshot not found: {image_path}",
                        confidence=1.0,
                    )
                ],
                layout_assessment="Cannot assess — screenshot missing",
                readability_score=1,
                summary=f"Screenshot not found: {expectation.name}",
            )

        try:
            return await self.provider.review_screenshot(
                image_path=image_path,
                screenshot_name=expectation.name,
                act=expectation.act,
                expected_elements=expectation.expected,
                layout_description=expectation.layout,
                context=expectation.context,
            )
        except Exception as e:
            logger.error(
                "Provider error reviewing %s: %s", expectation.name, e
            )
            return ScreenshotReview(
                screenshot_name=expectation.name,
                act=expectation.act,
                overall_status="fail",
                findings=[
                    ScreenshotFinding(
                        element="provider call",
                        status="fail",
                        description=f"Provider error: {e}",
                        confidence=1.0,
                    )
                ],
                layout_assessment="Cannot assess — provider error",
                readability_score=1,
                summary=f"Provider error reviewing {expectation.name}: {e}",
            )
