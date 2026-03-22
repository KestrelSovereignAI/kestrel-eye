"""GitHub issue reporter — auto-file, update, and close issues per iteration."""

import asyncio
import json
import logging
import shutil
from collections import defaultdict
from typing import Optional

from kestrel_eye.models import GitHubIssueSpec, ReviewReport, ScreenshotReview

logger = logging.getLogger(__name__)


class GitHubReporter:
    """Manages GitHub issue lifecycle for review failures."""

    def __init__(self, repo: str, labels: list[str]):
        self.repo = repo
        self.labels = labels
        self._gh_available: Optional[bool] = None

    def _check_gh(self) -> bool:
        """Check if gh CLI is available."""
        if self._gh_available is None:
            self._gh_available = shutil.which("gh") is not None
            if not self._gh_available:
                logger.warning(
                    "gh CLI not found — GitHub issue reporting disabled. "
                    "Install from https://cli.github.com/"
                )
        return self._gh_available

    async def report(
        self,
        review_report: ReviewReport,
        project_name: str,
    ) -> list[str]:
        """File/update/close issues based on review results.

        Returns:
            List of issue URLs created/updated/closed.
        """
        if not self._check_gh():
            return []

        urls: list[str] = []

        # Group failures by act
        failures_by_act: dict[str, list[ScreenshotReview]] = defaultdict(list)
        passing_acts: set[str] = set()

        for review in review_report.reviews:
            if review.overall_status in ("fail", "warning"):
                failures_by_act[review.act].append(review)
            else:
                passing_acts.add(review.act)

        # File or update issues for failing acts
        for act, failures in failures_by_act.items():
            url = await self.file_or_update_issue(
                act, failures, review_report.iteration, project_name
            )
            if url:
                urls.append(url)

        # Close issues for acts that now pass
        closed = await self.close_fixed_issues(
            list(passing_acts), review_report.iteration
        )
        urls.extend(closed)

        return urls

    async def file_or_update_issue(
        self,
        act: str,
        failures: list[ScreenshotReview],
        iteration: int,
        project_name: str,
    ) -> str:
        """Create or update issue for an act's failures."""
        title_prefix = f"[kestrel-eye] {act}"
        existing = await self._find_issue(title_prefix)

        body = self._format_issue_body(
            act, failures, iteration, project_name
        )

        if existing:
            # Add comment to existing issue
            comment = (
                f"**Iteration {iteration} update:**\n\n"
                f"{len(failures)} screenshot(s) still failing in {act}."
            )
            await self._run_gh(
                "issue", "comment", str(existing), "--body", comment,
                "--repo", self.repo,
            )
            return f"https://github.com/{self.repo}/issues/{existing} (updated)"

        # Create new issue
        title = f"{title_prefix} — {len(failures)} screenshot failures"
        label_args = []
        for label in self.labels:
            label_args.extend(["--label", label])

        result = await self._run_gh(
            "issue", "create",
            "--repo", self.repo,
            "--title", title,
            "--body", body,
            *label_args,
        )
        return result.strip() if result else ""

    async def close_fixed_issues(
        self,
        passing_acts: list[str],
        iteration: int,
    ) -> list[str]:
        """Close issues for acts that now pass."""
        closed: list[str] = []

        for act in passing_acts:
            title_prefix = f"[kestrel-eye] {act}"
            existing = await self._find_issue(title_prefix)
            if existing:
                comment = (
                    f"Fixed in iteration {iteration}. "
                    "All screenshots in this act now pass."
                )
                await self._run_gh(
                    "issue", "close", str(existing),
                    "--repo", self.repo,
                    "--comment", comment,
                )
                closed.append(
                    f"https://github.com/{self.repo}/issues/{existing} (closed)"
                )

        return closed

    async def _find_issue(self, title_prefix: str) -> Optional[int]:
        """Search for an existing open issue by title prefix."""
        result = await self._run_gh(
            "issue", "list",
            "--repo", self.repo,
            "--state", "open",
            "--search", f'"{title_prefix}" in:title',
            "--json", "number,title",
            "--limit", "5",
        )
        if not result:
            return None

        try:
            issues = json.loads(result)
            for issue in issues:
                if issue["title"].startswith(title_prefix):
                    return issue["number"]
        except (json.JSONDecodeError, KeyError):
            pass

        return None

    async def _run_gh(self, *args: str) -> str:
        """Run a gh CLI command and return stdout."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                logger.warning("gh %s failed: %s", args[0], stderr.decode()[:200])
                return ""
            return stdout.decode()
        except Exception as e:
            logger.warning("Failed to run gh: %s", e)
            return ""

    def _format_issue_body(
        self,
        act: str,
        failures: list[ScreenshotReview],
        iteration: int,
        project_name: str,
    ) -> str:
        """Format the issue body markdown."""
        lines = [
            "## kestrel-eye Visual Review Failure",
            "",
            f"**Project:** {project_name}",
            f"**Iteration:** {iteration}",
            "",
            "### Failing Screenshots",
            "",
        ]

        for review in failures:
            status_icon = "❌" if review.overall_status == "fail" else "⚠️"
            lines.append(f"#### {status_icon} {review.screenshot_name}")
            for finding in review.findings:
                if finding.status in ("fail", "warning"):
                    lines.append(
                        f"- {finding.description} (confidence: {finding.confidence:.2f})"
                    )
            lines.append("")

        lines.extend([
            "### How to Fix",
            "",
            "Run `kestrel-eye run --loop` to start the review loop, "
            "or let kestrel-talon handle it:",
            "```bash",
            f"kestrel-talon claim --repo {self.repo} --issue <this_issue_number>",
            "```",
        ])

        return "\n".join(lines)
