"""Smoke tests for configuration loading."""

from __future__ import annotations

import config


def test_required_discord_settings_loaded() -> None:
    assert config.DISCORD_TOKEN
    assert config.DISCORD_CHANNEL_ID > 0


def test_facebook_sources_loaded() -> None:
    assert config.FACEBOOK_SOURCES
    assert config.FACEBOOK_SOURCES[0].startswith("https://")


def test_scraper_and_webhook_defaults() -> None:
    assert isinstance(config.FACEBOOK_COOKIES_ENABLED, bool)
    assert isinstance(config.SCRAPER_ROTATE_USER_AGENT, bool)
    assert isinstance(config.WEBHOOK_URLS, list)
    assert isinstance(config.WEBHOOK_TIMEOUT, int)
