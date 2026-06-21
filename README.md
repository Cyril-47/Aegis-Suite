# Aegis Server Optimizer

[![Build & Publish Windows EXE Release](https://github.com/Cyril-47/Aegis-Suite/actions/workflows/release.yml/badge.svg)](https://github.com/Cyril-47/Aegis-Suite/actions/workflows/release.yml)
[![Verify Security Layering](https://github.com/Cyril-47/Aegis-Suite/actions/workflows/verify.yml/badge.svg)](https://github.com/Cyril-47/Aegis-Suite/actions/workflows/verify.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python Version: 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)

Aegis Server Optimizer is an interactive operations suite featuring a Discord bot and a FastAPI web dashboard designed to automatically scan, analyze, audit, and optimize Discord servers.

---

## 🚀 Features

### Core
- **Automated Server Health Scan**: Runs an automated audit scanning server verification levels, content filters, and administrator role security.
- **One-Click Server Layouts**: Choose from 18+ professional templates (`Gaming Guild`, `Social Community`, `Developer Hub`, `Anime`, `Education`, etc.) to restructure channels and categories.
- **Safe Channel Archiving**: Move old text/voice channels into an archived category to prevent chat history loss instead of deleting them.
- **Automated Welcomer & Auto-Roles**: Assign roles (e.g. `Verified Member`) and post welcoming embeds upon new member joins.
- **Robust Auto-Moderation Suite**: Filters links, prevents mention raid spam, blocks toxic words via custom lists, and logs violations to `#mod-logs`.

### Intelligence Engine
- **Guardian Mode — Automation Engine**: Rule-based automation with 13 triggers (member join/leave, messages, voice, reactions, moderation events) and 10 safe actions (timeout, kick, ban, role assignment, channel lock, slowmode). Rules configurable from the dashboard UI with conditions.
- **Adaptive Raid Detection**: Statistical anomaly detection for join/message/mod-action rates. Learns baseline over 24-hour windows and triggers alerts when rates exceed baseline by 2-5 standard deviations.
- **Fuzzy Spam Detection**: Levenshtein distance-based spam detection with 90% similarity threshold. Detects exact duplicates, fuzzy variations, and cross-user raid spam campaigns.
- **Sentiment Analysis with Stability Threshold**: VADER-based sentiment scoring with a 20-message learning window to prevent single-message score volatility. Normalizes leetspeak, abbreviations, and slang before scoring.
- **Activity Intelligence**: Statistical analysis of message activity by hour and day-of-week. Finds peak hours, dead zones, and optimal times for events/giveaways.
- **Smart Recommendations**: Scans server state against 10+ rule-based checks and returns prioritized recommendations with severity, impact score, and auto-fix availability.
- **One-Click Auto Fix**: Executes automated fixes (create channels, archive inactive, remove unused roles, enable welcome/raid mode, lock server, etc.) with rollback capability.

### Smart Analyzers (12)
- **Config Doctor**: Diagnoses server config health across 5 dimensions (security, moderation, growth, automation, reliability) with 0-100 scores.
- **Permission Doctor**: Scans all roles for dangerous permission combinations (Administrator abuse, escalation paths, public roles with channel management).
- **Smart Raid Detector**: Analyzes recent member joins for raid patterns (join rate, new accounts, similar usernames) with threat levels.
- **Smart Growth Advisor**: Analyzes server growth health (retention rate, activity ratio, channel count, welcome config).
- **Smart Welcome Analyzer**: Evaluates onboarding completeness (welcome message, rules channel, auto-role, verification level).
- **Smart Role Cleaner**: Detects unused roles, duplicates, and obsolete roles (90+ days old, no permissions, 0 members).
- **Smart Channel Cleaner**: Identifies dead channels (no messages in 30+ days) and duplicates.
- **Smart Backup Advisor**: Tracks backup health with staleness thresholds and protection score.
- **Server Maturity Score**: Comprehensive maturity score across 6 dimensions (security, moderation, growth, automation, reliability, community health).

### Analytics & Monitoring
- **Channel Heatmap**: 24x7 hour-by-day-of-week activity heatmap.
- **Ticket SLA Tracking**: Average first response time, resolution time, open rate, per-staff metrics.
- **Growth Recommendations**: Data-driven advice based on retention, activity trends, and peak times.
- **Server Benchmarking**: Percentile comparison against all servers in the system.
- **Trend Forecasting**: Linear regression forecasting of messages/day, active users, and daily joins for 7 days.
- **Moderator Intelligence**: Mod action leaderboard and response time tracking.
- **Member Retention**: 1-day, 7-day, and 30-day retention rate calculations.
- **Permission Heatmap**: Visual matrix of roles mapped against 12 key permissions.
- **Incident Timeline**: Correlated moderation events grouped within 5-minute windows.
- **Live Alerts (SSE)**: Real-time push updates for health score changes, notifications, and timeline events.

### Automation & Maintenance
- **Dynamic Slowmode System**: Tracks per-channel message rates in real-time. Auto-applies slowmode when threshold exceeded, auto-removes after burst window.
- **Nightly DB Backup**: Automated database backups with configurable schedule and retention.
- **Auto Role Cleanup**: Daily prune of empty, unmanaged roles.
- **DB Vacuum**: Weekly SQLite vacuum to reclaim space.
- **Channel Archive**: Archive inactive channels after configurable days.
- **Scheduled Messages**: One-time and recurring message scheduling with web UI.
- **Auto-Responders**: Keyword-triggered automatic replies with CRUD management.

### Bot Features
- **Modular Cog Architecture**: 10 focused cogs (Moderation, Config, Events, Intelligence, Music, Automation, Tickets, Giveaways, Leveling, Utils) loaded dynamically.
- **Music Player**: `/play` (YouTube URL or search), `/pause`, `/resume`, `/skip`, `/stop`, `/volume`, queue management.
- **Leveling & XP System**: `/rank` (rank card), `/leaderboard`, `/set-xp-role` with role-specific XP multipliers.
- **Giveaway System**: `/giveaway start`, `/giveaway end`, `/giveaway reroll` with duration and winner count.
- **Ticket System**: Private support ticket channels with staff assignment and close commands.
- **Observability Stack**: Structured logging with secret redaction, request-ID tracking, metrics collection, and security headers middleware.
- **Live Terminal Logging Console**: Real-time WebSocket log streaming on the dashboard.

---

## 🏗️ Architecture & Connection Flows

Aegis Suite is designed as a **unified desktop service application** running within a **single process** on a **single asyncio event loop**. FastAPI (Uvicorn) and the Discord.py client operate in-process sharing memory structures and direct database access.

### 1. Hosted Mode (Multi-Tenant SaaS Setup)
Allows multiple server administrators to manage their respective servers through a single hosted bot deployment using link authorization.

```mermaid
sequenceDiagram
    actor Owner as Discord Owner
    participant Web as FastAPI Web App
    participant Bot as Discord.py Bot
    participant Discord as Discord Gateway

    Owner->>Web: Visit Public Dashboard Login
    Owner->>Discord: Click "Invite Bot" & Authorize to Guild
    Owner->>Bot: Run /linkdashboard in Text Channel
    Bot-->>Owner: Generate temporary 6-digit linking code (10m expiry)
    Owner->>Web: Enter 6-digit code on dashboard
    Web->>Bot: Verify code in-process
    Web-->>Owner: Authenticated session established (JWT)
```

### 2. Self-Hosted Mode (Private Standalone Setup)
Ideal for single server owners running the application locally on a private PC or private VPS.

```mermaid
flowchart TD
    Start([Launch AegisOptimizer.exe / run.py]) --> CheckEnv{Credentials Exist?}
    CheckEnv -- No --> ShowWizard[Launch First-Run Console Wizard]
    ShowWizard --> GetSecrets[Prompt for Token, Client ID, Admin Password]
    GetSecrets --> Encrypt[Encrypt with Win32 DPAPI & Write .env.enc]
    Encrypt --> Reboot[Reboot Application]
    CheckEnv -- Yes --> Decrypt[Decrypt Secrets in Memory]
    Decrypt --> DB[Initialize SQLite Engine & Alembic Migrations]
    DB --> Web[Start FastAPI Server on Port 8000]
    Web --> Browser[Auto-Open Web Browser to Dashboard]
    Web --> DiscordBot[Authenticate & Start Discord Bot Task]
```

### 3. Dashboard ↔ Bot Communication
Illustrates how subsystems communicate directly via a shared memory layer on a single asyncio event loop.

```mermaid
graph LR
    subgraph Single Process Concurrency Event Loop
        Uvicorn[Uvicorn ASGI Web Server] <--> SharedState[AppCore Concurrency State]
        DiscordClient[Discord.py Bot Task] <--> SharedState
        SharedState <--> SQLAlchemy[SQLAlchemy Engine & Locks]
        SharedState <--> CogLoader[Modular Cog Loader]
    end
    SQLAlchemy <--> SQLite[(SQLite Database)]
    CogLoader <--> Cogs[10 Cogs: Moderation, Config, Events, Intelligence, Music, Automation, Tickets, Giveaways, Leveling, Utils]
```

### 4. Automation Engine Flow
How Guardian Mode processes Discord events through the rule engine.

```mermaid
flowchart TD
    DiscordEvent[Discord Gateway Event] --> BotCog[Bot Cog Handler]
    BotCog --> Context[Build Context: user, channel, guild, message]
    Context --> Engine[AutomationEngine.evaluate_trigger]
    Engine --> Rules{Rule Matches?}
    Rules -- Yes --> Actions[Execute Actions: timeout, kick, ban, role, message, slowmode, lock]
    Actions --> Log[Log to Execution Log]
    Rules -- No --> Skip[No Action]
```

### 5. First-Run Onboarding Flow
Detailed logic executed when the console wizard runs for first-run setups:

```mermaid
flowchart TD
    SetupWizard[first_run_wizard.py] --> InputToken[Prompt for Discord Bot Token]
    InputToken --> ValidateToken{Validate Shape & Auth?}
    ValidateToken -- Invalid --> InputToken
    ValidateToken -- Valid --> InputClient[Prompt for Discord Client ID]
    InputClient --> ValidateClient{Validate Shape?}
    ValidateClient -- Invalid --> InputClient
    ValidateClient -- Valid --> InputPass[Prompt for Admin Password]
    InputPass --> HashPass[Hash Password via PBKDF2-SHA256]
    HashPass --> SaveSecrets[Write secrets to encrypted .env.enc]
```

### 6. Safe Mode Recovery Flow
When startup checks fail (e.g. database corruptions, invalid credentials), Aegis enters Safe Mode to serve an administrative recovery panel.

```mermaid
sequenceDiagram
    participant Core as AppCore
    participant State as State Machine
    participant DB as SQLite DB
    participant Web as FastAPI Server
    participant Bot as Discord.py Bot

    Core->>DB: Run PRAGMA integrity_check
    alt DB Corrupted / Connection Fails
        Core->>State: Transition to SAFE_MODE (Reason: DB_RECOVERY)
        Core->>Bot: Cancel / Suspend Bot Task
        Core->>Web: Start ASGI Server & Serve /wizard/ and /api/recovery/ (Bypassing Auth)
        Note over Web: Owner recovers config or restores DB backups via Web UI
    end
```

---

## ⚙️ Getting Started

### Quick Start (Run from Source)
1. **Clone the Repository**:
   ```cmd
   git clone https://github.com/Cyril-47/Aegis-Suite.git
   cd Aegis-Suite
   ```
2. **Launch Application**:
   ```cmd
   python run.py
   ```
   *The launcher automatically configures a local Python virtual environment, installs standard dependencies, resolves `FFmpeg` for voice/music, and launches the web interface at `http://127.0.0.1:8000`.*

### Installation via pip
To install Aegis Suite as an editable developer package:
```cmd
pip install -e .
```
You can now start the application from anywhere using the `aegis` console entry point command:
```cmd
aegis
```

---

## 🤖 Discord Bot Setup

The Aegis bot is hosted by us — you do not need to create a Discord application or paste any token.

1. **Invite Aegis to your server.** Click the **Invite Bot** button on the dashboard login page at `https://[your domain]/`. You must have **Administrator** permission on the target Discord server.
2. **Run `!linkdashboard` or `/linkdashboard` in your server.** In any text channel, type `!linkdashboard` (instant prefix command fallback) or `/linkdashboard` (slash command). The bot will reply with a 6-digit alphanumeric connection code that is valid for 10 minutes.
3. **Paste the code into the dashboard.** Back at `https://[your domain]/`, paste the 6-digit code into the login field and click **Unlock Dashboard**.
4. **You're in.** The dashboard now shows your server's panel. Codes are single-use; if you need to log in again later, run `!linkdashboard` or `/linkdashboard` to mint a fresh one.

---

## 🏠 Hosting Modes

Aegis Suite is designed to be run in Local PC mode. In previous versions, Cloud mode was supported for deploying the repository to a paid third-party host (such as Render, Railway, or a generic Docker VPS). However, as of this version, Cloud Mode is deprecated and has been completely removed from the Aegis Suite.

### Local PC Mode

Local PC mode runs the Windows EXE on the Maintainer's own desktop or laptop. The bot process is alive only while the PC is powered on, awake, and connected to the internet. Any Aegis feature that requires a continuous connection to Discord — for example, message-driven auto-moderation, the giveaway end-time scheduler, or `on_guild_remove` session revocation — will not run while the PC is offline, asleep, or disconnected. Schedules and timers do not "catch up" when the PC wakes back up; events that fired during downtime are simply missed.

### Cloud Mode

**Removed**: Cloud Mode (which allowed deploying to providers like Render, Railway, or generic Docker VPS) has been deprecated and completely removed as of this version. Any previous deployment templates or automated setup flows targeting these cloud environments are no longer supported. This resolves deployment failures on platforms like Railway.

### Feature availability

The features below depend on the bot process being continuously connected to Discord. The two lists are kept in lock-step with the dashboard's Feature Availability Warning panel — if you change one surface, change the other.

**Impacted by intermittent uptime:**

- Auto-moderation message handlers
- Guardian Mode automation triggers
- Dynamic slowmode enforcement
- Raid detection and auto-lockdown
- Fuzzy spam detection
- Sentiment analysis and scoring
- Scheduled messages background loop
- Giveaway end-time scheduler
- Leveling XP grants on member messages
- `on_guild_remove` session revocation
- `/linkdashboard` pairing-code expiry
- Periodic audit log roll-ups
- Welcome embeds and auto-role assignment on member join
- Auto-responders
- Live SSE alert stream

**Unaffected by intermittent uptime:**

- Dashboard configuration changes
- Server health audit scan
- Server layout optimizer
- Role creator
- Role panel deployment
- Custom commands configuration
- Server template save and apply
- Embed builder
- Server backup and restore
- Audit log viewer
- Smart analyzers (config doctor, permission doctor, role/channel cleaners)
- Analytics dashboards (heatmaps, growth, benchmarks, trends)
- Config history and rollback
- Ticket intelligence and moderator intelligence
- Member retention and growth center
- Permission heatmap
- Security checks and scoring

The features in the **Impacted** list will not run while the host PC is offline, asleep, or disconnected from Discord. Switch to Cloud mode if any of those features are critical to your community.

### `AEGIS_HOSTING_MODE` environment variable

For headless deploys (Render, self-hosted deployment) where no human can click the first-launch chooser, you can pre-select the hosting mode by setting `AEGIS_HOSTING_MODE` in the platform's environment-variable panel. This sits alongside the other environment variables Aegis reads at startup — `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, and `BOT_API_URL` — and follows these rules:

- **Accepted values**: exactly `local_pc` or `cloud`. The value is matched case-insensitively after stripping leading and trailing whitespace, so `Cloud`, ` LOCAL_PC `, and `cloud` are all accepted.
- **First boot, no value persisted**: the env var's value is written to `config.json` under `hosting_mode` and becomes the active mode.
- **A value is already persisted**: the env var is **ignored**. Once a Maintainer (or a previous boot) has recorded a choice, `AEGIS_HOSTING_MODE` will never silently overwrite it or override a dashboard switch. Change the mode from the dashboard's Settings panel instead.
- **Invalid values**: anything other than `local_pc` or `cloud` is logged at WARNING level (naming the offending value) and ignored. Startup continues normally.

The hosting mode is a non-sensitive deployment preference, so unlike the four secrets above it lives in `config.json` rather than the DPAPI-encrypted Secret Store.

---

## 🔐 Secrets at Rest

For the local Windows EXE flow, the bot's secrets — `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `BOT_API_URL` — are stored encrypted at rest using **Windows DPAPI** (Data Protection API). The encrypted blob (`.env.enc`) is bound to your Windows user account and your machine; copying it to another user, another PC, or off the disk yields ciphertext that cannot be decrypted.

```cmd
# One-time: encrypt the plaintext .env into .env.enc and remove the cleartext
python -m secret_store encrypt --source .env --dest .env.enc --delete-source

# Decrypt to stdout (or to a file with --dest)
python -m secret_store decrypt --source .env.enc
```

---

## 🛠️ Development & Release Pipelines

- **Code Styling**: Standardized using `black` and linter via `ruff`.
- **Testing**: Run pytest: `python -m pytest`
- **Standalone Builds**: Compiles the standalone executable `AegisOptimizer.exe` under `dist/`:
  ```cmd
  python build_exe.py
  ```

---

## ❓ FAQ & Troubleshooting

### 1. Bot is online but commands do not respond?
Verify that **Privileged Gateway Intents** are toggled **ON** in your [Discord Developer Portal](https://discord.com/developers/applications):
* Presence Intent
* Server Members Intent
* Message Content Intent

### 2. "Another instance is already running" error?
Aegis enforces single-instance execution. Check your system tray for running processes or delete `temp_appdata/aegis.lock` if the application terminated abruptly.

### 3. Health gauge stays at 80% and doesn't move?
This is by design. The sentiment analyzer requires 20 messages before showing real scores to prevent single-message volatility. The gauge displays "Collecting data..." during this learning phase. After 20 messages, it snaps to the calculated average.

### 4. Guardian Mode rules don't trigger?
Rules are evaluated in real-time on Discord events. Ensure:
- The rule is **enabled** (toggle on)
- The **trigger** matches the event type (e.g., `message_sent` for new messages)
- The bot has the required permissions (kick, ban, timeout, manage channels)
- Check the **Last Interventions** log in the Automation Center for execution status

### 5. Smart analyzers show "No data"?
The smart analyzers (role cleaner, channel cleaner, etc.) require the bot to have been running for at least 24 hours to collect baseline data. Some analyzers (channel cleaner) need message history to identify dead channels.

### 6. Music bot won't join voice channel?
Ensure `FFmpeg` is installed and accessible in your PATH. The launcher checks for FFmpeg at startup. If missing, install it via your package manager or download from https://ffmpeg.org/download.html.

### 7. How do I restore a backup?
Go to **Dashboard → Backup & Restore**, select a backup from the list, and click **Restore**. The bot will recreate channels and roles from the backup snapshot. Note: message history is not included in backups.

---

## ⚠️ Known Technical Debt & Limits

- **In-Memory Global State**: Authentication token caches (`_revoked_tokens`, `_validated_tokens`) and rate-limit counters are stored in-process and lost on restart. Suitable for single-instance local PC mode; needs Redis/DB for multi-process deployments.
- **Sentiment Learning Window**: The health gauge requires 20 messages before showing real scores (intentional stability feature). During the learning phase, the gauge holds at 80%.
- **Automation Engine — Reactive Only**: Guardian Mode fires on Discord gateway events only. There is no periodic "sweep" or cron-style scheduling for tasks like daily scans or weekly reports.
- **JSON Configuration Contention**: The current version uses local JSON files (`config.json`, `giveaways.json`, `audit_log.json`) for mutable configurations. While sufficient for small-scale local deployments, concurrent writes on large multi-tenant servers under high load can cause file corruptions or race conditions.
- **SQLite Migration Roadmap**: If scaling up for public SaaS usage, it is highly recommended to migrate the configurations, custom commands, leveling stats, backups, and pairings data to a structured SQLite database (using `aiosqlite`) to support transactional integrity and concurrent locks.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
