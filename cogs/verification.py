"""
Verification Cog — Handles new member captcha verification flow.

When a user joins:
  1. Creates/updates their record in the database
  2. DMs them a verification link with an embedded captcha
  3. Logs the join event
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from captcha_server import create_verification_token
from config import get_settings
from database import get_session
from models import User, UserEvent
from utils.embed_factory import verification_embed

logger = logging.getLogger(__name__)
_settings = get_settings()


class VerificationCog(commands.Cog, name="Verification"):
    """Manages captcha-based user verification."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Triggered when a new member joins the server."""
        if member.bot:
            return

        logger.info("New member joined: %s (%d)", member, member.id)

        # Upsert user record in DB
        async with get_session() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(User).where(User.discord_id == member.id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    discord_id=member.id,
                    username=str(member),
                    display_name=member.display_name,
                    is_verified=False,
                    joined_at=datetime.now(timezone.utc),
                )
                session.add(user)
            else:
                user.username = str(member)
                user.display_name = member.display_name

            # Log join event
            event = UserEvent(
                user_id=member.id,
                event_type="join",
                details=f"User joined the server: {member} ({member.id})",
            )
            session.add(event)

        # Generate verification token and link
        token = create_verification_token(member.id)
        captcha_url = f"{_settings.captcha_server_url}/verify/{token}"

        # Build DM embed with button
        embed = verification_embed(captcha_url)
        view = VerifyButtonView(captcha_url)

        try:
            await member.send(embed=embed, view=view)
            logger.info("Sent verification DM to %s (%d)", member, member.id)
        except discord.Forbidden:
            logger.warning(
                "Cannot DM user %s (%d) — DMs are disabled. "
                "Consider posting in a #verification channel.",
                member,
                member.id,
            )
            # Fallback: try to post in a system channel
            if member.guild.system_channel:
                try:
                    await member.guild.system_channel.send(
                        f"{member.mention}, I couldn't DM you. "
                        f"Please enable DMs or click here to verify:",
                        embed=embed,
                        view=view,
                    )
                except discord.Forbidden:
                    logger.error("Cannot post in system channel either.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log when a member leaves the server."""
        if member.bot:
            return

        async with get_session() as session:
            event = UserEvent(
                user_id=member.id,
                event_type="leave",
                details=f"User left or was removed: {member} ({member.id})",
            )
            session.add(event)

        logger.info("Member left: %s (%d)", member, member.id)

    @discord.app_commands.command(
        name="reverify",
        description="Resend the verification link to a user",
    )
    @discord.app_commands.checks.has_permissions(manage_roles=True)
    async def reverify(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        """Manually resend verification to a user (mod command)."""
        await interaction.response.defer(ephemeral=True)
        if member.bot:
            await interaction.followup.send(
                "❌ Cannot verify bots.", ephemeral=True
            )
            return

        token = create_verification_token(member.id)
        captcha_url = f"{_settings.captcha_server_url}/verify/{token}"
        embed = verification_embed(captcha_url)
        view = VerifyButtonView(captcha_url)

        try:
            await member.send(embed=embed, view=view)
            await interaction.followup.send(
                f"✅ Verification link sent to {member.mention}.", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Could not DM {member.mention} — their DMs are disabled.",
                ephemeral=True,
            )


class VerifyButtonView(discord.ui.View):
    """A view containing a single 'Verify' button that links to the captcha page."""

    def __init__(self, url: str) -> None:
        super().__init__(timeout=1800)  # 30-minute timeout
        self.add_item(
            discord.ui.Button(
                label="🔒 Verify Now",
                style=discord.ButtonStyle.link,
                url=url,
            )
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(VerificationCog(bot))