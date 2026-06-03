# Requirements Document

## Introduction

This specification defines **Phase V2.0 — Correctness & Consolidation** for Aegis Suite. It is the first, unblocking phase of the V2 program: a set of correctness and security fixes that must land before any V2 architecture work (SQL config, repositories, cog refactor, plugins) begins.

Aegis Suite currently consists of a legacy core (`bot_manager.py`, `web_server.py`, `utils.py`, `auth.py`) and a newer `aegis/` package that wraps and partially supersedes it. V1 hardening unified several systems (the leveling module is now a redirect shim; `utils.get_writeable_path` now resolves through `Paths`), but three classes of defect remain that are correctness or security risks today:

1. **Config write divergence / data loss** — `aegis/config/loader.ConfigStore.save()` serializes only the fields modeled in `ConfigModel`, so saving through it can delete unmodeled keys (`giveaways`, `scheduled_messages`, `guild_configs`, `revoked_guilds`, `pending_pairings`, `leveling_settings`, `auto_responders`) that the legacy `utils` layer manages in the same file.
2. **Dual entrypoint** — `run.py` launches the legacy `web_server:app`, while the packaged executable launches `aegis/__main__.py` (the AppCore path). Source runs and shipped binaries are therefore different applications.
3. **Unauthenticated destructive endpoints** — recovery and wizard routes are bypassed in the auth middleware by path prefix, so destructive actions (`/api/recovery/db/rebuild`, `/db/restore`, `/restart`) and token overwrite are reachable without an authenticated session in RUNNING state.

This phase also removes shipped test-bypass shortcuts, verifies the already-unified leveling singleton with a regression lock, and stops bundling developer secrets (`.env.enc`) into the distributed executable.

This phase is **correctness and consolidation only**. It introduces no new architectural abstractions (no SQL-backed config, no dependency-injection container, no event bus, no repository layer). Config storage remains JSON at `%APPDATA%\Aegis\config\config.json`; only write *behavior* changes.

## Glossary

- **Aegis_Suite**: The combined single-process application comprising the Discord bot, the FastAPI dashboard, and the recovery/wizard web surface.
- **ConfigStore**: The configuration accessor in `aegis/config/loader.py` that loads, validates (via `ConfigModel`), and atomically saves the JSON configuration file.
- **ConfigModel**: The Pydantic model set in `aegis/config/schema.py` (`ConfigModel`, `WelcomeSettingsModel`, `AutomodSettingsModel`, `TicketSettingsModel`) describing the modeled subset of configuration.
- **Legacy_Config_Layer**: The configuration CRUD in `utils.py` (`load_config`, `save_config`, `config_lock`, `DEFAULT_CONFIG`) that reads and writes the same JSON file and preserves all keys.
- **Config_File**: The JSON configuration file resolved by `Paths().config_file` at `%APPDATA%\Aegis\config\config.json`.
- **Unmodeled_Key**: Any key present in the Config_File that is not a field of ConfigModel (for example `giveaways`, `scheduled_messages`, `guild_configs`, `revoked_guilds`, `pending_pairings`, `leveling_settings`, `auto_responders`).
- **Config_Lock**: The single re-entrant lock `utils.config_lock` that serializes all config writes.
- **Unified_Entrypoint**: The `aegis/__main__.py` `main()` function that builds and runs `AppCore`.
- **AppCore**: The orchestrator in `aegis/core/app_core.py` that owns the event loop, lifecycle state machine, and subsystems.
- **Lifecycle_State**: The current state from `aegis/core/state.py` (`BOOTING`, `SAFE_MODE`, `RUNNING`, `SHUTTING_DOWN`), accessible via `core.state.current_state`.
- **Auth_Middleware**: The HTTP middleware in `aegis/web/app.py` that gates `/api/*` requests.
- **Destructive_Recovery_Endpoint**: One of `POST /api/recovery/db/rebuild`, `POST /api/recovery/db/restore`, `POST /api/recovery/restart`.
- **Pre_Auth_Recovery_Endpoint**: Wizard and recovery endpoints required for first-run and lockout recovery (wizard token/guilds/templates/finish, `POST /api/recovery/token`, `POST /api/recovery/retry`, `GET /api/recovery/backups`).
- **Admin_Session**: A session whose validated JWT role is `admin`, per `auth.validate_session` and `auth.get_session_role`.
- **Token_Validation_Routine**: `validate_token` in `aegis/bot/runner.py`, used by startup checks and the wizard.
- **Test_Bypass**: Shipped logic that returns a success verdict based on a hardcoded token literal, a substring heuristic, or the `PYTEST_CURRENT_TEST` environment variable, rather than performing real validation.
- **Leveling_System**: The single `LevelingSystem` instance exported as `aegis.bot.leveling.leveling_system` and re-exported by the legacy `leveling.py` shim.
- **Secret_Files**: The `.env` and `.env.enc` files holding the Discord token and other secrets.
- **Distributed_Executable**: The PyInstaller-produced `AegisOptimizer.exe` shipped to users, configured by `build_exe.py` and `AegisOptimizer.spec`.
- **Maintainer**: The operator running Aegis_Suite.

## Requirements

### Requirement 1: Non-destructive configuration writes

**User Story:** As a Maintainer, I want saving configuration through any code path to preserve all of my existing settings, so that an edit through the new ConfigStore never silently deletes features like giveaways, scheduled messages, or per-guild configuration.

#### Acceptance Criteria

1. WHEN ConfigStore.save() writes the Config_File, THE Aegis_Suite SHALL preserve every Unmodeled_Key and its value that existed in the Config_File prior to the write.
2. WHEN ConfigStore.save() writes a field that is modeled in ConfigModel, THE Aegis_Suite SHALL use the model's value for that field.
3. WHEN ConfigStore.save() executes, THE Aegis_Suite SHALL read the prior on-disk Config_File and merge the model fields over it rather than replacing the file with only modeled fields.
4. THE ConfigStore SHALL perform the read-merge-write sequence under the Config_Lock and SHALL NOT introduce a second, separate lock.
5. WHEN ConfigStore.save() executes, THE Aegis_Suite SHALL retain the existing atomic temp-file-then-replace behavior and the existing `backups/config` snapshot behavior.
6. IF the write fails after the temporary file is created, THEN THE Aegis_Suite SHALL remove the temporary file and SHALL NOT leave the Config_File in a partially written state.

### Requirement 2: Configuration schema preserves unknown fields

**User Story:** As a Maintainer, I want the configuration models to keep fields they do not recognize, so that a model round-trip cannot drop data added by other components or future versions.

#### Acceptance Criteria

1. THE ConfigModel and its nested models (WelcomeSettingsModel, AutomodSettingsModel, TicketSettingsModel) SHALL be configured to allow and retain extra fields.
2. WHEN a config model is constructed from a dictionary containing keys not declared as fields, THE Aegis_Suite SHALL retain those keys in the model's serialized output.
3. THE Aegis_Suite SHALL NOT change the names, types, or default values of existing modeled fields in this phase.

### Requirement 3: Single consolidated entrypoint

**User Story:** As a developer, I want the source run and the packaged executable to launch the same application, so that testing the source path validates what ships.

#### Acceptance Criteria

1. WHEN the source entrypoint `run.py` launches the application, THE Aegis_Suite SHALL delegate the launch to the Unified_Entrypoint `aegis/__main__.py` `main()`.
2. THE Aegis_Suite SHALL NOT launch the legacy `web_server:app` as the served application from `run.py`.
3. THE `run.py` module SHALL NOT import `web_server` at module load time after this change.
4. WHEN delegating to the Unified_Entrypoint, THE Aegis_Suite SHALL NOT create or run a second asyncio event loop around the entrypoint, WHERE the Unified_Entrypoint already manages its own loop.
5. THE Aegis_Suite SHALL retain source-run environment preparation (virtual-environment creation, dependency installation, FFmpeg PATH resolution) that is required only for source runs, WHERE such preparation does not affect the frozen executable.
6. THE Aegis_Suite SHALL remove the legacy console first-run wizard invocation from the `run.py` launch path and SHALL NOT delete the `first_run_wizard.py` module in this phase.

### Requirement 4: Recovery and wizard endpoint authorization

**User Story:** As a Maintainer, I want destructive recovery actions to require an authenticated administrator, so that a logged-out user, another local process, or a cross-origin browser request cannot wipe my database or overwrite my token while the app is running.

#### Acceptance Criteria

1. WHILE the Lifecycle_State is RUNNING, IF a request to a Destructive_Recovery_Endpoint does not carry a valid Admin_Session, THEN THE Aegis_Suite SHALL reject the request with HTTP 401 or 403 and SHALL NOT perform the action.
2. THE Aegis_Suite SHALL require a valid Admin_Session for every Destructive_Recovery_Endpoint in every Lifecycle_State.
3. WHILE the Lifecycle_State is SAFE_MODE, or WHILE the admin password hash is unset (first run), THE Aegis_Suite SHALL allow access to Pre_Auth_Recovery_Endpoints without an authenticated session so that first-run setup and lockout recovery remain possible.
4. THE Auth_Middleware SHALL determine the SAFE_MODE carve-out from the authoritative lifecycle state at `request.app.state.core.state.current_state`.
5. IF a state-changing request to a wizard or recovery endpoint carries an `Origin` header that does not match the local dashboard origin, THEN THE Aegis_Suite SHALL reject the request.
6. WHERE a state-changing wizard or recovery request carries no `Origin` header, THE Aegis_Suite SHALL allow the request to proceed to its normal authorization check.
7. THE Aegis_Suite SHALL apply the Admin_Session check both in the Auth_Middleware and within each Destructive_Recovery_Endpoint handler as defense in depth.

### Requirement 5: Leveling system unification verification

**User Story:** As a Maintainer, I want there to be exactly one leveling data store, so that XP awarded by the bot is the same XP read by the dashboard and persisted to the database.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL expose exactly one Leveling_System instance, such that `leveling.leveling_system` and `aegis.bot.leveling.leveling_system` refer to the identical object.
2. WHEN the Leveling_System has had its database engine set, THE Aegis_Suite SHALL make a value written through the bot-facing import readable through the database-facing import.
3. IF a second independent Leveling_System instantiation is discovered, THEN THE implementer SHALL report it and SHALL NOT refactor leveling behavior within this phase.

### Requirement 6: Removal of production test bypasses

**User Story:** As a Maintainer, I want token and guild validation to always perform real checks in the shipped product, so that a malformed or fake token cannot be accepted as valid.

#### Acceptance Criteria

1. THE Token_Validation_Routine SHALL NOT return a validation verdict based on a hardcoded token literal, a token substring heuristic, or the `PYTEST_CURRENT_TEST` environment variable.
2. WHEN the Token_Validation_Routine is invoked in shipped code, THE Aegis_Suite SHALL perform the real validation path consisting of a format check and a Discord login probe bounded by the configured timeout.
3. THE `/wizard/guilds` endpoint SHALL NOT return hardcoded placeholder guilds and SHALL always query the real Discord guilds API.
4. THE shipped (non-test) code under `aegis/` SHALL contain none of the removed Test_Bypass literals.
5. WHERE existing tests relied on Test_Bypass behavior, THE Aegis_Suite test suite SHALL be updated to inject a test double (mock) for the Discord client or HTTP call rather than relying on shipped shortcuts.

### Requirement 7: Secret storage hygiene

**User Story:** As a Maintainer, I want my secrets stored in my user data directory and never embedded in the shipped executable, so that distributing or upgrading the executable cannot leak or delete my credentials.

#### Acceptance Criteria

1. THE build configuration in `build_exe.py` and `AegisOptimizer.spec` SHALL NOT bundle `.env` or `.env.enc` into the Distributed_Executable.
2. THE Aegis_Suite SHALL resolve the Secret_Files under the data directory root `%APPDATA%\Aegis` at runtime.
3. THE build configuration SHALL continue to bundle the non-secret data sets required at runtime: `static`, `templates`, `alembic.ini`, and `aegis/db/migrations`.
4. IF runtime verification finds that the Secret_Files do not resolve under the data directory root, THEN THE implementer SHALL report the discrepancy and SHALL NOT silently rework the path fallback in this phase.

## Out of Scope

The following are explicitly excluded from Phase V2.0 and belong to later V2 phases:

1. SQL-backed configuration, the repository pattern, and removal of the JSON config format.
2. Dependency-injection container, service registry, and event bus.
3. Discord cog refactor and command isolation.
4. RBAC redesign and WebSocket migration of the dashboard.
5. Plugin SDK work of any kind.
6. Deleting the legacy modules `web_server.py`, `bot_manager.py`, or `first_run_wizard.py`.
7. Dedicated indexed XP tables and any change to leveling persistence behavior.
