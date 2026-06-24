"""
bot.py - Core execution entrypoint for BY BOTS.

This is the main Python script that:
  - Initialises logging to console and file.
  - Connects to Discord using discord.py.
  - Creates/migrates SQLite tables on startup.
  - Starts a background scheduler (APScheduler) to scan Facebook group.
  - Formats and forwards new Facebook posts to Discord.
  - Registers slash commands: /ping, /status, /testembed, /recent.
"""

import asyncio
import atexit
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from modules.database import (
    init_db,
    get_total_posts,
    get_meta,
    get_recent_posts,
    is_duplicate,
    save_post,
    set_meta,
)
from modules.discord_embed import (
    build_sample_embed,
    build_status_embed,
    build_post_embed,
    build_recent_posts_embed,
    build_additional_image_embeds,
)
from modules.facebook_monitor import close_browser, fetch_group_posts
from modules.webhook_sender import WebhookSender, format_post_for_webhook

SECURITY_REMINDER_MESSAGE = """🚨 SECURITY ALERT 🚨

⚠️ Beware of Scammers, Hackers, and Cheaters!

To ensure a fair and secure gaming environment, BY RAN ONLINE strictly prohibits any form of cheating, hacking, exploiting, botting, or unauthorized third-party software.

🔒 Account Security
• Never share your password.
• Staff and GMs will NEVER ask for your account credentials.
• Do not download suspicious files or programs from unknown sources.
• Avoid account sharing to protect your account and items.

🚫 Prohibited Activities
• Hacks / Cheat Programs
• Bots / Auto-Farm Tools
• Exploits & Abuse of Bugs
• Modified Game Files
• Real Money Trading (if prohibited by server rules)
• Account Theft or Impersonation

📢 Report Suspicious Activity
If you encounter a scammer, hacker, exploiter, or any suspicious behavior, please report it immediately.

Required Information:
• Character Name
• Date & Time
• Screenshot / Video Evidence
• Description of the Incident

📩 Report Through:
• Discord Ticket System
• Official Facebook Page
• Contact a GM or Administrator

🛡️ Help us keep BY RAN ONLINE safe, fair, and enjoyable for everyone.

— BY RAN ONLINE Management Team
"""

# ── Logging Setup ─────────────────────────────────────────────────────────────
os.makedirs(config.LOG_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        RotatingFileHandler(
            config.LOG_FILE,
            maxBytes=config.LOG_MAX_BYTES,
            backupCount=config.LOG_BACKUP_COUNT,
            encoding="utf-8",
        ),
    ],
)
logger = logging.getLogger("bybots")

_lock_file_handle = None


def acquire_single_instance_lock() -> None:
    """Prevent multiple bot processes from running at the same time."""
    global _lock_file_handle

    try:
        _lock_file_handle = open(config.LOCK_FILE, "w", encoding="utf-8")
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
        
        if sys.platform == "win32":
            import msvcrt
            _lock_file_handle.seek(0)
            msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            _lock_file_handle.seek(0)
            fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        logger.fatal(
            "Another BY BOTS instance is already running. "
            "Stop the other process before starting again."
        )
        sys.exit(1)

    atexit.register(release_single_instance_lock)


def release_single_instance_lock() -> None:
    """Release the process lock on exit."""
    global _lock_file_handle

    if _lock_file_handle is None:
        return

    try:
        if sys.platform == "win32":
            import msvcrt

            _lock_file_handle.seek(0)
            msvcrt.locking(_lock_file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_lock_file_handle.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        _lock_file_handle.close()
        _lock_file_handle = None


# ── Discord Bot Subclass ──────────────────────────────────────────────────────
class ByBotsBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.scheduler = AsyncIOScheduler()
        self._scan_lock = asyncio.Lock()
        self.webhook_sender: WebhookSender | None = None

    async def setup_hook(self) -> None:
        """Called once before the client logs in. Used for all async initialization."""
        logger.info("Starting bot setup hook...")

        try:
            await init_db()
        except Exception as e:
            logger.error("Failed to initialise database: %s", e, exc_info=True)
            raise

        # Sync slash commands — failure here must NOT prevent the scheduler from starting
        try:
            if config.DISCORD_GUILD_ID:
                guild = discord.Object(id=config.DISCORD_GUILD_ID)
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                logger.info(
                    "Application commands synced to guild %s.", config.DISCORD_GUILD_ID
                )
            else:
                await self.tree.sync()
                logger.info("Application commands synced globally.")
        except Exception as e:
            logger.error(
                "Failed to sync application commands (non-fatal): %s", e, exc_info=True
            )

        if config.WEBHOOK_ENABLED and config.WEBHOOK_URLS:
            self.webhook_sender = WebhookSender(
                config.WEBHOOK_URLS,
                timeout=config.WEBHOOK_TIMEOUT,
            )
            logger.info(
                "Webhook delivery enabled for %d endpoint(s).",
                len(config.WEBHOOK_URLS),
            )
            if config.WEBHOOK_ONLY:
                logger.info(
                    "WEBHOOK_ONLY mode active — Discord channel posting is disabled."
                )

        try:
            # Always start the scheduler regardless of sync outcome
            self.scheduler.add_job(
                self.check_facebook_group,
                "interval",
                seconds=config.CHECK_INTERVAL,
                next_run_time=datetime.now(timezone.utc),
                id="facebook_check",
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            
            # Add security reminder job if enabled
            if config.SECURITY_REMINDER_ENABLED and config.DISCORD_SECURITY_CHANNEL_ID:
                self.scheduler.add_job(
                    self.send_security_reminder,
                    "interval",
                    seconds=config.SECURITY_REMINDER_INTERVAL,
                    next_run_time=datetime.now(timezone.utc),
                    id="security_reminder",
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
                logger.info(
                    "Security reminder scheduler started with interval of %s seconds to channel %s.",
                    config.SECURITY_REMINDER_INTERVAL,
                    config.DISCORD_SECURITY_CHANNEL_ID,
                )
            
            self.scheduler.start()
            logger.info(
                "Facebook monitoring scheduler started with check interval of %s seconds.",
                config.CHECK_INTERVAL,
            )
        except Exception as e:
            logger.error("Failed to start scheduler: %s", e, exc_info=True)
            raise

    async def on_ready(self) -> None:
        logger.info("Logged in as %s (ID: %s)", self.user, self.user.id)
        logger.info("BY BOTS is online and monitoring Facebook")
        print("BY BOTS is online and monitoring Facebook")

        logger.info("BY BOTS has joined %d guild(s):", len(self.guilds))
        for guild in self.guilds:
            logger.info("  - Guild: '%s' (ID: %s)", guild.name, guild.id)
            channels = guild.text_channels
            logger.info(
                "    Text Channels: %s",
                ", ".join(f"'{c.name}' (ID: {c.id})" for c in channels),
            )

        try:
            await self.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="Monitoring Facebook Community",
                )
            )
            logger.info("Presence activity set.")
        except Exception as e:
            logger.error("Failed to set presence: %s", e, exc_info=True)

    async def close(self) -> None:
        """Cleanly shut down the scheduler and browser before disconnecting."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down.")
        if self.webhook_sender is not None:
            await self.webhook_sender.close()
            self.webhook_sender = None
        await close_browser()
        await super().close()

    async def _send_post_webhooks(self, post) -> bool:
        """Deliver a post payload to configured webhook endpoints."""
        if self.webhook_sender is None:
            return False

        results = await self.webhook_sender.send_post(format_post_for_webhook(post))
        if not results:
            return False

        success_count = sum(1 for ok in results.values() if ok)
        logger.info(
            "Webhook delivery for post %s: %d/%d endpoint(s) succeeded.",
            post.post_id,
            success_count,
            len(results),
        )
        return success_count > 0

    async def _resolve_channel(self, channel_id: int) -> discord.abc.Messageable | None:
        """Return the Discord text channel for the given channel_id, or None on failure."""
        channel = self.get_channel(channel_id)
        if channel is not None:
            return channel

        try:
            channel = await self.fetch_channel(channel_id)
            if not isinstance(channel, discord.abc.Messageable):
                logger.error(
                    "Channel ID %s is not a messageable text channel.",
                    channel_id,
                )
                return None
            return channel
        except discord.NotFound:
            logger.error(
                "Discord channel ID %s not found (404).",
                channel_id,
            )
        except discord.Forbidden:
            logger.error(
                "Bot lacks permission to access channel ID %s.",
                channel_id,
            )
        except Exception as ec:
            logger.error(
                "Failed to fetch channel ID %s: %s", channel_id, ec
            )
        return None

    async def _resolve_target_channel(self):
        """Return the configured Discord text channel, or None on failure."""
        return await self._resolve_channel(config.DISCORD_CHANNEL_ID)

    async def send_security_reminder(self) -> None:
        """Send the configured security reminder message to the dedicated channel."""
        if not config.DISCORD_SECURITY_CHANNEL_ID:
            logger.warning(
                "Security reminder not sent because DISCORD_SECURITY_CHANNEL_ID is not configured."
            )
            return

        channel = await self._resolve_channel(config.DISCORD_SECURITY_CHANNEL_ID)
        if channel is None:
            logger.warning(
                "Security reminder channel %s could not be resolved.",
                config.DISCORD_SECURITY_CHANNEL_ID,
            )
            return

        prefix = "@everyone\n\n" if config.SECURITY_REMINDER_PING_EVERYONE else ""
        try:
            await channel.send(content=prefix + SECURITY_REMINDER_MESSAGE)
            logger.info(
                "Security reminder sent to channel %s.",
                config.DISCORD_SECURITY_CHANNEL_ID,
            )
        except discord.DiscordException as de:
            logger.error(
                "Discord API error sending security reminder: %s", de, exc_info=True
            )
        except Exception as e:
            logger.error(
                "Unexpected error sending security reminder: %s", e, exc_info=True
            )

    async def check_facebook_group(self) -> dict:
        """Periodic task: scrape Facebook posts from configured sources and forward new ones to Discord."""
        async with self._scan_lock:
            logger.info("Starting scheduled Facebook scan...")

            try:
                total_posts = await get_total_posts()
                seed_mode = config.SEED_ON_FIRST_RUN and total_posts == 0
                
                new_posts_count = 0
                seeded_count = 0
                skipped_no_channel = 0
                filtered_count = 0
                total_scraped = 0

                # Cache of resolved channels during this run
                resolved_channels: dict[int, discord.abc.Messageable] = {}

                for source_url in getattr(config, "FACEBOOK_SOURCES", [config.FACEBOOK_GROUP_URL]):
                    logger.info("Scraping source: %s", source_url)
                    try:
                        posts = await fetch_group_posts(source_url)
                    except Exception as scrape_err:
                        logger.error("Failed to scrape source %s: %s", source_url, scrape_err, exc_info=True)
                        continue

                    total_scraped += len(posts)
                    logger.info(
                        "Scrape complete for %s. Retrieved %d post(s).", source_url, len(posts)
                    )

                    if seed_mode:
                        logger.info(
                            "First-run seed mode active for %s: recording %d existing post(s) "
                            "without forwarding to Discord.",
                            source_url,
                            len(posts),
                        )

                    for post in reversed(posts):
                        if await is_duplicate(post.post_id):
                            continue

                        # Apply author filtering if enabled
                        if config.FILTER_BY_AUTHOR and config.ALLOWED_AUTHORS:
                            if post.author not in config.ALLOWED_AUTHORS:
                                logger.info(
                                    "Post %s from author '%s' filtered out (not in allowed authors list)",
                                    post.post_id,
                                    post.author
                                )
                                # Save to DB for deduplication but don't forward to Discord
                                await save_post(
                                    post.post_id, post.author, post.post_url, post.timestamp
                                )
                                filtered_count += 1
                                continue

                        logger.info(
                            "New post detected: %s (Author: %s)", post.post_id, post.author
                        )

                        # Seed mode → save to DB only
                        if seed_mode:
                            await save_post(
                                post.post_id, post.author, post.post_url, post.timestamp
                            )
                            seeded_count += 1
                            continue

                        # Determine routing target channels
                        target_channel_ids = set()
                        matched_keywords = []
                        post_content_lower = (post.content or "").lower()

                        # Special routing for live stream posts
                        if post.is_live_stream and config.DISCORD_STREAMER_CHANNEL_ID:
                            target_channel_ids.add(config.DISCORD_STREAMER_CHANNEL_ID)
                            matched_keywords.append("live stream")
                            logger.info(
                                "Post %s detected as live stream: routing to streamer channel %s",
                                post.post_id,
                                config.DISCORD_STREAMER_CHANNEL_ID
                            )
                        else:
                            # Sort keywords by length in descending order to match longer phrases first
                            sorted_routes = sorted(config.DISCORD_ROUTES.keys(), key=len, reverse=True)
                            for keyword in sorted_routes:
                                if keyword in post_content_lower:
                                    cid = config.DISCORD_ROUTES[keyword]
                                    if cid not in target_channel_ids:
                                        target_channel_ids.add(cid)
                                        matched_keywords.append(keyword)

                        is_routed = bool(target_channel_ids)
                        if not target_channel_ids:
                            target_channel_ids.add(config.DISCORD_CHANNEL_ID)

                        # Determine custom color based on matched keywords
                        custom_color = None
                        if matched_keywords and not post.is_live_stream:
                            # Use the color of the first matched keyword (highest priority)
                            for keyword in matched_keywords:
                                if keyword in config.DISCORD_ROUTE_COLORS:
                                    custom_color = config.DISCORD_ROUTE_COLORS[keyword]
                                    logger.debug(
                                        "Post %s using custom color 0x%06X for keyword '%s'",
                                        post.post_id, custom_color, keyword
                                    )
                                    break

                        # Build list of channels to try sending to (with fallback logic)
                        channels_to_send = []
                        for cid in target_channel_ids:
                            if cid not in resolved_channels:
                                resolved_channels[cid] = await self._resolve_channel(cid)

                            chan = resolved_channels[cid]
                            if chan is not None:
                                channels_to_send.append((cid, chan, False))
                            else:
                                if cid != config.DISCORD_CHANNEL_ID:
                                    logger.warning(
                                        "Routed channel ID %s for keywords %s was not resolvable. "
                                        "Falling back to default channel ID %s.",
                                        cid, matched_keywords, config.DISCORD_CHANNEL_ID
                                    )
                                    default_cid = config.DISCORD_CHANNEL_ID
                                    if default_cid not in resolved_channels:
                                        resolved_channels[default_cid] = await self._resolve_channel(default_cid)

                                    default_chan = resolved_channels[default_cid]
                                    if default_chan is not None:
                                        if default_cid not in target_channel_ids:
                                            channels_to_send.append((default_cid, default_chan, True))

                        if not channels_to_send and not config.WEBHOOK_ONLY:
                            logger.warning(
                                "No channels available to forward post %s. Saving to database.",
                                post.post_id
                            )
                            await save_post(
                                post.post_id, post.author, post.post_url, post.timestamp
                            )
                            skipped_no_channel += 1
                            continue

                        embed = build_post_embed(
                            author=post.author,
                            content=post.content,
                            post_url=post.post_url,
                            timestamp=post.timestamp,
                            image_url=post.image_url,
                            image_urls=post.image_urls,
                            is_live_stream=post.is_live_stream,
                            streamer_name=post.streamer_name,
                            reaction_count=post.reaction_count,
                            comment_count=post.comment_count,
                            share_count=post.share_count,
                            custom_color=custom_color,
                        )

                        # Build additional embeds for image gallery
                        additional_embeds = build_additional_image_embeds(
                            post.image_urls,
                            post.post_url,
                            post.author,
                        )

                        ping_content = None
                        if config.DISCORD_PING_ROLE_ID:
                            ping_content = f"<@&{config.DISCORD_PING_ROLE_ID}>"

                        sent_successfully = False
                        webhook_sent = False
                        if config.WEBHOOK_ENABLED:
                            webhook_sent = await self._send_post_webhooks(post)

                        if config.WEBHOOK_ONLY:
                            sent_successfully = webhook_sent
                            if not webhook_sent:
                                logger.warning(
                                    "WEBHOOK_ONLY mode: post %s was not delivered to any webhook.",
                                    post.post_id,
                                )
                        else:
                            for cid, chan, is_fallback in channels_to_send:
                                try:
                                    # Send main embed with content/ping
                                    await chan.send(content=ping_content, embed=embed)

                                    # Send additional images as follow-up embeds
                                    for img_embed in additional_embeds:
                                        await asyncio.sleep(0.5)
                                        await chan.send(embed=img_embed)

                                    route_lbl = "default fallback" if is_fallback else (
                                        f"keyword routing: {matched_keywords}" if is_routed else "default channel"
                                    )
                                    logger.info(
                                        "Discord message sent for post: %s to channel '%s' (ID: %s) via %s (%d image(s))",
                                        post.post_id, chan.name if hasattr(chan, 'name') else 'unknown', cid, route_lbl, len(post.image_urls)
                                    )
                                    sent_successfully = True
                                    await asyncio.sleep(1.5)
                                except discord.DiscordException as de:
                                    logger.error(
                                        "Discord API error sending message for post %s to channel %s: %s",
                                        post.post_id,
                                        cid,
                                        de,
                                    )
                                    if cid != config.DISCORD_CHANNEL_ID and config.DISCORD_CHANNEL_ID not in [x[0] for x in channels_to_send]:
                                        default_cid = config.DISCORD_CHANNEL_ID
                                        if default_cid not in resolved_channels:
                                            resolved_channels[default_cid] = await self._resolve_channel(default_cid)
                                        default_chan = resolved_channels[default_cid]
                                        if default_chan is not None:
                                            try:
                                                await default_chan.send(content=ping_content, embed=embed)

                                                # Send additional images
                                                for img_embed in additional_embeds:
                                                    await asyncio.sleep(0.5)
                                                    await default_chan.send(embed=img_embed)

                                                logger.info(
                                                    "Discord message sent for post: %s to default channel '%s' (ID: %s) as fallback after error on %s (%d image(s))",
                                                    post.post_id, default_chan.name if hasattr(default_chan, 'name') else 'unknown', default_cid, cid, len(post.image_urls)
                                                )
                                                sent_successfully = True
                                                await asyncio.sleep(1.5)
                                            except Exception as ex_fallback:
                                                logger.error("Fallback to default channel failed for post %s: %s", post.post_id, ex_fallback)
                                except Exception as ex:
                                    logger.error(
                                        "Unexpected error sending post %s to channel %s: %s", post.post_id, cid, ex
                                    )

                            if not sent_successfully and webhook_sent:
                                sent_successfully = True

                        await save_post(
                            post.post_id, post.author, post.post_url, post.timestamp
                        )
                        if sent_successfully:
                            new_posts_count += 1
                        else:
                            skipped_no_channel += 1

                now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                await set_meta("last_scan", now_str)

                if seed_mode and seeded_count:
                    await set_meta("seeded", now_str)
                    logger.info(
                        "Scheduled Facebook check finished. Seeded %d existing post(s).",
                        seeded_count,
                    )
                elif filtered_count:
                    logger.info(
                        "Scheduled Facebook check finished. Posted %d new post(s), filtered %d post(s) by author.",
                        new_posts_count,
                        filtered_count,
                    )
                elif skipped_no_channel:
                    logger.warning(
                        "Scheduled Facebook check finished. Saved %d post(s) to DB "
                        "(channels unavailable, not forwarded to Discord).",
                        skipped_no_channel,
                    )
                else:
                    logger.info(
                        "Scheduled Facebook check finished. Posted %d new post(s).",
                        new_posts_count,
                    )

                return {
                    "success": True,
                    "new_posts": new_posts_count,
                    "seeded": seeded_count,
                    "skipped": skipped_no_channel,
                    "filtered": filtered_count,
                    "total_scraped": total_scraped,
                }

            except Exception as e:
                logger.error("Error during scheduled Facebook scan: %s", e, exc_info=True)
                return {
                    "success": False,
                    "error": str(e),
                }


bot = ByBotsBot()

# ── Slash Commands ────────────────────────────────────────────────────────────

@bot.tree.command(name="ping", description="Returns Pong!")
async def ping(interaction: discord.Interaction) -> None:
    """Simple connection check command."""
    logger.info("Command /ping invoked by %s", interaction.user)
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! 🏓 Latency: `{latency_ms}ms`")


@bot.tree.command(name="status", description="Get the status of the BY BOTS Facebook monitor.")
async def status(interaction: discord.Interaction) -> None:
    """Returns the bot's health, last scan timestamp, and post count."""
    logger.info("Command /status invoked by %s", interaction.user)
    try:
        total_posts = await get_total_posts()
        last_scan = await get_meta("last_scan", "Never")

        is_active = bot.scheduler.running
        bot_status = "Online — Monitoring Active" if is_active else "Online — Scheduler Off"

        embed = build_status_embed(
            bot_status=bot_status,
            last_scan=last_scan,
            total_posts=total_posts,
        )
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error("Error building status embed: %s", e, exc_info=True)
        await interaction.response.send_message(
            "Error retrieving status. Check logs.", ephemeral=True
        )


@bot.tree.command(name="testembed", description="Sends a sample Facebook post embed.")
async def testembed(interaction: discord.Interaction) -> None:
    """Sends a formatted sample post embed to check visual layout."""
    logger.info("Command /testembed invoked by %s", interaction.user)
    try:
        embed = build_sample_embed()
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error("Error building test embed: %s", e, exc_info=True)
        await interaction.response.send_message(
            "Error generating test embed. Check logs.", ephemeral=True
        )


@bot.tree.command(name="recent", description="Show recently forwarded Facebook posts.")
async def recent(interaction: discord.Interaction) -> None:
    """Returns the last few posts stored in the database."""
    logger.info("Command /recent invoked by %s", interaction.user)
    try:
        posts = await get_recent_posts(limit=5)
        embed = build_recent_posts_embed(posts)
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        logger.error("Error building recent posts embed: %s", e, exc_info=True)
        await interaction.response.send_message(
            "Error retrieving recent posts. Check logs.", ephemeral=True
        )


@bot.tree.command(name="forcecheck", description="Manually trigger a scan of the Facebook sources for new posts.")
async def forcecheck(interaction: discord.Interaction) -> None:
    """Manually trigger a Facebook scan on demand."""
    logger.info("Command /forcecheck invoked by %s", interaction.user)
    if bot._scan_lock.locked():
        await interaction.response.send_message(
            "⚠️ A Facebook scan is already in progress. Please try again in a moment.",
            ephemeral=True
        )
        return

    await interaction.response.defer(thinking=True)
    try:
        res = await bot.check_facebook_group()
        if res.get("success"):
            new_p = res.get("new_posts", 0)
            seeded = res.get("seeded", 0)
            skipped = res.get("skipped", 0)
            filtered = res.get("filtered", 0)
            scraped = res.get("total_scraped", 0)
            
            msg = f"✅ **Facebook Scan Complete!**\n"
            msg += f"• Scraped `{scraped}` posts from Facebook feeds.\n"
            if new_p > 0:
                msg += f"• Forwarded `{new_p}` new post(s) to Discord."
            elif seeded > 0:
                msg += f"• Seeded `{seeded}` existing post(s) in database."
            elif skipped > 0:
                msg += f"• Saved `{skipped}` post(s) to database (no Discord channel available)."
            else:
                msg += f"• No new posts found."
            
            if filtered > 0:
                msg += f"\n• Filtered `{filtered}` post(s) by author (not forwarded)."
            
            await interaction.followup.send(msg)
        else:
            err = res.get("error", "Unknown error")
            await interaction.followup.send(f"❌ **Facebook Scan Failed:** `{err}`")
    except Exception as e:
        logger.error("Error in forcecheck command: %s", e, exc_info=True)
        await interaction.followup.send(f"❌ **An unexpected error occurred:** `{e}`")


# ── Entry Point ───────────────────────────────────────────────────────────────
def main() -> None:
    acquire_single_instance_lock()
    token = config.DISCORD_TOKEN
    logger.info("Starting bot client...")
    try:
        bot.run(token, log_handler=None)
    except discord.LoginFailure:
        logger.fatal("Invalid Discord Token provided. Please check your .env file.")
    except Exception as e:
        logger.fatal("Fatal error running bot: %s", e, exc_info=True)


if __name__ == "__main__":
    main()
