"""Unit tests for webhook delivery."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from modules.facebook_monitor import FacebookPost
from modules.webhook_sender import WebhookSender, format_post_for_webhook


def test_format_post_for_webhook_includes_metadata() -> None:
    post = FacebookPost(
        post_id="abc123",
        author="Alice",
        content="Patch notes",
        post_url="https://www.facebook.com/groups/foo/posts/abc123",
        timestamp="2 hrs",
        image_urls=["https://cdn.example/image.jpg"],
    )

    payload = format_post_for_webhook(post)

    assert payload["post_id"] == "abc123"
    assert payload["author"] == "Alice"
    assert payload["event_type"] == "new_facebook_post"
    assert payload["source"] == "BY-BOTS"
    assert payload["image_urls"] == ["https://cdn.example/image.jpg"]


@pytest.mark.asyncio
async def test_send_post_reports_success_and_failure() -> None:
    sender = WebhookSender(
        ["https://hooks.example/ok", "https://hooks.example/fail"],
        timeout=5,
    )

    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_response_ok.raise_for_status = MagicMock()

    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 500
    mock_response_fail.text = "error"
    mock_response_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
        "boom",
        request=MagicMock(),
        response=mock_response_fail,
    )

    mock_client = AsyncMock()
    mock_client.is_closed = False
    mock_client.post = AsyncMock(side_effect=[mock_response_ok, mock_response_fail])

    with patch.object(sender, "_ensure_client", AsyncMock(return_value=mock_client)):
        results = await sender.send_post({"post_id": "1"})

    assert results["https://hooks.example/ok"] is True
    assert results["https://hooks.example/fail"] is False
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_send_post_with_no_urls_returns_empty_dict() -> None:
    sender = WebhookSender([])
    assert await sender.send_post({"post_id": "1"}) == {}
