"""Tests for config loading and validation."""

import pytest
from pathlib import Path

from kestrel_eye.config import (
    EyeConfig,
    GitHubConfig,
    ModelConfig,
    ScreenshotExpectation,
    load_config,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_load_valid_config():
    """Valid eye.toml loads correctly."""
    config = load_config(FIXTURES / "sample_eye.toml")
    assert config.name == "Test Project"
    assert config.screenshot_dir == "tests/fixtures"
    assert config.test_cmd == "echo 'test screenshots ready'"
    assert config.model.provider == "anthropic"
    assert config.model.model == "claude-haiku-4-5-20251001"
    assert config.github is not None
    assert config.github.repo == "KestrelSovereignAI/kestrel-eye"
    assert len(config.screenshots) == 1
    assert config.screenshots[0].name == "sample_screenshot.png"
    assert config.screenshots[0].act == "Act 1: Identity"
    assert config.screenshots[0].severity == "critical"
    assert len(config.screenshots[0].expected) == 3


def test_load_missing_config():
    """Missing eye.toml raises FileNotFoundError with helpful message."""
    with pytest.raises(FileNotFoundError, match="kestrel-eye init"):
        load_config(Path("nonexistent.toml"))


def test_screenshot_expectation_defaults():
    """ScreenshotExpectation has sensible defaults."""
    exp = ScreenshotExpectation(
        name="test.png",
        act="Act 1",
        expected=["element"],
        layout="simple layout",
    )
    assert exp.severity == "critical"


def test_model_config_defaults():
    """ModelConfig has sensible defaults."""
    mc = ModelConfig()
    assert mc.provider == "anthropic"
    assert mc.model == "claude-haiku-4-5-20251001"


def test_eye_config_empty_screenshots():
    """Empty screenshots list is valid (for kestrel-eye init)."""
    config = EyeConfig(
        name="Test",
        screenshot_dir="./screenshots",
        screenshots=[],
    )
    assert len(config.screenshots) == 0


def test_eye_config_empty_screenshot_dir():
    """Empty screenshot_dir raises validation error."""
    with pytest.raises(Exception):
        EyeConfig(
            name="Test",
            screenshot_dir="",
        )


def test_github_config_default_labels():
    """GitHubConfig has default labels."""
    gh = GitHubConfig(repo="owner/repo")
    assert "kestrel-eye" in gh.labels
    assert "automated" in gh.labels


def test_model_config_invalid_provider():
    """Invalid provider raises validation error."""
    with pytest.raises(Exception):
        ModelConfig(provider="invalid", model="test")
