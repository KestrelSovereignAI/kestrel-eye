"""OpenAI vision provider using response_format for structured output."""

import json
import logging
import os
from pathlib import Path

import openai

from kestrel_eye.models import ScreenshotReview
from kestrel_eye.providers.base import (
    SYSTEM_PROMPT,
    VisionProvider,
    build_user_prompt,
    encode_image,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(VisionProvider):
    """Review screenshots using OpenAI vision models."""

    def __init__(self, model: str = "gpt-4o-mini"):
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required.\n"
                "Set it with: export OPENAI_API_KEY=sk-..."
            )
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def review_screenshot(
        self,
        image_path: Path,
        screenshot_name: str,
        act: str,
        expected_elements: list[str],
        layout_description: str,
    ) -> ScreenshotReview:
        """Send screenshot to OpenAI for structured review."""
        b64_data, mime_type = encode_image(image_path)
        user_prompt = build_user_prompt(
            screenshot_name, act, expected_elements, layout_description
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_data}",
                            "detail": "low",
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            },
        ]

        max_retries = 2
        last_error = None

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=1024,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ScreenshotReview",
                            "schema": ScreenshotReview.model_json_schema(),
                            "strict": False,
                        },
                    },
                )

                content = response.choices[0].message.content
                if content:
                    data = json.loads(content)
                    return ScreenshotReview.model_validate(data)

                last_error = "Empty response content"
                logger.warning(
                    "Attempt %d: %s, retrying...", attempt + 1, last_error
                )

            except (openai.APIError, openai.APIConnectionError) as e:
                last_error = str(e)
                logger.warning("Attempt %d API error: %s", attempt + 1, e)
                if attempt == max_retries - 1:
                    raise

            except (json.JSONDecodeError, Exception) as e:
                last_error = str(e)
                logger.warning(
                    "Attempt %d parse error: %s", attempt + 1, e
                )

        raise RuntimeError(
            f"Failed to get structured review after {max_retries} attempts: {last_error}"
        )
