# Changelog

All notable changes to the Aegis Suite project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.7.2] - 2026-09-20

### Added
- **Triage Cockpit Dashboard Architecture (Linear / Snyk Style)**: Replaced cramped, nested column scrollbox with a modern 2026 SaaS Triage Cockpit on the Smart Command Center dashboard. The card highlights the top 4 highest-priority actionable issues ranked by severity, health impact, and safety risk.
- **Slide-Over Action Center Drawer (`#action-center-drawer`)**: Introduced an enterprise slide-over drawer sliding in smoothly from the right with frosted glass backdrop (`#action-drawer-backdrop`), accessible via `"View All Issues in Queue →"`. Features include:
  - **Live Search & Filter**: Real-time debounce search by issue title, category, type, or detail.
  - **Category Filter Tabs**: Dynamic category chips (`All`, `Security`, `Channels`, `Roles`, `Backups`) with live issue counters.
  - **Comprehensive Remediation View**: Scrollable view of all 20+ issues with full permission requirements, projected health gains, and direct remediation buttons.
  - **Drawer Control Toolbar & Footer**: Quick-close triggers (backdrop click, close button, `Esc` keyboard shortcut), potential health gain summary, and one-click "Re-Scan" trigger.
- **Synchronized Batch Safe Remediation**: Synced the `"⚡ Fix All Safe (N)"` one-click remediation action across both the dashboard cockpit header and the action drawer header.

### Fixed
- **"Constantly Moving" Card Jitter & Hover Thrashing**: Eliminated accordion-style dynamic height expansion (`.collapsible-content`) that fired on `mouseenter`/`mouseleave`, which previously caused the entire list of cards to bounce and jump when moving the cursor across cards. Replaced with static inline metadata pills (`+N Health • Score → N%`) with constant, stable card heights and subtle 2px vertical elevation.
- **10-Second Destructive DOM Interval Wiping**: Introduced data-signature hashing (`queueSig = JSON.stringify(...)`) to cache the rendered fix queue. Skipping DOM destruction when telemetry data has not changed prevents the 10-second polling flicker and preserves UI interaction state.
- **Nested Column Scroll-Trapping**: Removed fixed 580px nested scrollbox (`.cc-scrollable-card`) that trapped mouse wheel events on web dashboards. Upgraded to natural-height `.cc-triage-card` with balanced proportions matching the adjacent Command Center Activity Feed.
- **Multi-Theme Action Drawer Styling**: Implemented specialized glassmorphism, border glows, search inputs, and contrast adjustments for Dark Obsidian, Light Quartz, Liquid Glass, and Neon Synthwave themes.

### Changed
- Bumped application cache busters to `v=2.7.2` in `index.html`.

## [2.7.1] - 2026-09-19

### Added
- **Command Center Category Filter Chips**: Added interactive category filter tabs (`All`, `Security`, `Channels`, `Roles`, `Backups`) in Priority Action Center, allowing admins to instantly filter 20+ issues by category with dynamic item counters.
- **1-Click "Fix All Safe" Batch Action**: Added automated batch remediation button in Priority Action Center header (`Fix All Safe (N)`), enabling server administrators to resolve all zero-risk issues in a single click with real-time toast tracking and automatic health score recalibration.
- **Header Global Utility Actions Cluster**: Created `.header-global-actions` container on the far top-right of the dashboard header, housing the live System Telemetry indicator and a dedicated Fullscreen toggle button separated by an elegant glass divider.
- **Aegis Real-Time Sentinel Footer**: Added live continuous telemetry pulse status to the Command Center Activity Feed, maintaining visual symmetry with the adjacent Priority Action Center.

### Fixed
- **Dashboard Long Scroll & Blank Half-Page Layout Flaw**: Resolved asymmetric multi-column grid stretch in Command Center where 24 unpaginated issue cards (~2,100px) forced the adjacent Activity Feed (~150px) to stretch over 2,000px of desolate blank whitespace; introduced `.cc-scrollable-card` and `.cc-scrollable-body` (`height: 580px; overflow-y: auto;`) to equalize both columns into compact, balanced bento cards with smooth internal scrolling and pinned headers.
- **Sub-Optimal Fullscreen Button Placement**: Decoupled the Fullscreen toggle button from inside `.server-selector-wrapper` (where it was mistakenly grouped with Discord guild options) and relocated it to the far top-right window action cluster (`#btn-header-fullscreen`).
- **Sidebar Footer De-congestion**: Removed cramped 3rd button from `.sidebar-footer-actions`, restoring the sidebar footer to a spacious, balanced 2-button layout (`Theme` and `Log Out`) with optimal 44px touch targets.
- **Light & Liquid Glass Theme Fullscreen Affordance**: Added theme-specific styling for the new `.btn-header-utility` button with active glowing borders, micro-press scaling (`scale(0.95)`), and smooth icon transitions (`fa-expand` ↔ `fa-compress`).

### Changed
- Bumped asset cache busters to `v=2.7.1` in `index.html`.

## [2.7.0] - 2026-09-19

### Added
- **Fullscreen Mode Architecture**: Dual-engine fullscreen controller supporting native PyWebView desktop fullscreen and HTML5 Web Fullscreen API fallback, with dedicated sidebar toggle (`#btn-fullscreen-toggle`), header quick-action (`#btn-header-fullscreen`), and global `F11` keyboard shortcut.
- **Ultrawide & High-Resolution Display Support**: Responsive container containment (`max-width: 2200px; margin: 0 auto;`) and fluid grid scaling for 2K, 4K, and 21:9 / 32:9 ultrawide monitors.
- **Living Micro-Interactions & Animation Suite**: Hardware-accelerated cursor spotlight tracking, zero-CPU spring press physics (`transform: scale(0.95)`), SVG circular gauge spring-draw animations, self-terminating requestAnimationFrame KPI odometer counters, and ambient background auroras.
- **Neon Synthwave Cyberpunk Theme**: Added high-energy retro-futuristic synthwave theme with hot magenta glows, cyan accents, dark grid background, and custom analytics card styling.
- **Apple-Grade Alabaster Quartz (Light Theme) Overhaul**: Complete redesign of Light Quartz theme featuring luminous alabaster canvas (`#f8fafc` to `#f1f5f9`), specular white rim glints (`inset 0 1px 0 #ffffff`), dual-stop luminous cursor hover glow with `mix-blend-mode: multiply`, high-contrast white toast cards, and high-visibility toggle switches.
- **Native Desktop Branding**: Stamped `AegisOptimizer.exe` binary with `logo.ico` and bundled high-resolution assets into PyInstaller package.

### Fixed
- **System Tray Icon ("Blue Block" Bug)**: Fixed asset path resolution in `SystemTrayManager` which previously looked inside `%APPDATA%\Aegis` data directory; upgraded `tray_icon.png` to a crisp 64x64 RGBA icon with Lanczos filtering, eliminating the fallback blue rectangle.
- **Window Title Bar Icon**: Resolved issue where WinForms defaulted to generic Windows application icon; dynamically bound `window_ref.native.Icon` to bundled `logo.ico`.
- **Top Header Text & Border Overlap**: Replaced fixed header heights and zero vertical padding with `min-height: var(--header-height); height: auto !important; padding: 14px var(--content-padding-x) !important;` so multi-line subtitle descriptions never clip or intersect `border-bottom`.
- **Macro Gutter Alignment**: Synchronized `.top-header` padding directly with `--content-padding-x` across all responsive breakpoints (`48px`, `32px`, `24px`, `16px`), eliminating the horizontal offset between header controls and bento content cards.
- **Header Controls Baseline Mismatch**: Standardized server selector dropdown and `#btn-refresh-guilds` icon button to matching 36px heights and flex-centered alignments.
- **KPI Stat Card Bottom Axis Alignment**: Converted `.stat-card-clean` to flex column layout with `margin-top: auto` on `.stat-sub` so status badges align along the exact same horizontal baseline across the grid.
- **Bot Connection Details Height Discrepancy**: Applied `align-items: stretch` and matching internal padding (16px 20px) to `.health-metrics` and `.bot-info-details`.
- **Backup CTA Button Baseline**: Structured `.backup-action-box` with flex column layouts and `margin-top: auto` on action buttons to prevent vertical drift from differing description copy.
- **Sidebar Active Nav Indicator Anchoring**: Re-anchored `.nav-item.active::before` flush to the item edge (`left: 0; width: 3.5px; border-radius: 9px 0 0 9px;`) to eliminate clipping on compact sidebars and hover translation drift.
- **Smart Module Pills Grid Distortion**: Refactored `.smart-mod-grid` from flexbox wrap to responsive CSS grid `repeat(auto-fit, minmax(130px, 1fr))`, preventing orphan pills from stretching.
- **Sub-Tab Layout Jump**: Removed rogue `mb-4` from line 760 of `index.html` to establish an identical 20px spacing cadence across all sub-tab views.
- **Dashboard De-congestion & Anti-Flicker**: Eliminated layout flicker during page loads, removed "Live Stream" header text, and added comfortable breathing room across cards.

### Changed
- Updated stylesheet and script cache busters to `v2.7.0` in `index.html`.
- Automatically hide "Target Server:" text label on displays $\le$ 1200px to free up horizontal space for header titles.

---

## [2.4.0] - 2026-07-26

### Added
- **Liquid Glass Design System**: Premium deep frosted glass theme with dynamic glassmorphism tokens (`aegis_theme`), custom HSL color palette, smooth backdrop blurs, and glass surface borders.
- **Independent Discord Invite Link Filter**: Added a standalone `#automod-invites` UI toggle and backend configuration persistence for filtering Discord invite codes (`discord.gg`) independently from general URL link filtering.
- **Real-Time Data & Logs Auto-Sync**: Added 10-second active tab polling and WebSocket message dispatchers in `static/app.js` to auto-refresh Audit Logs, Incident Timelines, System Logs, and Leveling history in real time.
- **Toast Notification Engine Redesign**: Glassmorphic toast notifications with automatic deduplication, reflow re-animations, active timeout resets, and a max 3 toast queue limit.

### Fixed
- **AutoMod & Link Filter Toggle Lock**: Fixed invalid CSS `pointer-events = '1'` property in `updateAutomodTogglesState()`. Sub-toggles can now be turned on/off without interaction locks.
- **Discord Preview Simulators**: Refined centering and padding on Welcome Preview, Panel Message Preview, and Visual Simulator Preview cards across Dark, Light, and Liquid Glass themes.
- **Chart & Canvas Lifecycle**: Added explicit `chart.destroy()` calls in `renderActivityChart` and `renderPermissionHeatmap` to prevent canvas re-render leaks during rapid navigation.

---

## [2.3.0] - 2026-06-23

### Added
- **Adaptive Slowmode System**: 6-layer intelligence replacing static burst threshold. Raid hook (guild-scoped), catastrophic flood detection (30+ msg/s), baseline-aware flood (15+ msg/s + senders + baseline), dynamic threshold with member scaling, progressive escalation (3s/5s/10s/15s), admin protection with auto-remove ownership tracking.
- **Baseline Drift Protection**: Dual-window baseline (`min(5min, 60min)`) prevents attackers from training the detector.
- **Scaled Unique Sender Requirement**: `>= max(3, rate/10)` makes raid spoofing harder at scale.
- **Maturity Index Dashboard**: 6-dimension server health scoring (Security, Moderation, Automation, Growth, Reliability, Community) with animated gauge and progress bars.
- **Chronological Incident Timeline**: 24-hour rolling incident log with automated mitigation action tracking.
- **Config Snapshot History**: Config change tracking and rollback capability.
- **Server Health Gauge Animation**: Animated SVG circle fill with number counter on both Command Center and Smart Features.
- **Welcome Message Variables**: `{user}` now shows display name (username/nickname), `{mention}` for clickable mentions.
- **Sentiment Evasion Normalization**: Abbreviation expansion, leetspeak mapping, repeated char collapse, apostrophe normalization before VADER analysis.
- **Maintenance Cog**: Scheduled role cleanup (daily), DB vacuum (weekly), channel archive (daily).
- **AutoFixEngine Expanded**: 18 action mappings covering all raid detector and spam detector actions.

### Fixed
- Welcome message showing raw user mention instead of username.
- Server Health gauge stuck on "Loading Auditor..." due to duplicate element IDs.
- Config Snapshot History stuck loading due to duplicate `id="cc-config-history"`.
- Skeleton loaders degrading to infinite loading on API failure.
- Emergency slowmode trigger bypassing unique sender checks.
- Raid threat not guild-scoped (applied to all guilds).
- Server Health gauge missing circle animation.

### Changed
- Bot config reloads on every `on_message` for live dashboard changes.
- Dashboard slowmode UI shows adaptive values ("3 msg/s (adaptive)", "3-10s (tiered)").
- 22 development summary files moved to `docs/changelog-archive/`.
- `pyproject.toml` now includes `vaderSentiment` dependency.
- `AegisOptimizer.spec` uses dynamic Discord path resolution instead of hardcoded user path.

---

## [2.2.5] - 2026-06-13

### Added
- "Enable Voting Reactions" toggle switch in the Embed Builder footer settings, allowing server managers to selectively enable or disable automatic emoji reactions for custom embeds.
- Support for inline base64 image data URLs in the Embed Builder, which are decoded and sent as file attachments to Discord.
- Auto-extraction of direct image URLs from Google Images search query URLs.
- Support for username target resolution (e.g. `cyril7662`) in DMs targeting.

### Fixed
- Relocated **Member Milestone Triggers** card from the **Auto-Moderation** tab to the **Welcome Setup** tab for better logical organization.
- Resolved HTML nesting syntax errors that previously broke layout alignment in subsequent tabs (such as Role Creator) and pushed sections out of the main wrapper.
- Fixed Uvicorn config crash on `--noconsole` windowless executables by setting Uvicorn `log_config=None` to avoid checking `sys.stdout` (which is `None` in GUI mode).

## [2.2.4] - 2026-06-12

### Added
- Startup dependency checker that logs OK/MISSING status for all critical dependencies (discord.py, PyNaCl, yt-dlp, FFmpeg, etc.).
- `--install-deps` CLI flag in `run.py` to force dependency installation.
- `probe` parameter on `validate_token()` to skip live Discord API login during startup for faster boot.
- `RevokedToken` SQLAlchemy model for persisting revoked session tokens in SQLite.
- PyJWT integration replacing hand-rolled JWT implementation for session tokens.
- Local bundling of FontAwesome 6.4.0 and Google Fonts (Inter, Outfit) for offline dashboard support.
- `LevelingSettingsModel` and all missing fields added to `ConfigModel` schema.
- `get_active_core()` helper to abstract safe access to the `_active_cores` registry.
- Lazy-initialized `asyncio.Lock` replacing `ThreadSafeReentrantAsyncLock` for giveaway store.
- `asyncio.to_thread` for all file I/O in giveaway load/save operations.

### Changed
- All root-level shim modules (`auth.py`, `bot_manager.py`, `utils.py`, `secret_store.py`, `leveling.py`, `audit_log.py`, `music_manager.py`) removed; all imports migrated to canonical `aegis.*` namespace.
- `load_config()` and `save_config()` now delegate to `ConfigStore` under the hood with dynamic imports to avoid circular dependencies.
- `run.py` rewritten to check for missing packages before installing; reads from `_PACKAGE_IMPORT_MAP` instead of a hardcoded list.
- `load_env_file()` wrapped in try/except to prevent import-time crashes on malformed `.env` files.
- Token and intents startup checks combined into a single `validate_token()` call to halve startup time.
- Engine log output redacted to show only database filename, not absolute path.
- Dashboard Pydantic models consolidated into `aegis/config/schema.py`; duplicate definitions removed from `dashboard.py`.
- Ruff lint rules `F401` (unused imports) and `F841` (unused variables) enabled; all violations cleaned.
- `asyncio.get_event_loop()` replaced with `asyncio.new_event_loop()` + `set_event_loop()` in `__main__.py`.
- DPAPI `.env` deletion gated on `sys.platform == "win32"` to avoid breaking Linux/macOS dev environments.
- CI workflow `verify.yml` updated to run pytest before PyInstaller build.
- `.env` secrets rotated to placeholder values; `.env.backup` deleted; `config.json` sanitized.

### Fixed
- Music `MusicPlayer` import path corrected from `music_manager` shim to `aegis.bot.music`.
- PyNaCl availability check moved to module level with clear error message.
- FFmpeg missing now sends user-facing error message to Discord channel instead of silently failing.
- User-facing error messages improved across bot commands (missing permissions, cooldowns, music failures).
- `audioop` deprecation warning from discord.py (upstream issue, not actionable).

### Removed
- Unused `davey` dependency from `requirements.txt` and `pyproject.toml`.
- Legacy `setup_logging()` function from `aegis/core/utils.py` (replaced by `aegis/core/logging_setup.py`).
- `ThreadSafeReentrantAsyncLock` class (replaced by lazy `asyncio.Lock`).
- Duplicate Pydantic model definitions from `aegis/web/routes/dashboard.py`.

---

## [2.1.0-RC1] - 2026-06-03

### Added
- Created `pyproject.toml` supporting `pip install -e .` editable developer setups.
- Implemented automatic invocation of the console onboarding wizard `first_run_wizard.py` in launcher `run.py` when config is absent.
- Expanded CI/CD pull request workflows in `verify.yml` to run the full pytest suite.
- Added comprehensive `ARCHITECTURE.md` detailing system modules, event loop concurrency, database migration rollbacks, and security models.
- Established issue and pull request templates inside `.github/`.
- Created structured governance files (`CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`).

### Changed
- Standardized release workflows to correctly target the `master` branch.
- Synchronized Inno Setup build settings and versions inside `setup.iss` to `2.1.0-RC1`.
- Cleaned PyInstaller specifications inside `build_exe.py` to auto-resolve packaged modules.
- Modernized tests (`test_hosting_mode_selector.py` and `test_managed_hosting.py`) to import directly from production modules.
- Relocated developer utility script `clean_release.py` into the `scripts/` folder.

### Removed
- Removed the legacy `sys.modules["web_server"]` mock shim from `conftest.py`.
- Removed screenshot placeholders and table layouts from `README.md` (replaced with diagnostic Mermaid diagrams).
