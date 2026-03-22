"""Base interface for vision providers."""

import base64
import logging
from abc import ABC, abstractmethod
from pathlib import Path

from kestrel_eye.models import ScreenshotReview

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an expert UI/UX quality reviewer. You are reviewing screenshots from an \
automated E2E test run.

For each screenshot, you will be told:
- What elements SHOULD be visible
- What the layout SHOULD look like

Your job is to examine the screenshot carefully and report:
- Whether each expected element is actually present and visible
- The overall layout quality and readability
- Any issues that would look bad to a viewer

Be precise and specific. If something is partially visible or cut off, mark it as \
"warning" not "pass". If you cannot determine whether an element is present, mark \
it as "unclear" with a description of what you see instead.

Rate readability 1-5 where:
  5 = everything crisp, readable, well-composed
  4 = minor issues, generally good
  3 = some elements hard to read or awkwardly positioned
  2 = significant readability or layout problems
  1 = major issues, unusable or broken appearance\
"""


def build_user_prompt(
    screenshot_name: str,
    act: str,
    expected_elements: list[str],
    layout_description: str,
) -> str:
    """Build the user prompt for a screenshot review."""
    elements_list = "\n".join(f"- {e}" for e in expected_elements)
    return (
        f"Review this screenshot: {screenshot_name}\n"
        f"Part of: {act}\n\n"
        f"Expected elements (check each one):\n{elements_list}\n\n"
        f"Expected layout:\n{layout_description}\n\n"
        "Examine the screenshot carefully and report your findings for each expected element."
    )


def encode_image(image_path: Path) -> tuple[str, str]:
    """Read an image file and return (base64_data, mime_type).

    Args:
        image_path: Path to the image file.

    Returns:
        Tuple of (base64-encoded data, MIME type).

    Raises:
        FileNotFoundError: If image doesn't exist.
    """
    if not image_path.exists():
        raise FileNotFoundError(f"Screenshot not found: {image_path}")

    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")

    suffix = image_path.suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    mime_type = mime_types.get(suffix, "image/png")

    return b64, mime_type


class VisionProvider(ABC):
    """Base class for vision model providers."""

    @abstractmethod
    async def review_screenshot(
        self,
        image_path: Path,
        screenshot_name: str,
        act: str,
        expected_elements: list[str],
        layout_description: str,
    ) -> ScreenshotReview:
        """Send screenshot + expectations to vision model, get structured review.

        Args:
            image_path: Path to the screenshot PNG.
            screenshot_name: Filename for the report.
            act: Logical grouping (e.g. 'Act 1: Cryptographic Identity').
            expected_elements: List of things that should be visible.
            layout_description: Description of expected layout.

        Returns:
            Structured review of the screenshot.
        """
