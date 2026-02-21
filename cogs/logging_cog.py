"""
Logging Cog — Passive event listeners for comprehensive audit logging.

Logs the following events to the database AND mod channel:
  - Member join / leave
  - Role changes & nickname changes
  - Timeout applied / removed
  - Message edits, deletes, and bulk deletes
  - Bans & unbans (including external ones)
  - Voice state changes (join/leave/move channels)
  - Channel create/delete/update
  - Username/avatar changes
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

from config import get_settings
from database import get_session
from models import User, UserEvent
from utils.embed_factory import Colours

logger = logging.getLogger(__name__)
_settings = get_settings()


class LoggingCog(commands.Cog, name="Logging"):
    """Passive audit logging for user events."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ── Member Join / Leave ──────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Log member joins."""
        if member.bot:
            return

        async with get_session() as session:
            await self._ensure_user(session, member)
            event = UserEvent(
                user_id=member.id,
                event_type="join",
                details=f"Joined {member.guild.name}",
            )
            session.add(event)

        await self._send_log(
            f"📥 **Member Joined** — {member.mention} ({member})\n"
            f"Account created: <t:{int(member.created_at.timestamp())}:R>"
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Log member leaves/kicks."""
        if member.bot:
            return

        async with get_session() as session:
            await self._ensure_user(session, member)
            event = UserEvent(
                user_id=member.id,
                event_type="leave",
                details=f"Left/Kicked from {member.guild.name}",
            )
            session.add(event)

        roles = ", ".join(r.name for r in member.roles if r.name != "@everyone")
        await self._send_log(
            f"📤 **Member Left** — {member} (`{member.id}`)\n"
            f"Roles: {roles or 'None'}"
        )


    @commands.Cog.listener()
    async def on_member_update(
        self, before: discord.Member, after: discord.Member
    ) -> None:
        """Log role changes, nickname changes, and timeout changes."""
        if before.bot:
            return

        added_roles = set(after.roles) - set(before.roles)
        removed_roles = set(before.roles) - set(after.roles)

        if added_roles or removed_roles:
            details_parts: list[str] = []
            if added_roles:
                names = ", ".join(r.name for r in added_roles)
                details_parts.append(f"Roles added: {names}")
            if removed_roles:
                names = ", ".join(r.name for r in removed_roles)
                details_parts.append(f"Roles removed: {names}")

            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="role_change",
                    details=" | ".join(details_parts),
                )
                session.add(event)

            await self._send_log(
                f"🏷️ **Role Update** — {after.mention}\n{' | '.join(details_parts)}"
            )

        if before.nick != after.nick:
            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="nickname_change",
                    details=f"'{before.nick}' → '{after.nick}'",
                )
                session.add(event)

            await self._send_log(
                f"✏️ **Nickname Change** — {after.mention}\n"
                f"`{before.nick or before.name}` → `{after.nick or after.name}`"
            )

        before_timeout = before.timed_out_until
        after_timeout = after.timed_out_until
        now = datetime.now(timezone.utc)

        if (before_timeout is None or before_timeout <= now) and (
            after_timeout is not None and after_timeout > now
        ):
            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="timeout_applied",
                    details=f"Timed out until <t:{int(after_timeout.timestamp())}:F>",
                )
                session.add(event)

            await self._send_log(
                f"⏰ **Timeout Applied** — {after.mention}\n"
                f"Until: <t:{int(after_timeout.timestamp())}:F> "
                f"(<t:{int(after_timeout.timestamp())}:R>)"
            )

        elif (before_timeout is not None and before_timeout > now) and (
            after_timeout is None or after_timeout <= now
        ):
            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="timeout_removed",
                    details="Timeout was removed",
                )
                session.add(event)

            await self._send_log(
                f"✅ **Timeout Removed** — {after.mention}"
            )


    @commands.Cog.listener()
    async def on_user_update(
        self, before: discord.User, after: discord.User
    ) -> None:
        """Log username and avatar changes."""
        if before.bot:
            return

        if str(before) != str(after):
            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="username_change",
                    details=f"'{before}' → '{after}'",
                )
                session.add(event)

            await self._send_log(
                f"📛 **Username Change** — <@{after.id}>\n`{before}` → `{after}`"
            )

        if before.avatar != after.avatar:
            async with get_session() as session:
                await self._ensure_user(session, after)
                event = UserEvent(
                    user_id=after.id,
                    event_type="avatar_change",
                    details="User changed their avatar",
                )
                session.add(event)

            await self._send_log(
                f"🖼️ **Avatar Changed** — <@{after.id}>"
            )


    @commands.Cog.listener()
    async def on_message_edit(
        self, before: discord.Message, after: discord.Message
    ) -> None:
        """Log message edits."""
        if before.author.bot or before.content == after.content:
            return

        async with get_session() as session:
            await self._ensure_user(session, before.author)
            event = UserEvent(
                user_id=before.author.id,
                event_type="message_edit",
                details=(
                    f"Channel: #{before.channel} | "
                    f"Before: {before.content[:500]} | "
                    f"After: {after.content[:500]}"
                ),
            )
            session.add(event)

        await self._send_log(
            f"✏️ **Message Edited** — {before.author.mention} in <#{before.channel.id}>\n"
            f"**Before:** {before.content[:200]}\n"
            f"**After:** {after.content[:200]}"
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        """Log message deletions."""
        if message.author.bot:
            return

        async with get_session() as session:
            await self._ensure_user(session, message.author)
            event = UserEvent(
                user_id=message.author.id,
                event_type="message_delete",
                details=(
                    f"Channel: #{message.channel} | "
                    f"Content: {message.content[:500]}"
                ),
            )
            session.add(event)

        await self._send_log(
            f"🗑️ **Message Deleted** — {message.author.mention} in <#{message.channel.id}>\n"
            f"**Content:** {message.content[:300] or '*[empty/embed]*'}"
        )

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]) -> None:
        """Log bulk message deletions (e.g. from /purge)."""
        if not messages:
            return

        channel = messages[0].channel
        authors = set()
        for msg in messages:
            if not msg.author.bot:
                authors.add(msg.author.id)

        for author_id in authors:
            async with get_session() as session:
                event = UserEvent(
                    user_id=author_id,
                    event_type="bulk_message_delete",
                    details=(
                        f"Channel: #{channel} | "
                        f"{len(messages)} messages bulk deleted"
                    ),
                )
                session.add(event)

        await self._send_log(
            f"🗑️ **Bulk Delete** — **{len(messages)}** messages deleted in <#{channel.id}>\n"
            f"Authors: {', '.join(f'<@{uid}>' for uid in list(authors)[:10])}"
        )


    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        """Log bans (including those not done via our commands)."""
        async with get_session() as session:
            await self._ensure_user(session, user)
            event = UserEvent(
                user_id=user.id,
                event_type="banned",
                details=f"User banned from {guild.name}",
            )
            session.add(event)

        await self._send_log(f"🔨 **Member Banned** — {user} (`{user.id}`)")

    @commands.Cog.listener()
    async def on_member_unban(
        self, guild: discord.Guild, user: discord.User
    ) -> None:
        """Log unbans."""
        async with get_session() as session:
            await self._ensure_user(session, user)
            event = UserEvent(
                user_id=user.id,
                event_type="unbanned",
                details=f"User unbanned from {guild.name}",
            )
            session.add(event)

        await self._send_log(f"✅ **Member Unbanned** — {user} (`{user.id}`)")


    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Log voice channel joins, leaves, and moves."""
        if member.bot:
            return

        if before.channel is None and after.channel is not None:
            async with get_session() as session:
                await self._ensure_user(session, member)
                event = UserEvent(
                    user_id=member.id,
                    event_type="voice_join",
                    details=f"Joined voice channel: #{after.channel.name}",
                )
                session.add(event)

            await self._send_log(
                f"🔊 **Voice Join** — {member.mention} joined **{after.channel.name}**"
            )

        elif before.channel is not None and after.channel is None:
            async with get_session() as session:
                await self._ensure_user(session, member)
                event = UserEvent(
                    user_id=member.id,
                    event_type="voice_leave",
                    details=f"Left voice channel: #{before.channel.name}",
                )
                session.add(event)

            await self._send_log(
                f"🔇 **Voice Leave** — {member.mention} left **{before.channel.name}**"
            )

        elif (
            before.channel is not None
            and after.channel is not None
            and before.channel != after.channel
        ):
            async with get_session() as session:
                await self._ensure_user(session, member)
                event = UserEvent(
                    user_id=member.id,
                    event_type="voice_move",
                    details=f"Moved: #{before.channel.name} → #{after.channel.name}",
                )
                session.add(event)

            await self._send_log(
                f"🔀 **Voice Move** — {member.mention}: "
                f"**{before.channel.name}** → **{after.channel.name}**"
            )


    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel) -> None:
        await self._send_log(
            f"📁 **Channel Created** — #{channel.name} (`{channel.id}`) "
            f"Type: {channel.type}"
        )

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        await self._send_log(
            f"📁 **Channel Deleted** — #{channel.name} (`{channel.id}`) "
            f"Type: {channel.type}"
        )

    @commands.Cog.listener()
    async def on_guild_channel_update(
        self,
        before: discord.abc.GuildChannel,
        after: discord.abc.GuildChannel,
    ) -> None:
        changes: list[str] = []
        if before.name != after.name:
            changes.append(f"Name: `{before.name}` → `{after.name}`")
        if hasattr(before, "topic") and hasattr(after, "topic"):
            if before.topic != after.topic:
                changes.append("Topic changed")

        if changes:
            await self._send_log(
                f"📁 **Channel Updated** — #{after.name}\n" + "\n".join(changes)
            )


    async def _send_log(self, content: str) -> None:
        """Send a log message to the mod channel."""
        mod_channel = self.bot.get_channel(_settings.mod_channel_id)
        if mod_channel is None or not isinstance(mod_channel, discord.TextChannel):
            return

        embed = discord.Embed(
            description=content,
            colour=Colours.NEUTRAL,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Audit Log")
        try:
            await mod_channel.send(embed=embed)
        except discord.Forbidden:
            logger.warning("Cannot send to mod channel — missing permissions.")

    @staticmethod
    async def _ensure_user(session, member: discord.Member | discord.User) -> None:
        """Ensure a user record exists in the DB."""
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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LoggingCog(bot))
