"""
AutoMod Cog — Automatic message scanning for blacklisted content.

Scans every message against the blacklist word filter.
On detection → deletes message, sends alert embed to mod channel with action buttons.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord.ext import commands

from config import get_settings
from database import get_session
from models import Message, ModAction, User, UserEvent, Warning
from utils.blacklist import blacklist_filter
from utils.embed_factory import Colours, mod_alert_embed, mod_action_embed

logger = logging.getLogger(__name__)
_settings = get_settings()


class AutoModCog(commands.Cog, name="AutoMod"):

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Scan every message for blacklisted content."""
        if message.author.bot or message.guild is None:
            return

        content = message.content
        if not content:
            return

        member = message.author
        assert isinstance(member, discord.Member)

        is_blacklisted, matched_words = blacklist_filter.check(content)

        if is_blacklisted:
            await self._flag_message(
                message=message,
                matched_words=matched_words,
            )

    async def _flag_message(
        self,
        *,
        message: discord.Message,
        matched_words: list[str],
    ) -> None:
        """Flag a message, delete it, and send an alert to the mod channel."""
        member = message.author
        assert isinstance(member, discord.Member)
        explanation = f"Blacklisted words detected: {', '.join(matched_words)}"

        await self._log_message(
            message,
            flagged=True,
            flag_reason=explanation,
            flag_severity="SEVERE",
        )

        async with get_session() as session:
            event = UserEvent(
                user_id=member.id,
                event_type="message_flagged",
                details=f"Blacklisted words: {', '.join(matched_words)}",
            )
            session.add(event)

        mod_channel = self.bot.get_channel(_settings.mod_channel_id)
        if mod_channel is None or not isinstance(mod_channel, discord.TextChannel):
            logger.error("Mod channel %d not found!", _settings.mod_channel_id)
            return

        embed = mod_alert_embed(
            title="Blacklisted Content Detected",
            member=member,
            message_content=message.content,
            channel=message.channel,
            severity="SEVERE",
            category="blacklisted_word",
            confidence=1.0,
            explanation=explanation,
        )

        view = ModActionView(
            target_id=member.id,
            message_id=message.id,
            channel_id=message.channel.id,
        )

        ping_content = ""
        if _settings.mod_role_id:
            ping_content = f"<@&{_settings.mod_role_id}> 🚨 Blacklisted word detected!"

        await mod_channel.send(content=ping_content, embed=embed, view=view)

        try:
            await message.delete()
            logger.info(
                "Auto-deleted blacklisted message from %s (%d): %s",
                member, member.id, ', '.join(matched_words),
            )
        except discord.Forbidden:
            logger.warning(
                "Cannot delete message from %s — missing permissions.", member
            )
        except discord.NotFound:
            pass

    async def _log_message(
        self,
        message: discord.Message,
        *,
        flagged: bool = False,
        flag_reason: str | None = None,
        flag_severity: str | None = None,
    ) -> None:
        """Log a message to the database."""
        async with get_session() as session:
            from sqlalchemy import select

            # Ensure user exists
            result = await session.execute(
                select(User).where(User.discord_id == message.author.id)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    discord_id=message.author.id,
                    username=str(message.author),
                    display_name=message.author.display_name,
                    is_verified=False,
                )
                session.add(user)
                await session.flush()

            msg_record = Message(
                message_id=message.id,
                user_id=message.author.id,
                guild_id=message.guild.id if message.guild else 0,
                channel_id=message.channel.id,
                content=message.content[:4000],  
                flagged=flagged,
                flag_reason=flag_reason,
                flag_severity=flag_severity,
            )
            session.add(msg_record)


class ModActionView(discord.ui.View):
    """
    Interactive buttons for moderators to take action on flagged messages.

    Each button executes a mod action and logs it to the database.
    """

    def __init__(
        self,
        target_id: int,
        message_id: int,
        channel_id: int,
    ) -> None:
        super().__init__(timeout=None)
        self.target_id = target_id
        self.message_id = message_id
        self.channel_id = channel_id

    async def _get_target_member(
        self, interaction: discord.Interaction
    ) -> Optional[discord.Member]:
        """Fetch the target member from the guild."""
        if interaction.guild is None:
            return None
        member = interaction.guild.get_member(self.target_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(self.target_id)
            except discord.NotFound:
                return None
        return member

    async def _check_permissions(
        self, interaction: discord.Interaction
    ) -> bool:
        """Ensure only moderators can use these buttons."""
        assert isinstance(interaction.user, discord.Member)
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(
                "❌ You don't have permission to do this.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="⚠️ Warn",
        style=discord.ButtonStyle.secondary,
        custom_id="mod_action:warn",
    )
    async def warn_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._check_permissions(interaction):
            return

        member = await self._get_target_member(interaction)
        if member is None:
            await interaction.response.send_message(
                "❌ User not found in server.", ephemeral=True
            )
            return

        # Log warning to DB
        async with get_session() as session:
            warning = Warning(
                user_id=member.id,
                reason="Flagged message — blacklisted content",
                issued_by=interaction.user.id,
            )
            session.add(warning)
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="warn",
                reason="Flagged message — blacklisted content",
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="warned",
                details=f"Warned by {interaction.user} via automod alert",
            )
            session.add(event)

        try:
            await member.send(
                f"⚠️ **Warning** — You have been warned in **{interaction.guild.name}** "
                f"for using blacklisted words. Please review the server rules."
            )
        except discord.Forbidden:
            pass

        embed = mod_action_embed(
            action="warn",
            target=member,
            moderator=interaction.user,
            reason="Flagged message — blacklisted content",
        )
        await interaction.response.send_message(embed=embed)
        self._disable_buttons()
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="⏰ Timeout (1h)",
        style=discord.ButtonStyle.primary,
        custom_id="mod_action:timeout",
    )
    async def timeout_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._check_permissions(interaction):
            return

        member = await self._get_target_member(interaction)
        if member is None:
            await interaction.response.send_message(
                "❌ User not found in server.", ephemeral=True
            )
            return

        duration = timedelta(hours=1)
        try:
            await member.timeout(duration, reason="Automod — blacklisted content")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to timeout this user.", ephemeral=True
            )
            return

        async with get_session() as session:
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="timeout",
                reason="Flagged message — blacklisted content",
                duration_minutes=60,
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="timed_out",
                details=f"Timed out for 1h by {interaction.user} via automod alert",
            )
            session.add(event)

        embed = mod_action_embed(
            action="timeout",
            target=member,
            moderator=interaction.user,
            reason="Blacklisted content",
            duration="1 hour",
        )
        await interaction.response.send_message(embed=embed)
        self._disable_buttons()
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="👢 Kick",
        style=discord.ButtonStyle.danger,
        custom_id="mod_action:kick",
    )
    async def kick_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._check_permissions(interaction):
            return

        member = await self._get_target_member(interaction)
        if member is None:
            await interaction.response.send_message(
                "❌ User not found in server.", ephemeral=True
            )
            return

        try:
            await member.send(
                f"👢 You have been **kicked** from **{interaction.guild.name}** "
                f"for using blacklisted words."
            )
        except discord.Forbidden:
            pass

        try:
            await member.kick(reason="Automod — blacklisted content")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to kick this user.", ephemeral=True
            )
            return

        async with get_session() as session:
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="kick",
                reason="Flagged message — blacklisted content",
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="kicked",
                details=f"Kicked by {interaction.user} via automod alert",
            )
            session.add(event)

        embed = mod_action_embed(
            action="kick",
            target=member,
            moderator=interaction.user,
            reason="Blacklisted content",
        )
        await interaction.response.send_message(embed=embed)
        self._disable_buttons()
        await interaction.message.edit(view=self)

    @discord.ui.button(
        label="🔨 Ban",
        style=discord.ButtonStyle.danger,
        custom_id="mod_action:ban",
    )
    async def ban_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not await self._check_permissions(interaction):
            return

        member = await self._get_target_member(interaction)
        if member is None:
            await interaction.response.send_message(
                "❌ User not found in server.", ephemeral=True
            )
            return

        try:
            await member.send(
                f"🔨 You have been **banned** from **{interaction.guild.name}** "
                f"for using blacklisted words."
            )
        except discord.Forbidden:
            pass

        try:
            await interaction.guild.ban(
                member,
                reason="Automod — blacklisted content",
                delete_message_days=1,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to ban this user.", ephemeral=True
            )
            return

        async with get_session() as session:
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="ban",
                reason="Flagged message — blacklisted content",
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="banned",
                details=f"Banned by {interaction.user} via automod alert",
            )
            session.add(event)

        embed = mod_action_embed(
            action="ban",
            target=member,
            moderator=interaction.user,
            reason="Blacklisted content",
        )
        await interaction.response.send_message(embed=embed)
        self._disable_buttons()
        await interaction.message.edit(view=self)

    def _disable_buttons(self) -> None:
        """Disable all buttons after an action is taken."""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoModCog(bot))
