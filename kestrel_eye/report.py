"""Report generation — JSON and Markdown output."""

import json
import sys
from pathlib import Path

from kestrel_eye.models import ReviewReport


def generate_json_report(report: ReviewReport, output_path: Path) -> None:
    """Write ReviewReport as JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report.model_dump_json(indent=2))


def generate_markdown_report(
    report: ReviewReport,
    project_name: str,
    output_path: Path,
) -> None:
    """Write human-readable markdown report."""
    lines = [
        f"# kestrel-eye Review — {project_name}",
        "",
        f"**Iteration:** {report.iteration} | "
        f"**Model:** {report.model_used} | "
        f"**Time:** {report.timestamp}",
        "",
        "## Summary",
        "",
        "| Status | Count |",
        "|--------|-------|",
        f"| Pass | {report.passed} |",
        f"| Fail | {report.failed} |",
        f"| Warning | {report.warnings} |",
        "",
    ]

    if report.fixed_since_last:
        lines.append(
            f"**Fixed this iteration:** {', '.join(report.fixed_since_last)}"
        )
    if report.regressed_since_last:
        lines.append(
            f"**Regressed this iteration:** {', '.join(report.regressed_since_last)}"
        )
    if not report.fixed_since_last and not report.regressed_since_last:
        if report.iteration > 1:
            lines.append("**No changes since last iteration.**")
    lines.append("")

    lines.append("## Screenshots")
    lines.append("")

    for review in report.reviews:
        status_label = review.overall_status.capitalize()
        lines.append(
            f"### {status_label} — {review.screenshot_name} ({review.act})"
        )
        lines.append(f"Readability: {review.readability_score}/5")
        lines.append("")

        if review.overall_status == "pass" and all(
            f.status == "pass" for f in review.findings
        ):
            lines.append("All expected elements present.")
        else:
            for finding in review.findings:
                status_icon = {
                    "pass": "Pass",
                    "fail": "Fail",
                    "warning": "Warning",
                    "unclear": "Unclear",
                }[finding.status]
                lines.append(
                    f"- {status_icon}: {finding.description} "
                    f"[confidence: {finding.confidence:.2f}]"
                )

        if review.layout_assessment:
            lines.append("")
            lines.append(f"> **Layout:** {review.layout_assessment}")

        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))


def print_iteration_summary(report: ReviewReport) -> None:
    """Print concise one-line summary to stdout."""
    parts = [f"[kestrel-eye] Iteration {report.iteration}:"]
    parts.append(
        f"{report.passed}/{report.total_screenshots} pass, {report.failed} fail"
    )
    if report.fixed_since_last:
        parts.append(f"| Fixed: {len(report.fixed_since_last)}")
    if report.regressed_since_last:
        parts.append(f"| Regressed: {len(report.regressed_since_last)}")
    print(" ".join(parts))


def format_failure_summary(report: ReviewReport, report_path: str = "") -> str:
    """Format concise failure summary for stderr (used by CLI for talon).

    This is what talon's quality gate captures and feeds to the agent.
    """
    lines = [
        f"kestrel-eye: {report.passed}/{report.total_screenshots} pass, "
        f"{report.failed} fail, {report.warnings} warning"
    ]

    failures = [r for r in report.reviews if r.overall_status in ("fail", "warning")]
    if failures:
        lines.append("")
        lines.append("FAILURES:")
        for review in failures:
            # Use the first non-pass finding as the one-line description
            desc = review.summary
            for f in review.findings:
                if f.status in ("fail", "warning"):
                    desc = f.description
                    break
            lines.append(f"  {review.screenshot_name} ({review.act}) — {desc}")

    if report_path:
        lines.append("")
        lines.append(f"Full report: {report_path}")

    return "\n".join(lines)
