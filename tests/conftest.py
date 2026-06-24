"""Shared pytest fixtures and environment setup for BY BOTS tests."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Minimal env so config.py can import during tests
os.environ.setdefault("DISCORD_TOKEN", "test-discord-token")
os.environ.setdefault("DISCORD_CHANNEL_ID", "123456789012345678")
os.environ.setdefault("FACEBOOK_SOURCES", "https://www.facebook.com/groups/testgroup")
os.environ.setdefault("WEBHOOK_ENABLED", "false")
os.environ.setdefault("FACEBOOK_COOKIES_ENABLED", "false")
