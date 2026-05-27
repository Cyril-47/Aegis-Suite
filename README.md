# Aegis Server Optimizer

Aegis Server Optimizer is an interactive server operations suite written in Python containing a Discord bot and a FastAPI web dashboard designed to automatically scan, analyze, audit, and optimize Discord servers with single-click layout configurations, welcome greeting embeds, custom command responses, support tickets, layouts backup/restore, and auto-moderation.

---

## 🚀 Features

- **Circular Server Health Score Indicator**: Runs an automated audit scanning server verification levels, content filters, public administrator rights, and insecure roles.
- **One-Click Server Layout Optimizations**: Choose from three professional layouts (`Gaming Guild`, `Social Community`, or `Developer Hub`) to instantly restructure channels and categories.
- **Safe Channel Handling**: Offers options to safely move existing channels into an `📦 ARCHIVED CHANNELS` category to prevent chat history loss, rather than delete them.
- **Automated Welcoming Module**: Configures customizable welcome cards, color themes, embed headers, and auto-assigns roles (e.g. `Verified Member`) upon user joins.
- **Robust Auto-Moderation Suite**: Filters links, prevents mention raid spam, blocks toxic profanity using a custom word blocklist, and logs violations to a staff `#mod-logs` channel.
- **Live Terminal Logging Console**: Real-time websocket feed displaying server logs and bot actions directly on the dashboard page.

---

## ⚙️ Deployment Targets

Aegis Server Optimizer supports two deployment models depending on your target audience:

### Target A: Local Desktop App (Standalone / Private Server)
Ideal for single server owners running the dashboard locally.
1. **Compilation**: Run the build script to compile the application as a directory:
   ```cmd
   python build_exe.py
   ```
   *This compiles the python scripts into binary bytecode (.pyc) inside `dist/AegisOptimizer/`, bundling static frontend assets, and directs shortcut creation to installer scripts (e.g. Inno Setup).*
2. **Execution**: Run `dist/AegisOptimizer/AegisOptimizer.exe`. It resolves writeable config databases (such as `config.json` and `.env`) inside the application directory.

### Target B: Hosted Multi-Tenant Service (Public / SaaS Bot)
Ideal for public deployment where multiple server admins connect via a single hosted bot.
1. **Hosting**: Run the web server and bot processes concurrently on a Linux VPS, Docker container, or platform like Railway.
2. **Reverse Proxy (TLS)**: Front the application with a reverse proxy like Caddy (see `Caddyfile` for automated LetsEncrypt SSL certificate configuration) to encrypt WebSocket handshakes and API tokens.
3. **Linking Flow**: Server owners run the `/linkdashboard` slash command inside their Discord server to receive a temporary 6-digit linking code to unlock their server's panel on the dashboard.

---

## 🤖 Discord Bot Setup Instructions

When you open the web interface for the first time, you will see a Setup Wizard. Here is how to gather the requested credentials:

1. Visit the **[Discord Developer Portal](https://discord.com/developers/applications)**.
2. Click **New Application** on the top right and name it *Aegis Server Optimizer*.
3. Under the **General Information** tab, copy the **Application ID**. This is your **Client ID**.
4. Go to the **Bot** tab on the left sidebar:
   - Scroll down to the **Privileged Gateway Intents** section.
   - **CRITICAL**: Turn on both **Server Members Intent** and **Message Content Intent**. Click **Save Changes**.
   - Scroll back up and click **Reset Token**. Copy the generated token string. This is your **Bot Token**.
5. Paste the **Bot Token** and **Client ID** into the Dashboard Wizard and click **Save & Start Bot**.
6. Once the bot status updates to **Online**, click the **Invite Bot** button in the top right of the dashboard to add the bot to your Discord server (make sure you have Administrator permissions on the server).
7. In the dashboard top-right dropdown, select your server, run a **Scan Server** audit, and execute your desired **Layout Optimization**!

---

## ⚠️ Known Technical Debt & Limits

- **JSON Configuration Contention**: The current version uses local JSON files (`config.json`, `giveaways.json`, `audit_log.json`) for mutable configurations. While sufficient for small-scale local deployments, concurrent writes on large multi-tenant servers under high load can cause file corruptions or race conditions.
- **SQLite Migration Roadmap**: If scaling up for public SaaS usage, it is highly recommended to migrate the configurations, custom commands, leveling stats, backups, and pairings data to a structured SQLite database (using `aiosqlite`) to support transactional integrity and concurrent locks.
