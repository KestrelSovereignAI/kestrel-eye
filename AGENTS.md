# kestrel-eye — Agent & Developer Guide

> For CLI usage, configuration, and provider setup, see [README.md](README.md).

## Ecosystem

kestrel-eye is part of the [Kestrel](https://github.com/KestrelSovereignAI) ecosystem:

```
kestrel-sovereign (governance framework: DID, constitution, memory)
    ├─ kestrel-talon (autonomous coding agent — issue → PR)
    │   ├─ kestrel-eye (screenshot quality gating via AI vision — this repo)
    │   └─ kestrel-flight (Playwright demo/test orchestration)
    └─ kestrel-claw (TypeScript agent runtime, OpenClaw fork)
```

- **kestrel-talon** — autonomous issue processor that invokes kestrel-eye as a quality gate (`--eye-check`). talon handles the retry loop; kestrel-eye runs as a single-pass check.
- **kestrel-flight** — npm library (`@kestrel/flight`) for narrated Playwright demos. Screenshot naming (`01-name.png`) is eye-compatible.
- **kestrel-sovereign** — governance framework. kestrel-eye has no dependency on it.

## Architecture

```
CLI (cli.py) → EyeRunner (runner.py) → DemoReviewer (reviewer.py) → VisionProvider
                    ↓                        ↓                           ↓
              subprocess (test_cmd)    ScreenshotReview (models.py)   providers/
              Report (report.py)       ReviewReport                   ├─ anthropic.py
              GitHubReporter                                          ├─ openai.py
                (reporter.py)                                         └─ claude_sdk.py
```

### Key modules

| Module | Purpose |
|--------|---------|
| `cli.py` | CLI entry point — `init`, `validate`, `run`, `review` commands |
| `config.py` | TOML config loading and Pydantic validation (`EyeConfig`) |
| `runner.py` | `EyeRunner` — orchestrates test execution, review, reporting, loop |
| `reviewer.py` | `DemoReviewer` — reviews all screenshots via vision provider |
| `models.py` | Pydantic models: `ScreenshotFinding`, `ScreenshotReview`, `ReviewReport`, `GitHubIssueSpec` |
| `report.py` | JSON and Markdown report generation, iteration diff summaries |
| `reporter.py` | `GitHubReporter` — creates/updates/closes GitHub issues per act via `gh` CLI |
| `providers/base.py` | `VisionProvider` ABC — system prompt, image encoding, user prompt builder |
| `providers/anthropic.py` | Anthropic Claude via SDK — structured output via `tool_use` constraint |
| `providers/openai.py` | OpenAI via SDK — structured output via `response_format` JSON schema |
| `providers/claude_sdk.py` | Claude Agent SDK — OAuth auth, no API key needed |

## Key Design Decisions

- **Standalone** — no dependency on kestrel-sovereign or kestrel-talon
- **Direct API calls** — thin wrappers around Anthropic/OpenAI SDKs, no heavy LLM framework
- **eye.toml** — each consuming project provides a TOML config mapping screenshots to expectations
- **Quality gate compatible** — exit codes (0=pass, 1=fail, 2=error) + stderr summary for talon integration
- **Structured output** — all providers return Pydantic-validated `ScreenshotReview` objects, not free text

## Development

### Setup

```bash
uv pip install -e ".[dev]"
```

### Tests

```bash
# Unit tests (no API calls)
uv run pytest tests/unit/

# Integration tests (requires API keys)
uv run pytest tests/integration/ -m integration

# All tests
uv run pytest
```

All unit tests mock the vision providers. Integration tests hit real APIs and are skipped if keys are missing.

### Code style

- Python 3.10+, type hints throughout
- Pydantic v2 for data models and config validation
- Async providers (`async def review_screenshot`)
- `subprocess.run` for test execution and `gh` CLI calls
- No global state — config flows through constructors

## Internals

### Vision provider protocol

All providers inherit from `VisionProvider` (in `providers/base.py`):

1. `SYSTEM_PROMPT` — shared instructions for reviewing UI quality
2. `build_user_prompt()` — formats screenshot name, expected elements, layout, context into a review request
3. `encode_image()` — base64-encodes images with MIME type detection
4. `review_screenshot()` — abstract async method returning `ScreenshotReview`

Providers retry up to 2 times on API errors. The Claude SDK provider falls back to text parsing if structured output is unavailable.

### Provider auto-selection

When `provider = "anthropic"` but no `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` is set, the system upgrades to the `claude_sdk` provider automatically.

### Review data flow

```
eye.toml → EyeConfig → EyeRunner.run_once()
                            ├─ run_tests() → subprocess (test_cmd)
                            ├─ run_review() → DemoReviewer.review_all()
                            │                    └─ review_single() per screenshot
                            │                         └─ provider.review_screenshot()
                            │                              → ScreenshotReview
                            ├─ build ReviewReport (with iteration diff)
                            ├─ write JSON + Markdown reports
                            └─ GitHubReporter (if --file-issues)
```

### Iteration tracking

`compute_iteration_diff()` in `models.py` compares consecutive `ReviewReport` objects, returning (fixed, regressed) screenshot name sets. The runner maintains a history list for multi-iteration runs.

### GitHub issue lifecycle

`GitHubReporter` groups failures by act, then:
- **New failure** → creates issue with title, failure details, labels (`kestrel-eye`, severity)
- **Existing failure** → comments on the issue with updated findings
- **Fixed** → closes the issue

All GitHub operations use `gh` CLI subprocess calls.

## Exit Codes

- `0` — all screenshots pass
- `1` — failures found (stderr has summary)
- `2` — config error or no screenshots found
