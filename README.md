# kestrel-eye

Vision-verified E2E feedback loop — cheap AI reviews your screenshots until they're perfect.

Part of the [Kestrel](https://github.com/KestrelSovereignAI) ecosystem:
- **kestrel-talon** — autonomous coding agent (issue → implementation → PR)
- **kestrel-flight** — Playwright demo/test orchestration library
- **kestrel-sovereign** — governance framework (DID identity, constitution, memory)
- **kestrel-claw** — TypeScript agent runtime (OpenClaw fork with sovereign features)

## Install

```bash
pip install kestrel-eye
```

Or for local development:

```bash
uv pip install -e ".[dev]"
```

## Quick Start

```bash
# Generate starter config
kestrel-eye init

# Edit eye.toml with your screenshot expectations

# Run tests + review screenshots
kestrel-eye run

# Interactive loop until all pass
kestrel-eye run --loop

# Review existing screenshots without running tests
kestrel-eye review
```

## Configuration

Each project provides an `eye.toml` mapping screenshots to visual expectations:

```toml
[eye]
name = "my-app"
screenshot_dir = "demo-output"
test_cmd = "npx playwright test --config=demo_config.cjs"

[eye.model]
provider = "anthropic"
model = "claude-haiku-4-5-20251001"

[eye.github]
repo = "owner/my-app"

[[eye.screenshots]]
name = "01-homepage.png"
act = "Act 1: Identity"
severity = "critical"
expected = [
  "Company logo in top-left corner",
  "Navigation bar with Home, About, Contact links",
  "Hero section with welcome message",
]
layout = "Logo top-left, nav bar horizontal across top, hero centered below"
context = "User has just loaded the application for the first time"
```

### Screenshot fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | yes | Filename (e.g. `01-homepage.png`) |
| `act` | yes | Logical grouping for issue filing |
| `severity` | yes | `critical` or `warning` |
| `expected` | yes | List of UI elements that should be visible |
| `layout` | yes | Description of expected spatial arrangement |
| `context` | no | Demo script narration / additional context for the reviewer |

## Vision Providers

kestrel-eye supports three vision model backends:

### Anthropic (default)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
kestrel-eye run
```

Also supports OAuth via `ANTHROPIC_AUTH_TOKEN`.

### OpenAI

```toml
[eye.model]
provider = "openai"
model = "gpt-4o-mini"
```

```bash
export OPENAI_API_KEY=sk-...
kestrel-eye run
```

### Claude Agent SDK (no API key)

If no API key is found, kestrel-eye automatically falls back to the Claude Agent SDK, which uses OAuth from `claude login`. No environment variables needed.

```toml
[eye.model]
provider = "claude_sdk"
model = "claude-haiku-4-5-20251001"
```

## CLI Commands

### `kestrel-eye init`

Generate a starter `eye.toml` template.

### `kestrel-eye validate`

Validate `eye.toml` and check that referenced screenshots exist.

### `kestrel-eye run`

Run tests (via `test_cmd`), review screenshots, generate reports.

| Flag | Default | Description |
|------|---------|-------------|
| `--loop` | off | Interactive loop mode (waits for input between iterations) |
| `--max-iterations` | 10 | Max iterations in loop mode |
| `--file-issues` | off | Create/update/close GitHub issues per act |
| `--model` | from config | Override vision model |

### `kestrel-eye review`

Review existing screenshots without running tests.

| Flag | Default | Description |
|------|---------|-------------|
| `--screenshot-dir` | from config | Override screenshot directory |

## Reports

Each run generates:

- **JSON report** — machine-readable `ReviewReport` for programmatic access
- **Markdown report** — human-readable summary with per-screenshot findings, layout assessments, and iteration diffs
- **Iteration summary** — one-line console output
- **Failure summary** — concise stderr output for talon integration

## GitHub Integration

With `--file-issues`, kestrel-eye manages GitHub issues per act:

- **Creates** issues for failing acts with failure details and fix instructions
- **Updates** existing issues with comments on subsequent iterations
- **Closes** issues when the act passes

Requires the `gh` CLI authenticated.

## kestrel-talon Integration

kestrel-eye runs as a quality gate in kestrel-talon's pipeline:

```yaml
# .kestreltalon/quality.yaml
eye:
  config: "eye-spawn.toml"
  screenshot_cmd: "npx playwright test --config=demo_config.cjs"
```

Or via CLI:

```bash
kestrel-talon claim --repo owner/repo --issue 42 --eye-check --eye-config eye-spawn.toml
```

talon handles the retry loop — kestrel-eye runs as a single-pass quality check. Failures are fed back to the agent for fixing.

## kestrel-flight Compatibility

Screenshot naming from kestrel-flight (`01-name.png`, `02-name.png`) matches kestrel-eye TOML config expectations. Use kestrel-flight's `demoScreenshot()` to produce screenshots, then review them with kestrel-eye.

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All screenshots pass |
| `1` | Failures found (stderr has summary) |
| `2` | Config error or no screenshots found |

## License

MIT
