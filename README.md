---
title: Discord Moderation Bot
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_file: bot.py
pinned: false
---

# 🛡️ Discord Moderation Bot

A production-grade Python Discord bot with captcha verification, blacklist-based content moderation, interactive mod tools, and full audit logging.

## Features

- **Captcha Verification** — New members must complete an hCaptcha challenge to access the server
- **Blacklist Content Filter** — Automatic detection and deletion of blacklisted words with leet-speak normalization
- **Interactive Mod Alerts** — Flagged messages are sent to a mod channel with Warn / Timeout / Kick / Ban buttons
- **Mod Role Pinging** — Severe violations automatically ping your mod role for immediate action
- **Slash Commands** — `/warn`, `/kick`, `/ban`, `/timeout`, `/unban`, `/purge`, `/userinfo`, `/modlog`, `/stafflog`
- **Staff Activity Tracking** — Every mod action is logged so admins can review staff behaviour
- **Comprehensive Audit Logging** — Roles, nicknames, timeouts, messages, bans, voice activity — all logged to PostgreSQL and mod channel
- **Secure Config** — Environment-variable-only secrets with pydantic validation

## Tech Stack

| Layer | Technology |
|---|---|
| Bot | discord.py 2.x |
| Database | PostgreSQL + SQLAlchemy 2.0 async + asyncpg |
| Captcha | hCaptcha + aiohttp web server |
| Config | pydantic-settings + python-dotenv |
| Deployment | Docker + Docker Compose |

---

## Quick Start

### 1. Prerequisites

- Python 3.11+ (3.12 recommended)
- PostgreSQL 14+
- A [Discord Bot Token](https://discord.com/developers/applications)
- [hCaptcha keys](https://www.hcaptcha.com/) (free tier works)

### 2. Clone & Configure

```bash
git clone <your-repo-url>
cd discord_bot

# Create .env and fill in your values
cp .env.example .env
# Edit .env with your real tokens, IDs, and credentials
```

### 3. Discord Server Setup

1. Create a **Verified** role in your server
2. Create a **#mod-alerts** channel visible only to admins
3. Set server permissions so unverified users can only see a welcome/rules channel
4. Copy the **Guild ID**, **Verified Role ID**, **Mod Channel ID**, and **Mod Role ID** into `.env`

### 4. Bot Permissions

When creating your bot at the Discord Developer Portal, enable:
- **Privileged Gateway Intents**: Message Content, Server Members, Presence
- **Bot Permissions**: Administrator (or granular: Manage Roles, Kick Members, Ban Members, Moderate Members, Send Messages, Manage Messages, Read Message History, Embed Links)

### 5. Run Locally

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Make sure PostgreSQL is running, then:
python bot.py
```

### 6. Run with Docker

```bash
# Build and start bot + PostgreSQL
docker-compose up -d

# View logs
docker-compose logs -f bot

# Stop
docker-compose down
```

---

## Deploy to Hosting Services

### Railway

1. Push to a GitHub repo
2. Connect the repo on [Railway](https://railway.app)
3. Add a PostgreSQL plugin
4. Set all `.env` variables in Railway's dashboard
5. Railway auto-detects the `Procfile` and deploys

### Render

1. Push to GitHub
2. Create a new **Background Worker** on [Render](https://render.com)
3. Add a PostgreSQL database
4. Set environment variables
5. Deploy

### VPS (Ubuntu/Debian)

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone, configure .env, then:
docker-compose up -d
```

---

## Project Structure

```
discord_bot/
├── bot.py                  # Bot entrypoint
├── config.py               # Secure config (pydantic-settings)
├── database.py             # Async DB engine & sessions
├── models.py               # SQLAlchemy ORM models
├── captcha_server.py       # hCaptcha web server
├── blacklist.txt           # Banned words (one per line)
├── cogs/
│   ├── verification.py     # Captcha join flow
│   ├── automod.py          # Blacklist scanning + mod alerts
│   ├── moderation.py       # Slash commands (/warn, /kick, etc.)
│   └── logging_cog.py      # Passive audit logging
├── utils/
│   ├── blacklist.py        # Blacklist filter engine
│   └── embed_factory.py    # Reusable embed builders
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── Procfile
└── .gitignore
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from Discord Developer Portal |
| `GUILD_ID` | ✅ | Your Discord server ID |
| `VERIFIED_ROLE_ID` | ✅ | Role assigned after captcha verification |
| `MOD_CHANNEL_ID` | ✅ | Channel for mod alerts (admin-only) |
| `MOD_ROLE_ID` | ❌ | Role to ping on severe violations (set to `0` to disable) |
| `DATABASE_URL` | ✅ | PostgreSQL URL (`postgresql+asyncpg://...`) |
| `HCAPTCHA_SITE_KEY` | ✅ | hCaptcha site key |
| `HCAPTCHA_SECRET_KEY` | ✅ | hCaptcha secret key |
| `SIGNING_SECRET` | ✅ | Secret for verification token signing |
| `CAPTCHA_SERVER_URL` | ❌ | Public URL of captcha server (default: `http://localhost:8080`) |
| `CAPTCHA_SERVER_PORT` | ❌ | Captcha server port (default: `8080`) |
| `COMMAND_PREFIX` | ❌ | Legacy command prefix (default: `!`) |
| `LOG_LEVEL` | ❌ | Logging level (default: `INFO`) |

## Database Schema

The bot tracks everything in 5 tables:

- **users** — Discord members with verification status
- **messages** — All message metadata + flagged status
- **mod_actions** — Kick, ban, warn, timeout records
- **warnings** — Individual warning records
- **user_events** — Full audit log (joins, leaves, role changes, timeouts, edits, flags, mod activity)

---

## License

MIT
