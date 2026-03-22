"""Load and validate eye.toml configuration."""

import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, field_validator

if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[no-redefine]


class ScreenshotExpectation(BaseModel):
    """Expected content for a single screenshot."""

    name: str
    act: str
    severity: Literal["critical", "warning"] = "critical"
    expected: list[str]
    layout: str


class ModelConfig(BaseModel):
    """Vision model configuration."""

    provider: Literal["anthropic", "openai"] = "anthropic"
    model: str = "claude-haiku-4-5-20251001"


class GitHubConfig(BaseModel):
    """GitHub issue reporter configuration."""

    repo: str
    labels: list[str] = ["kestrel-eye", "automated"]


class EyeConfig(BaseModel):
    """Root configuration loaded from eye.toml."""

    name: str
    screenshot_dir: str
    test_cmd: str = ""
    model: ModelConfig = ModelConfig()
    github: Optional[GitHubConfig] = None
    screenshots: list[ScreenshotExpectation] = []

    @field_validator("screenshot_dir")
    @classmethod
    def validate_screenshot_dir(cls, v: str) -> str:
        if not v:
            raise ValueError("screenshot_dir must not be empty")
        return v


def load_config(path: Path = Path("eye.toml")) -> EyeConfig:
    """Load and validate eye.toml.

    Args:
        path: Path to eye.toml file.

    Returns:
        Validated EyeConfig.

    Raises:
        FileNotFoundError: If eye.toml doesn't exist.
        ValueError: If config is invalid.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            "Run 'kestrel-eye init' to create one."
        )

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    eye = raw.get("eye", {})
    if not eye:
        raise ValueError("eye.toml must have an [eye] section")

    screenshots = eye.pop("screenshots", [])

    return EyeConfig(
        name=eye.get("name", ""),
        screenshot_dir=eye.get("screenshot_dir", ""),
        test_cmd=eye.get("test_cmd", ""),
        model=ModelConfig(**eye.get("model", {})),
        github=GitHubConfig(**eye["github"]) if "github" in eye else None,
        screenshots=[ScreenshotExpectation(**s) for s in screenshots],
    )
