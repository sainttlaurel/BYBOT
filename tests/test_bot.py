"""Unit tests for bot scheduled reminder behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import bot as bot_module


@pytest.mark.asyncio
async def test_send_security_reminder_sends_message(monkeypatch) -> None:
    bot_instance = bot_module.ByBotsBot()
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()

    monkeypatch.setattr(bot_module.ByBotsBot, "_resolve_channel", AsyncMock(return_value=mock_channel))
    monkeypatch.setattr(bot_module.config, "DISCORD_SECURITY_CHANNEL_ID", 1514162841899368519)
    monkeypatch.setattr(bot_module.config, "SECURITY_REMINDER_PING_EVERYONE", False)

    await bot_instance.send_security_reminder()

    mock_channel.send.assert_awaited_once()
    sent_args = mock_channel.send.call_args.kwargs
    assert "content" in sent_args
    assert "🚨 SECURITY ALERT 🚨" in sent_args["content"]
    assert "Never share your password." in sent_args["content"]


@pytest.mark.asyncio
async def test_send_security_reminder_skips_when_channel_unavailable(monkeypatch) -> None:
    bot_instance = bot_module.ByBotsBot()
    monkeypatch.setattr(bot_module.ByBotsBot, "_resolve_channel", AsyncMock(return_value=None))
    monkeypatch.setattr(bot_module.config, "DISCORD_SECURITY_CHANNEL_ID", 1514162841899368519)

    await bot_instance.send_security_reminder()

    # If no channel is available, there should be no exception and no send call.
    # _resolve_channel returning None means the method returns without sending.
    assert bot_instance._resolve_channel.await_count == 1
