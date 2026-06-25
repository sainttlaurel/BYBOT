"""
modules/facebook_monitor.py - Facebook Group scraper for BY BOTS.

Uses Playwright (headless Chromium) to load the public Facebook group page
and extract recent post data without requiring an API key.

Extracted per post:
  - post_id   : unique identifier extracted from the post URL
  - author    : display name of the poster
  - content   : text body of the post
  - post_url  : direct link to the individual post
  - timestamp : human-readable date string shown on the post
  - image_url : URL of the first attached image, or None

Features:
  - Cookie persistence: saves/loads Facebook session cookies to reduce login walls
  - Proxy support: routes traffic through a configured HTTP/SOCKS proxy
  - User-agent rotation: picks a random UA from a pool on each browser launch
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
    TimeoutError as PWTimeoutError,
)

import config

logger = logging.getLogger(__name__)

# ── Default user-agent pool (overridden by config.SCRAPER_USER_AGENTS if set) ─
_DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
]


def _cookies_file() -> Path:
    """Return the configured path for persisted Facebook session cookies."""
    return Path(config.FACEBOOK_COOKIES_PATH)


def _user_agent_pool() -> list[str]:
    """Return the configured user-agent pool, or built-in defaults."""
    return config.SCRAPER_USER_AGENTS or _DEFAULT_USER_AGENTS


def _pick_user_agent() -> str:
    """Pick a user-agent from the pool (random or fixed based on config)."""
    pool = _user_agent_pool()
    if config.SCRAPER_ROTATE_USER_AGENT:
        return random.choice(pool)
    return pool[0]

# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class FacebookPost:
    post_id: str
    author: str
    content: str
    post_url: str
    timestamp: str
    image_url: Optional[str] = field(default=None)
    image_urls: list[str] = field(default_factory=list)
    is_live_stream: bool = field(default=False)
    streamer_name: Optional[str] = field(default=None)
    reaction_count: Optional[int] = field(default=None)
    comment_count: Optional[int] = field(default=None)
    share_count: Optional[int] = field(default=None)


# ── Selectors (adjust if Facebook changes its markup) ─────────────────────────
_POST_ARTICLE_SEL = "div[role='article']"
_AUTHOR_SEL = "h2 a b, h3 a b, h2 a strong, h3 a strong, h2 a, h3 a"
_TIMESTAMP_SEL = "abbr, a[role='link'] abbr"
_POST_LINK_SEL = "a[href*='/posts/'], a[href*='?story_fbid='], a[href*='/permalink/']"
_IMAGE_SEL = "img[src*='scontent']"
_REACTION_SEL = "span[aria-label*='reaction'], div[aria-label*='reaction']"
_COMMENT_SEL = "span:has-text('comment'), span:has-text('Comment')"
_SHARE_SEL = "span:has-text('share'), span:has-text('Share')"

_POST_ID_RE = re.compile(
    r"/posts/([^/?#]+)"
    r"|story_fbid=([^&]+)"
    r"|/(\d{10,})"
)

# Regex patterns to detect live stream posts
_LIVE_STREAM_PATTERNS = [
    re.compile(r"(.+?)\s+was\s+live", re.IGNORECASE),
    re.compile(r"(.+?)\s+is\s+live", re.IGNORECASE),
    re.compile(r"(.+?)\s+went\s+live", re.IGNORECASE),
]

MAX_RETRIES = int(getattr(config, "SCRAPER_MAX_RETRIES", 3))
RETRY_DELAY = int(getattr(config, "SCRAPER_RETRY_DELAY", 5))

# Reused browser session (one Chromium instance for the bot lifetime)
_playwright: Playwright | None = None
_browser: Browser | None = None
_context: BrowserContext | None = None
_page: Page | None = None
_scan_lock = asyncio.Lock()


def _extract_post_id(url: str) -> Optional[str]:
    """Pull a stable post identifier out of a Facebook post URL."""
    m = _POST_ID_RE.search(url)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def _detect_live_stream(content: str, author: str) -> tuple[bool, Optional[str]]:
    """
    Detect if a post is a live stream announcement.
    Returns (is_live_stream, streamer_name).
    """
    if not content:
        return False, None
    
    # Check first few lines for live stream patterns
    first_lines = "\n".join(content.split("\n")[:3])
    
    for pattern in _LIVE_STREAM_PATTERNS:
        match = pattern.search(first_lines)
        if match:
            streamer_name = match.group(1).strip()
            # Remove common suffixes like "Plays", "Gaming", etc. for cleaner display
            return True, streamer_name
    
    return False, None


def _extract_number_from_text(text: str) -> Optional[int]:
    """
    Extract a numeric count from text like '123', '1.2K', '5.3M'.
    Returns the approximate integer value, or None if not parseable.
    """
    if not text:
        return None
    
    text = text.strip().upper()
    
    # Handle 'K' (thousands) and 'M' (millions)
    multiplier = 1
    if text.endswith('K'):
        multiplier = 1000
        text = text[:-1]
    elif text.endswith('M'):
        multiplier = 1000000
        text = text[:-1]
    
    try:
        # Remove commas and convert to float, then apply multiplier
        num = float(text.replace(',', ''))
        return int(num * multiplier)
    except (ValueError, AttributeError):
        return None


async def _extract_engagement_metrics(article) -> tuple[Optional[int], Optional[int], Optional[int]]:
    """
    Extract reaction, comment, and share counts from a Facebook post article.
    Returns (reaction_count, comment_count, share_count).
    Facebook's DOM structure varies, so this uses heuristics.
    """
    reaction_count = None
    comment_count = None
    share_count = None
    
    try:
        # Get all text content from the article
        article_text = await article.inner_text()
        lines = article_text.lower().split('\n')
        
        # Look for engagement metrics in typical Facebook patterns
        for line in lines:
            line_stripped = line.strip()
            
            # Match patterns like "123 reactions", "1.2K reactions", "All reactions: 456"
            if 'reaction' in line_stripped and reaction_count is None:
                # Try to find numbers before or after 'reaction'
                words = line_stripped.replace(':', ' ').replace(',', '').split()
                for i, word in enumerate(words):
                    if 'reaction' in word and i > 0:
                        reaction_count = _extract_number_from_text(words[i-1])
                        break
            
            # Match "123 comments", "1.2K comments"
            if 'comment' in line_stripped and comment_count is None:
                words = line_stripped.replace(':', ' ').replace(',', '').split()
                for i, word in enumerate(words):
                    if 'comment' in word and i > 0:
                        comment_count = _extract_number_from_text(words[i-1])
                        break
            
            # Match "123 shares", "1.2K shares"
            if 'share' in line_stripped and share_count is None:
                words = line_stripped.replace(':', ' ').replace(',', '').split()
                for i, word in enumerate(words):
                    if 'share' in word and i > 0:
                        share_count = _extract_number_from_text(words[i-1])
                        break
        
        # Alternative: look for aria-labels with engagement info
        if reaction_count is None:
            try:
                reaction_elements = await article.query_selector_all("span[aria-label], div[aria-label]")
                for elem in reaction_elements:
                    aria_label = await elem.get_attribute("aria-label")
                    if aria_label and 'reaction' in aria_label.lower():
                        # Try to extract number from aria-label
                        reaction_count = _extract_number_from_text(aria_label.split()[0])
                        break
            except Exception:
                pass
    
    except Exception as exc:
        logger.debug("Error extracting engagement metrics: %s", exc)
    
    return reaction_count, comment_count, share_count


async def _scroll_page(page: Page, scrolls: int | None = None) -> None:
    """Scroll the page a few times to load feed content, then dismiss any login popup.

    Default scrolls can be configured via `config.SCRAPER_SCROLLS` (int).
    """
    if scrolls is None:
        scrolls = getattr(config, "SCRAPER_SCROLLS", 3)
    for _ in range(scrolls):
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(1.2)
    # Dismiss login popup once after all scrolling is done
    await _dismiss_login_popup(page)


async def _dismiss_login_popup(page: Page) -> None:
    """Close the Facebook login wall if it appears."""
    selectors = [
        "div[aria-label='Close']",
        "div[role='dialog'] div[aria-label='Close']",
        "[data-testid='cookie-policy-manage-dialog'] button",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.is_visible(timeout=500):
                await btn.click(timeout=2000)
                await asyncio.sleep(0.5)
                logger.info("Dismissed Facebook login wall popup.")
                return
        except Exception:
            continue


async def _expand_see_more(article) -> None:
    """Expand collapsed post bodies before reading inner_text()."""
    see_more_selectors = [
        "div[role='button']:has-text('See more')",
        "div[role='button']:has-text('See More')",
        "span:has-text('See more')",
        "span:has-text('See More')",
    ]
    for sel in see_more_selectors:
        try:
            buttons = await article.query_selector_all(sel)
            for btn in buttons:
                try:
                    # Use a strict timeout so a closed/crashed page never hangs the scan
                    visible = await asyncio.wait_for(
                        btn.is_visible(), timeout=2.0
                    )
                    if visible:
                        await asyncio.wait_for(
                            btn.click(timeout=2000), timeout=3.0
                        )
                        await asyncio.sleep(0.4)
                except (asyncio.TimeoutError, Exception):
                    pass
        except Exception:
            pass


_UI_ONLY_LABELS = frozenset({
    "Admin", "Moderator", "Group participant", "Visual storyteller",
    "Featured", "Public", "Joined", "Group", "Friends",
    "Like", "Comment", "Share", "Follow", "Send",
    "View more comments", "View previous comments",
    "Most relevant", "All comments",
})

_FOOTER_MARKERS = [
    "All reactions:",
    "Like\nComment\nShare",
    "Like\nComment",
    "Comment\nShare",
]


def _clean_content(content: str, author: str, timestamp: str) -> str:
    """Strip Facebook UI chrome from raw article inner_text."""
    if author and author != "Unknown":
        content = content.replace(author, "", 1).strip()
    if timestamp and timestamp != "Unknown time":
        content = content.replace(timestamp, "", 1).strip()

    for marker in _FOOTER_MARKERS:
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx]

    content = content.replace("See more", "").replace("See More", "")
    content = content.replace("See translation", "").replace("See Translation", "")

    def has_alnum(s: str) -> bool:
        return any(c.isalnum() for c in s)

    lines = content.split("\n")
    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if cleaned and cleaned[-1] != "":
                cleaned.append("")
            continue
        if stripped in _UI_ONLY_LABELS:
            continue
        if len(stripped) <= 2 and not has_alnum(stripped):
            continue
        cleaned.append(stripped)

    while cleaned and cleaned[-1] == "":
        cleaned.pop()

    return "\n".join(cleaned).strip()


async def _parse_articles(page: Page) -> list[FacebookPost]:
    """Extract post data from all article elements currently in the DOM."""
    articles = await page.query_selector_all(_POST_ARTICLE_SEL)
    posts: list[FacebookPost] = []

    for article in articles:
        try:
            link_el = await article.query_selector(_POST_LINK_SEL)
            if not link_el:
                continue
            post_url: str = await link_el.get_attribute("href") or ""
            if not post_url.startswith("http"):
                post_url = "https://www.facebook.com" + post_url

            post_id = _extract_post_id(post_url)
            if not post_id:
                logger.debug("Could not extract post_id from URL: %s", post_url)
                continue

            author_el = await article.query_selector(_AUTHOR_SEL)
            author = "Unknown"
            if author_el:
                author_text = (await author_el.inner_text()).strip()
                if author_text:
                    author = author_text

            timestamp = "Unknown time"
            aria_label = await link_el.get_attribute("aria-label")
            if aria_label:
                timestamp = aria_label.strip()
            else:
                text_val = await link_el.inner_text()
                if text_val:
                    timestamp = text_val.strip()
            if timestamp == "Unknown time" or not timestamp:
                ts_el = await article.query_selector(_TIMESTAMP_SEL)
                if ts_el:
                    timestamp = (await ts_el.get_attribute("title") or await ts_el.inner_text()).strip()

            await _expand_see_more(article)

            raw_text = await article.inner_text()
            content = _clean_content(raw_text, author, timestamp)

            # Extract all images from the post
            img_els = await article.query_selector_all(_IMAGE_SEL)
            image_url: Optional[str] = None
            image_urls: list[str] = []
            for img_el in img_els:
                src = await img_el.get_attribute("src")
                if src and "scontent" in src:
                    image_urls.append(src)
            
            # Keep first image in image_url for backward compatibility
            if image_urls:
                image_url = image_urls[0]

            # Detect live stream posts
            is_live_stream, streamer_name = _detect_live_stream(content, author)

            # Extract engagement metrics (reactions, comments, shares)
            reaction_count, comment_count, share_count = await _extract_engagement_metrics(article)

            posts.append(
                FacebookPost(
                    post_id=post_id,
                    author=author,
                    content=content,
                    post_url=post_url,
                    timestamp=timestamp,
                    image_url=image_url,
                    image_urls=image_urls,
                    is_live_stream=is_live_stream,
                    streamer_name=streamer_name,
                    reaction_count=reaction_count,
                    comment_count=comment_count,
                    share_count=share_count,
                )
            )
        except Exception as exc:
            logger.warning("Error parsing article element: %s", exc, exc_info=True)
            continue

    return posts


async def _reset_browser() -> None:
    """Tear down the shared browser session."""
    global _playwright, _browser, _context, _page

    if _page is not None:
        try:
            await _page.close()
        except Exception:
            pass
        _page = None

    if _context is not None:
        try:
            await _context.close()
        except Exception:
            pass
        _context = None

    if _browser is not None:
        try:
            await _browser.close()
        except Exception:
            pass
        _browser = None

    if _playwright is not None:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None


async def close_browser() -> None:
    """Shut down the shared Playwright browser. Called on bot shutdown."""
    async with _scan_lock:
        await _reset_browser()
        logger.info("Playwright browser session closed.")


# ── Cookie helpers ────────────────────────────────────────────────────────────

def _load_cookies() -> list[dict]:
    """Load persisted Facebook cookies from disk. Returns empty list if none saved."""
    if not config.FACEBOOK_COOKIES_ENABLED:
        return []

    cookies_path = _cookies_file()
    if not cookies_path.exists():
        return []
    try:
        raw = cookies_path.read_text(encoding="utf-8")
        cookies = json.loads(raw)
        if isinstance(cookies, list):
            logger.info("Loaded %d cookie(s) from %s", len(cookies), cookies_path)
            return cookies
    except Exception as exc:
        logger.warning("Could not read cookies file %s: %s", cookies_path, exc)
    return []


async def _save_cookies(context: BrowserContext) -> None:
    """Persist current browser cookies to disk for reuse across restarts."""
    if not config.FACEBOOK_COOKIES_ENABLED:
        return

    try:
        cookies_path = _cookies_file()
        cookies_path.parent.mkdir(parents=True, exist_ok=True)
        cookies = await context.cookies()
        cookies_path.write_text(
            json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Saved %d cookie(s) to %s", len(cookies), cookies_path)
    except Exception as exc:
        logger.warning("Could not save cookies: %s", exc)


async def clear_cookies() -> None:
    """Delete the persisted cookie file. Call this if sessions become stale."""
    try:
        cookies_path = _cookies_file()
        if cookies_path.exists():
            cookies_path.unlink()
            logger.info("Cookie file cleared: %s", cookies_path)
    except Exception as exc:
        logger.warning("Could not clear cookie file: %s", exc)


async def _ensure_page() -> Page:
    """Return a reusable page, launching Chromium on first use.

    On each fresh browser launch:
      - Picks a random user-agent from USER_AGENTS
      - Configures proxy if SCRAPER_PROXY is set in config
      - Injects any previously saved Facebook cookies into the context
      - Saves updated cookies back to disk after the page loads
    """
    global _playwright, _browser, _context, _page

    if _browser is not None and not _browser.is_connected():
        logger.warning("Playwright browser disconnected; restarting session.")
        await _reset_browser()

    if _page is not None:
        if _page.is_closed():
            logger.warning("Playwright page was closed; recreating.")
            _page = None
        else:
            return _page

    try:
        user_agent = _pick_user_agent()
        logger.info("Browser UA: %s", user_agent[:60] + "…")

        proxy_config: dict | None = None
        if config.SCRAPER_PROXY:
            proxy_config = {"server": config.SCRAPER_PROXY}
            if config.SCRAPER_PROXY_USERNAME and config.SCRAPER_PROXY_PASSWORD:
                proxy_config["username"] = config.SCRAPER_PROXY_USERNAME
                proxy_config["password"] = config.SCRAPER_PROXY_PASSWORD
            logger.info("Using proxy: %s", config.SCRAPER_PROXY)

        _playwright = await async_playwright().start()
        # Safer Chromium launch args for constrained environments (e.g., Railway)
        launch_kwargs: dict = {
            "headless": True,
            "args": [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
                "--single-process",
                "--no-zygote",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-background-networking",
            ],
        }
        if proxy_config:
            launch_kwargs["proxy"] = proxy_config

        _browser = await _playwright.chromium.launch(**launch_kwargs)

        context_kwargs: dict = {
            "user_agent": user_agent,
            "viewport": {"width": 1280, "height": 900},
            "locale": "en-US",
            "java_script_enabled": True,
        }
        _context = await _browser.new_context(**context_kwargs)

        # Inject persisted cookies so Facebook doesn't show a login wall
        saved_cookies = _load_cookies()
        if saved_cookies:
            try:
                await _context.add_cookies(saved_cookies)
                logger.info("Injected %d persisted cookie(s) into browser context.", len(saved_cookies))
            except Exception as exc:
                logger.warning("Failed to inject cookies (they may be stale): %s", exc)

        _page = await _context.new_page()
        await _page.route(
            "**/*.{mp4,webm,ogg,mp3,wav,flac,aac,woff,woff2,ttf,otf}",
            lambda route: route.abort(),
        )
        logger.info("Playwright browser session started (reused across scans).")
        return _page
    except Exception:
        await _reset_browser()
        raise


async def fetch_group_posts(
    source_url: str = config.FACEBOOK_GROUP_URL,
) -> list[FacebookPost]:
    """
    Scrape the Facebook group or page and return recent posts.

    Uses a shared browser instance and a scan lock to prevent overlapping scrapes.
    Retries up to MAX_RETRIES times on navigation failures.
    """
    async with _scan_lock:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return await _scrape_with_browser(source_url)
            except PWTimeoutError as exc:
                logger.warning(
                    "Playwright timeout on attempt %d/%d: %s", attempt, MAX_RETRIES, exc
                )
            except Exception as exc:
                logger.error(
                    "Unexpected error on attempt %d/%d: %s",
                    attempt, MAX_RETRIES, exc,
                    exc_info=True,
                )
                # Reset browser if we see a crash-like message
                msg = str(exc)
                if "Page crashed" in msg or "Target crashed" in msg:
                    logger.warning("Detected page crash; resetting browser session.")
                    await _reset_browser()

            # Exponential backoff between retries
            if attempt < MAX_RETRIES:
                backoff = RETRY_DELAY * (2 ** (attempt - 1))
                logger.info("Retrying in %d seconds (attempt %d/%d)...", backoff, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(backoff)

        logger.error("All %d attempts to fetch Facebook posts failed.", MAX_RETRIES)
        return []


async def _scrape_with_browser(source_url: str) -> list[FacebookPost]:
    """Navigate with the shared browser and scrape posts."""
    page = await _ensure_page()

    logger.info("Navigating to Facebook source: %s", source_url)
    await page.goto(source_url, wait_until="domcontentloaded", timeout=60_000)

    await _dismiss_login_popup(page)
    await _scroll_page(page)

    posts = await _parse_articles(page)
    logger.info("Scraped %d post(s) from Facebook source.", len(posts))

    if _context is not None:
        await _save_cookies(_context)

    return posts
