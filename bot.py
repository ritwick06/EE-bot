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
        # Load cogs
        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
                logger.info("Loaded extension: %s", ext)
            except Exception as e:
                logger.error("Failed to load extension %s: %s", ext, e, exc_info=True)
                sys.exit(1)

        # Sync slash commands to the guild
        try:
            guild = discord.Object(id=settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Slash commands synced to guild %d", settings.guild_id)
        except Exception as e:
            logger.warning("Failed to sync commands (could be rate-limited): %s", e)

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
        """Graceful shutdown: stop DB connections. Web server logic handled in main."""
        logger.info("Shutting down bot...")
        await super().close()
        logger.info("Bot shutdown complete.")


async def main_async() -> None:
    """Async entry point — initializes core services, starts web server, then bot."""
    # Initialize database first
    logger.info("Initializing database...")
    await init_db()

    bot = ModBot()

    # Start captcha web server BEFORE connecting to Discord to satisfy Render port binding
    logger.info("Starting web server to bind port for Render health checks...")
    bot.captcha_server = CaptchaServer(bot)
    await bot.captcha_server.start()

    logger.info("Web server started. Connecting to Discord...")
    try:
        async with bot:
            await bot.start(settings.discord_token)
    except discord.HTTPException as e:
        if e.status == 429:
            logger.critical(
                "Discord Rate Limit (429) hit! The bot cannot login right now. "
                "Keeping the process alive so Render doesn't restart it repeatedly. "
                "Error details: %s", e
            )
            # Sleep indefinitely to keep web server alive, satisfying Render's health checks
            while True:
                await asyncio.sleep(3600)
        else:
            raise
    except KeyboardInterrupt:
        pass
    finally:
        # Cleanup
        if bot.captcha_server:
            await bot.captcha_server.stop()
        await close_db()


def main() -> None:
    """Entry point."""
    # Handle SIGINT / SIGTERM gracefully
    if sys.platform != "win32":
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # We handle shutdown signals internally within main_async if needed,
        # but asyncio.run automatically cancels tasks on termination.

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt.")
    except Exception as e:
        logger.critical("Fatal error: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
