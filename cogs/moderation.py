"""
Moderation Cog — Explicit slash commands for server moderators.

Commands:
  /warn     <user> <reason>           — Issue a warning
  /kick     <user> [reason]           — Kick a member
  /ban      <user> [reason]           — Ban a member
  /timeout  <user> <duration> [reason] — Timeout a member
  /unban    <user_id> [reason]        — Unban a user
  /userinfo <user>                    — View user history
  /modlog   [user] [limit]            — View recent mod actions
"""

from __future__ import annotations

import logging
from datetime import timedelta, datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import get_settings
from database import get_session
from models import Message, ModAction, User, UserEvent, Warning
from utils.embed_factory import (
    Colours,
    error_embed,
    mod_action_embed,
    success_embed,
    user_info_embed,
)

logger = logging.getLogger(__name__)
_settings = get_settings()


class ModerationCog(commands.Cog, name="Moderation"):
    """Explicit moderation commands for server staff."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── /warn ────────────────────────────────────────────────────────────

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to warn", reason="Reason for the warning")
    async def warn(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str,
    ) -> None:
        if member.bot:
            await interaction.response.send_message(
                embed=error_embed("Error", "Cannot warn bots."), ephemeral=True
            )
            return

        async with get_session() as session:
            # Ensure user exists
            await self._ensure_user(session, member)

            warning = Warning(
                user_id=member.id,
                reason=reason,
                issued_by=interaction.user.id,
            )
            session.add(warning)

            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="warn",
                reason=reason,
            )
            session.add(action)

            event = UserEvent(
                user_id=member.id,
                event_type="warned",
                details=f"Warned by {interaction.user}: {reason}",
            )
            session.add(event)

        # DM the user
        try:
            await member.send(
                f"⚠️ **Warning** — You have been warned in **{interaction.guild.name}**.\n"
                f"**Reason:** {reason}"
            )
        except discord.Forbidden:
            pass

        # Log moderator activity
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            mod_event = UserEvent(
                user_id=interaction.user.id,
                event_type="mod_action_performed",
                details=f"Warned {member} ({member.id}): {reason}",
            )
            session.add(mod_event)

        embed = mod_action_embed(
            action="warn",
            target=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(embed=embed)
        logger.info("%s warned %s: %s", interaction.user, member, reason)

    # ── /kick ────────────────────────────────────────────────────────────

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.describe(
        member="The member to kick", reason="Reason for the kick"
    )
    async def kick(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        if member.bot:
            await interaction.response.send_message(
                embed=error_embed("Error", "Cannot kick bots via this command."),
                ephemeral=True,
            )
            return

        # Hierarchy check
        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Error",
                    "You cannot kick a member with equal or higher role.",
                ),
                ephemeral=True,
            )
            return

        # DM before kick
        try:
            await member.send(
                f"👢 You have been **kicked** from **{interaction.guild.name}**.\n"
                f"**Reason:** {reason}"
            )
        except discord.Forbidden:
            pass

        try:
            await member.kick(reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Error", "I don't have permission to kick this user."),
                ephemeral=True,
            )
            return

        async with get_session() as session:
            await self._ensure_user(session, member)
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="kick",
                reason=reason,
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="kicked",
                details=f"Kicked by {interaction.user}: {reason}",
            )
            session.add(event)

        # Log moderator activity
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            mod_event = UserEvent(
                user_id=interaction.user.id,
                event_type="mod_action_performed",
                details=f"Kicked {member} ({member.id}): {reason}",
            )
            session.add(mod_event)

        embed = mod_action_embed(
            action="kick",
            target=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(embed=embed)
        logger.info("%s kicked %s: %s", interaction.user, member, reason)

    # ── /ban ─────────────────────────────────────────────────────────────

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        member="The member to ban", reason="Reason for the ban"
    )
    async def ban(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        if member.bot:
            await interaction.response.send_message(
                embed=error_embed("Error", "Cannot ban bots via this command."),
                ephemeral=True,
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Error",
                    "You cannot ban a member with equal or higher role.",
                ),
                ephemeral=True,
            )
            return

        # DM before ban
        try:
            await member.send(
                f"🔨 You have been **banned** from **{interaction.guild.name}**.\n"
                f"**Reason:** {reason}"
            )
        except discord.Forbidden:
            pass

        try:
            await interaction.guild.ban(
                member,
                reason=f"{interaction.user}: {reason}",
                delete_message_days=1,
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed("Error", "I don't have permission to ban this user."),
                ephemeral=True,
            )
            return

        async with get_session() as session:
            await self._ensure_user(session, member)
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="ban",
                reason=reason,
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="banned",
                details=f"Banned by {interaction.user}: {reason}",
            )
            session.add(event)

        # Log moderator activity
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            mod_event = UserEvent(
                user_id=interaction.user.id,
                event_type="mod_action_performed",
                details=f"Banned {member} ({member.id}): {reason}",
            )
            session.add(mod_event)

        embed = mod_action_embed(
            action="ban",
            target=member,
            moderator=interaction.user,
            reason=reason,
        )
        await interaction.response.send_message(embed=embed)
        logger.info("%s banned %s: %s", interaction.user, member, reason)

    # ── /timeout ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="timeout", description="Timeout a member for a specified duration"
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.describe(
        member="The member to timeout",
        minutes="Duration in minutes (max 40320 = 28 days)",
        reason="Reason for the timeout",
    )
    async def timeout(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: Optional[str] = "No reason provided",
    ) -> None:
        if member.bot:
            await interaction.response.send_message(
                embed=error_embed("Error", "Cannot timeout bots."), ephemeral=True
            )
            return

        if member.top_role >= interaction.user.top_role:
            await interaction.response.send_message(
                embed=error_embed(
                    "Error",
                    "You cannot timeout a member with equal or higher role.",
                ),
                ephemeral=True,
            )
            return

        duration = timedelta(minutes=minutes)
        try:
            await member.timeout(duration, reason=f"{interaction.user}: {reason}")
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    "Error", "I don't have permission to timeout this user."
                ),
                ephemeral=True,
            )
            return

        async with get_session() as session:
            await self._ensure_user(session, member)
            action = ModAction(
                target_user_id=member.id,
                moderator_id=interaction.user.id,
                action_type="timeout",
                reason=reason,
                duration_minutes=minutes,
            )
            session.add(action)
            event = UserEvent(
                user_id=member.id,
                event_type="timed_out",
                details=f"Timed out for {minutes}m by {interaction.user}: {reason}",
            )
            session.add(event)

        # Format duration for display
        if minutes >= 1440:
            dur_str = f"{minutes // 1440}d {(minutes % 1440) // 60}h"
        elif minutes >= 60:
            dur_str = f"{minutes // 60}h {minutes % 60}m"
        else:
            dur_str = f"{minutes}m"

        try:
            await member.send(
                f"⏰ You have been **timed out** in **{interaction.guild.name}** "
                f"for **{dur_str}**.\n**Reason:** {reason}"
            )
        except discord.Forbidden:
            pass

        embed = mod_action_embed(
            action="timeout",
            target=member,
            moderator=interaction.user,
            reason=reason,
            duration=dur_str,
        )
        # Log moderator activity
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            mod_event = UserEvent(
                user_id=interaction.user.id,
                event_type="mod_action_performed",
                details=f"Timed out {member} ({member.id}) for {dur_str}: {reason}",
            )
            session.add(mod_event)

        await interaction.response.send_message(embed=embed)
        logger.info(
            "%s timed out %s for %s: %s",
            interaction.user, member, dur_str, reason,
        )

    # ── /unban ───────────────────────────────────────────────────────────

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(
        user_id="The Discord user ID to unban", reason="Reason for the unban"
    )
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: Optional[str] = "No reason provided",
    ) -> None:
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(
                embed=error_embed("Error", "Invalid user ID."), ephemeral=True
            )
            return

        try:
            user = await self.bot.fetch_user(uid)
            await interaction.guild.unban(user, reason=f"{interaction.user}: {reason}")
        except discord.NotFound:
            await interaction.response.send_message(
                embed=error_embed("Error", "This user is not banned."),
                ephemeral=True,
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                embed=error_embed(
                    "Error", "I don't have permission to unban this user."
                ),
                ephemeral=True,
            )
            return

        async with get_session() as session:
            action = ModAction(
                target_user_id=uid,
                moderator_id=interaction.user.id,
                action_type="unban",
                reason=reason,
            )
            session.add(action)

        # Log moderator activity
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            mod_event = UserEvent(
                user_id=interaction.user.id,
                event_type="mod_action_performed",
                details=f"Unbanned {user} ({uid}): {reason}",
            )
            session.add(mod_event)

        await interaction.response.send_message(
            embed=success_embed("User Unbanned", f"**{user}** has been unbanned.")
        )
        logger.info("%s unbanned %s: %s", interaction.user, user, reason)

    # ── /purge ───────────────────────────────────────────────────────────

    @app_commands.command(
        name="purge", description="Bulk delete messages from a channel"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        amount="Number of messages to delete (1–100)",
        member="Optional: only delete messages from this member",
    )
    async def purge(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        member: Optional[discord.Member] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send(
                embed=error_embed("Error", "This command can only be used in text channels."),
                ephemeral=True,
            )
            return

        def check(msg: discord.Message) -> bool:
            if member:
                return msg.author.id == member.id
            return True

        try:
            deleted = await channel.purge(limit=amount, check=check)
        except discord.Forbidden:
            await interaction.followup.send(
                embed=error_embed("Error", "I don't have permission to delete messages."),
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(
                embed=error_embed("Error", f"Failed to purge: {e}"),
                ephemeral=True,
            )
            return

        # Log to DB
        target_info = f" from {member}" if member else ""
        async with get_session() as session:
            await self._ensure_user(session, interaction.user)
            action = ModAction(
                target_user_id=member.id if member else interaction.user.id,
                moderator_id=interaction.user.id,
                action_type="purge",
                reason=f"Purged {len(deleted)} messages{target_info} in #{channel.name}",
            )
            session.add(action)
            event = UserEvent(
                user_id=interaction.user.id,
                event_type="purge",
                details=f"Purged {len(deleted)} messages{target_info} in #{channel.name}",
            )
            session.add(event)

        await interaction.followup.send(
            embed=success_embed(
                "Messages Purged",
                f"🗑️ Deleted **{len(deleted)}** messages{target_info} in {channel.mention}.",
            ),
            ephemeral=True,
        )
        logger.info(
            "%s purged %d messages%s in #%s",
            interaction.user, len(deleted), target_info, channel.name,
        )

    # ── /userinfo ────────────────────────────────────────────────────────

    @app_commands.command(
        name="userinfo", description="View a user's moderation history"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(member="The member to look up")
    async def userinfo(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
    ) -> None:
        await interaction.response.defer()
        from sqlalchemy import func, select

        async with get_session() as session:
            # Warning count
            warning_result = await session.execute(
                select(func.count(Warning.id)).where(Warning.user_id == member.id)
            )
            warning_count = warning_result.scalar() or 0

            # Mod action count
            action_result = await session.execute(
                select(func.count(ModAction.id)).where(
                    ModAction.target_user_id == member.id
                )
            )
            action_count = action_result.scalar() or 0

            # Flagged message count
            flagged_result = await session.execute(
                select(func.count(Message.id)).where(
                    Message.user_id == member.id, Message.flagged == True
                )
            )
            flagged_count = flagged_result.scalar() or 0

            # User record
            user_result = await session.execute(
                select(User).where(User.discord_id == member.id)
            )
            user = user_result.scalar_one_or_none()

        embed = user_info_embed(
            member=member,
            is_verified=user.is_verified if user else False,
            warning_count=warning_count,
            action_count=action_count,
            flagged_message_count=flagged_count,
            join_date=user.joined_at if user else member.joined_at,
        )
        await interaction.followup.send(embed=embed)

    # ── /modlog ──────────────────────────────────────────────────────────

    @app_commands.command(
        name="modlog", description="View recent moderation actions"
    )
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.describe(
        member="Optional: filter by member",
        limit="Number of entries to show (default 10, max 25)",
    )
    async def modlog(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        limit: app_commands.Range[int, 1, 25] = 10,
    ) -> None:
        await interaction.response.defer()
        from sqlalchemy import select

        async with get_session() as session:
            query = select(ModAction).order_by(ModAction.created_at.desc()).limit(limit)
            if member:
                query = query.where(ModAction.target_user_id == member.id)

            result = await session.execute(query)
            actions = result.scalars().all()

        if not actions:
            await interaction.followup.send(
                embed=error_embed("Mod Log", "No moderation actions found."),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="📋 Moderation Log",
            colour=Colours.INFO,
            timestamp=datetime.now(timezone.utc),
        )

        for action in actions:
            moderator = self.bot.get_user(action.moderator_id)
            mod_name = str(moderator) if moderator else f"ID:{action.moderator_id}"
            target = self.bot.get_user(action.target_user_id)
            target_name = str(target) if target else f"ID:{action.target_user_id}"

            value = (
                f"**Target:** {target_name}\n"
                f"**Mod:** {mod_name}\n"
                f"**Reason:** {action.reason or 'N/A'}"
            )
            if action.duration_minutes:
                value += f"\n**Duration:** {action.duration_minutes}m"

            timestamp = (
                f"<t:{int(action.created_at.timestamp())}:R>"
                if action.created_at
                else "Unknown"
            )
            embed.add_field(
                name=f"{action.action_type.upper()} • {timestamp}",
                value=value,
                inline=False,
            )

        await interaction.followup.send(embed=embed)

    # ── /stafflog ─────────────────────────────────────────────────────────

    @app_commands.command(
        name="stafflog", description="View recent moderator activity"
    )
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        moderator="Optional: filter by moderator",
        limit="Number of entries to show (default 15, max 25)",
    )
    async def stafflog(
        self,
        interaction: discord.Interaction,
        moderator: Optional[discord.Member] = None,
        limit: app_commands.Range[int, 1, 25] = 15,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        from sqlalchemy import select

        async with get_session() as session:
            query = (
                select(UserEvent)
                .where(UserEvent.event_type == "mod_action_performed")
                .order_by(UserEvent.created_at.desc())
                .limit(limit)
            )
            if moderator:
                query = query.where(UserEvent.user_id == moderator.id)

            result = await session.execute(query)
            events = result.scalars().all()

        if not events:
            await interaction.followup.send(
                embed=error_embed("Staff Log", "No moderator activity found."),
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🛡️ Staff Activity Log",
            colour=Colours.INFO,
            timestamp=datetime.now(timezone.utc),
        )

        for event in events:
            mod = self.bot.get_user(event.user_id)
            mod_name = str(mod) if mod else f"ID:{event.user_id}"

            timestamp = (
                f"<t:{int(event.created_at.timestamp())}:R>"
                if event.created_at
                else "Unknown"
            )
            embed.add_field(
                name=f"{mod_name} • {timestamp}",
                value=event.details[:200] if event.details else "No details",
                inline=False,
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ── Helpers ──────────────────────────────────────────────────────────

    @staticmethod
    async def _ensure_user(session, member: discord.Member | discord.User) -> None:
        """Make sure a user record exists in the DB."""
        from sqlalchemy import select

        result = await session.execute(
            select(User).where(User.discord_id == member.id)
        )
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                discord_id=member.id,
                username=str(member),
                display_name=getattr(member, "display_name", str(member)),
                is_verified=False,
            )
            session.add(user)
            await session.flush()

    # ── Error handlers ───────────────────────────────────────────────────

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            embed = error_embed(
                "Permission Denied",
                "You don't have the required permissions for this command.",
            )
        else:
            logger.error("Moderation command error: %s", error, exc_info=True)
            embed = error_embed("Error", "An unexpected error occurred.")

        try:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
