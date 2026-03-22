"""Integration test — real vision API call with fixture screenshot."""

import os
from pathlib import Path

import pytest

from kestrel_eye.models import ScreenshotReview

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="No ANTHROPIC_API_KEY — skipping live API test",
)
@pytest.mark.asyncio
async def test_review_real_screenshot_anthropic():
    """Send a real screenshot to Haiku and verify structured output."""
    from kestrel_eye.providers.anthropic import AnthropicProvider

    provider = AnthropicProvider(model="claude-haiku-4-5-20251001")
    review = await provider.review_screenshot(
        image_path=FIXTURES / "sample_screenshot.png",
        screenshot_name="01-did-identity.png",
        act="Act 1: Cryptographic Identity",
        expected_elements=[
            "Agent name visible (e.g. 'Kestrel Demo Agent')",
            "DID string starting with did:pkh:eip155:",
            "Identity panel layout with agent info",
        ],
        layout_description="Identity panel with agent name at top, DID below, avatar to the left",
    )

    assert isinstance(review, ScreenshotReview)
    assert review.screenshot_name == "01-did-identity.png"
    assert review.act == "Act 1: Cryptographic Identity"
    assert review.overall_status in ("pass", "fail", "warning")
    assert len(review.findings) > 0
    assert 1 <= review.readability_score <= 5
    assert review.summary

    for finding in review.findings:
        assert finding.status in ("pass", "fail", "warning", "unclear")
        assert 0.0 <= finding.confidence <= 1.0
        assert finding.element
        assert finding.description


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("OPENAI_API_KEY"),
    reason="No OPENAI_API_KEY — skipping live API test",
)
@pytest.mark.asyncio
async def test_review_real_screenshot_openai():
    """Send same screenshot to GPT-4o-mini for provider parity check."""
    from kestrel_eye.providers.openai import OpenAIProvider

    provider = OpenAIProvider(model="gpt-4o-mini")
    review = await provider.review_screenshot(
        image_path=FIXTURES / "sample_screenshot.png",
        screenshot_name="01-did-identity.png",
        act="Act 1: Cryptographic Identity",
        expected_elements=[
            "Agent name visible",
            "DID string starting with did:pkh:",
            "Identity panel layout",
        ],
        layout_description="Identity panel with agent name at top, DID below",
    )

    assert isinstance(review, ScreenshotReview)
    assert len(review.findings) > 0
    assert 1 <= review.readability_score <= 5
