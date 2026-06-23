# Aegis Suite Documentation

Welcome to the Aegis Suite documentation. Aegis is a Discord bot management dashboard that provides server optimization, moderation, and analytics features.

## Features

- **Server Optimization** — Automated server layout management
- **Auto-Moderation** — Spam protection, link blocking, word filters
- **Analytics** — Message tracking, voice activity, member retention
- **Server Auditor** — Health scoring across security, moderation, structure, engagement, and automation
- **Security Center** — Permission analysis, config diagnostics, anti-raid protection
- **Tickets** — Support desk management with auto-categorization
- **Leveling** — XP rewards and rank systems
- **Music** — Voice channel audio streaming
- **Embed Builder** — Visual Discord embed designer
- **Scheduler** — Automated timed announcements
- **Giveaways** — Interactive giveaway management
- **Role Panels** — Self-assignable role selection

## Quick Start

### Installation

```bash
pip install -e .
```

### First Run

```bash
python run.py
```

This will:
1. Check for dependencies
2. Launch the setup wizard
3. Open the dashboard in your browser

### Running the Bot

```bash
python -m aegis
```

## Architecture

Aegis uses a single-process architecture with:

- **FastAPI** — Web server for the dashboard
- **discord.py** — Discord bot client
- **SQLAlchemy** — Database ORM (SQLite)
- **asyncio** — Event loop management

### Directory Structure

```
aegis/
├── bot/           # Discord bot commands and handlers
├── config/        # Configuration management
├── core/          # Core utilities and lifecycle
├── db/            # Database models and migrations
├── web/           # FastAPI routes and dashboard
├── analytics/     # Analytics engine
└── __main__.py    # Entry point
```

## API Reference

See the individual module documentation for API details.

## Contributing

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for development guidelines.
