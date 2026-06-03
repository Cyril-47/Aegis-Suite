# Requirements Document

## Introduction

The Aegis Suite today supports exactly one Discord bot per installation, gathered through a console-only first-run wizard (`first_run_wizard.py`) that prompts on stdin for a bot token, a client ID, and an admin password. Two real-world frictions have surfaced:

1. The console wizard is unfriendly for non-technical maintainers. A maintainer who double-clicks an EXE expecting a graphical app is dropped into a terminal that hides input, validates regex matches with cryptic messages, and offers no second chance after Ctrl+C.
2. A maintainer running multiple Discord servers (for example, one gaming server and one study server) cannot give each server its own bot identity (different bot username, different avatar, different status). The codebase wires a single global `discord.Client` at boot, and every dashboard operation routes through that one client.

This feature addresses both at once. It introduces a graphical first-run wizard built on Python's stdlib `tkinter` (no new dependencies), a multi-bot registry (`BotIdentity` records persisted in `config.json` with their tokens DPAPI-encrypted in an envelope managed by `secret_store.py`), a "+ Add Bot" management UI on the dashboard, and a per-server bot pin so each Discord guild can be controlled by a different bot identity. The existing console wizard remains as the headless / TTY-only fallback. The existing `/linkdashboard` Pairing_Onboarding_Flow remains the only Tenant entry surface; no token form is reintroduced for tenants.

Every Aegis_Suite installation in this spec runs at least one bot the operator configured themselves. The shipped EXE does not point at any maintainer-hosted default bot, and the maintainer of the upstream Aegis repository is not expected to host a 24/7 instance that other users connect to. Each operator who installs Aegis_Suite — solo maintainer, multi-server maintainer, casual end user — completes the GUI_Setup_Wizard (or the Console_Setup_Wizard fallback) on their own machine to register their first BotIdentity before uvicorn ever binds the port.

### Threat model — honesty paragraph

The only at-rest secret guarantee in scope for this spec is the existing DPAPI envelope from `secret_store.py`, originally introduced by the `managed-hosting-migration` spec and unchanged here. Bot tokens registered through the GUI_Setup_Wizard, the Console_Setup_Wizard, or the Bots_Management_UI are encrypted into the Multi_Bot_Secret_Envelope, bound to the local Windows user account, and not decryptable by a different Windows user or on a different machine. This spec inherits that boundary and introduces no additional threat-model claims; readers who need the full disclosure on user-added local bot tokens should consult the `managed-hosting-migration` spec where the DPAPI design is documented.

### Preserved invariants

This feature is strictly additive on top of the `managed-hosting-migration` and `hosting-mode-selector` specs:

- `static/index.html` MUST NOT regrow `#setup-wizard`, `#wizard-token`, `#wizard-client-id`, `#btn-save-wizard`, `#btn-bot-toggle`, or `#btn-reconfigure`.
- `ConfigModel` in `web_server.py` MUST NOT regain a `bot_token` field.
- `POST /api/bot/start` and `POST /api/bot/stop` MUST NOT be reintroduced.
- `/linkdashboard` MUST remain the only Tenant entry surface; the Bots_Management_UI is admin-only.
- The `Hosting_Mode` selector and the `AEGIS_HOSTING_MODE` env-var bootstrap continue to work unchanged; multi-bot is orthogonal to hosting mode.
- The single-blob `.env.enc` format produced by today's `secret_store.encrypt_env_file` MUST remain readable by the new envelope-aware loader so existing installations upgrade without manual re-entry.

## Glossary

- **Aegis_Suite**: The combined Discord bot manager (`bot_manager.py`) and FastAPI dashboard (`web_server.py`) under deployment.
- **Maintainer**: The operator who installs Aegis_Suite on their own machine (or on a paid host they provisioned per the `hosting-mode-selector` spec) and holds the admin password for that installation.
- **Tenant**: A Discord server administrator who reaches the dashboard via the `/linkdashboard` Pairing_Onboarding_Flow. Tenants do not see the Bots_Management_UI.
- **BotIdentity**: A persisted record describing one Discord bot the Aegis_Suite installation can run. Fields: `id` (UUID string), `name` (human-readable label), `token_ref` (key into the Multi_Bot_Secret_Envelope), `client_id` (Discord application ID for the invite URL), `created_at` (ISO-8601 timestamp), `created_by_role` (`admin` or `platform_owner`), `status` (last observed `online`, `offline`, `connecting`, or `error`), `last_error` (optional string), `pinned_guild_ids` (array of Discord guild IDs this BotIdentity controls). Persisted as an entry inside the `bot_identities` array in `config.json`.
- **BotRegistry**: The in-process module-level structure in `bot_manager.py` that holds N concurrent `discord.Client` instances keyed by `BotIdentity.id`. Replaces the current single-`bot_instance` global.
- **GUI_Setup_Wizard**: The first-run setup window built on Python's stdlib `tkinter`, launched in place of the console wizard whenever a graphical session is available. Always collects bot token, client ID, admin password (with confirmation), and an optional public dashboard URL.
- **Console_Setup_Wizard**: The existing `first_run_wizard.py` module that prompts on stdin. Retained as the headless / TTY-only fallback when the GUI_Setup_Wizard cannot be displayed.
- **Bots_Management_UI**: A new admin-only section of the dashboard that lists every registered BotIdentity with avatar, name, online/offline/error status, connected-server count, per-row actions (rename, edit token, remove), and a top-level "+" Add Bot button that opens an inline form collecting the same field set as the Console_Setup_Wizard.
- **Server_Bot_Pin**: The association between a Discord guild and the BotIdentity that controls it. Set during the `/linkdashboard` flow (the admin picks which BotIdentity to pin) and recorded both inside the BotIdentity's `pinned_guild_ids` array and in the per-guild config under `guild_configs[guild_id].bot_identity_id`.
- **Multi_Bot_Secret_Envelope**: The forward-compatible JSON layout for `.env.enc` that holds N independently-encrypted bot tokens keyed by `BotIdentity.id`, alongside the existing maintainer secrets (`JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `BOT_API_URL`). The legacy single-blob `AEGIS_DPAPI_V1` format produced by today's `secret_store.encrypt_env_file` MUST remain readable so existing installations upgrade without manual re-entry.
- **Pairing_Onboarding_Flow**: The existing four-step Tenant entry path: invite the bot, run `/linkdashboard`, copy the 6-character code, paste it into the dashboard. Defined in `managed-hosting-migration`.
- **Hosting_Mode**: The Local_PC / Cloud deployment preference recorded in `config.json` by the `hosting-mode-selector` spec. Read but not modified by this spec.
- **Headless_Environment**: Any runtime where a graphical session cannot be opened. Detected via the absence of `DISPLAY` (Linux), `WAYLAND_DISPLAY` (Linux), or by an explicit `AEGIS_HEADLESS=1` environment variable, OR by the standard `tkinter.Tk()` constructor raising `_tkinter.TclError`, OR by `RAILWAY_ENVIRONMENT` / `RENDER` being set (matching the `run.py` cloud detection).

## Requirements

### Requirement 1: Graphical first-run setup wizard

**User Story:** As a non-technical Maintainer who double-clicked the Aegis EXE, I want a small graphical setup window instead of a terminal prompt, so that I can configure the bot without using stdin.

#### Acceptance Criteria

1. WHEN the Aegis_Suite launcher detects that no credential source exists and the runtime is not a Headless_Environment, THE Aegis_Suite SHALL launch the GUI_Setup_Wizard built on Python's stdlib `tkinter` and SHALL NOT launch the Console_Setup_Wizard.
2. THE GUI_Setup_Wizard SHALL collect the same field set as the Console_Setup_Wizard: bot token, client ID, admin password, admin password confirmation, and an optional public dashboard URL.
3. THE GUI_Setup_Wizard SHALL require non-empty values for the bot token, client ID, admin password, and admin password confirmation fields before allowing the Maintainer to submit.
4. THE GUI_Setup_Wizard SHALL render the bot token and admin password fields with masked input (e.g. `show="*"` on the `tkinter.Entry`).
5. WHEN the Maintainer submits the GUI_Setup_Wizard with a bot token that fails the existing format check (`first_run_wizard._validate_bot_token`), THE Aegis_Suite SHALL display a visible inline error message naming the failing field and SHALL NOT persist any value to disk.
6. WHEN the Maintainer submits the GUI_Setup_Wizard with a client ID that fails the existing format check (`first_run_wizard._validate_client_id`), THE Aegis_Suite SHALL display a visible inline error message naming the failing field and SHALL NOT persist any value to disk.
7. WHEN the Maintainer submits the GUI_Setup_Wizard with non-matching admin password and confirmation entries, THE Aegis_Suite SHALL display a visible inline error message and SHALL NOT persist any value to disk.
8. WHEN the GUI_Setup_Wizard completes successfully, THE Aegis_Suite SHALL persist the collected values via the same code path used by the Console_Setup_Wizard so that DPAPI encryption, plaintext-`.env` cleanup, and `config.json` `client_id` mirroring all happen identically.
9. WHEN the Maintainer closes the GUI_Setup_Wizard window without submitting, THE Aegis_Suite SHALL exit with a non-zero status code and SHALL NOT start uvicorn.

### Requirement 2: Console wizard remains the headless fallback

**User Story:** As a Maintainer running the launcher over SSH or on a headless Linux container, I want the existing console wizard to still work, so that the new GUI does not block me from completing setup.

#### Acceptance Criteria

1. WHEN the Aegis_Suite launcher detects that the runtime is a Headless_Environment, THE Aegis_Suite SHALL launch the Console_Setup_Wizard and SHALL NOT attempt to launch the GUI_Setup_Wizard.
2. WHEN the Aegis_Suite launcher attempts to construct the GUI_Setup_Wizard top-level window and `tkinter.Tk()` raises an exception, THE Aegis_Suite SHALL log a maintainer-facing warning naming the exception class and SHALL fall back to the Console_Setup_Wizard within the same process.
3. WHEN the environment variable `AEGIS_HEADLESS` is set to a non-empty value, THE Aegis_Suite SHALL treat the runtime as a Headless_Environment regardless of any graphical-session indicators.
4. THE Console_Setup_Wizard SHALL retain its existing field set, validators, and DPAPI encryption behavior unchanged from the `managed-hosting-migration` baseline.
5. THE Aegis_Suite SHALL NOT introduce any new third-party dependency for the GUI_Setup_Wizard; the wizard SHALL use only Python's stdlib `tkinter` module.

### Requirement 3: BotIdentity data model

**User Story:** As a Maintainer running multiple Discord servers, I want each server to be controllable by a different bot identity, so that I can give each server its own bot username, avatar, and status.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL persist registered bot identities as a top-level array named `bot_identities` in `config.json`, where each element is a JSON object containing the fields `id`, `name`, `token_ref`, `client_id`, `created_at`, `created_by_role`, `status`, `last_error`, and `pinned_guild_ids`.
2. THE Aegis_Suite SHALL generate the `id` field as a UUID v4 string at the moment of BotIdentity creation and SHALL NOT mutate the value over the lifetime of the BotIdentity.
3. THE Aegis_Suite SHALL constrain the `name` field to a maximum length of 64 characters and SHALL reject names containing characters outside the set `[A-Za-z0-9 _-]`.
4. THE Aegis_Suite SHALL store the bot token outside of `config.json` by writing the token into the Multi_Bot_Secret_Envelope under the key equal to the BotIdentity's `id`, and SHALL store only the envelope key reference in the `token_ref` field of the BotIdentity record.
5. THE Aegis_Suite SHALL constrain the `created_by_role` field to exactly one of `admin` or `platform_owner`.
6. THE Aegis_Suite SHALL constrain the `status` field to exactly one of `online`, `offline`, `connecting`, or `error`.
7. THE Aegis_Suite SHALL NOT include the `token_ref` field, the bot token plaintext, or any DPAPI ciphertext bytes in any REST response body returned to a browser.
8. WHEN a `bot_identities` array is missing from a freshly loaded `config.json`, THE Aegis_Suite SHALL treat the array as empty and SHALL NOT raise an error.
9. THE Aegis_Suite SHALL acquire `utils.config_lock` for every read-modify-write of the `bot_identities` array, consistent with all other writers of `config.json`.

### Requirement 4: Multi-bot secret envelope with backwards compatibility

**User Story:** As a Maintainer with an existing single-bot installation, I want my upgrade to multi-bot to leave my existing `.env.enc` readable, so that I do not need to re-enter my bot token after the upgrade.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL extend `secret_store.py` to support a Multi_Bot_Secret_Envelope JSON layout containing a magic header `AEGIS_DPAPI_V2`, a `secrets` object whose keys include the existing maintainer secret names (`DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `BOT_API_URL`) plus one entry per registered BotIdentity keyed by `bot:{BotIdentity.id}`, and a `version` integer field set to `2`.
2. THE Aegis_Suite SHALL DPAPI-encrypt each value in the `secrets` object independently so that adding or removing one bot token does not require decrypting and re-encrypting unrelated maintainer secrets.
3. WHEN the loader in `secret_store.decrypt_env_file` encounters an existing `AEGIS_DPAPI_V1` magic header (the legacy single-blob layout produced by `managed-hosting-migration`), THE Aegis_Suite SHALL decrypt the legacy blob, parse it as `KEY=VALUE` lines, and expose the values to callers as if they had come from a `version: 2` envelope.
4. WHEN the loader successfully reads a legacy `AEGIS_DPAPI_V1` envelope and a write to the envelope is required, THE Aegis_Suite SHALL upgrade the on-disk file to the `AEGIS_DPAPI_V2` layout in the same write so the next read uses the new format.
5. IF the loader encounters an envelope file whose magic header is neither `AEGIS_DPAPI_V1` nor `AEGIS_DPAPI_V2`, THEN THE Aegis_Suite SHALL raise `secret_store.CorruptedSecretFile` and SHALL NOT attempt to decrypt the file.
6. THE Aegis_Suite SHALL provide a function `secret_store.write_secret(envelope_path, key, plaintext_bytes)` that adds or replaces a single secret in the envelope under `utils.config_lock`-equivalent serialization, and a function `secret_store.read_secret(envelope_path, key)` that returns the decrypted plaintext bytes for one key or `None` if absent.
7. WHEN `secret_store.write_secret` is called on a host where DPAPI is unavailable, THE Aegis_Suite SHALL raise `secret_store.DPAPIUnavailableError` consistent with the existing single-blob behavior.

### Requirement 5: Bot registry and per-bot Discord client routing

**User Story:** As a Maintainer with multiple registered bot identities, I want each registered bot to run its own Discord connection in parallel, so that operations on one server are dispatched to the bot pinned to that server.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL replace the current single `bot_instance` global in `bot_manager.py` with a BotRegistry data structure that holds zero or more concurrent `discord.Client` instances keyed by `BotIdentity.id`.
2. WHEN the FastAPI lifespan startup runs and the persisted `bot_identities` array is non-empty, THE Aegis_Suite SHALL start one `discord.Client` per BotIdentity, each connecting to its own gateway with the token loaded from the Multi_Bot_Secret_Envelope under `bot:{BotIdentity.id}`.
3. THE Aegis_Suite SHALL register the `/linkdashboard` slash command on every BotIdentity's `discord.Client`.
4. THE Aegis_Suite SHALL register the `/unlink` and `/unlink purge` slash commands on every BotIdentity's `discord.Client`, preserving the existing `on_guild_remove` revocation and pending-pairing cleanup behavior on each.
5. WHEN a dashboard operation targets a Discord guild and that guild has a Server_Bot_Pin recorded, THE Aegis_Suite SHALL dispatch the operation to the `discord.Client` whose BotIdentity matches the pin and SHALL NOT dispatch the operation to any other client.
6. IF a dashboard operation targets a Discord guild that has no Server_Bot_Pin recorded, THEN THE Aegis_Suite SHALL respond with HTTP 409 and a body naming the missing pin so the admin can complete the linking flow.
7. WHEN a BotIdentity's `discord.Client` raises a connection error, THE Aegis_Suite SHALL update that BotIdentity's `status` field to `error`, SHALL set its `last_error` field to the exception's string representation truncated to 256 characters, and SHALL NOT terminate the other BotIdentities' clients.
8. WHEN the FastAPI lifespan shutdown runs, THE Aegis_Suite SHALL stop every BotIdentity's `discord.Client` cleanly before returning control to uvicorn.

### Requirement 6: Bots management UI in the dashboard

**User Story:** As a Maintainer with multiple bot identities, I want a dashboard panel that lists every bot and lets me add, rename, or remove one, so that I can manage all my bots from one place.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL render a Bots_Management_UI panel in the dashboard reachable from a top-level navigation entry labelled `Bots`.
2. WHERE the visitor's session role is not `admin`, THE Aegis_Suite SHALL NOT expose the Bots_Management_UI navigation entry and SHALL respond with HTTP 403 to any direct request that attempts to render it.
3. THE Bots_Management_UI SHALL display, for every registered BotIdentity, a row containing the bot's avatar (rendered from the BotIdentity's last observed avatar URL or a generic fallback when unavailable), the bot's `name`, the bot's `status` rendered as one of `online`, `offline`, `connecting`, or `error`, and the count of guilds in `pinned_guild_ids`.
4. THE Bots_Management_UI SHALL display a top-level button labelled `+ Add Bot` that opens an inline form collecting a name, a bot token, and a client ID.
5. WHEN the admin submits the `+ Add Bot` form with a name violating Requirement 3.3, THE Aegis_Suite SHALL display a visible inline error message and SHALL NOT create the BotIdentity.
6. WHEN the admin submits the `+ Add Bot` form with a bot token that fails the existing format check used by the Console_Setup_Wizard, THE Aegis_Suite SHALL display a visible inline error message and SHALL NOT create the BotIdentity.
7. THE Bots_Management_UI SHALL provide a per-row Rename action that updates the BotIdentity's `name` field via `PUT /api/bots/{id}` and refreshes the row.
8. THE Bots_Management_UI SHALL provide a per-row Edit Token action that opens an inline masked-input form collecting a replacement token and overwrites the secret in the Multi_Bot_Secret_Envelope without changing the BotIdentity's `id`.
9. THE Bots_Management_UI SHALL provide a per-row Remove action that deletes the BotIdentity via `DELETE /api/bots/{id}` after a confirmation interaction, removes the secret from the Multi_Bot_Secret_Envelope, and clears every Server_Bot_Pin that referenced the removed BotIdentity.
10. THE Bots_Management_UI SHALL NOT display the bot token plaintext, the `token_ref` field, or any DPAPI ciphertext bytes.

### Requirement 7: Per-server bot pin during the linking flow

**User Story:** As an admin linking a Discord server to the dashboard, I want to choose which of my registered bots controls that server, so that each of my Discord servers can have its own bot identity.

#### Acceptance Criteria

1. WHEN an admin runs the `/linkdashboard` slash command on a guild that is not currently pinned to any BotIdentity, THE Aegis_Suite SHALL prompt the admin (in the dashboard, after pairing-code redemption) to pick which BotIdentity should control that guild before any further configuration is allowed for that guild.
2. WHEN the admin selects a BotIdentity for a guild during the pin flow, THE Aegis_Suite SHALL append the guild's ID to that BotIdentity's `pinned_guild_ids` array and SHALL set `guild_configs[guild_id].bot_identity_id` to the chosen BotIdentity's `id`, both writes performed under `utils.config_lock`.
3. THE Aegis_Suite SHALL display the controlling BotIdentity's `name` and avatar next to each guild in the dashboard's existing server selector.
4. WHERE the visitor's session role is `tenant`, THE Aegis_Suite SHALL display only the BotIdentity pinned to the tenant's own guild and SHALL NOT enumerate any other BotIdentity to that visitor.
5. WHEN the admin invokes the per-row Remove action on a BotIdentity that has one or more pinned guilds, THE Aegis_Suite SHALL display a confirmation dialog naming the affected guilds and SHALL clear the pin from every affected guild after the admin confirms.
6. THE Aegis_Suite SHALL persist the Server_Bot_Pin in `config.json` only; the pin SHALL NOT be written to `.env`, `.env.enc`, or any file managed by `secret_store.py`, because the pin is a non-sensitive routing preference and not a secret.
7. IF a Server_Bot_Pin references a `bot_identity_id` that no longer exists in the `bot_identities` array, THEN THE Aegis_Suite SHALL treat the pin as absent and SHALL surface the missing-pin response described in Requirement 5.6 on the next dashboard operation targeting that guild.

### Requirement 8: REST API for bot management

**User Story:** As the dashboard frontend, I want a small REST contract for listing, creating, renaming, retoking, and removing bot identities, so that the Bots_Management_UI can talk to the same source of truth as the bot registry.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL expose `GET /api/bots` returning a JSON array of BotIdentity records with the fields `id`, `name`, `client_id`, `created_at`, `created_by_role`, `status`, `last_error`, and `pinned_guild_ids` only; the response SHALL NOT include `token_ref`, the bot token plaintext, or any DPAPI ciphertext bytes.
2. THE Aegis_Suite SHALL expose `POST /api/bots` accepting a JSON body with `name`, `token`, and `client_id` and creating a new BotIdentity, encrypting the token into the Multi_Bot_Secret_Envelope, and starting the new `discord.Client` in the BotRegistry.
3. THE Aegis_Suite SHALL expose `PUT /api/bots/{id}` accepting a JSON body with optional `name` and optional `token` fields and applying only the fields that are present.
4. THE Aegis_Suite SHALL expose `DELETE /api/bots/{id}` removing the BotIdentity from `bot_identities`, removing the secret from the Multi_Bot_Secret_Envelope, stopping the corresponding `discord.Client` in the BotRegistry, and clearing every Server_Bot_Pin that referenced the deleted BotIdentity.
5. WHEN any of `GET /api/bots`, `POST /api/bots`, `PUT /api/bots/{id}`, or `DELETE /api/bots/{id}` is invoked by a session whose role is not `admin`, THE Aegis_Suite SHALL respond with HTTP 403 and SHALL NOT modify `config.json` or the Multi_Bot_Secret_Envelope.
6. WHEN any of `POST /api/bots` or `PUT /api/bots/{id}` is invoked with a `name` violating Requirement 3.3, THE Aegis_Suite SHALL respond with HTTP 400 naming the failing field and SHALL NOT modify `config.json` or the Multi_Bot_Secret_Envelope.
7. WHEN any of `POST /api/bots` or `PUT /api/bots/{id}` is invoked with a `token` that fails the existing token format check, THE Aegis_Suite SHALL respond with HTTP 400 naming the failing field and SHALL NOT modify `config.json` or the Multi_Bot_Secret_Envelope.
8. WHEN `DELETE /api/bots/{id}` is invoked with an `id` that does not exist in `bot_identities`, THE Aegis_Suite SHALL respond with HTTP 404 and SHALL NOT modify `config.json` or the Multi_Bot_Secret_Envelope.

### Requirement 9: /api/status bots summary

**User Story:** As the dashboard frontend, I want the existing status poll to summarize every bot's online/offline state in one round-trip, so that the Bots_Management_UI can render the status column without an extra fetch on every page load.

#### Acceptance Criteria

1. THE `GET /api/status` response SHALL include a top-level field named `bots` whose value is a JSON array.
2. WHERE the visitor's session role is `admin`, THE `bots` array SHALL contain one entry per registered BotIdentity with the fields `id`, `name`, and `status`.
3. WHERE the visitor's session role is `tenant`, THE `bots` array SHALL contain at most one entry, corresponding to the BotIdentity pinned to the tenant's guild, with the fields `id`, `name`, and `status`.
4. WHERE the visitor is unauthenticated, THE `bots` array SHALL be empty.
5. THE `bots` array SHALL NOT include the bot token plaintext, the `token_ref` field, or any DPAPI ciphertext bytes.
6. THE `GET /api/status` response SHALL retain its existing fields (`status`, `has_token`, `ffmpeg_installed`, `role`, `guild_id`, `bot_user`, `client_id`, `hosting_mode`) unchanged.

### Requirement 10: Preserve managed-hosting-migration and hosting-mode-selector invariants

**User Story:** As the operator of an existing Aegis_Suite deployment, I want this feature to add capability without rolling back any of the security or deployment work that already landed, so that multi-bot does not become a regression vector.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL NOT reintroduce the `#setup-wizard` element, the `#wizard-token` input, the `#wizard-client-id` input, the `#btn-save-wizard` button, the `#btn-bot-toggle` button, or the `#btn-reconfigure` button in `static/index.html`.
2. THE Aegis_Suite SHALL NOT reintroduce a `bot_token` field on the `ConfigModel` Pydantic model in `web_server.py`.
3. THE Aegis_Suite SHALL NOT reintroduce the `POST /api/bot/start` or `POST /api/bot/stop` HTTP endpoints.
4. THE Aegis_Suite SHALL continue to require Tenants to enter the dashboard via the `/linkdashboard` Pairing_Onboarding_Flow and SHALL NOT add any alternative Tenant entry surface.
5. THE Aegis_Suite SHALL continue to enforce the existing JWT signature verification, guild-scoped `auth_middleware` checks, per-guild sliding-window rate limiter, `on_guild_remove` session revocation, `is_regex_safe` ReDoS guard, and `escapeHtml` XSS guard.
6. THE Aegis_Suite SHALL continue to honor the `Hosting_Mode` selector and the `AEGIS_HOSTING_MODE` env-var bootstrap from the `hosting-mode-selector` spec without modification.
7. THE Aegis_Suite SHALL continue to store the maintainer secrets `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, and `BOT_API_URL` in the Multi_Bot_Secret_Envelope (or the legacy `AEGIS_DPAPI_V1` envelope until the next write upgrades it) and SHALL continue to load them via `utils.load_env_file`.
8. THE Aegis_Suite SHALL NOT expose the bot token plaintext, the `token_ref` field, the Multi_Bot_Secret_Envelope ciphertext, or the DPAPI envelope file contents through any REST response body.
