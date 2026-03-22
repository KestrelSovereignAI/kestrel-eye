# kestrel-eye — Agent Instructions

## Overview

kestrel-eye is a standalone, pip-installable dev tool that reviews UI screenshots using cheap vision models and provides structured feedback in a loop until everything passes.

**Part of the [kestrel-talon](https://github.com/KestrelSovereignAI/kestrel-talon) agentic coding ecosystem.**

## Key Design Decisions

- **Standalone** — no dependency on kestrel-sovereign or kestrel-talon
- **Direct API calls** — thin wrappers around Anthropic/OpenAI SDKs, no heavy LLM framework
- **eye.toml** — each consuming project provides a TOML config mapping screenshots to expectations
- **Quality gate compatible** — exit codes (0=pass, 1=fail, 2=error) + stderr summary for talon integration

## kestrel-talon Integration

kestrel-eye integrates with talon via the quality gate system:

```yaml
# .kestreltalon/quality.yaml
checks:
  - kestrel-eye run
```

talon handles the retry loop — kestrel-eye runs as a single pass quality check.

## Running Tests

```bash
# Unit tests (no API calls)
uv run pytest tests/unit/

# Integration tests (requires API keys)
uv run pytest tests/integration/ -m integration

# All tests
uv run pytest
```

## Exit Codes

- `0` — all screenshots pass
- `1` — failures found (stderr has summary)
- `2` — config error or no screenshots found
