# Requirements Document

## Introduction

The Aegis Suite can be deployed two different ways: a Maintainer can run the Windows EXE on their own desktop, or they can deploy the same repository to a paid third-party host (Railway, Render, a generic Docker VPS) that they purchase and configure themselves. Each deployment carries a very different uptime profile. A desktop instance is online only while the user is at their PC; a cloud instance is online 24/7. Several Aegis features (auto-moderation, scheduled messages, giveaway timers, leveling roll-ups, periodic pairing-code expiry, `on_guild_remove` revocation, audit log roll-ups) only behave correctly when the bot process is continuously online, so the Maintainer needs a clear, one-time choice between the two deployment styles and a persistent, visible reminder of which one they picked.

This feature adds a **Hosting Mode Selector** to the dashboard. On first launch the dashboard presents a side-by-side chooser between Local_PC_Mode and Cloud_Mode. Each option carries a Feature_Availability_Warning panel that lists exactly which features are impacted by intermittent uptime and which features are unaffected. The selected mode persists across restarts, surfaces as a Hosting_Mode_Badge in the dashboard header so every visitor can see it at a glance, and can be changed later from a Settings panel that re-displays the same warning and requires explicit confirmation.

The Cloud_Mode option does **not** provision a paid server on the user's behalf. The dashboard's only role in Cloud_Mode is to record the Maintainer's choice and silence the Local-PC-only warnings. The README is updated to point Cloud_Mode users at the existing Railway button, the Render manual flow, and the generic Docker path so they can deploy the repo themselves.

This spec is purely additive on top of the recently completed `managed-hosting-migration` spec. The `/linkdashboard` Pairing_Onboarding_Flow remains the only tenant entry point. The DPAPI-encrypted `.env.enc` Secret_Store contract from `managed-hosting-migration` is left untouched. The hosting mode preference is **not** a secret; it lives in the existing `config.json` so the `.env` / `.env.enc` keep carrying credentials only.

## Glossary

- **Aegis_Suite**: The combined Discord bot (`bot_manager.py`) and FastAPI dashboard (`web_server.py`).
- **Maintainer**: The operator who installs Aegis_Suite, holds the admin password, and chooses the Hosting_Mode for that installation.
- **Tenant**: A Discord server administrator who reaches the dashboard via the `/linkdashboard` Pairing_Onboarding_Flow. Tenants do not choose the Hosting_Mode but they do see the Hosting_Mode_Badge and the Feature_Availability_Warning.
- **Hosting_Mode**: The persisted enumeration recording how this installation is being run. Exactly two values are valid: `local_pc` (Local_PC_Mode) and `cloud` (Cloud_Mode).
- **Local_PC_Mode**: The Hosting_Mode value indicating Aegis_Suite is running as a Windows EXE on the Maintainer's own desktop or laptop with intermittent uptime.
- **Cloud_Mode**: The Hosting_Mode value indicating Aegis_Suite is running on a paid third-party host (Railway, Render, generic Docker VPS) the Maintainer provisioned and configured themselves, with continuous 24/7 uptime expected.
- **Hosting_Mode_Selector**: The full-screen modal shown on first launch (and on demand from Settings) where the Maintainer picks between Local_PC_Mode and Cloud_Mode.
- **Feature_Availability_Warning**: A persistent, read-only panel on the dashboard that lists, in two clearly separated groups, the Aegis_Suite features impacted by intermittent uptime and the Aegis_Suite features unaffected by intermittent uptime. The panel is visible whenever the active Hosting_Mode is Local_PC_Mode.
- **Hosting_Mode_Badge**: A small visual indicator rendered in the dashboard header that displays the human-readable label of the active Hosting_Mode (`Local PC` or `Cloud`) and visually distinguishes the two states.
- **Hosting_Mode_Settings_Panel**: The Settings tab section that lets a logged-in admin change the Hosting_Mode after first launch, re-displaying the Feature_Availability_Warning and requiring an explicit confirmation step before applying the change.
- **Pairing_Onboarding_Flow**: The existing four-step Tenant entry path: invite the bot, run `/linkdashboard`, copy the 6-character code, paste it into the dashboard. Defined in the `managed-hosting-migration` spec.
- **Secret_Store**: The DPAPI-encrypted `.env.enc` mechanism added by the `managed-hosting-migration` spec for storing `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, and `BOT_API_URL` at rest. Out of scope for this spec.
- **Managed_Hosting_Invariants**: The set of behaviors locked in by the `managed-hosting-migration` spec that this spec must not regress: removal of the user-facing Setup_Wizard, deletion of `POST /api/bot/start` and `POST /api/bot/stop`, the maintainer-only `DISCORD_BOT_TOKEN` source, the `/linkdashboard` Pairing_Onboarding_Flow as the only Tenant entry point, the DPAPI-encrypted Secret_Store, and the existing JWT / rate-limit / guild-isolation / `on_guild_remove` revocation behaviors.

## Requirements

### Requirement 1: First-launch hosting mode chooser

**User Story:** As a Maintainer, I want the dashboard to ask me which hosting style I am using on first launch, so that the dashboard can show me the right warnings without me hunting through Settings.

#### Acceptance Criteria

1. WHEN the Aegis_Suite dashboard is loaded by an authenticated admin and no Hosting_Mode value is currently persisted, THE Aegis_Suite SHALL display the Hosting_Mode_Selector as a modal overlay above the rest of the dashboard.
2. THE Hosting_Mode_Selector SHALL present exactly two side-by-side option cards labelled `Local PC` and `Cloud`.
3. THE Hosting_Mode_Selector SHALL describe Local_PC_Mode as "Run the Aegis EXE on your own machine. Intermittent uptime — features that need a 24/7 connection will not run while your PC is off or asleep."
4. THE Hosting_Mode_Selector SHALL describe Cloud_Mode as "Deploy this repository to a paid host you provisioned yourself (Railway, Render, generic Docker VPS). Continuous 24/7 uptime expected. Aegis does not provision the host for you."
5. WHEN the Maintainer selects an option card and confirms the choice, THE Aegis_Suite SHALL persist the chosen Hosting_Mode (per Requirement 5) and SHALL dismiss the Hosting_Mode_Selector.
6. WHILE no Hosting_Mode value is persisted and the visitor's session role is `tenant`, THE Aegis_Suite SHALL NOT display the Hosting_Mode_Selector and SHALL render the dashboard with the Hosting_Mode_Badge in an `Unconfigured` state.
7. WHEN a Hosting_Mode value is already persisted, THE Aegis_Suite SHALL NOT display the Hosting_Mode_Selector on dashboard load.

### Requirement 2: Cloud mode does not provision a host

**User Story:** As a Maintainer choosing Cloud_Mode, I want the dashboard to be honest that I am the one buying and configuring the server, so that I am not led to expect a managed deployment that does not exist.

#### Acceptance Criteria

1. THE Hosting_Mode_Selector Cloud_Mode option card SHALL state that the Maintainer is responsible for provisioning, paying for, and configuring the third-party host.
2. THE Hosting_Mode_Selector Cloud_Mode option card SHALL link to the deployment instructions in `README.md` covering at least the Railway one-click button path, the Render manual deployment path, and the generic Docker / VPS path.
3. WHEN the Maintainer selects Cloud_Mode, THE Aegis_Suite SHALL NOT make any outbound API call to Railway, Render, or any other hosting provider.
4. WHEN the Maintainer selects Cloud_Mode, THE Aegis_Suite SHALL NOT prompt for, store, or transmit any third-party hosting provider credential, API token, or billing information.
5. WHEN the Maintainer selects Cloud_Mode, THE Aegis_Suite SHALL persist the Hosting_Mode value `cloud` and SHALL silence the Local_PC_Mode-only Feature_Availability_Warning panel on subsequent loads.

### Requirement 3: Feature availability warning content for Local PC mode

**User Story:** As a Maintainer running on Local_PC_Mode, I want a complete list of which features are impacted by my PC being offline and which features are not, so that I can make an informed decision about whether to upgrade to a paid host.

#### Acceptance Criteria

1. WHILE the persisted Hosting_Mode is `local_pc`, THE Aegis_Suite SHALL render the Feature_Availability_Warning panel on the dashboard.
2. THE Feature_Availability_Warning panel SHALL contain a section titled "Impacted by intermittent uptime" that names the following features: auto-moderation message handlers, scheduled messages background loop, giveaway end-time scheduler, leveling XP grants on member messages, `on_guild_remove` session revocation, `/linkdashboard` pairing-code expiry, periodic audit log roll-ups, welcome embeds and auto-role assignment on member join, and auto-responders.
3. THE Feature_Availability_Warning panel SHALL contain a section titled "Unaffected by intermittent uptime" that names the following features: dashboard configuration changes, server health audit scan, server layout optimizer, role creator, role panel deployment, custom commands configuration, server template save and apply, embed builder, server backup and restore, and audit log viewer.
4. THE Feature_Availability_Warning panel SHALL state, in plain text, that features in the "Impacted" section will not run while the host PC is offline, asleep, or disconnected from Discord.
5. WHILE the persisted Hosting_Mode is `cloud`, THE Aegis_Suite SHALL NOT render the Feature_Availability_Warning panel on the dashboard.
6. THE Feature_Availability_Warning panel SHALL be displayed as a non-dismissable read-only panel; THE Aegis_Suite SHALL NOT provide a "dismiss" or "do not show again" control on the Feature_Availability_Warning panel while the active Hosting_Mode is `local_pc`.
7. WHERE the visitor's session role is `tenant`, THE Aegis_Suite SHALL render the Feature_Availability_Warning panel as read-only with no link to the Hosting_Mode_Settings_Panel.

### Requirement 4: Hosting mode badge in dashboard header

**User Story:** As a Tenant or Maintainer using the dashboard, I want a small persistent badge that tells me which hosting mode this installation is running in, so that I always know what to expect from the bot's uptime.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL render the Hosting_Mode_Badge inside the dashboard header (`.top-header`) on every authenticated dashboard view.
2. WHEN the persisted Hosting_Mode is `local_pc`, THE Hosting_Mode_Badge SHALL display the text `Local PC` and SHALL use a visual style distinct from the Cloud_Mode style (for example, an amber-coloured pill).
3. WHEN the persisted Hosting_Mode is `cloud`, THE Hosting_Mode_Badge SHALL display the text `Cloud` and SHALL use a visual style distinct from the Local_PC_Mode style (for example, a green-coloured pill).
4. WHEN no Hosting_Mode value is persisted, THE Hosting_Mode_Badge SHALL display the text `Unconfigured` in a neutral visual style.
5. WHERE the visitor's session role is `admin`, THE Hosting_Mode_Badge SHALL be a clickable element that opens the Hosting_Mode_Settings_Panel.
6. WHERE the visitor's session role is `tenant`, THE Hosting_Mode_Badge SHALL be rendered as a non-interactive read-only label.
7. THE Hosting_Mode_Badge SHALL include a tooltip or accessible label naming the active Hosting_Mode in full (`Local PC mode — intermittent uptime` or `Cloud mode — 24/7 uptime`).

### Requirement 5: Persistence across restarts

**User Story:** As a Maintainer, I want my hosting mode choice to survive dashboard restarts, browser closes, and EXE relaunches, so that I am not asked the same question every time I open the app.

#### Acceptance Criteria

1. WHEN the Maintainer confirms a Hosting_Mode selection in either the Hosting_Mode_Selector or the Hosting_Mode_Settings_Panel, THE Aegis_Suite SHALL write the chosen value to the `hosting_mode` key in `config.json` under the protection of `utils.config_lock`.
2. THE Aegis_Suite SHALL accept exactly two valid string values for the `hosting_mode` key: `local_pc` and `cloud`.
3. WHEN the FastAPI lifespan startup runs, THE Aegis_Suite SHALL read the `hosting_mode` key from `config.json` and SHALL expose it via the `GET /api/status` and `GET /api/hosting-mode` endpoints.
4. IF the `hosting_mode` key is missing, empty, or contains a value other than `local_pc` or `cloud`, THEN THE Aegis_Suite SHALL treat the Hosting_Mode as unset and SHALL trigger the first-launch behavior in Requirement 1.
5. THE Aegis_Suite SHALL NOT store the Hosting_Mode value in `localStorage`, `sessionStorage`, cookies, or any browser-side storage as the source of truth; the dashboard SHALL fetch the active Hosting_Mode from the server on every page load.
6. THE Aegis_Suite SHALL NOT write the Hosting_Mode value to `.env`, `.env.enc`, or any file managed by the Secret_Store, because the Hosting_Mode is a non-sensitive deployment preference and not a secret.

### Requirement 6: Environment variable override for headless deploys

**User Story:** As a Maintainer deploying to Railway or Render, I want to pre-select Cloud_Mode through an environment variable, so that the headless cloud instance does not sit on the chooser overlay waiting for a human click.

#### Acceptance Criteria

1. WHEN the FastAPI lifespan startup runs and the environment variable `AEGIS_HOSTING_MODE` is set to the value `local_pc` or `cloud` and no `hosting_mode` key is currently persisted in `config.json`, THE Aegis_Suite SHALL write that value to `config.json` and SHALL treat it as the active Hosting_Mode.
2. WHEN the FastAPI lifespan startup runs and the environment variable `AEGIS_HOSTING_MODE` is set to a value other than `local_pc` or `cloud`, THE Aegis_Suite SHALL log a maintainer-facing warning naming the invalid value and SHALL ignore the environment variable.
3. WHEN a `hosting_mode` value is already persisted in `config.json`, THE Aegis_Suite SHALL leave the persisted value unchanged regardless of the `AEGIS_HOSTING_MODE` environment variable, so that environment-variable changes never silently overwrite an explicit Maintainer choice.
4. THE Aegis_Suite SHALL document the `AEGIS_HOSTING_MODE` environment variable in `README.md` alongside `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, and `BOT_API_URL`.

### Requirement 7: Hosting mode settings panel and switching flow

**User Story:** As a Maintainer, I want to change my hosting mode later from a Settings panel, so that I can switch from Local_PC_Mode to Cloud_Mode after I finish my Railway deploy.

#### Acceptance Criteria

1. WHERE the visitor's session role is `admin`, THE Aegis_Suite SHALL provide a Hosting_Mode_Settings_Panel reachable from the dashboard Settings area and from clicking the Hosting_Mode_Badge.
2. THE Hosting_Mode_Settings_Panel SHALL display the active Hosting_Mode and SHALL offer a control to switch to the other Hosting_Mode value.
3. WHEN the admin requests a Hosting_Mode change in the Hosting_Mode_Settings_Panel, THE Aegis_Suite SHALL display the same Feature_Availability_Warning content described in Requirement 3 for the target Hosting_Mode before applying the change.
4. WHEN the admin requests a Hosting_Mode change in the Hosting_Mode_Settings_Panel, THE Aegis_Suite SHALL require an explicit confirmation interaction (for example, a confirmation button labelled `Switch to Local PC` or `Switch to Cloud`) before persisting the new value.
5. IF the admin cancels the confirmation step in the Hosting_Mode_Settings_Panel, THEN THE Aegis_Suite SHALL leave the persisted Hosting_Mode unchanged and SHALL dismiss the confirmation dialog.
6. WHEN the admin confirms the Hosting_Mode change, THE Aegis_Suite SHALL persist the new value (per Requirement 5), SHALL update the Hosting_Mode_Badge to reflect the new value, and SHALL append a `CONFIG_CHANGE` entry to the existing audit log naming the old and new Hosting_Mode values.
7. WHERE the visitor's session role is `tenant`, THE Aegis_Suite SHALL NOT expose the Hosting_Mode_Settings_Panel and SHALL respond to any direct request to change the Hosting_Mode with HTTP 403.

### Requirement 8: Backend hosting mode API endpoints

**User Story:** As the dashboard frontend, I want a small REST contract for reading and writing the hosting mode, so that the chooser, the badge, and the settings panel can all talk to the same source of truth.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL expose `GET /api/hosting-mode` returning a JSON body of the form `{"hosting_mode": "local_pc" | "cloud" | null}` where `null` indicates the value has not been set.
2. THE Aegis_Suite SHALL expose `PUT /api/hosting-mode` accepting a JSON body of the form `{"hosting_mode": "local_pc" | "cloud"}`.
3. WHEN `PUT /api/hosting-mode` is invoked with a body whose `hosting_mode` field is missing, empty, or not equal to `local_pc` or `cloud`, THE Aegis_Suite SHALL respond with HTTP 400 and SHALL NOT modify `config.json`.
4. WHEN `PUT /api/hosting-mode` is invoked by a session whose role is not `admin`, THE Aegis_Suite SHALL respond with HTTP 403 and SHALL NOT modify `config.json`.
5. WHEN `GET /api/hosting-mode` is invoked by an unauthenticated visitor, THE Aegis_Suite SHALL respond with HTTP 401, consistent with the existing `auth_middleware` behavior for `/api/*` routes other than the explicitly-allowed `/api/auth/*` and `/api/status` paths.
6. THE `GET /api/status` response SHALL include a `hosting_mode` field carrying the same value returned by `GET /api/hosting-mode`, so the dashboard can render the Hosting_Mode_Badge on the very first status poll without a second round-trip.

### Requirement 9: Storage location is config.json, not the secret store

**User Story:** As a Maintainer, I want my hosting mode preference stored next to my other non-sensitive dashboard preferences, so that secret storage stays focused on credentials and not lifestyle settings.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL persist the Hosting_Mode value as a top-level string field named `hosting_mode` inside `config.json`.
2. THE Aegis_Suite SHALL NOT persist the Hosting_Mode value inside `.env`, `.env.enc`, the DPAPI-encrypted Secret_Store, or any other file that the `secret_store.py` module manages.
3. THE Aegis_Suite SHALL update `config.example.json` to include the `hosting_mode` field with an empty-string default value so new clones of the repository document the field's existence.
4. THE Aegis_Suite SHALL retain the existing `.gitignore` exclusion for `config.json` so the persisted Hosting_Mode value of any individual installation is not committed to source control.
5. WHEN `config.json` is read or written for the Hosting_Mode, THE Aegis_Suite SHALL acquire `utils.config_lock` (or its async equivalent for the call site) to remain consistent with all other writers of `config.json`.

### Requirement 10: README documents both hosting paths

**User Story:** As a Maintainer reading the README, I want a clear explanation of the two hosting paths and which features are affected by each, so that I can pick the right one before I install Aegis.

#### Acceptance Criteria

1. THE `README.md` SHALL contain a section titled "Hosting Modes" (or equivalent) explaining the difference between Local_PC_Mode and Cloud_Mode.
2. THE Hosting Modes section SHALL state that Local_PC_Mode runs the Windows EXE on the Maintainer's own machine and is subject to intermittent uptime.
3. THE Hosting Modes section SHALL state that Cloud_Mode runs the same repository on a paid third-party host the Maintainer provisioned themselves and SHALL list at least the Railway one-click button path, the Render manual deployment path, and the generic Docker / VPS path.
4. THE Hosting Modes section SHALL list the same set of "Impacted by intermittent uptime" features named in Requirement 3.2 and the same set of "Unaffected by intermittent uptime" features named in Requirement 3.3, so the dashboard panel and the README cannot drift apart.
5. THE Hosting Modes section SHALL document the `AEGIS_HOSTING_MODE` environment variable as the headless override mechanism described in Requirement 6.
6. THE `README.md` SHALL retain the existing "🤖 Discord Bot Setup" section describing the `/linkdashboard` Pairing_Onboarding_Flow without modification.
7. THE `README.md` SHALL retain the existing "🔐 Secrets at Rest (Local EXE Deployment)" section describing the DPAPI-encrypted Secret_Store without modification.

### Requirement 11: Preserve managed-hosting-migration invariants

**User Story:** As the operator of an existing Aegis_Suite deployment, I want this feature to add UX without rolling back any of the security or deployment work that already landed, so that the new chooser does not become a regression vector.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL NOT reintroduce the `#setup-wizard` element, the `#wizard-token` input, the `#wizard-client-id` input, the `#btn-save-wizard` button, the `#btn-bot-toggle` button, or the `#btn-reconfigure` button in `static/index.html`.
2. THE Aegis_Suite SHALL NOT reintroduce a `bot_token` field on the `ConfigModel` Pydantic model in `web_server.py`.
3. THE Aegis_Suite SHALL NOT reintroduce the `POST /api/bot/start` or `POST /api/bot/stop` HTTP endpoints.
4. THE Aegis_Suite SHALL continue to load `DISCORD_BOT_TOKEN` exclusively via `utils.get_bot_token` from `os.environ`, populated by the server-side `.env` or DPAPI-decrypted `.env.enc`.
5. THE Aegis_Suite SHALL continue to require Tenants to enter the dashboard via the `/linkdashboard` Pairing_Onboarding_Flow and SHALL NOT add any alternative Tenant entry surface.
6. THE Aegis_Suite SHALL continue to enforce the existing JWT signature verification, guild-scoped `auth_middleware` checks, per-guild sliding-window rate limiter, `on_guild_remove` session revocation, `is_regex_safe` ReDoS guard, and `escapeHtml` XSS guard.
7. THE Aegis_Suite SHALL continue to use the DPAPI-encrypted `.env.enc` Secret_Store for `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, and `BOT_API_URL` on local Windows installs without any change introduced by this spec.
