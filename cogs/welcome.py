"""
Welcome Cog — Greets new members with a customized image banner.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()

FONT_BOLD_URL = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf"
FONT_REGULAR_URL = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Regular.ttf"

class WelcomeCog(commands.Cog, name="Welcome"):
    """Greets users when they join with a customized banner."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.font_bold_path = os.path.join("images", "Roboto-Bold.ttf")
        self.font_regular_path = os.path.join("images", "Roboto-Regular.ttf")
        self.banner_base_path = os.path.join("images", "welcome_banner.png")
        
        # We start a background task to ensure fonts are downloaded
        self.bot.loop.create_task(self._ensure_fonts())

    async def _ensure_fonts(self) -> None:
        """Download Roboto fonts if they aren't available locally."""
        try:
            async with aiohttp.ClientSession() as session:
                if not os.path.exists(self.font_bold_path):
                    logger.info("Downloading Roboto-Bold.ttf...")
                    async with session.get(FONT_BOLD_URL) as resp:
                        content = await resp.read()
                        with open(self.font_bold_path, "wb") as f:
                            f.write(content)
                
                if not os.path.exists(self.font_regular_path):
                    logger.info("Downloading Roboto-Regular.ttf...")
                    async with session.get(FONT_REGULAR_URL) as resp:
                        content = await resp.read()
                        with open(self.font_regular_path, "wb") as f:
                            f.write(content)
        except Exception as e:
            logger.error("Failed to download fonts: %s", e)

    def _create_circular_avatar(self, avatar_img: Image.Image, size: int) -> Image.Image:
        avatar_img = avatar_img.resize((size, size), Image.Resampling.LANCZOS).convert("RGBA")
        mask = Image.new("L", (size, size), 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, size, size), fill=255)
        output = ImageOps.fit(avatar_img, mask.size, centering=(0.5, 0.5))
        output.putalpha(mask)
        return output

    def _generate_banner(self, avatar_bytes: bytes, username: str) -> io.BytesIO:
        """Generates the welcome banner image."""
        if not os.path.exists(self.banner_base_path):
            raise FileNotFoundError(f"Welcome banner not found at {self.banner_base_path}")

        original_banner = Image.open(self.banner_base_path).convert("RGBA")
        
        # Resize to standard width (1024)
        target_width = 1024
        w_percent = (target_width / float(original_banner.size[0]))
        target_height = int((float(original_banner.size[1]) * float(w_percent)))
        
        banner = original_banner.resize((target_width, target_height), Image.Resampling.LANCZOS)
        width, height = banner.size

        # Paste avatar
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar_size = 180
        # The glowing circle is on the left side, approx center x=190
        avatar_x = 190 - (avatar_size // 2)
        avatar_y = (height - avatar_size) // 2
        
        circular_avatar = self._create_circular_avatar(avatar, avatar_size)
        banner.alpha_composite(circular_avatar, (avatar_x, avatar_y))

        # Add text
        draw = ImageDraw.Draw(banner)
        try:
            font_large = ImageFont.truetype(self.font_bold_path, 45)
            font_small = ImageFont.truetype(self.font_regular_path, 28)
        except (IOError, OSError):
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        welcome_text = "Welcome to the Server!"

        w_u = draw.textlength(username, font=font_large)
        w_w = draw.textlength(welcome_text, font=font_small)

        # Center the text in the remaining space on the right (from x=380 to 1024)
        text_center_x = 380 + (1024 - 380) // 2

        # Draw Username
        draw.text(
            (text_center_x - w_u / 2, (height // 2) - 40), 
            username, 
            font=font_large, 
            fill="white"
        )
        # Draw Welcome text
        draw.text(
            (text_center_x - w_w / 2, (height // 2) + 20), 
            welcome_text, 
            font=font_small, 
            fill="lightgray"
        )

        output_buffer = io.BytesIO()
        banner.save(output_buffer, format="PNG")
        output_buffer.seek(0)
        return output_buffer

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Listener invoked when a member joins the server."""
        if not _settings.welcome_channel_id or member.bot:
            return

        welcome_channel = self.bot.get_channel(_settings.welcome_channel_id)
        if welcome_channel is None or not isinstance(welcome_channel, discord.TextChannel):
            logger.warning("Welcome channel not found or is not a text channel.")
            return

        try:
            # Download avatar
            avatar_bytes = await member.display_avatar.read()

            # Run computationally heavy image processing in a thread
            loop = asyncio.get_running_loop()
            output_buffer = await loop.run_in_executor(
                None, 
                self._generate_banner, 
                avatar_bytes, 
                str(member)
            )

            file = discord.File(fp=output_buffer, filename="welcome_banner.png")
            await welcome_channel.send(
                content=f"Welcome to the server, {member.mention}! 🎉", 
                file=file
            )
            logger.info("Sent welcome banner for %s", member)

        except Exception as e:
            logger.error("Failed to generate/send welcome banner for %s: %s", member, e, exc_info=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
