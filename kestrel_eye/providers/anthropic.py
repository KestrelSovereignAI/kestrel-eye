"""Anthropic vision provider using Claude's tool_use for structured output."""

import json
import logging
import os
from pathlib import Path

import anthropic

from kestrel_eye.models import ScreenshotReview
from kestrel_eye.providers.base import (
    SYSTEM_PROMPT,
    VisionProvider,
    build_user_prompt,
    encode_image,
)

logger = logging.getLogger(__name__)

# JSON schema for ScreenshotReview, used as tool input schema
REVIEW_TOOL_SCHEMA = {
    "name": "submit_review",
    "description": "Submit the structured review of the screenshot.",
    "input_schema": ScreenshotReview.model_json_schema(),
}


class AnthropicProvider(VisionProvider):
    """Review screenshots using Anthropic Claude vision models."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not api_key and not auth_token:
            raise RuntimeError(
                "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN required.\n"
                "API key: export ANTHROPIC_API_KEY=sk-ant-...\n"
                "OAuth (Claude Max): export ANTHROPIC_AUTH_TOKEN=..."
            )
        # SDK picks up from env automatically — just don't pass explicit api_key
        # when using auth_token, since they're mutually exclusive
        if auth_token:
            self.client = anthropic.AsyncAnthropic(auth_token=auth_token)
        else:
            self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def review_screenshot(
        self,
        image_path: Path,
        screenshot_name: str,
        act: str,
        expected_elements: list[str],
        layout_description: str,
        context: str = "",
    ) -> ScreenshotReview:
        """Send screenshot to Claude for structured review."""
        b64_data, mime_type = encode_image(image_path)
        user_prompt = build_user_prompt(
            screenshot_name, act, expected_elements, layout_description, context
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64_data,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ]

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    tools=[REVIEW_TOOL_SCHEMA],
                    tool_choice={"type": "tool", "name": "submit_review"},
                )

                # Extract tool_use block
                for block in response.content:
                    if block.type == "tool_use" and block.name == "submit_review":
                        return ScreenshotReview.model_validate(block.input)

                last_error = "No submit_review tool_use block in response"
                logger.warning(
                    "Attempt %d: %s, retrying...", attempt + 1, last_error
                )

            except (anthropic.APIError, anthropic.APIConnectionError) as e:
                last_error = str(e)
                logger.warning("Attempt %d API error: %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    raise

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Attempt %d parse error: %s", attempt + 1, e
                )

        raise RuntimeError(
            f"Failed to get structured review after {max_retries} attempts: {last_error}"
        )
