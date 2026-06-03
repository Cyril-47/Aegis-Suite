# Requirements Document

## Introduction

Aegis Suite is a local-first Discord server management application for non-technical users — small community owners, streamers, gaming communities, and beginners with little technical knowledge. The product goal is to make creating and managing Discord communities simple through a guided web interface, with no command line ever required.

This specification — "Aegis Suite — Foundational Architecture" — defines the Phase 1 (V1) foundation: a single-process monolith that hosts the Discord bot, the HTTP API, and the web dashboard inside one Uvicorn-hosted asyncio event loop. The architecture is deliberately defensive, packageable into a single executable, and incrementally refactorable over a six-month horizon.

This is a **refactor of an existing, working Discord bot codebase**, not a greenfield rewrite. The current codebase already provides a Discord bot (`bot_manager.py`), a FastAPI dashboard (`web_server.py`), authentication (`auth.py`), a first-run wizard (`first_run_wizard.py`), a secret store (`secret_store.py`), an audit log (`audit_log.py`), leveling and music features (`leveling.py`, `music_manager.py`), static dashboard assets under `static/`, and built-in server templates (`templates/community.json`, `templates/gaming.json`). The foundational architecture **preserves and relocates** this functionality rather than replacing it: existing FastAPI routes, Discord.py cogs, and dashboard templates are wrapped and moved into a new folder structure, and the existing SQLite schema is folded into Alembic via a baseline revision rather than recreated.

The architectural stance is governed by three principles:

1. **One process, one event loop** — bot, API, and dashboard share a single asyncio loop. No IPC, no second runtime, no threads for the bot.
2. **YAGNI enforced** — extension points are plain Python base classes and registry dictionaries. No dependency-injection container, no factory framework, no event bus, no microservices, no Docker, no Redis, no message queue.
3. **Refactor, don't rewrite** — existing working functionality is wrapped and relocated; mutable state is separated from code so the executable can be replaced without data loss.

The foundation introduces an `AppCore` lifecycle state machine (BOOTING → SAFE_MODE | RUNNING → SHUTTING_DOWN), a fail-soft startup sequence, a first-class Safe Mode recovery state, a guided Setup Wizard, silent backed-up database migrations, a data-driven template engine, a Beginner/Advanced UI mode flag, a mobile-friendly responsive dashboard layer, a one-click diagnostics packager, and a lightweight health registry. All recovery and configuration happens in-browser.

## Glossary

- **Aegis_Suite**: The combined single-process application comprising the Discord bot, the HTTP API, and the web dashboard, deployed as a single Windows executable.
- **AppCore**: The single top-level object that owns the asyncio event loop lifecycle and three concerns: the Lifecycle_State_Machine, the ASGI_Server_Task, and the Bot_Task.
- **Lifecycle_State_Machine**: The state machine governing application state with the states BOOTING, SAFE_MODE, RUNNING, and SHUTTING_DOWN.
- **Event_Loop**: The single shared asyncio event loop that hosts both the ASGI_Server_Task and the Bot_Task.
- **ASGI_Server_Task**: The asyncio task running the programmatically launched Uvicorn server that serves the Web_Layer.
- **Bot_Task**: The supervised, cancellable asyncio task running the Discord bot. It is started in RUNNING state and is absent in SAFE_MODE.
- **Web_Layer**: The FastAPI application, HTTP routes, dashboard templates, and static assets served by the ASGI_Server_Task. The Web_Layer is the recovery surface and runs in both RUNNING and SAFE_MODE.
- **Safe_Mode**: A first-class operating state in which the Web_Layer is active and the Bot_Task is not started. Safe_Mode carries a Reason_Code that drives the recovery flow rendered in the dashboard.
- **Reason_Code**: A single value identifying why Safe_Mode was entered. The defined Reason_Codes are `needs-setup`, `token-recovery`, `db-recovery`, and `intent-recovery`.
- **Startup_Check**: One step in the linear startup sequence. Each Startup_Check produces a Verdict and records its result into the Health_Registry.
- **Verdict**: The outcome of a Startup_Check, one of `OK`, `FATAL-to-bot`, or `FATAL-to-app`. A `FATAL-to-bot` Verdict causes a transition to Safe_Mode; a `FATAL-to-app` Verdict prevents startup.
- **Setup_Wizard**: The guided, in-browser onboarding flow served by the Web_Layer. It runs automatically on first launch and is the recovery target for the `needs-setup` Reason_Code.
- **Setup_Complete_Flag**: A persisted configuration flag indicating that the Setup_Wizard has been completed. Its absence triggers `needs-setup` Safe_Mode on every boot.
- **Token_Validation_Routine**: The single shared routine that validates a Discord token via a lightweight authentication probe and checks intent capability. It is invoked both by a Startup_Check and by the Setup_Wizard token step.
- **Data_Directory**: The user-data directory located at `%APPDATA%\Aegis\`, outside the executable, holding all mutable state (database, config, backups, templates, diagnostics, logs).
- **Paths_Module**: The single source of truth (`aegis/config/paths.py`) for all file and directory locations under the Data_Directory; it creates missing directories on boot.
- **Config_Store**: The persisted application configuration at `%APPDATA%\Aegis\config\config.json`, including the Setup_Complete_Flag and the UI_Mode flag.
- **Secret_Store**: The persisted, DPAPI-protected secret store at `%APPDATA%\Aegis\.env.enc` on Windows (falling back to plaintext `.env` on non-Windows/development), storing the Discord token and the JWT session secret.
- **Database**: The SQLite database file at `%APPDATA%\Aegis\aegis.db`, accessed through SQLAlchemy ORM with WAL journaling and a single-connection model.
- **Migration_Engine**: The Alembic-based component that compares the Database's current revision to head and applies pending migrations silently, with an automatic full-file backup taken before each migration.
- **DB_Backup**: A full-file copy of the Database written to `%APPDATA%\Aegis\backups\db\` before a migration, named `aegis_<rev>_<timestamp>.db`.
- **Template**: A plain JSON document describing a server's intended structure (categories, channels, roles, permission outlines, optional defaults).
- **Templates_Engine**: The component (`aegis/templates_engine/`) that defines and validates the Template schema, imports and exports Templates, applies a Template to a guild, and clones a guild into a Template.
- **Builtin_Template**: One of three shipped Templates (Gaming, Community, Creator) stored as JSON files under `templates/builtin/`, loaded as data rather than hardcoded.
- **Template_Registry**: A registry dictionary mapping a Template `kind` value to its Builtin_Template file.
- **UI_Mode**: A single presentation flag stored in the Config_Store with the values `beginner` and `advanced`. Beginner is the default. UI_Mode controls only what the frontend renders, never backend capability.
- **Health_Registry**: A plain shared in-memory object that each subsystem updates in place during the lifecycle. It backs the health payload exposed by the Web_Layer.
- **Health_Payload**: The JSON document assembled from the Health_Registry describing the state of the web, database, bot, intents, and Safe_Mode subsystems.
- **Diagnostics_Packager**: The component (`aegis/diagnostics/packager.py`) that assembles a sanitized, read-only diagnostics archive on demand.
- **Diagnostics_Package**: A timestamped zip archive written under `%APPDATA%\Aegis\diagnostics\` containing logs, app version, database status, runtime status, and a sanitized config snapshot.
- **Config_Sanitizer**: The centralized serializer that redacts the Discord token and all secrets before configuration data reaches the Diagnostics_Package or the logs.
- **Maintainer**: The non-technical operator who installs and runs Aegis_Suite on their own Windows machine.

## Requirements

### Requirement 1: Single-process shared event loop orchestration

**User Story:** As a Maintainer running Aegis on my own Windows PC, I want the bot, API, and dashboard to run together in one process, so that the application is simple to launch, debug, and package as a single executable.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL run the ASGI_Server_Task and the Bot_Task concurrently within a single shared Event_Loop inside one operating-system process.
2. THE AppCore SHALL own the Event_Loop lifecycle and SHALL hold the Lifecycle_State_Machine, the ASGI_Server_Task, and the Bot_Task.
3. THE Aegis_Suite SHALL launch Uvicorn programmatically as the ASGI_Server_Task and SHALL NOT spawn a separate Uvicorn process.
4. THE Aegis_Suite SHALL run the Discord bot as the Bot_Task and SHALL NOT invoke a blocking `bot.run()` entry point.
5. THE Aegis_Suite SHALL NOT use operating-system threads, inter-process communication, or a second runtime to coordinate the bot, the API, and the dashboard.
6. IF an unhandled exception occurs during AppCore startup before the Lifecycle_State_Machine reaches its running state, THEN THE AppCore SHALL transition the Lifecycle_State_Machine to SAFE_MODE, SHALL keep the operating-system process running, and SHALL record a diagnostic indicating the failure cause.
7. WHEN the AppCore requests cancellation of the Bot_Task or the ASGI_Server_Task, THE Aegis_Suite SHALL terminate the requested task within 10 seconds.
8. WHILE the Lifecycle_State_Machine is in its running state, IF the Bot_Task terminates unexpectedly, THEN THE AppCore SHALL transition the Lifecycle_State_Machine to SAFE_MODE and SHALL keep the operating-system process running.
9. WHEN a shutdown is requested, THE AppCore SHALL cancel both the ASGI_Server_Task and the Bot_Task and SHALL stop the Event_Loop within 15 seconds.

### Requirement 2: Lifecycle state machine

**User Story:** As a Maintainer, I want the application to track exactly what state it is in, so that the dashboard always shows me a coherent picture of whether the bot is running or recovering.

#### Acceptance Criteria

1. THE Lifecycle_State_Machine SHALL occupy exactly one of the states BOOTING, SAFE_MODE, RUNNING, or SHUTTING_DOWN at any time.
2. WHEN the Aegis_Suite process starts, THE Lifecycle_State_Machine SHALL begin in the BOOTING state.
3. WHEN all Startup_Checks return an `OK` Verdict, THE Lifecycle_State_Machine SHALL transition from BOOTING to RUNNING.
4. WHEN any Startup_Check returns a `FATAL-to-bot` Verdict, THE Lifecycle_State_Machine SHALL transition from BOOTING to SAFE_MODE carrying the corresponding Reason_Code.
5. WHEN a shutdown signal is received, THE Lifecycle_State_Machine SHALL transition to SHUTTING_DOWN.
6. THE AppCore SHALL record the current Lifecycle_State_Machine state into the Health_Registry on every state transition.

### Requirement 3: Graceful and idempotent shutdown

**User Story:** As a Maintainer, I want closing the application to shut down cleanly without leaving the database or Discord connection in a broken state, so that my next launch starts cleanly.

#### Acceptance Criteria

1. WHEN a shutdown signal is received, THE AppCore SHALL set the Lifecycle_State_Machine to SHUTTING_DOWN before performing any teardown step.
2. WHEN shutting down, THE AppCore SHALL cancel the Bot_Task and await the Discord connection close before stopping the ASGI_Server_Task, WHERE the Bot_Task is present.
3. WHEN stopping the ASGI_Server_Task, THE AppCore SHALL signal Uvicorn to stop and SHALL drain in-flight requests within a bounded timeout.
4. WHEN the ASGI_Server_Task has stopped, THE AppCore SHALL dispose the SQLAlchemy engine and flush logs before closing the Event_Loop.
5. WHEN shutdown completes, THE AppCore SHALL exit with process status code 0.
6. THE AppCore SHALL make every shutdown step idempotent and bounded by a timeout.
7. IF a second shutdown signal is received during SHUTTING_DOWN, THEN THE AppCore SHALL force immediate process exit.

### Requirement 4: Data directory separation from executable

**User Story:** As a Maintainer, I want all my settings and data stored outside the executable, so that replacing the executable with a newer build never loses my configuration or community templates.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL store all mutable state under the Data_Directory at `%APPDATA%\Aegis\`.
2. THE Aegis_Suite SHALL store within the Data_Directory the Database at `aegis.db`, the Config_Store at `config\config.json`, database backups under `backups\db`, config backups under `backups\config`, built-in templates under `templates\builtin`, user templates under `templates\user`, diagnostics archives under `diagnostics`, and log files at `logs\aegis.log` and `logs\aegis.err.log`.
3. THE Aegis_Suite SHALL include within the executable only application code and shipped default files and SHALL NOT write mutable state inside the executable's install location.
4. THE Paths_Module SHALL be the single source of truth for all Data_Directory locations.
5. WHEN the Aegis_Suite boots, THE Paths_Module SHALL create any missing directory within the Data_Directory.
6. WHERE the Data_Directory is replaced alongside a newer executable build, THE Aegis_Suite SHALL retain all previously stored configuration, database, templates, and backups.

### Requirement 5: Fail-soft startup sequence

**User Story:** As a Maintainer, I want the application to detect problems at startup and guide me to a fix instead of crashing, so that I am never stranded at a blank screen.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL execute the Startup_Checks in dependency order: (1) resolve the Data_Directory and create missing directories, (2) initialize logging with rotation, (3) load the Config_Store, (4) open the Database and run a PRAGMA integrity check, (5) run pending Alembic migrations with a backup, (6) validate the Discord token via the Token_Validation_Routine, and (7) verify required intents are declared and enabled.
2. IF a Startup_Check returns a non-`OK` Verdict, THEN THE Aegis_Suite SHALL stop the Startup_Check sequence and SHALL NOT execute the remaining Startup_Checks.
3. IF resolving the Data_Directory fails because the location is unwritable, THEN THE Aegis_Suite SHALL treat the Verdict as `FATAL-to-app`, present an observable error indication identifying the unwritable location, and SHALL NOT continue startup.
4. IF logging initialization with rotation fails, THEN THE Aegis_Suite SHALL degrade to console logging and SHALL continue startup.
5. IF the Config_Store is missing, unreadable, or fails validation, THEN THE Aegis_Suite SHALL transition to SAFE_MODE with Reason_Code `needs-setup`.
6. IF the Aegis_Suite cannot open the Database or the Database PRAGMA integrity check reports corruption, THEN THE Aegis_Suite SHALL transition to SAFE_MODE with Reason_Code `db-recovery`.
7. IF the Discord token fails validation, including when the Token_Validation_Routine authentication probe does not return within 10 seconds, THEN THE Aegis_Suite SHALL transition to SAFE_MODE with Reason_Code `token-recovery`.
8. IF a required intent is not declared and enabled, THEN THE Aegis_Suite SHALL transition to SAFE_MODE with Reason_Code `intent-recovery`.
9. WHEN every Startup_Check returns an `OK` Verdict, THE Aegis_Suite SHALL transition to RUNNING, start the ASGI_Server_Task, start the Bot_Task, and open the default browser to the dashboard.
10. WHEN any Startup_Check returns a `FATAL-to-bot` Verdict, THE Aegis_Suite SHALL transition to SAFE_MODE, start the ASGI_Server_Task only, leave the Bot_Task unstarted, and open the default browser to the recovery flow.
11. IF the default browser does not open after the Aegis_Suite starts the ASGI_Server_Task, THEN THE Aegis_Suite SHALL record an observable indication of the local dashboard URL so the Maintainer can open it manually.
12. THE Aegis_Suite SHALL record the Verdict of each Startup_Check into the Health_Registry.

### Requirement 6: Web layer available in every operating state

**User Story:** As a Maintainer whose setup failed, I want the dashboard to still load, so that I can fix the problem in my browser without touching a command line.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL start the ASGI_Server_Task in both the RUNNING state and the SAFE_MODE state.
2. THE Aegis_Suite SHALL NOT disable the Web_Layer in any non-shutdown state.
3. WHILE the Lifecycle_State_Machine is in SAFE_MODE, THE Aegis_Suite SHALL serve the recovery flow through the Web_Layer.

### Requirement 7: First-class Safe Mode recovery state

**User Story:** As a non-technical Maintainer, I want Safe Mode to walk me through fixing whatever went wrong, so that I can recover entirely in my browser without restarting or using a terminal.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL treat Safe_Mode as a first-class operating state carrying exactly one Reason_Code drawn from the set {`needs-setup`, `token-recovery`, `db-recovery`, `intent-recovery`}, and SHALL render the Reason_Code-specific recovery flow rather than a generic error screen.
2. WHILE in Safe_Mode, THE Aegis_Suite SHALL keep the Web_Layer serving HTTP requests and SHALL keep the Bot_Task in an unstarted state.
3. WHEN the Reason_Code is `needs-setup`, THE Aegis_Suite SHALL render the Setup_Wizard as the recovery flow.
4. WHEN the Reason_Code is `token-recovery`, THE Aegis_Suite SHALL render a flow to re-enter and re-validate the Discord token.
5. WHEN the Reason_Code is `db-recovery`, THE Aegis_Suite SHALL render a flow offering to restore from a DB_Backup, rebuild the Database, or open diagnostics.
6. WHEN the Reason_Code is `intent-recovery`, THE Aegis_Suite SHALL render guided intent instructions and a re-check control.
7. WHEN the Maintainer completes the guided fix and requests a retry, THE Aegis_Suite SHALL re-run the Startup_Checks beginning at the step associated with the active Reason_Code and SHALL complete the re-run within 30 seconds.
8. WHEN a retry causes all re-run Startup_Checks to return an `OK` Verdict, THE Aegis_Suite SHALL promote the Lifecycle_State_Machine from SAFE_MODE to RUNNING and SHALL start the Bot_Task on the running Event_Loop within 5 seconds without restarting the process.
9. IF a retry leaves any re-run Startup_Check with a non-`OK` Verdict, THEN THE Aegis_Suite SHALL remain in SAFE_MODE, SHALL retain the active Reason_Code, and SHALL render guidance corresponding to the non-`OK` Verdict of the failed Startup_Check.
10. THE Aegis_Suite SHALL present guided in-browser recovery as the primary recovery option and SHALL offer a full process restart as a fallback recovery option.
11. THE Aegis_Suite SHALL include the Safe_Mode active state and Reason_Code in the Health_Payload.
12. THE Aegis_Suite SHALL perform all Safe_Mode recovery through guided web interface actions and SHALL NOT require any command-line interaction.
13. WHILE re-running Startup_Checks after a retry request, THE Aegis_Suite SHALL keep the Web_Layer serving HTTP requests and SHALL indicate to the Maintainer that a re-check is in progress.

### Requirement 8: Setup Wizard onboarding flow

**User Story:** As a beginner creating my first Discord community, I want a step-by-step setup wizard, so that I can connect my bot and build my server without any technical knowledge.

#### Acceptance Criteria

1. WHEN the Aegis_Suite boots and the Setup_Complete_Flag is absent, THE Aegis_Suite SHALL enter SAFE_MODE with Reason_Code `needs-setup` and serve the Setup_Wizard.
2. THE Setup_Wizard SHALL present the steps in order: Welcome overview, Token entry, Server selection, Template selection, and Finish.
3. WHEN the Maintainer submits a Discord token in the Token entry step, THE Aegis_Suite SHALL validate the token using the Token_Validation_Routine, completing the authentication probe and the intent capability check within 10 seconds.
4. WHEN token validation succeeds, THE Aegis_Suite SHALL persist the token to the Secret_Store and SHALL NOT write the token to any log file or Diagnostics_Package.
5. IF token validation fails, or does not complete within the 10-second validation timeout, in the Token entry step, THEN THE Aegis_Suite SHALL display an inline error message indicating whether the authentication probe or the intent capability check failed, SHALL keep the Maintainer on the Token entry step, and SHALL NOT advance to the Server selection step.
6. WHEN the Maintainer reaches the Server selection step, THE Aegis_Suite SHALL enumerate the guilds accessible to the validated token and SHALL allow the Maintainer to select exactly one target guild.
7. THE Setup_Wizard SHALL offer in the Template selection step the choices Gaming, Community, Creator, and start-empty, and SHALL display a preview of the selected Template structure before it is applied.
8. WHEN the Maintainer completes the Finish step, THE Aegis_Suite SHALL set the Setup_Complete_Flag in the Config_Store and re-run the Startup_Checks.
9. THE Setup_Wizard SHALL reuse the Token_Validation_Routine that the startup token Startup_Check uses, as a single shared code path invoked by two callers.
10. THE Setup_Wizard SHALL reuse the dashboard layout and shared components.
11. WHILE the Setup_Complete_Flag is absent, THE Aegis_Suite SHALL re-enter `needs-setup` Safe_Mode on every boot until the Setup_Wizard is completed.
12. IF the guild enumeration in the Server selection step returns zero accessible guilds or does not complete within 10 seconds, THEN THE Aegis_Suite SHALL display an inline message indicating that no selectable guild is available and SHALL NOT advance to the Template selection step.
13. WHEN every Startup_Check re-run after the Finish step returns an `OK` Verdict, THE Aegis_Suite SHALL redirect the browser to the dashboard.
14. IF re-running the Startup_Checks after the Finish step yields any non-`OK` Verdict, THEN THE Aegis_Suite SHALL remain in SAFE_MODE carrying the Reason_Code corresponding to the failed Startup_Check and SHALL NOT redirect the browser to the dashboard.

### Requirement 9: Database storage and access model

**User Story:** As a Maintainer, I want my configuration and community data stored in a reliable local database, so that my settings survive restarts and are safe from corruption under normal use.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL store persistent application data in a SQLite Database at `%APPDATA%\Aegis\aegis.db` accessed through the SQLAlchemy ORM.
2. THE Aegis_Suite SHALL operate the Database with WAL journaling and a single-connection model.
3. THE Database SHALL contain the V1 schema tables `schema_meta`, `config_kv`, `templates`, `servers`, `apply_history`, and `migration_log`.
4. THE `schema_meta` table SHALL store key and value pairs for version tracking and application metadata.
5. THE `templates` table SHALL store the fields `id`, `name`, `kind`, `json`, `source`, and `created_at`.
6. THE `servers` table SHALL store the fields `id`, `guild_id`, `name`, `mode`, and `last_synced`.
7. THE `apply_history` table SHALL store the fields `id`, `server_id`, `template_id`, `applied_at`, and `result`.
8. THE `migration_log` table SHALL store the fields `id`, `from_rev`, `to_rev`, `backup_path`, `status`, and `ts`.

### Requirement 10: Silent, backed-up, reversible migrations

**User Story:** As a non-technical Maintainer, I want database upgrades to happen automatically and safely, so that updating Aegis never asks me to run migration commands or risks losing my data.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL use Alembic as the authoritative owner of the Database schema.
2. THE Aegis_Suite SHALL adopt the existing tables into Alembic through an initial baseline revision rather than recreating them, so existing databases gain version tracking without data loss.
3. WHEN the Aegis_Suite boots, THE Migration_Engine SHALL read the Database's current revision and compare it to the head revision.
4. WHEN the current revision equals the head revision, THE Migration_Engine SHALL continue startup silently without creating a DB_Backup, without running a migration, and without recording a `migration_log` row.
5. WHEN the current revision is behind the head revision, THE Migration_Engine SHALL copy the Database to a DB_Backup named `aegis_<rev>_<timestamp>.db` under `backups\db` before applying any migration.
6. WHEN beginning a migration, THE Migration_Engine SHALL record a `migration_log` row with status `started` capturing the from and to revisions.
7. WHEN a migration completes successfully, THE Migration_Engine SHALL set the corresponding `migration_log` status to `success` and record the DB_Backup path.
8. IF a migration fails, THEN THE Migration_Engine SHALL restore the DB_Backup over the Database, set the corresponding `migration_log` status to `rolled_back`, and transition to SAFE_MODE with Reason_Code `db-recovery`.
9. THE Migration_Engine SHALL retain at most the 10 most recent DB_Backup files under `backups\db` and SHALL delete older DB_Backup files.
10. IF the Database was created by a newer build whose revision is ahead of the running build's head revision, THEN THE Aegis_Suite SHALL refuse to downgrade the Database and SHALL transition to SAFE_MODE with Reason_Code `db-recovery`.
11. IF creating the DB_Backup fails before a migration is applied, THEN THE Migration_Engine SHALL abort the migration, leave the Database unchanged, record a `migration_log` row capturing the failure, and transition to SAFE_MODE with Reason_Code `db-recovery`.
12. IF restoring the DB_Backup over the Database fails during a rollback, THEN THE Migration_Engine SHALL set the corresponding `migration_log` status to `rolled_back` and transition to SAFE_MODE with Reason_Code `db-recovery`.

### Requirement 11: Template schema and validation

**User Story:** As a Maintainer, I want server templates to follow one well-defined format, so that built-in templates, my imports, and my exports all behave consistently.

#### Acceptance Criteria

1. THE Templates_Engine SHALL define a Template as a JSON document describing categories, channels, roles, permission outlines, and optional defaults.
2. THE Templates_Engine SHALL validate every Template against the Template JSON schema before storing or applying it.
3. THE Templates_Engine SHALL route Builtin_Templates, imported Templates, and exported Templates through the same validation path and the same apply path.
4. IF a Template fails schema validation, THEN THE Templates_Engine SHALL reject the Template and return a descriptive error.
5. THE Templates_Engine SHALL expose the operations defined in `model.py` for schema definition and validation, `io.py` for import and export, and `apply.py` for apply-to-server and clone-from-server.

### Requirement 12: Data-driven built-in templates and extension point

**User Story:** As a Maintainer choosing a starting layout, I want ready-made Gaming, Community, and Creator templates, so that I can build a structured server in one click.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL ship the Gaming, Community, and Creator Builtin_Templates as JSON files under `templates\builtin` rather than as hardcoded structures.
2. THE Template_Registry SHALL map each Template `kind` value to its Builtin_Template file.
3. WHERE a new Template kind is added, THE Aegis_Suite SHALL recognize it through the addition of a JSON file and a Template_Registry entry without code changes to the apply or validation paths.
4. THE Aegis_Suite SHALL preserve the existing `templates/community.json` and `templates/gaming.json` content by relocating it into the data-driven Builtin_Template set.

### Requirement 13: Template import, export, clone, and apply operations

**User Story:** As a Maintainer, I want to import, export, clone, and apply templates, so that I can reuse and share server structures.

#### Acceptance Criteria

1. WHEN a Maintainer imports a Template, THE Templates_Engine SHALL load the JSON, validate it, and store it in the `templates` table with `source` set to `imported`.
2. WHEN a Maintainer exports a Template, THE Templates_Engine SHALL read the Template, serialize it, and write it to `templates\user`.
3. WHEN a Maintainer clones a server, THE Templates_Engine SHALL read the live Discord structure of the target guild, produce a Template JSON document, and store or export it through the standard validation path.
4. WHEN a Maintainer applies a Template to a target guild, THE Templates_Engine SHALL diff the Template against the target guild and create the missing structure.
5. WHEN a Template apply operation completes, THE Aegis_Suite SHALL record an `apply_history` row capturing the server, the Template, the applied timestamp, and the result.
6. IF recording the `apply_history` row fails after the Template structure has been created in the target guild, THEN THE Aegis_Suite SHALL retain the created Discord structure, SHALL NOT reverse the applied changes, and SHALL record an observable indication that history recording failed.

### Requirement 14: Beginner and Advanced UI mode

**User Story:** As a beginner, I want a simplified interface by default, so that I am not overwhelmed by advanced controls, while still allowing advanced users to reveal full controls.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL store the UI_Mode flag in the Config_Store with the value `beginner` as the default.
2. WHILE the UI_Mode is `beginner`, THE Aegis_Suite SHALL hide raw permission editing, manual Template JSON editing, and diagnostics internals, and SHALL surface only guided actions.
3. WHILE the UI_Mode is `advanced`, THE Aegis_Suite SHALL reveal the full set of controls.
4. THE Aegis_Suite SHALL expose the same HTTP API regardless of the UI_Mode value.
5. THE Aegis_Suite SHALL implement UI_Mode purely as a frontend rendering concern and SHALL NOT remove any capability from the data model when the UI_Mode is `beginner`.

### Requirement 15: Mobile-friendly responsive dashboard

**User Story:** As a Maintainer managing my community from my phone, I want the dashboard to be usable on a small screen, so that I can manage my server on the go.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL extend the existing dashboard templates and static assets with a mobile-first responsive CSS layer and SHALL NOT replace the existing markup.
2. THE Aegis_Suite SHALL render a fluid layout, stacked navigation, and touch-sized targets at narrow viewport widths.
3. THE Aegis_Suite SHALL render the existing desktop layout at a wide-viewport breakpoint.
4. THE Aegis_Suite SHALL reuse the existing routes and templates and SHALL NOT change the data flow or endpoints to achieve responsive layout.
5. THE Setup_Wizard SHALL reuse the same responsive shell as the dashboard.

### Requirement 16: One-click diagnostics package

**User Story:** As a Maintainer asking for support, I want to generate a diagnostics package with one click, so that I can share my application state without exposing my secrets.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL provide a one-click "Generate Diagnostics Package" action in the dashboard.
2. WHEN the Maintainer triggers diagnostics generation, THE Diagnostics_Packager SHALL collect the tail of `aegis.log` and `aegis.err.log`, the application version, the Database status, the runtime status, and a sanitized config snapshot.
3. THE Diagnostics_Packager SHALL include in the Database status the integrity check result, the schema revision, and the Database file size.
4. THE Diagnostics_Packager SHALL include in the runtime status the current Lifecycle_State_Machine state, the uptime, and the Safe_Mode Reason_Code when Safe_Mode is active.
5. THE Diagnostics_Packager SHALL perform only read operations and SHALL NOT mutate application state.
6. THE Diagnostics_Packager SHALL assemble the collected data into a timestamped zip archive under `diagnostics` and offer it for download through the dashboard.
7. THE Config_Sanitizer SHALL redact the value of the Discord token and every secret before configuration data is written into the Diagnostics_Package, WHILE preserving the configuration structure and the non-secret key names so the snapshot remains useful for troubleshooting.
8. THE Aegis_Suite SHALL apply the same Config_Sanitizer redaction rule so that the Discord token value and secret values never enter the logs.
9. WHILE the Lifecycle_State_Machine is in SAFE_MODE, THE Aegis_Suite SHALL keep the diagnostics generation action available.

### Requirement 17: Lightweight health monitoring

**User Story:** As a Maintainer, I want a status panel that shows whether each part of Aegis is healthy, so that I can see at a glance what is working and what needs attention.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL maintain a Health_Registry that each subsystem updates in place during the lifecycle.
2. THE Aegis_Suite SHALL expose the Health_Payload through a dashboard endpoint consumed by the dashboard status panel.
3. THE Health_Payload SHALL include the web subsystem state, the database subsystem state covering reachability, integrity, and at-head revision, the bot subsystem state covering connected-and-ready or disabled, the intents subsystem state covering declared-and-enabled, and the Safe_Mode state covering the active flag and Reason_Code or false.
4. THE Aegis_Suite SHALL assemble the Health_Payload by reading cached statuses from the Health_Registry rather than performing live probes.
5. THE Aegis_Suite SHALL produce a meaningful Health_Payload in every operating state.
6. THE Aegis_Suite SHALL implement the Health_Registry as a plain shared object updated in place and SHALL NOT introduce an event bus or publish-subscribe mechanism.

### Requirement 18: Preservation and relocation of existing functionality

**User Story:** As an operator of the existing Aegis bot, I want the refactor to keep my working features intact, so that adopting the new architecture does not regress what already works.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL relocate the existing application code under the `aegis/` package using the subpackages `core/`, `config/`, `db/`, `bot/`, `web/`, `templates_engine/`, and `diagnostics/`.
2. THE Aegis_Suite SHALL wrap and relocate the existing FastAPI routes, Discord.py cogs, and dashboard templates rather than replacing them.
3. THE Aegis_Suite SHALL preserve the existing leveling and music functionality during relocation.
4. THE Aegis_Suite SHALL adopt the existing SQLite schema through the Alembic baseline revision without data loss.
5. THE Aegis_Suite SHALL preserve the existing built-in template content during relocation into `templates\builtin`.

### Requirement 19: YAGNI-constrained extension points

**User Story:** As a maintainer of the codebase over a six-month horizon, I want extension points kept minimal, so that the foundation stays simple to understand and package.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL implement extension points as plain Python base classes and registry dictionaries.
2. THE Aegis_Suite SHALL NOT introduce a dependency-injection container, a factory framework, or an event bus.
3. THE Aegis_Suite SHALL NOT introduce microservices, Docker, Redis, or a message queue into the V1 architecture.
4. THE Aegis_Suite SHALL package as a single executable using a single asyncio loop suitable for PyInstaller on Windows.

## Non-Functional Requirements

### Requirement 20: Usability for non-technical users

**User Story:** As a non-technical community owner, I want every task to be achievable in the browser, so that I never need to open a terminal or edit a config file by hand.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL provide a graphical web interface path for setup, configuration, and recovery, and SHALL NOT require command-line interaction for any of these tasks.
2. THE Aegis_Suite SHALL NOT require the Maintainer to manually edit the Config_Store or the Database to complete setup or recovery.
3. WHEN a Startup_Check fails, THE Aegis_Suite SHALL present guided recovery instructions in the dashboard rather than a raw error trace.

### Requirement 21: Single-executable deployment on Windows

**User Story:** As a Maintainer, I want to run Aegis from a single executable, so that installation is as simple as downloading and double-clicking.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL deploy as a single Windows executable that bundles the application code and shipped defaults.
2. THE Aegis_Suite SHALL run on a single asyncio Event_Loop in a single thread to remain compatible with PyInstaller packaging on Windows.
3. WHERE the executable is replaced with a newer build, THE Aegis_Suite SHALL continue to operate against the existing Data_Directory without data loss.

### Requirement 22: Secret confidentiality

**User Story:** As a Maintainer, I want my Discord token and secrets protected, so that sharing diagnostics or reading logs never leaks my credentials.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL route all configuration serialization destined for logs or diagnostics through the centralized Config_Sanitizer.
2. THE Config_Sanitizer SHALL redact the value of the Discord token and every secret value before it reaches a log file or a Diagnostics_Package, WHILE leaving non-secret key names and the configuration structure intact.
3. THE Aegis_Suite SHALL NOT expose the Discord token plaintext through the Health_Payload, the Diagnostics_Package, or any log file.

### Requirement 23: Startup responsiveness and recovery availability

**User Story:** As a Maintainer, I want the dashboard to become reachable promptly even when something is wrong, so that I can begin recovery quickly.

#### Acceptance Criteria

1. WHEN the Aegis_Suite enters SAFE_MODE during startup, THE Aegis_Suite SHALL start the ASGI_Server_Task so the recovery flow is reachable in the browser.
2. THE Health_Payload endpoint SHALL respond using cached Health_Registry statuses so that it remains safe to poll repeatedly without triggering live probes.
3. WHEN promoting from SAFE_MODE to RUNNING after a successful retry, THE Aegis_Suite SHALL start the Bot_Task on the running Event_Loop without a full process restart.

### Requirement 24: Defensive data safety

**User Story:** As a Maintainer, I want destructive operations to be protected by automatic backups, so that I can recover if an upgrade or change goes wrong.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL create an automatic full-file DB_Backup before every migration that changes the Database schema.
2. THE Aegis_Suite SHALL perform migration rollback by restoring the DB_Backup file over the Database rather than by reverse-applying schema changes.
3. THE Aegis_Suite SHALL retain DB_Backup files under a bounded rotation retention policy to limit disk usage.

### Requirement 25: Maintainability over the six-month horizon

**User Story:** As a codebase maintainer, I want the foundation to favor simple, debuggable patterns, so that it stays maintainable without specialist infrastructure knowledge.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL use cooperative single-threaded scheduling on one Event_Loop so that stack traces remain linear and no locks are required for in-loop state.
2. THE Aegis_Suite SHALL provide one cancellation path for shutdown.
3. THE Aegis_Suite SHALL keep mutable state separated from code under the Data_Directory to support incremental refactoring and executable replacement.

## Phase 1 Scope Boundaries

Phase 1 delivers the foundational architecture described above. The following statements bound what Phase 1 includes:

1. Phase 1 delivers a single-process monolith hosting the bot, API, and dashboard on one shared asyncio Event_Loop owned by the AppCore.
2. Phase 1 delivers the Lifecycle_State_Machine with the states BOOTING, SAFE_MODE, RUNNING, and SHUTTING_DOWN, and the fail-soft startup sequence with the seven ordered Startup_Checks.
3. Phase 1 delivers Safe_Mode as a first-class state covering exactly the four Reason_Codes `needs-setup`, `token-recovery`, `db-recovery`, and `intent-recovery`.
4. Phase 1 delivers the Setup_Wizard covering Welcome, Token entry, Server selection, Template selection, and Finish.
5. Phase 1 delivers the SQLite Database with the six V1 schema tables, SQLAlchemy ORM, WAL journaling, and the Alembic baseline plus silent backed-up migrations.
6. Phase 1 delivers the Templates_Engine with three data-driven Builtin_Templates (Gaming, Community, Creator) and the import, export, clone, and apply operations.
7. Phase 1 delivers the Beginner/Advanced UI_Mode flag, the mobile-friendly responsive CSS layer over existing markup, the one-click Diagnostics_Package, and the Health_Registry with its Health_Payload endpoint.
8. Phase 1 delivers the `aegis/` folder reorganization and the relocation of existing routes, cogs, templates, and schema without rewriting working functionality.
9. Phase 1 targets the local-first single-user Windows desktop deployment as the primary deployment model.
10. Phase 1 targets a six-month horizon, favoring a minimal surface, defensive defaults, and file-copy rollback over clever migrations.

## Out of Scope

The following items are explicitly excluded from Phase 1:

1. Multi-process or multi-runtime architectures, threaded FastAPI hosting, and any inter-process communication between the bot and the web layer.
2. Microservices, Docker, Redis, message queues, event buses, dependency-injection containers, and factory frameworks.
3. Cloud, hosted multi-tenant, or SaaS deployment of this foundation. The hosting-mode, managed-hosting, and multi-bot concerns are covered by the separate `hosting-mode-selector`, `managed-hosting-migration`, and `multi-bot-and-gui-setup` specifications and are not part of this foundation.
4. Running more than one Discord bot identity per installation within this foundation.
5. Operating systems other than Windows for the single-executable deployment target.
6. Database engines other than SQLite, multi-connection pooling, and reverse-applied (non-file-copy) migration rollback.
7. Reverse proxy, TLS termination, and public-internet exposure of the dashboard.
8. Reverse migrations that downgrade a Database created by a newer build; the foundation refuses to downgrade and enters Safe_Mode instead.
9. New feature development for leveling, music, or moderation beyond preserving and relocating the existing functionality.
10. Hardcoded built-in templates; all built-in templates are shipped as JSON data files.
11. Any command-line interface for setup, configuration, recovery, or migration.
