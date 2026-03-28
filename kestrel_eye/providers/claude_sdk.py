"""Claude Agent SDK vision provider — uses OAuth automatically via claude CLI."""

import json
import logging
from pathlib import Path

from kestrel_eye.models import ScreenshotReview
from kestrel_eye.providers.base import (
    SYSTEM_PROMPT,
    VisionProvider,
    build_user_prompt,
)

logger = logging.getLogger(__name__)


class ClaudeSDKProvider(VisionProvider):
    """Review screenshots using Claude Agent SDK (inherits OAuth from claude CLI)."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001", max_tokens: int = 4096):
        self.model = model
        self.max_tokens = max_tokens

    async def review_screenshot(
        self,
        image_path: Path,
        screenshot_name: str,
        act: str,
        expected_elements: list[str],
        layout_description: str,
        context: str = "",
    ) -> ScreenshotReview:
        """Send screenshot to Claude via Agent SDK for structured review."""
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

        user_prompt = build_user_prompt(
            screenshot_name, act, expected_elements, layout_description, context
        )

        # The Agent SDK wraps the claude CLI which can read files directly.
        # We tell it to read the image and review it, with structured output.
        prompt = (
            f"Review the screenshot at: {image_path.absolute()}\n\n"
            f"{user_prompt}\n\n"
            "Read the image file and review it."
        )

        options = ClaudeAgentOptions(
            model=self.model,
            max_turns=3,
            permission_mode="bypassPermissions",
            system_prompt=SYSTEM_PROMPT,
            output_format={
                "type": "json_schema",
                "schema": ScreenshotReview.model_json_schema(),
            },
        )

        result_message = None
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, ResultMessage):
                result_message = message

        if result_message is None:
            raise RuntimeError("No result from Claude Agent SDK")

        # With output_format, structured_output has the parsed JSON
        if result_message.structured_output is not None:
            if isinstance(result_message.structured_output, dict):
                return ScreenshotReview.model_validate(result_message.structured_output)
            return ScreenshotReview.model_validate_json(
                json.dumps(result_message.structured_output)
            )

        # Fallback: parse from result text
        if result_message.result:
            return ScreenshotReview.model_validate_json(result_message.result)

        raise RuntimeError(
            f"No structured output or result text from Claude Agent SDK. "
            f"Stop reason: {result_message.stop_reason}"
        )
