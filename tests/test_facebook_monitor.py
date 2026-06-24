"""Unit tests for Facebook monitor helper functions."""

from __future__ import annotations

import pytest

from modules.facebook_monitor import (
    FacebookPost,
    _clean_content,
    _detect_live_stream,
    _extract_number_from_text,
    _extract_post_id,
    _pick_user_agent,
)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.facebook.com/groups/foo/posts/1234567890", "1234567890"),
        ("https://www.facebook.com/photo?story_fbid=9876543210", "9876543210"),
        ("https://www.facebook.com/groups/foo/permalink/5555555555555555", "5555555555555555"),
        ("https://www.facebook.com/groups/foo", None),
    ],
)
def test_extract_post_id(url: str, expected: str | None) -> None:
    assert _extract_post_id(url) == expected


@pytest.mark.parametrize(
    "content,expected_live,expected_name",
    [
        ("Alice was live.\nPlaying now", True, "Alice"),
        ("Bob is live", True, "Bob"),
        ("Regular announcement", False, None),
    ],
)
def test_detect_live_stream(
    content: str, expected_live: bool, expected_name: str | None
) -> None:
    is_live, name = _detect_live_stream(content, "Alice")
    assert is_live is expected_live
    assert name == expected_name


@pytest.mark.parametrize(
    "text,expected",
    [
        ("123", 123),
        ("1.2K", 1200),
        ("5.3M", 5300000),
        ("not-a-number", None),
    ],
)
def test_extract_number_from_text(text: str, expected: int | None) -> None:
    assert _extract_number_from_text(text) == expected


def test_clean_content_strips_ui_labels() -> None:
    raw = "Admin\nAlice\n2 hrs\nHello world\nLike\nComment\nShare"
    cleaned = _clean_content(raw, "Alice", "2 hrs")
    assert "Admin" not in cleaned.split("\n")
    assert "Hello world" in cleaned
    assert "Like" not in cleaned


def test_pick_user_agent_uses_configured_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    import config

    monkeypatch.setattr(config, "SCRAPER_USER_AGENTS", ["Custom-Agent/1.0"])
    monkeypatch.setattr(config, "SCRAPER_ROTATE_USER_AGENT", False)
    assert _pick_user_agent() == "Custom-Agent/1.0"


def test_facebook_post_dataclass_defaults() -> None:
    post = FacebookPost(
        post_id="1",
        author="Alice",
        content="Hello",
        post_url="https://example.com",
        timestamp="now",
    )
    assert post.image_urls == []
    assert post.is_live_stream is False
