# BY BOTS

Facebook group and page monitor that forwards new posts to Discord with keyword routing, live stream detection, author filtering, and a web dashboard.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Features](#features)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Discord Commands](#discord-commands)
- [Web Dashboard](#web-dashboard)
- [Analytics](#analytics)
- [Docker Deployment](#docker-deployment)
- [Railway.app Deployment](#railwayapp-deployment)
- [Operations](#operations)
- [Testing](#testing)
- [Changelog](#changelog)
- [Roadmap](#roadmap)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [License](#license)

## Overview

BY BOTS scrapes configured Facebook sources with Playwright (no Facebook API required), deduplicates posts in SQLite, and publishes rich Discord embeds. It supports multi-channel keyword routing, live stream detection, optional author whitelists, image galleries, engagement metrics, auto-restart, and a local web dashboard.

| Item | Value |
|------|-------|
| Runtime | Python 3.11+ |
| Discord library | discord.py 2.3.2 |
| Scheduler | APScheduler 3.10.4 |
| Scraper | Playwright (Chromium) |
| Database | SQLite |
| Dashboard | Flask 3.0.0 |
| Default scan interval | 300 seconds (5 minutes) |

## Project Structure

```
BY-BOTS/
├── src/                          # Main application source code
│   ├── bot.py                    # Core Discord bot and scheduler
│   ├── config.py                 # Configuration loader (reads .env)
│   ├── dashboard.py              # Flask web dashboard
│   ├── gui.py                    # Windows GUI launcher
│   ├── modules/                  # Supporting modules
│   │   ├── database.py           # SQLite database operations
│   │   ├── discord_embed.py      # Embed builder for Discord
│   │   ├── facebook_monitor.py   # Playwright scraper for Facebook
│   │   └── webhook_sender.py     # HTTP webhook delivery
│   ├── templates/                # HTML templates for dashboard
│   └── cookies/                  # Persistent Facebook session cookies
│
├── config/                       # Configuration and deployment files
│   ├── Dockerfile                # Docker image definition
│   ├── docker-compose.yml        # Multi-container setup
│   ├── .env.example              # Template for environment variables
│   └── pytest.ini                # Pytest configuration
│
├── docs/                         # Deployment and setup guides
│   └── DEPLOYMENT_GUIDES.md      # Railway, Oracle, and local setup
│
├── tests/                        # Test suite
│   ├── conftest.py               # Pytest fixtures
│   ├── test_bot.py               # Bot tests
│   ├── test_config.py            # Configuration tests
│   ├── test_facebook_monitor.py  # Scraper tests
│   └── test_webhook_sender.py    # Webhook tests
│
├── logs/                         # Application logs (created at runtime)
├── .env                          # Environment variables (do not commit)
├── .env.example                  # Environment template
├── requirements.txt              # Python dependencies
├── run.bat                       # Windows launcher with menu
├── README.md                     # This file
└── database.db                   # SQLite database (created at runtime)
```

## Features

### Monitoring

- Multi-source Facebook monitoring (groups and pages)
- Playwright-based scraping without Facebook API credentials
- Cookie persistence to reduce Facebook login walls across restarts
- Optional HTTP/SOCKS proxy and rotating user-agent pool for scraper resilience
- Duplicate prevention via SQLite
- Configurable scan interval
- First-run seed mode to avoid backlog spam

### Discord Integration

- Rich embeds with images, timestamps, and metadata
- Keyword-based routing to multiple channels
- Optional role pings
- Fallback routing when a target channel is unavailable
- Live stream detection with dedicated channel routing
- Image gallery support (multiple images per post)
- Reaction, comment, and share counts in embed footer
- Configurable embed colors per route keyword
- Optional HTTP webhook delivery for external integrations (alongside or instead of Discord posting)
- Periodic security reminder broadcasts with customizable interval

### Management

- Slash commands: /ping, /status, /testembed, /recent, /forcecheck
- Windows GUI launcher (run.bat)
- Web dashboard (dashboard.py)
- Interactive menu system with bot control options

## Quick Start

### Requirements

- Python 3.11+
- Discord bot token with Send Messages and Embed Links permissions
- Playwright Chromium (installed during setup)

### Installation

```bash
cd BY-BOTS
cp config/.env.example .env
pip install -r requirements.txt
playwright install chromium
```

Minimum .env values:

```env
DISCORD_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
DISCORD_GUILD_ID=your_server_id_here
FACEBOOK_SOURCES=https://www.facebook.com/groups/your_group
```

### Run Options

| Method | Command | Use case |
|--------|---------|----------|
| First-time setup | run.bat install | Install dependencies and Playwright |
| GUI (Windows) | run.bat gui | Interactive launcher with menu |
| Web dashboard | run.bat dashboard | Browser UI at http://127.0.0.1:5000 |
| Bot only | run.bat bot | Basic run in background window |
| Bot + Dashboard | run.bat all | Start both services together |
| Kill processes | run.bat kill | Stop all running bot processes |
| Test reminder | run.bat test_reminder | Test security reminder settings |
| Help | run.bat help | Show available commands |

Note: On Python 3.13 or newer, run.bat install installs audioop-lts automatically (required by discord.py).

## Configuration

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | Required | Discord bot token |
| `DISCORD_CHANNEL_ID` | Required | Default fallback text channel ID |
| `DISCORD_GUILD_ID` | Optional | Guild ID for instant slash command sync |
| `FACEBOOK_SOURCES` | Required | Comma-separated Facebook URLs |
| `CHECK_INTERVAL` | `300` | Seconds between scans |
| `SEED_ON_FIRST_RUN` | `true` | Record existing posts without forwarding on first run |
| `DATABASE_PATH` | `database.db` | SQLite database path |

### Advanced Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_PING_ROLE_ID` | — | Role to ping on new posts |
| `DISCORD_STREAMER_CHANNEL_ID` | — | Channel for live stream posts |
| `DISCORD_SECURITY_CHANNEL_ID` | — | Channel for periodic security reminders and warnings |
| `SECURITY_REMINDER_ENABLED` | `false` | Enable periodic security reminder broadcasts |
| `SECURITY_REMINDER_INTERVAL` | `300` | Seconds between security reminder messages |
| `SECURITY_REMINDER_PING_EVERYONE` | `false` | Ping `@everyone` when reminders are sent |
| `FILTER_BY_AUTHOR` | `false` | Enable author whitelist |
| `ALLOWED_AUTHORS` | — | Comma-separated author names (exact match) |
| `DISCORD_ROUTE_<keyword>` | — | Route posts containing keyword to channel ID |
| `DISCORD_ROUTE_COLOR_<keyword>` | — | Custom embed color (hex or integer) |
| `DASHBOARD_HOST` | `127.0.0.1` | Dashboard bind address |
| `DASHBOARD_PORT` | `5000` | Dashboard port |
| `DASHBOARD_SECRET_KEY` | — | Flask session secret |

### Scraper Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `SCRAPER_PROXY` | — | HTTP/SOCKS proxy URL for Playwright (e.g. `http://127.0.0.1:8080`) |
| `SCRAPER_PROXY_USERNAME` | — | Proxy username (optional) |
| `SCRAPER_PROXY_PASSWORD` | — | Proxy password (optional) |
| `FACEBOOK_COOKIES_ENABLED` | `true` | Save/load Facebook session cookies between runs |
| `FACEBOOK_COOKIES_PATH` | `cookies/facebook_cookies.json` | Path to the persisted cookie file |
| `SCRAPER_ROTATE_USER_AGENT` | `true` | Pick a random user-agent on each browser launch |
| `SCRAPER_USER_AGENTS` | — | Pipe-separated custom user-agent pool (overrides built-in list) |

Cookies are written after each successful scrape. Delete the cookie file (or call `clear_cookies()` from `facebook_monitor`) if Facebook sessions become stale.

### Webhook Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_URLS` | — | Comma-separated HTTP endpoint URLs |
| `WEBHOOK_ENABLED` | `true` when URLs are set | Send JSON payloads for new posts |
| `WEBHOOK_ONLY` | `false` | Skip Discord channel posting; deliver via webhooks only |
| `WEBHOOK_TIMEOUT` | `30` | HTTP request timeout in seconds |

Webhook payload shape (one POST per new post, per endpoint):

```json
{
  "event_type": "new_facebook_post",
  "source": "BY-BOTS",
  "post_id": "1234567890",
  "author": "Page Name",
  "content": "Post body text",
  "post_url": "https://www.facebook.com/...",
  "timestamp": "2 hrs",
  "image_url": "https://...",
  "image_urls": ["https://..."],
  "is_live_stream": false,
  "streamer_name": null,
  "reaction_count": 42,
  "comment_count": 3,
  "share_count": 1
}
```

### Routing Example

```env
DISCORD_CHANNEL_ID=1514161755700334655
DISCORD_ROUTE_maintenance_alert=1514161795651338402
DISCORD_ROUTE_event=1514161881768788079
DISCORD_ROUTE_patch_notes=1514162058374021170
DISCORD_ROUTE_COLOR_maintenance_alert=#FF0000
DISCORD_ROUTE_COLOR_event=#00FF00
DISCORD_ROUTE_COLOR_patch_notes=#3B88C3
DISCORD_STREAMER_CHANNEL_ID=1514162887168626828
```

Underscores in route variable names become spaces in keywords (`maintenance_alert` matches `maintenance alert`).

## Discord Commands

| Command | Description |
|---------|-------------|
| `/ping` | Connection check and latency |
| `/status` | Bot health, last scan, post count, filter info |
| `/testembed` | Preview sample post embed |
| `/recent` | Last 5 stored posts |
| `/forcecheck` | Manual Facebook scan with result metrics |

`/forcecheck` returns counts for scraped, forwarded, seeded, filtered, and skipped posts.

## Web Dashboard

Launch with `python dashboard.py` and open http://127.0.0.1:5000.

| Page | Purpose |
|------|---------|
| Dashboard | Bot control, quick stats, recent posts |
| Configuration | Edit `.env` settings through a web form |
| Logs | Live log viewer with auto-refresh |
| Statistics | Full analytics and charts |

Dashboard controls read the bot PID from `.bybots.lock` and verify the process is alive before reporting status.

## Analytics

The Statistics page and `/api/stats` endpoint expose numeric metrics from the SQLite database.

| Metric | Description |
|--------|-------------|
| `total_posts` | All posts stored in the database |
| `unique_authors` | Count of distinct Facebook authors |
| `posts_today` | Posts stored today (UTC) |
| `posts_7d` | Posts stored in the last 7 days |
| `posts_30d` | Posts stored in the last 30 days |
| `avg_posts_per_day` | Total posts divided by tracking period length |
| `posts_by_day` | Daily post counts for the last 30 days |
| `author_counts` | Per-author post totals and share percentage |
| `last_scan` | Timestamp of the most recent Facebook scan |
| `configured_sources` | Number of Facebook URLs in `FACEBOOK_SOURCES` |
| `recent_posts` | Last 10 posts with author, timestamps, and links |

Example API response shape:

```json
{
  "total_posts": 142,
  "unique_authors": 8,
  "posts_today": 3,
  "posts_7d": 24,
  "posts_30d": 98,
  "avg_posts_per_day": 4.7,
  "posts_by_day": [{"date": "2026-06-23", "count": 3}],
  "author_counts": [{"author": "Admin", "count": 45}],
  "last_scan": "2026-06-23 12:00:00 UTC",
  "configured_sources": 2
}
```

## Docker Deployment

### Files

| File | Purpose |
|------|---------|
| config/Dockerfile | Python 3.11 image with Playwright Chromium |
| config/docker-compose.yml | Multi-container setup with bot and optional dashboard |
| config/.env.example | Template for environment variables |

### Quick Start

```bash
mkdir -p data logs
cp config/.env.example .env
# Edit .env with your tokens and channel IDs

docker compose -f config/docker-compose.yml up -d --build
```

Bot data is stored in ./data/database.db. Logs are written to ./logs/.

### Optional Dashboard Service

```bash
docker compose -f config/docker-compose.yml --profile dashboard up -d --build
```

The dashboard is exposed on port 5000 (override with DASHBOARD_PORT in .env).

### Health Check

The bot container health check verifies .bybots.lock exists, indicating the bot process is running.

## Railway.app Deployment

Deploy your bot to Railway.app for 24/7 hosting at no cost (with free credits).

### Prerequisites

- GitHub account (push code to repository)
- Railway.app account (sign up with GitHub)
- Discord bot token and channel IDs configured

### Deployment Steps

1. Push code to GitHub repository
2. Sign up at Railway.app with GitHub account
3. Create new project from GitHub repo
4. Add environment variables (from .env file)
5. Railway automatically builds and deploys
6. Deployment completes in 2-5 minutes

### Configuration on Railway

1. Go to project Variables tab
2. Add all variables from your .env file:
   - DISCORD_TOKEN
   - DISCORD_CHANNEL_ID
   - FACEBOOK_SOURCES
   - Security reminder settings
   - All other configuration variables

3. Railway auto-redeploys when you push to GitHub

### Monitoring

- Dashboard shows deployment status (Building/Running/Failed)
- View real-time logs in Console tab
- Bot appears online in Discord when deployment succeeds
- Check CPU, Memory, and Network metrics

### Costs

Railway provides 5 USD/month free credits. Most Discord bots use less than this, keeping hosting free. Spending limits can be configured to prevent overages.

For detailed setup instructions, see docs/DEPLOYMENT_GUIDES.md

## Operations

Use run.bat as the single launcher for BY BOTS entrypoints:

```bat
run.bat install        # Install Python dependencies and Playwright
run.bat bot            # Run the Discord/Facebook monitor bot
run.bat dashboard      # Run the local web dashboard
run.bat gui            # Run the Windows GUI launcher
run.bat all            # Start both bot and dashboard together
run.bat kill           # Stop all running bot processes
run.bat test_reminder  # Test security reminder configuration
run.bat help           # Show available commands
```

Interactive Menu:

Run run.bat without arguments to open the interactive menu where you can select options 0-8.

Source code is located in src/ directory. Main entrypoints are src/bot.py and src/dashboard.py.

## Testing

Install dev dependencies (included in requirements.txt) and run the test suite from project root:

```bash
pip install -r requirements.txt
pytest --config=config/pytest.ini
```

Or simply:

```bash
pytest
```

Tests are in tests/ directory and cover configuration loading, Facebook scraper helpers, and webhook delivery (with mocked HTTP). They do not launch Playwright or connect to Discord.

## Changelog

### v7.0 — Scraper Resilience, Webhooks, and Tests

- Added Facebook cookie persistence (`FACEBOOK_COOKIES_*`) to reduce login walls
- Added optional scraper proxy and user-agent rotation settings
- Added HTTP webhook delivery as a supplement or alternative to Discord posting
- Added pytest suite under `tests/` for config, scraper helpers, and webhooks

### v6.0 — Docker and Analytics

- Added `Dockerfile`, `docker-compose.yml`, and `.dockerignore`
- Fixed dashboard database queries to match the actual SQLite schema
- Added numeric analytics: daily volume, 7/30-day counts, author breakdown, averages
- Fixed bot status detection using `.bybots.lock` PID with stale lock cleanup
- Revised README to standard GitHub documentation format

### v5.0 — Web Dashboard

- Flask dashboard with configuration editor, bot controls, live logs, and statistics
- REST API for config, logs, stats, and bot management

### v4.0 — Gallery, Metrics, Auto-Restart, Colors

- Multi-image gallery forwarding
- Reaction, comment, and share counts in embeds
- Watchdog and service wrapper for crash recovery
- Per-route embed color configuration

### v3.0 — Filtering and Live Streams

- Author whitelist filtering
- Live stream detection and dedicated channel routing

### v2.0 — Multi-Source and Manual Scan

- Multiple Facebook sources
- `/forcecheck` slash command

## Roadmap

- [x] Streamer live stream forwarding
- [x] Multiple Facebook sources
- [x] Post filtering by author
- [x] Image gallery support
- [x] Reaction/like count in embeds
- [x] Auto-restart on crash
- [x] Configurable embed colors
- [x] Web dashboard
- [x] Docker support
- [x] Cookie persistence for Facebook login walls
- [x] Proxy and rotating user-agents
- [x] Automated testing with pytest
- [x] Webhook support as alternative to bot posting

## Security

- Never commit `.env` (included in `.gitignore`)
- Rotate your Discord token immediately if it was exposed
- Run only one bot instance (`.bybots.lock` enforces single instance)
- Keep the dashboard on localhost unless you add authentication
- Facebook scraping carries ToS risk; use responsibly

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Bot will not start | Check logs/bybots.log, verify DISCORD_TOKEN, run run.bat install |
| No module named 'audioop' | Run run.bat install or pip install audioop-lts (Python 3.13+) |
| .bat files fail immediately | Run run.bat install first; ensure Python is on PATH |
| No posts in Discord | Verify DISCORD_CHANNEL_ID and bot permissions; run /status |
| Dashboard stats empty | Start the bot first; confirm DATABASE_PATH matches between bot and dashboard |
| Stale lock file | Delete .bybots.lock if no bot process is running |
| Docker health check failing | Confirm .env is valid and check docker compose logs |
| Port 5000 in use | Set DASHBOARD_PORT in .env to different port |
| Facebook login wall on every scan | Enable FACEBOOK_COOKIES_ENABLED=true, log in once manually if needed, or delete stale cookies |
| Scraper blocked by IP | Set SCRAPER_PROXY and optionally custom SCRAPER_USER_AGENTS |
| Webhooks not firing | Confirm WEBHOOK_URLS is set and WEBHOOK_ENABLED=true; check logs/bybots.log for HTTP errors |
| Railway deployment failed | Check deployment logs, verify .env variables are set correctly, ensure Dockerfile is not using VOLUME instruction |
| Railway port binding issues | Remove VOLUME instructions from Dockerfile, Railway uses its own volume system |

## License

This project is for educational and personal use. Facebook scraping should comply with Facebook's Terms of Service and applicable laws.

---

Built for the BY RAN ONLINE community.

**Maintainer:** Miguel Pilapil (Beeenek)
**Discord:** [Join BY RAN ONLINE Discord](https://discord.gg/byranofficial)
