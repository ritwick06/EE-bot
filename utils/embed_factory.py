"""
Reusable Discord embed builders for the moderation bot.

All embeds share a consistent visual style.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import discord


# ── Colour palette ───────────────────────────────────────────────────────────
class Colours:
    SUCCESS = discord.Colour(0x2ECC71)   # Green
    WARNING = discord.Colour(0xF39C12)   # Orange
    DANGER = discord.Colour(0xE74C3C)    # Red
    INFO = discord.Colour(0x3498DB)      # Blue
    NEUTRAL = discord.Colour(0x95A5A6)   # Grey
    VERIFY = discord.Colour(0x9B59B6)    # Purple


def mod_alert_embed(
    *,
    title: str,
    member: discord.Member,
    message_content: str,
    channel: discord.TextChannel | discord.abc.GuildChannel,
    severity: str,
    category: str,
    confidence: float,
    explanation: str,
) -> discord.Embed:
    """Build an embed for mod alerts triggered by automod."""
    colour = Colours.DANGER if severity == "SEVERE" else Colours.WARNING

    embed = discord.Embed(
        title=f"⚠️ {title}",
        colour=colour,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="👤 User",
        value=f"{member.mention} (`{member.display_name}`)",
        inline=True,
    )
    embed.add_field(name="📍 Channel", value=f"<#{channel.id}>", inline=True)
    embed.add_field(
        name="🔴 Severity",
        value=f"`{severity}` • {category}",
        inline=True,
    )
    embed.add_field(
        name="💬 Message",
        value=f"```\n{message_content[:1000]}\n```",
        inline=False,
    )
    embed.add_field(
        name="📋 Analysis",
        value=f"{explanation}\n**Confidence:** {confidence:.0%}",
        inline=False,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Use the buttons below to take action")
    return embed


def mod_action_embed(
    *,
    action: str,
    target: discord.Member | discord.User,
    moderator: discord.Member | discord.User,
    reason: str | None = None,
    duration: str | None = None,
) -> discord.Embed:
    """Build an embed confirming a moderation action."""
    action_icons = {
        "kick": "👢",
        "ban": "🔨",
        "warn": "⚠️",
        "timeout": "⏰",
        "unban": "✅",
    }
    icon = action_icons.get(action.lower(), "📋")

    embed = discord.Embed(
        title=f"{icon} Member {action.title()}ed",
        colour=Colours.DANGER if action in ("ban", "kick") else Colours.WARNING,
        timestamp=datetime.now(timezone.utc),
    )
    embed.add_field(
        name="Target",
        value=f"{target.mention} (`{target}`)",
        inline=True,
    )
    embed.add_field(
        name="Moderator",
        value=f"{moderator.mention}",
        inline=True,
    )
    if reason:
        embed.add_field(name="Reason", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duration", value=duration, inline=True)
    embed.set_thumbnail(url=target.display_avatar.url)
    return embed


def user_info_embed(
    *,
    member: discord.Member,
    is_verified: bool,
    warning_count: int,
    action_count: int,
    flagged_message_count: int,
    join_date: Optional[datetime] = None,
) -> discord.Embed:
    """Build an embed showing user information and history."""
    embed = discord.Embed(
        title=f"📋 User Info — {member.display_name}",
        colour=Colours.INFO,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="User", value=f"{member.mention}", inline=True)
    embed.add_field(name="ID", value=f"`{member.id}`", inline=True)
    embed.add_field(
        name="Verified",
        value="✅ Yes" if is_verified else "❌ No",
        inline=True,
    )
    embed.add_field(name="⚠️ Warnings", value=str(warning_count), inline=True)
    embed.add_field(name="🔨 Actions", value=str(action_count), inline=True)
    embed.add_field(
        name="🚩 Flagged Messages", value=str(flagged_message_count), inline=True
    )
    if join_date:
        embed.add_field(
            name="Joined",
            value=f"<t:{int(join_date.timestamp())}:R>",
            inline=True,
        )
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    if roles:
        embed.add_field(
            name="Roles",
            value=" ".join(roles[:15]),
            inline=False,
        )
    return embed


def verification_embed(captcha_url: str) -> discord.Embed:
    """Build the DM embed sent to new members for verification."""
    embed = discord.Embed(
        title="🔒 Verification Required",
        description=(
            "Welcome! To access the server, you need to verify that you're human.\n\n"
            "Click the button below to complete a quick captcha verification."
        ),
        colour=Colours.VERIFY,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="This link expires in 30 minutes")
    return embed


def success_embed(title: str, description: str) -> discord.Embed:
    """Generic success embed."""
    return discord.Embed(
        title=f"✅ {title}",
        description=description,
        colour=Colours.SUCCESS,
        timestamp=datetime.now(timezone.utc),
    )


def error_embed(title: str, description: str) -> discord.Embed:
    """Generic error embed."""
    return discord.Embed(
        title=f"❌ {title}",
        description=description,
        colour=Colours.DANGER,
        timestamp=datetime.now(timezone.utc),
    )
