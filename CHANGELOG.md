# Changelog

All notable changes to the Aegis Suite project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
- Welcome message showing raw `<@ID>` instead of username.
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
