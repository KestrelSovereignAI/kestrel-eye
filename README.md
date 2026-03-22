# kestrel-eye

Vision-verified E2E feedback loop — cheap AI reviews your screenshots until they're perfect.

Part of the [kestrel-talon](https://github.com/KestrelSovereignAI/kestrel-talon) agentic coding ecosystem.

## Install

```bash
pip install kestrel-eye
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
```

## kestrel-talon Integration

Add to `.kestreltalon/quality.yaml`:

```yaml
checks:
  - kestrel-eye run
```

That's it. talon handles the retry loop.
