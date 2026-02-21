"""
Discord Moderation Bot — Main Entrypoint

Initializes the bot, loads all cogs, starts the captcha web server,
and connects to Discord.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import discord
from discord.ext import commands

from captcha_server import CaptchaServer
from config import configure_logging, get_settings
from database import close_db, init_db

# ── Load settings and configure logging at module level ──────────────────────
settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)

# ── Cogs to load ─────────────────────────────────────────────────────────────
EXTENSIONS: list[str] = [
    "cogs.verification",
    "cogs.automod",
    "cogs.moderation",
    "cogs.logging_cog",
    "cogs.welcome",
]


class ModBot(commands.Bot):
    """
    Custom bot subclass with async lifecycle management.

    Handles database init, cog loading, captcha server, and
    graceful shutdown.
    """

    def __init__(self) -> None:
        intents = discord.Intents.all()  # Message content intent required

        super().__init__(
            command_prefix=settings.command_prefix,
            intents=intents,
            help_command=commands.DefaultHelpCommand(),
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="over the server 🛡️",
            ),
        )
        self.captcha_server: CaptchaServer | None = None

    async def setup_hook(self) -> None:
        """Called when the bot is starting up (before on_ready)."""
        # Initialize database
        logger.info("Initializing database...")
        await init_db()

        # Load cogs
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as e:
                logger.error("Failed to load extension %s: %s", ext, e, exc_info=True)
                sys.exit(1)

        # Sync slash commands to the guild
        guild = discord.Object(id=settings.guild_id)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        logger.info("Slash commands synced to guild %d", settings.guild_id)

        # Start captcha web server
        self.captcha_server = CaptchaServer(self)
        await self.captcha_server.start()

    async def on_ready(self) -> None:
        """Called when the bot is fully connected and ready."""
        logger.info("─" * 50)
        logger.info("Bot is READY!")
        logger.info("Logged in as: %s (ID: %d)", self.user, self.user.id)
        logger.info("Guild: %d", settings.guild_id)
        logger.info("Cogs loaded: %s", ", ".join(self.cogs.keys()))
        logger.info("─" * 50)

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        """Global error handler for prefix commands."""
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You don't have permission to use this command.")
            return
        logger.error("Command error: %s", error, exc_info=True)

    async def close(self) -> None:
        """Graceful shutdown: stop captcha server + DB connections."""
        logger.info("Shutting down...")
        if self.captcha_server:
            await self.captcha_server.stop()
        await close_db()
        await super().close()
        logger.info("Shutdown complete.")


def main() -> None:
    """Entry point — creates and runs the bot."""
    bot = ModBot()

    # Handle SIGINT / SIGTERM gracefully
    if sys.platform != "win32":
        loop = asyncio.new_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(bot.close()))

    try:
        bot.run(settings.discord_token, log_handler=None)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
