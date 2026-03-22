"""CLI entry point for kestrel-eye."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from kestrel_eye import __version__
from kestrel_eye.config import EyeConfig, load_config
from kestrel_eye.models import ReviewReport
from kestrel_eye.providers.base import VisionProvider
from kestrel_eye.report import format_failure_summary, print_iteration_summary
from kestrel_eye.reporter import GitHubReporter
from kestrel_eye.runner import EyeRunner, RunnerConfig


def create_provider(config: EyeConfig, model_override: str = "") -> VisionProvider:
    """Create the appropriate vision provider from config."""
    provider_name = config.model.provider
    model = model_override or config.model.model

    if provider_name == "anthropic":
        from kestrel_eye.providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model)
    elif provider_name == "openai":
        from kestrel_eye.providers.openai import OpenAIProvider
        return OpenAIProvider(model=model)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


def cmd_run(args: argparse.Namespace) -> int:
    """Execute run command."""
    config = load_config(Path(args.config))
    provider = create_provider(config, args.model or "")

    runner_config = RunnerConfig(
        eye_config=config,
        max_iterations=args.max_iterations,
        interactive=args.loop,
        file_issues=args.file_issues,
    )
    runner = EyeRunner(runner_config, provider)

    if args.loop:
        report = asyncio.run(runner.run_loop())
    else:
        report = asyncio.run(runner.run_once())

    exit_code = runner.get_exit_code(report)

    if exit_code == 1:
        report_path = str(Path(config.screenshot_dir) / "review.md")
        print(format_failure_summary(report, report_path), file=sys.stderr)

    if args.file_issues and config.github and exit_code != 0:
        reporter = GitHubReporter(config.github.repo, config.github.labels)
        asyncio.run(reporter.report(report, config.name))

    return exit_code


def cmd_review(args: argparse.Namespace) -> int:
    """Execute review command (skip test execution)."""
    config = load_config(Path(args.config))

    if args.screenshot_dir:
        config.screenshot_dir = args.screenshot_dir

    provider = create_provider(config, args.model or "")
    runner_config = RunnerConfig(eye_config=config)
    runner = EyeRunner(runner_config, provider)

    report = asyncio.run(runner.run_review_only())
    print_iteration_summary(report)

    exit_code = runner.get_exit_code(report)
    if exit_code == 1:
        report_path = str(Path(config.screenshot_dir) / "review.md")
        print(format_failure_summary(report, report_path), file=sys.stderr)

    return exit_code


def cmd_init(args: argparse.Namespace) -> int:
    """Generate a starter eye.toml."""
    path = Path("eye.toml")
    if path.exists():
        print(f"eye.toml already exists at {path.absolute()}", file=sys.stderr)
        return 1

    template = """\
[eye]
name = "My Project"
screenshot_dir = "screenshots"
test_cmd = "npx playwright test"

[eye.model]
provider = "anthropic"
model = "claude-haiku-4-5-20251001"

# [eye.github]
# repo = "owner/repo"
# labels = ["kestrel-eye", "automated"]

# Add screenshot expectations:
# [[eye.screenshots]]
# name = "01-homepage.png"
# act = "Homepage"
# severity = "critical"
# expected = ["Logo visible", "Navigation bar", "Hero section"]
# layout = "Standard landing page with nav at top"
"""
    path.write_text(template)
    print(f"Created {path.absolute()}")
    print("Edit eye.toml to add your screenshot expectations.")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate eye.toml and check screenshots exist."""
    try:
        config = load_config(Path(args.config))
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    screenshot_dir = Path(config.screenshot_dir)
    errors: list[str] = []

    if not screenshot_dir.exists():
        errors.append(f"screenshot_dir does not exist: {screenshot_dir}")

    if not config.screenshots:
        errors.append("No screenshot expectations defined in eye.toml")

    missing = []
    for s in config.screenshots:
        path = screenshot_dir / s.name
        if not path.exists():
            missing.append(s.name)

    if missing:
        errors.append(
            f"{len(missing)} screenshot(s) not found: {', '.join(missing[:5])}"
            + (f" (and {len(missing) - 5} more)" if len(missing) > 5 else "")
        )

    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        f"eye.toml valid: {config.name} — "
        f"{len(config.screenshots)} screenshots, "
        f"provider={config.model.provider}, "
        f"model={config.model.model}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="kestrel-eye",
        description="Vision-verified E2E feedback loop",
    )
    parser.add_argument(
        "--version", action="version", version=f"kestrel-eye {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run
    run_parser = subparsers.add_parser(
        "run", help="Run tests + review screenshots"
    )
    run_parser.add_argument(
        "--loop", action="store_true",
        help="Interactive loop: repeat until all pass",
    )
    run_parser.add_argument(
        "--max-iterations", type=int, default=10,
        help="Max iterations in loop mode (default: 10)",
    )
    run_parser.add_argument(
        "--file-issues", action="store_true",
        help="Create/update/close GitHub issues for failures",
    )
    run_parser.add_argument("--model", help="Override vision model")
    run_parser.add_argument(
        "--config", default="eye.toml", help="Path to config (default: eye.toml)"
    )

    # review
    review_parser = subparsers.add_parser(
        "review", help="Review existing screenshots (skip test execution)"
    )
    review_parser.add_argument(
        "--screenshot-dir", help="Override screenshot directory"
    )
    review_parser.add_argument("--model", help="Override vision model")
    review_parser.add_argument(
        "--config", default="eye.toml", help="Path to config (default: eye.toml)"
    )

    # init
    subparsers.add_parser("init", help="Generate starter eye.toml")

    # validate
    validate_parser = subparsers.add_parser(
        "validate", help="Validate eye.toml and check screenshots exist"
    )
    validate_parser.add_argument(
        "--config", default="eye.toml", help="Path to config (default: eye.toml)"
    )

    return parser


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    commands = {
        "run": cmd_run,
        "review": cmd_review,
        "init": cmd_init,
        "validate": cmd_validate,
    }

    handler = commands.get(args.command)
    if handler:
        try:
            sys.exit(handler(args))
        except KeyboardInterrupt:
            print("\nInterrupted.", file=sys.stderr)
            sys.exit(130)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
