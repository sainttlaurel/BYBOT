"""
modules/discord_embed.py - Discord embed builder for BY BOTS.

Converts a raw Facebook post into a rich discord.Embed ready to send.
Designed to look like a proper announcement card — large, informative,
and visually distinct inside the Discord channel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord

import config


_FACEBOOK_BLUE = config.BOT_COLOUR
_SUCCESS_GREEN = 0x43B581

_FB_ICON = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b8/"
    "2021_Facebook_icon.svg/240px-2021_Facebook_icon.svg.png"
)


def _format_count(count: int) -> str:
    """Format engagement count for display (e.g., 1234 -> 1.2K, 1234567 -> 1.2M)."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    elif count >= 1_000:
        return f"{count / 1_000:.1f}K"
    else:
        return str(count)


def _get_source_label(post_url: str) -> str:
    """Build a rich link with correct source label based on post URL."""
    is_group = "/groups/" in post_url
    
    matched_source = None
    for src in getattr(config, "FACEBOOK_SOURCES", [config.FACEBOOK_GROUP_URL]):
        src_path = config.facebook_source_display_path(src)
        if src_path in post_url:
            matched_source = src
            break
            
    if not matched_source:
        if is_group:
            parts = post_url.split("/groups/")
            if len(parts) > 1:
                group_name = parts[1].split("/")[0]
                matched_source = f"https://www.facebook.com/groups/{group_name}"
            else:
                matched_source = config.FACEBOOK_GROUP_URL
        else:
            parts = post_url.replace("https://www.facebook.com/", "").split("/")
            if parts:
                page_name = parts[0]
                matched_source = f"https://www.facebook.com/{page_name}"
            else:
                matched_source = config.FACEBOOK_GROUP_URL

    source_type = "Facebook Group" if is_group else "Facebook Page"
    return f"[{source_type}]({matched_source})"


def build_post_embed(
    author: str,
    content: str,
    post_url: str,
    timestamp: str,
    image_url: Optional[str] = None,
    image_urls: Optional[list[str]] = None,
    is_live_stream: bool = False,
    streamer_name: Optional[str] = None,
    reaction_count: Optional[int] = None,
    comment_count: Optional[int] = None,
    share_count: Optional[int] = None,
    custom_color: Optional[int] = None,
) -> discord.Embed:
    """Build a Discord embed for a Facebook post."""
    MAX_DESC = 3800
    MAX_TITLE = 250

    # Default to empty list if not provided
    if image_urls is None:
        image_urls = []

    # Determine embed color
    if custom_color is not None:
        colour = custom_color
    elif is_live_stream:
        colour = 0xFF0000  # Red color for live streams
    else:
        colour = _FACEBOOK_BLUE

    # Special handling for live stream posts
    if is_live_stream and streamer_name:
        title = f"🔴 {streamer_name} was Live!"
        
        if not content or not content.strip():
            body = f"**{streamer_name}** shared a live stream on Facebook!\n\n*Click the link below to watch the replay or catch them live next time.*"
        elif len(content) > MAX_DESC:
            body = (
                content[:MAX_DESC]
                + f"\n\n*…content truncated. [Watch stream →]({post_url})*"
            )
        else:
            body = content
    else:
        # Regular post handling
        if not content or not content.strip():
            body = "*No text content — see the original post for images or links.*"
        elif len(content) > MAX_DESC:
            body = (
                content[:MAX_DESC]
                + f"\n\n*…content truncated. [Read full post →]({post_url})*"
            )
        else:
            body = content

        first_line = next(
            (ln.strip() for ln in content.splitlines() if ln.strip()), ""
        ) if content else ""
        if len(first_line) > MAX_TITLE:
            first_line = first_line[: MAX_TITLE - 3] + "…"
        title = first_line or "📢 New Community Post"

    embed = discord.Embed(
        title=title,
        url=post_url,
        description=f"{body}\n\n**[👉 {'Watch Stream' if is_live_stream else 'View Full Post'} on Facebook]({post_url})**",
        colour=colour,
    )

    if is_live_stream:
        embed.set_author(
            name=f"{author}  •  Shared a Live Stream",
            icon_url=_FB_ICON,
        )
    else:
        embed.set_author(
            name=f"{author}  •  Posted on Facebook",
            icon_url=_FB_ICON,
        )

    embed.add_field(name="🗓️  Posted", value=f"`{timestamp}`", inline=True)
    embed.add_field(name="📍  Source", value=_get_source_label(post_url), inline=True)
    
    if is_live_stream:
        embed.add_field(name="🎮  Type", value="`Live Stream`", inline=True)
    else:
        embed.add_field(name="\u200b", value="\u200b", inline=True)

    embed.add_field(name="\u200b", value="─" * 33, inline=False)

    # Set the primary image (first image in the gallery)
    if image_urls and len(image_urls) > 0:
        embed.set_image(url=image_urls[0])
    elif image_url:
        embed.set_image(url=image_url)
    embed.set_thumbnail(url=_FB_ICON)

    matched_source = None
    for src in getattr(config, "FACEBOOK_SOURCES", [config.FACEBOOK_GROUP_URL]):
        src_path = config.facebook_source_display_path(src)
        if src_path in post_url:
            matched_source = src
            break
    if not matched_source:
        matched_source = config.FACEBOOK_GROUP_URL
    source_display = config.facebook_source_display_path(matched_source)

    footer_text = f"{config.BOT_FOOTER}  •  {source_display}"
    if is_live_stream:
        footer_text = f"🔴 Streamer Highlight  •  {source_display}"
    
    # Add engagement metrics to footer if available
    engagement_parts = []
    if reaction_count is not None and reaction_count > 0:
        engagement_parts.append(f"❤️ {_format_count(reaction_count)}")
    if comment_count is not None and comment_count > 0:
        engagement_parts.append(f"💬 {_format_count(comment_count)}")
    if share_count is not None and share_count > 0:
        engagement_parts.append(f"🔄 {_format_count(share_count)}")
    
    if engagement_parts:
        footer_text += "  •  " + "  ".join(engagement_parts)
    
    embed.set_footer(
        text=footer_text,
        icon_url=_FB_ICON,
    )
    embed.timestamp = datetime.now(timezone.utc)

    return embed


def build_additional_image_embeds(
    image_urls: list[str],
    post_url: str,
    author: str,
) -> list[discord.Embed]:
    """
    Build additional embeds for remaining images in a gallery post.
    Returns a list of minimal embeds, one for each image after the first.
    """
    if len(image_urls) <= 1:
        return []
    
    additional_embeds = []
    for idx, img_url in enumerate(image_urls[1:], start=2):
        embed = discord.Embed(
            url=post_url,
            colour=_FACEBOOK_BLUE,
        )
        embed.set_image(url=img_url)
        embed.set_footer(
            text=f"Image {idx} of {len(image_urls)}  •  {author}",
            icon_url=_FB_ICON,
        )
        additional_embeds.append(embed)
    
    return additional_embeds


def build_sample_embed() -> discord.Embed:
    """Return a hardcoded sample embed used by the /testembed command."""
    return build_post_embed(
        author="Ran BY online GS",
        content=(
            "🎉 BY RAN ONLINE — SERVER UPDATE & PATCH NOTES\n\n"
            "Hey everyone! We've just pushed a major update to the server.\n\n"
            "📌 What's new:\n"
            "• HP and Defense of Mia and Lucian have been rebalanced.\n"
            "• New daily quests added for mid-tier players.\n"
            "• Bug fix: inventory duplication glitch patched.\n"
            "• Guild War registration window extended to 48 hours.\n\n"
            "⚠️ Maintenance window: June 17, 2026 from 2:00 AM – 4:00 AM (PHT)\n\n"
            "Please make sure to log out before maintenance starts to avoid rollbacks.\n"
            "Thank you for your continued support! 🙏"
        ),
        post_url=f"{config.FACEBOOK_GROUP_URL.rstrip('/')}/posts/123456789",
        timestamp="June 16, 2026 at 12:00 PM",
        image_url=None,
    )


def build_status_embed(
    bot_status: str,
    last_scan: str,
    total_posts: int,
) -> discord.Embed:
    """Build the rich embed returned by the /status slash command."""
    interval_minutes = config.CHECK_INTERVAL // 60
    interval_secs = config.CHECK_INTERVAL % 60
    if interval_secs:
        interval_label = f"Every {config.CHECK_INTERVAL}s"
    else:
        interval_label = f"Every {interval_minutes} minute{'s' if interval_minutes != 1 else ''}"

    seed_note = ""
    if config.SEED_ON_FIRST_RUN:
        seed_note = "\nFirst-run seed mode is **enabled** (existing posts are recorded without posting)."

    sources_list = ", ".join(config.facebook_source_display_path(s) for s in getattr(config, "FACEBOOK_SOURCES", [config.FACEBOOK_GROUP_URL]))

    embed = discord.Embed(
        title="📊  BY BOTS — Monitor Status",
        description=(
            "Real-time status of the Facebook → Discord forwarding bot.\n"
            f"Scanning: **{sources_list}** ({interval_label.lower()})."
            f"{seed_note}"
        ),
        colour=_SUCCESS_GREEN,
    )
    embed.set_author(name="BY BOTS System Status", icon_url=_FB_ICON)

    embed.add_field(name="🤖  Bot Status", value=f"`{bot_status}`", inline=False)
    embed.add_field(name="🔍  Last Facebook Scan", value=f"`{last_scan}`", inline=True)
    embed.add_field(name="📬  Total Posts Forwarded", value=f"`{total_posts}`", inline=True)
    embed.add_field(name="⏱️  Check Interval", value=f"`{interval_label}`", inline=True)

    if config.DISCORD_ROUTES:
        routes_desc = ""
        for keyword, channel_id in config.DISCORD_ROUTES.items():
            routes_desc += f"• **{keyword}** ➔ <#{channel_id}>\n"
        embed.add_field(name="🛣️  Routed Channels", value=routes_desc.strip(), inline=False)

    # Show author filtering status
    if config.FILTER_BY_AUTHOR and config.ALLOWED_AUTHORS:
        authors_list = ", ".join(f"`{author}`" for author in config.ALLOWED_AUTHORS[:5])
        if len(config.ALLOWED_AUTHORS) > 5:
            authors_list += f" *(+{len(config.ALLOWED_AUTHORS) - 5} more)*"
        embed.add_field(
            name="👤  Author Filter", 
            value=f"**Enabled** — Only forwarding posts from:\n{authors_list}", 
            inline=False
        )
    elif config.FILTER_BY_AUTHOR:
        embed.add_field(
            name="👤  Author Filter", 
            value="**Enabled** but no authors specified (all posts blocked)", 
            inline=False
        )

    embed.add_field(name="\u200b", value="─" * 33, inline=False)

    embed.set_thumbnail(url=_FB_ICON)
    embed.set_footer(text=config.BOT_FOOTER, icon_url=_FB_ICON)
    embed.timestamp = datetime.now(timezone.utc)
    return embed


def build_recent_posts_embed(posts: list[dict]) -> discord.Embed:
    """Build the embed returned by the /recent command showing last N posts."""
    embed = discord.Embed(
        title="📋  BY BOTS — Recent Posts",
        description="Last posts forwarded from the Facebook group to this channel.",
        colour=_FACEBOOK_BLUE,
    )
    embed.set_author(name="BY BOTS • Post History", icon_url=_FB_ICON)

    if not posts:
        embed.description = "*No posts have been forwarded yet.*"
    else:
        for i, post in enumerate(posts, start=1):
            embed.add_field(
                name=f"{i}. {post['author']}",
                value=(
                    f"[View Post]({post['post_url']})\n"
                    f"Posted: `{post['created_at']}`\n"
                    f"Stored: `{post['stored_at'][:19]} UTC`"
                ),
                inline=False,
            )

    embed.set_thumbnail(url=_FB_ICON)
    embed.set_footer(text=config.BOT_FOOTER, icon_url=_FB_ICON)
    embed.timestamp = datetime.now(timezone.utc)
    return embed
