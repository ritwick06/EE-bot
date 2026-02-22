"""
Captcha verification web server.

Runs alongside the Discord bot using aiohttp. Serves an hCaptcha
widget and validates responses to verify Discord users.

Endpoints:
  GET  /verify/{token}  → Captcha HTML page
  POST /verify/{token}  → Validate hCaptcha, mark user verified
  GET  /health          → Health check for hosting platforms
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import get_settings
from database import get_session
from models import User, UserEvent

if TYPE_CHECKING:
    import discord

logger = logging.getLogger(__name__)

_settings = get_settings()

# ── Token serializer (signed + time-limited) ────────────────────────────────
_serializer = URLSafeTimedSerializer(_settings.signing_secret)

TOKEN_MAX_AGE = 1800  # 30 minutes


def create_verification_token(user_id: int) -> str:
    """Create a signed, time-limited token for a Discord user ID."""
    return _serializer.dumps(str(user_id), salt="captcha-verify")


def decode_verification_token(token: str) -> int | None:
    """Decode and validate a verification token. Returns user ID or None."""
    try:
        user_id_str = _serializer.loads(
            token, salt="captcha-verify", max_age=TOKEN_MAX_AGE
        )
        return int(user_id_str)
    except (BadSignature, SignatureExpired) as e:
        logger.warning("Invalid verification token: %s", e)
        return None


# ── HTML Template ────────────────────────────────────────────────────────────
_CAPTCHA_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Discord Verification</title>
    <script src="https://js.hcaptcha.com/1/api.js" async defer></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e0e0e0;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            padding: 40px;
            max-width: 440px;
            width: 90%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}
        .card h1 {{
            font-size: 1.6rem;
            margin-bottom: 8px;
            color: #fff;
        }}
        .card p {{
            font-size: 0.95rem;
            color: #b0b0b0;
            margin-bottom: 24px;
        }}
        .h-captcha {{
            display: flex;
            justify-content: center;
            margin-bottom: 24px;
        }}
        button {{
            background: linear-gradient(135deg, #5865F2, #7289DA);
            color: #fff;
            border: none;
            padding: 12px 32px;
            border-radius: 8px;
            font-size: 1rem;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        button:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 16px rgba(88, 101, 242, 0.4);
        }}
        .success {{
            color: #2ecc71;
            font-size: 1.1rem;
            margin-top: 16px;
        }}
        .error {{
            color: #e74c3c;
            font-size: 0.95rem;
            margin-top: 16px;
        }}
        .icon {{ font-size: 3rem; margin-bottom: 16px; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">🔒</div>
        <h1>Discord Verification</h1>
        <p>Complete the captcha below to verify your account and gain access to the server.</p>
        <form method="POST" action="/verify/{token}">
            <div class="h-captcha" data-sitekey="{site_key}"></div>
            <button type="submit">Verify Me</button>
        </form>
    </div>
</body>
</html>"""

_SUCCESS_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verified!</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e0e0e0;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(46, 204, 113, 0.3);
            border-radius: 16px;
            padding: 40px;
            max-width: 440px;
            width: 90%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}
        .icon {{ font-size: 3rem; margin-bottom: 16px; }}
        h1 {{ color: #2ecc71; margin-bottom: 8px; }}
        p {{ color: #b0b0b0; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>Verified Successfully!</h1>
        <p>You now have access to the server. You can close this page.</p>
    </div>
</body>
</html>"""

_ERROR_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification Failed</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #e0e0e0;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(20px);
            border: 1px solid rgba(231, 76, 60, 0.3);
            border-radius: 16px;
            padding: 40px;
            max-width: 440px;
            width: 90%;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
        }}
        .icon {{ font-size: 3rem; margin-bottom: 16px; }}
        h1 {{ color: #e74c3c; margin-bottom: 8px; }}
        p {{ color: #b0b0b0; }}
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">❌</div>
        <h1>Verification Failed</h1>
        <p>{error_message}</p>
    </div>
</body>
</html>"""


class CaptchaServer:
    """
    aiohttp web server for hCaptcha-based user verification.

    Runs in-process alongside the Discord bot.
    """

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot
        self._app = web.Application()
        self._runner: web.AppRunner | None = None
        self._setup_routes()

    def _setup_routes(self) -> None:
        self._app.router.add_get("/", self._handle_root)
        self._app.router.add_get("/verify/{token}", self._handle_captcha_page)
        self._app.router.add_post("/verify/{token}", self._handle_captcha_submit)
        self._app.router.add_get("/health", self._handle_health)

    # ── Route handlers ───────────────────────────────────────────────────

    async def _handle_root(self, request: web.Request) -> web.Response:
        return web.Response(text="Bot is alive and running!", content_type="text/plain")

    async def _handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "bot_ready": self._bot.is_ready()})

    async def _handle_captcha_page(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        user_id = decode_verification_token(token)

        if user_id is None:
            return web.Response(
                text=_ERROR_PAGE.format(
                    error_message="This verification link has expired or is invalid. "
                    "Please request a new one from the server."
                ),
                content_type="text/html",
            )

        html = _CAPTCHA_PAGE.format(
            token=token,
            site_key=_settings.hcaptcha_site_key,
        )
        return web.Response(text=html, content_type="text/html")

    async def _handle_captcha_submit(self, request: web.Request) -> web.Response:
        token = request.match_info["token"]
        user_id = decode_verification_token(token)

        if user_id is None:
            return web.Response(
                text=_ERROR_PAGE.format(
                    error_message="This verification link has expired or is invalid."
                ),
                content_type="text/html",
            )

        # Parse form data
        data = await request.post()
        captcha_response = data.get("h-captcha-response", "")

        if not captcha_response:
            return web.Response(
                text=_ERROR_PAGE.format(
                    error_message="Please complete the captcha before submitting."
                ),
                content_type="text/html",
            )

        # Validate with hCaptcha API
        is_valid = await self._verify_hcaptcha(str(captcha_response))

        if not is_valid:
            return web.Response(
                text=_ERROR_PAGE.format(
                    error_message="Captcha verification failed. Please try again."
                ),
                content_type="text/html",
            )

        # Mark user as verified in DB and assign role
        try:
            await self._complete_verification(user_id)
        except Exception as e:
            logger.error("Failed to complete verification for %d: %s", user_id, e)
            return web.Response(
                text=_ERROR_PAGE.format(
                    error_message="An error occurred. Please try again later."
                ),
                content_type="text/html",
            )

        return web.Response(text=_SUCCESS_PAGE, content_type="text/html")

    # ── hCaptcha API validation ──────────────────────────────────────────

    async def _verify_hcaptcha(self, response_token: str) -> bool:
        """Validate the hCaptcha response token with their API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://hcaptcha.com/siteverify",
                    data={
                        "secret": _settings.hcaptcha_secret_key,
                        "response": response_token,
                    },
                ) as resp:
                    result = await resp.json()
                    return result.get("success", False)
        except Exception as e:
            logger.error("hCaptcha API error: %s", e)
            return False

    # ── Post-verification logic ──────────────────────────────────────────

    async def _complete_verification(self, user_id: int) -> None:
        """Update DB and assign Discord role after successful captcha."""
        now = datetime.now(timezone.utc)

        # Update database
        async with get_session() as session:
            from sqlalchemy import select, update

            # Update user record
            await session.execute(
                update(User)
                .where(User.discord_id == user_id)
                .values(is_verified=True, verified_at=now)
            )

            # Log the verification event
            event = UserEvent(
                user_id=user_id,
                event_type="verified",
                details="User completed hCaptcha verification",
            )
            session.add(event)

        # Assign verified role in Discord
        guild = self._bot.get_guild(_settings.guild_id)
        if guild is None:
            logger.error("Guild %d not found!", _settings.guild_id)
            return

        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                logger.error("Could not fetch member %d", user_id)
                return

        role = guild.get_role(_settings.verified_role_id)
        if role is None:
            logger.error("Verified role %d not found!", _settings.verified_role_id)
            return

        await member.add_roles(role, reason="Captcha verification completed")
        logger.info("Verified user %s (%d) and assigned role.", member, user_id)

        # DM the user a success message
        try:
            await member.send("✅ You have been verified! You now have access to the server.")
        except discord.Forbidden:
            logger.info("Could not DM user %d (DMs disabled).", user_id)

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the web server."""
        import os
        port = int(os.environ.get("PORT", _settings.captcha_server_port))

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Captcha server running on port %d", port)

    async def stop(self) -> None:
        """Gracefully stop the web server."""
        if self._runner:
            await self._runner.cleanup()
            logger.info("Captcha server stopped.")
