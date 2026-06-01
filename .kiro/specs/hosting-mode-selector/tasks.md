# Implementation Plan: Hosting Mode Selector

## Overview

This plan layers a Hosting Mode Selector onto the existing Aegis Suite dashboard. The work is strictly additive on top of `managed-hosting-migration`: a new `hosting_mode` string in `config.json`, two new REST endpoints (`GET` / `PUT /api/hosting-mode`), an `AEGIS_HOSTING_MODE` env-var bootstrap inside the FastAPI lifespan, and three new dashboard UI artifacts (header badge, first-launch chooser, Local-PC-only feature warning panel) plus an admin-only Settings panel for switching modes.

Implementation language is **Python 3.12** for the backend and **vanilla ES2017 JavaScript** for the dashboard, matching the existing codebase. Per the design's "Why this feature does not use property-based testing" subsection, no property-based tests are added — the feature is pure UI / config / two-value enum CRUD, which the workflow rules flag as a poor PBT fit. Tests are example-based `pytest` cases against the existing `TestClient` pattern in `tests/test_managed_hosting.py`.

Each parent task groups edits to a single file (or one cohesive cluster) so wave 0 sub-tasks write to disjoint files and can execute in parallel. Test sub-tasks all target the new `tests/test_hosting_mode_selector.py` file and are therefore staggered across waves 1–3 (wave 1 creates the file, waves 2–3 append).

## Tasks

- [x] 1. Add `hosting_mode` to the persisted config schema
  - [x] 1.1 Add `hosting_mode` default to `utils.py` DEFAULT_CONFIG and to `config.example.json`
    - In `utils.py`: add `"hosting_mode": ""` as a top-level key inside `DEFAULT_CONFIG` (same convention as the existing empty-string defaults for `bot_token` and `admin_password_hash`)
    - In `config.example.json`: add `"hosting_mode": ""` as a top-level field so new clones of the repo document the field's existence
    - Do NOT modify `.env`, `.env.enc`, `secret_store.py`, or any DPAPI-related code
    - Do NOT modify `.gitignore` — the existing `config.json` exclusion is retained
    - _Requirements: 5.6, 9.1, 9.2, 9.3, 9.4, 11.7_
    - _Design: §Components and Interfaces — "Backend: utils.py", "Backend: config.example.json"; §Data Models — "config.json schema additions"_

- [x] 2. Add backend hosting-mode REST surface and lifespan bootstrap in `web_server.py`
  - [x] 2.1 Add `HostingModePutRequest`, `GET /api/hosting-mode`, `PUT /api/hosting-mode`, status extension, and `AEGIS_HOSTING_MODE` bootstrap to `web_server.py`
    - Define `class HostingModePutRequest(BaseModel)` with a single `hosting_mode: str` field, placed near the existing `ConfigModel` definition
    - Add `@app.get("/api/hosting-mode")` returning `{"hosting_mode": value | None}` where `value` is `config.get("hosting_mode")` only when it equals `"local_pc"` or `"cloud"`, else `None`; allow any authenticated session (admin or tenant) — `auth_middleware` already gates this
    - Add `@app.put("/api/hosting-mode")` that:
      1. Returns HTTP 403 when `auth.get_session_role(token) != "admin"`
      2. Returns HTTP 400 when the request body's `hosting_mode` is missing, empty, or not exactly `"local_pc"` / `"cloud"` (do NOT touch `config.json` on a 400)
      3. On success, acquires `utils.config_lock`, calls `utils.load_config()`, sets `config["hosting_mode"]`, calls `utils.save_config(config)`, and on a `False` return value responds HTTP 500 with `{"detail": "Failed to save hosting mode."}` and skips the audit log
      4. On a successful save, calls `audit_log.log_action(actor="admin", category="CONFIG_CHANGE", action=f"Hosting mode changed from '{old}' to '{new}'")` (best-effort, do not roll back the config write if logging fails)
      5. Returns `{"status": "success", "hosting_mode": new_value}` on 200
    - Extend the existing `@app.get("/api/status")` handler to include a `hosting_mode` field in its JSON body sourced from the same `config.json` value (using the same `local_pc | cloud | null` contract as `GET /api/hosting-mode`); leave every other `/api/status` field unchanged
    - In the existing `lifespan(app)` async context manager, BEFORE the existing `bot_manager.start_bot_service` call, add the `AEGIS_HOSTING_MODE` bootstrap block: read `config.json`; if `config.get("hosting_mode")` is empty, read `os.environ.get("AEGIS_HOSTING_MODE", "").strip().lower()`; when the env value equals `"local_pc"` or `"cloud"`, acquire `utils.config_lock`, re-read the config (race protection), and only write when `cfg.get("hosting_mode")` is still empty; when the env value is non-empty but not in the allowed pair, emit a `logger.warning(...)` naming the invalid value and continue
    - Extract the bootstrap logic into a module-level helper (for example `_bootstrap_hosting_mode_from_env()`) so it is callable directly from tests without spinning up uvicorn
    - Do NOT extend `auth_middleware`'s tenant-blocklist to `/api/hosting-mode` — GET must remain reachable for tenants so the badge can render
    - Do NOT reintroduce `bot_token` on `ConfigModel`, `POST /api/bot/start`, `POST /api/bot/stop`, or any setup-wizard surface
    - Do NOT add any outbound HTTP call to Railway, Render, or any other hosting provider in the PUT handler or the bootstrap helper; the dashboard's only role for Cloud_Mode is to record the choice
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 9.5, 11.2, 11.3, 11.4_
    - _Design: §Components and Interfaces — "Backend: web_server.py" (Pydantic model, new endpoints, modified GET /api/status, modified lifespan startup, auth_middleware interaction); §Error Handling — "Invalid hosting mode values", "Concurrent writes", "Audit log failures", "Tenant attempting PUT", "config.json write failures"_

- [x] 3. Add Hosting Mode UI elements to `static/index.html`
  - [x] 3.1 Insert the badge, selector overlay, warning panel, and settings panel into `static/index.html`
    - Inside the existing `.top-header > .header-right`, add `<button id="hosting-mode-badge" class="hosting-mode-badge state-unconfigured" title="Hosting mode" aria-label="Hosting mode: Unconfigured">` containing a Font Awesome icon and a `<span id="hosting-mode-badge-text">Unconfigured</span>`; the JS layer is responsible for swapping the `<button>` to a `<span>` clone for tenants
    - Add a new `<div id="hosting-mode-selector-overlay" class="wizard-container hidden">` that mirrors the existing `.wizard-box.glass` modal pattern used by `auth-setup-overlay`; inside, render two side-by-side `.option-card` blocks (`#hosting-mode-card-local-pc`, `#hosting-mode-card-cloud`) with the EXACT copy:
      - Local PC card body: `Run the Aegis EXE on your own machine. Intermittent uptime — features that need a 24/7 connection will not run while your PC is off or asleep.`
      - Cloud card body: `Deploy this repository to a paid host you provisioned yourself (Railway, Render, generic Docker VPS). Continuous 24/7 uptime expected. Aegis does not provision the host for you.` plus a sentence stating the Maintainer is responsible for provisioning, paying for, and configuring the third-party host, and a `<a href="README.md#hosting-modes">Deployment options</a>`-style link to the README Hosting Modes section
      - A confirm button (`#hosting-mode-confirm`) that is disabled until a card is selected
    - Do NOT add any input field, button, or hidden form element for third-party hosting provider API tokens, billing information, or account credentials inside `#hosting-mode-selector-overlay`; the Cloud card is purely descriptive plus an external link
    - Do NOT add any `<form>` action, `<a>` href, or `<button>` data attribute that points at a Railway, Render, or other provider API endpoint
    - Add `<section id="feature-availability-warning" class="card glass hidden">` containing two child sections:
      - `<section class="impacted">` with heading `Impacted by intermittent uptime` and a `<ul>` listing exactly: `auto-moderation message handlers`, `scheduled messages background loop`, `giveaway end-time scheduler`, `leveling XP grants on member messages`, `on_guild_remove session revocation`, `/linkdashboard pairing-code expiry`, `periodic audit log roll-ups`, `welcome embeds and auto-role assignment on member join`, `auto-responders`
      - `<section class="unaffected">` with heading `Unaffected by intermittent uptime` and a `<ul>` listing exactly: `dashboard configuration changes`, `server health audit scan`, `server layout optimizer`, `role creator`, `role panel deployment`, `custom commands configuration`, `server template save and apply`, `embed builder`, `server backup and restore`, `audit log viewer`
      - A short explanatory paragraph stating that features in the Impacted section will not run while the host PC is offline, asleep, or disconnected from Discord
      - Do NOT include any element with `data-action="dismiss"`, `id="dismiss-warning"`, or any "do not show again" control
    - Add `<section id="hosting-mode-settings-panel" class="card glass hidden">` inside the existing Settings tab pane (or, if no Settings pane exists, alongside the audit-log card), containing: a "Current mode: X" label, a "Switch to {other}" button, and an inline confirmation block that re-renders the same Impacted / Unaffected lists for the TARGET mode plus a confirm button labeled `Switch to Local PC` or `Switch to Cloud` and a cancel button
    - Do NOT reintroduce `#setup-wizard`, `#wizard-token`, `#wizard-client-id`, `#btn-save-wizard`, `#btn-bot-toggle`, or `#btn-reconfigure`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.6, 4.1, 4.2, 4.3, 4.4, 7.1, 7.2, 7.3, 7.4, 11.1_
    - _Design: §Components and Interfaces — "Frontend: static/index.html"_

- [x] 4. Add Hosting Mode styles to `static/style.css`
  - [x] 4.1 Append `.hosting-mode-badge`, `.feature-availability-warning`, and selector card styles to `static/style.css`
    - Add `.hosting-mode-badge` rules: pill-shaped, fits inside `.top-header > .header-right`, base padding/border-radius matching existing pill components in the file
    - Add three modifier classes using existing CSS variables — `.state-local-pc` uses `var(--warning)` (amber), `.state-cloud` uses `var(--success)` (green), `.state-unconfigured` uses `var(--text-muted)` (neutral)
    - Add `.feature-availability-warning` rules reusing the existing `.card.glass` look with a `var(--warning)`-tinted `border-left` flag on the `.impacted` child section
    - Add `#hosting-mode-selector-overlay` modal sizing rules and `.option-card` side-by-side flex layout consistent with the existing `.wizard-box.glass` styling
    - Do NOT introduce new color tokens, new fonts, or new CSS variables — only consume existing tokens (`--warning`, `--success`, `--text-muted`, `--card-bg`, `--card-border`)
    - _Requirements: 4.2, 4.3, 4.4_
    - _Design: §Components and Interfaces — "Frontend: static/style.css"_

- [x] 5. Wire Hosting Mode behavior into `static/app.js`
  - [x] 5.1 Add hosting-mode state, render functions, first-launch trigger, and settings flow to `static/app.js`
    - Declare a module-scoped object `let hostingMode = { value: null, pendingTarget: null };`
    - Implement `function renderHostingModeBadge(mode, role)`:
      - When `role === "admin"`, render the `<button id="hosting-mode-badge">` and bind a click handler that calls `openHostingModeSettings()`
      - When `role === "tenant"`, replace the `<button>` with a `<span>` clone (no click handler)
      - Set the visual state class and badge text: `local_pc` → `state-local-pc` + `Local PC`, `cloud` → `state-cloud` + `Cloud`, otherwise → `state-unconfigured` + `Unconfigured`
      - Set the `aria-label` attribute to `Hosting mode: Local PC mode — intermittent uptime`, `Hosting mode: Cloud mode — 24/7 uptime`, or `Hosting mode: Unconfigured` to match the active state
    - Implement `function renderFeatureAvailabilityWarning(mode)` that toggles the `hidden` class on `#feature-availability-warning` based on `mode === "local_pc"`; the DOM content is static so no innerHTML rewriting is needed
    - Implement `async function maybeShowHostingModeSelector()`:
      - Read role from `localStorage.getItem("admin_role")`; return early when role is not `"admin"`
      - `await fetch("/api/hosting-mode")`; on a non-OK response, return without opening the modal (do NOT fail open to the chooser on a network blip)
      - When the response `hosting_mode` field is `"local_pc"` or `"cloud"`, return without opening
      - Otherwise call `openHostingModeSelector()`
    - Implement `function openHostingModeSelector()` that removes the `hidden` class from `#hosting-mode-selector-overlay` and binds card-click handlers + the confirm-button handler that PUTs the chosen value to `/api/hosting-mode` and on a 200 response refreshes the badge / warning panel and re-applies the `hidden` class to the overlay
    - Implement `function openHostingModeSettings()` that toggles `#hosting-mode-settings-panel`, populates the current mode label, wires the "Switch to {other}" button to render the inline confirmation step (which re-uses the same Impacted/Unaffected feature lists for the TARGET mode), and on confirmation PUTs the new value, on cancellation closes the dialog without calling PUT
    - In the existing `checkStatus()` polling loop, after parsing the JSON response, capture `statusData.hosting_mode`, store it on `hostingMode.value`, and call `renderHostingModeBadge(statusData.hosting_mode, localStorage.getItem("admin_role"))` and `renderFeatureAvailabilityWarning(statusData.hosting_mode)` on every poll so the dashboard never caches a stale value
    - Call `maybeShowHostingModeSelector()` from the existing `initApp()` flow AFTER the auth check completes and BEFORE the rest of the dashboard renders
    - Do NOT introduce a `localStorage` / `sessionStorage` / cookie key for `hosting_mode` — the server is the single source of truth
    - Do NOT add any client-side fetch / XHR / `<form action>` targeting Railway, Render, or any other hosting provider; the Cloud_Mode UX is local-state-only
    - Do NOT reintroduce `saveWizardCredentials`, `startBot`, `stopBot`, or any reference to `/api/bot/start` or `/api/bot/stop`
    - _Requirements: 1.1, 1.5, 1.6, 1.7, 2.3, 2.4, 2.5, 3.1, 3.5, 3.7, 4.5, 4.6, 4.7, 5.5, 7.2, 7.4, 7.5, 7.7, 11.1_
    - _Design: §Components and Interfaces — "Frontend: static/app.js"; §Architecture — "First-launch decision flow", "Switching from Settings (existing install)"_

- [x] 6. Document hosting modes in `README.md`
  - [x] 6.1 Add a "Hosting Modes" section to `README.md`
    - Insert a new top-level section titled `## 🖥️ Hosting Modes` (or equivalent ASCII heading) placed AFTER the existing "🔐 Secrets at Rest (Local EXE Deployment)" section so the credential-handling docs come first
    - State that Local PC mode runs the Windows EXE on the Maintainer's own machine and is subject to intermittent uptime
    - State that Cloud mode runs the same repository on a paid third-party host the Maintainer provisioned themselves; explicitly list the Railway one-click button path, the Render manual deployment path, and the generic Docker / VPS path
    - Include the same "Impacted by intermittent uptime" feature list and the same "Unaffected by intermittent uptime" feature list verbatim from task 3.1 so the README and the dashboard panel cannot drift apart
    - Document the `AEGIS_HOSTING_MODE` environment variable: state it accepts `local_pc` or `cloud`, that it only runs at FastAPI startup, that it is ignored when `config.json` already has a value, and that invalid values are logged and ignored; place this alongside the existing `DISCORD_BOT_TOKEN`, `JWT_SECRET`, `ADMIN_PASSWORD_HASH`, `BOT_API_URL` documentation
    - Do NOT modify the existing "🤖 Discord Bot Setup" section describing the `/linkdashboard` Pairing Onboarding Flow
    - Do NOT modify the existing "🔐 Secrets at Rest (Local EXE Deployment)" section describing the DPAPI-encrypted Secret Store
    - _Requirements: 2.2, 6.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 11.7_
    - _Design: §Architecture — "Why an environment-variable bootstrap is needed"; §Data Models — "Environment variables"_

- [x] 7. Checkpoint — verify dashboard surface and config integrity
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Add automated regression tests for the hosting mode selector
  - [x]* 8.1 Create `tests/test_hosting_mode_selector.py` with REST endpoint tests
    - Use `fastapi.testclient.TestClient(app)` with a `tmp_path`-isolated `config.json` fixture (mirror the pattern in `tests/test_managed_hosting.py`)
    - Implement `test_get_hosting_mode_returns_null_when_unset` — empty `hosting_mode` in `config.json`; admin GET returns body `{"hosting_mode": null}` with HTTP 200
    - Implement `test_get_hosting_mode_returns_local_pc` — seed `local_pc`; admin GET returns `{"hosting_mode": "local_pc"}`
    - Implement `test_get_hosting_mode_returns_cloud_for_tenant` — seed `cloud`; tenant session GET returns `{"hosting_mode": "cloud"}` with 200 (tenants are allowed to read)
    - Implement `test_get_hosting_mode_unauthenticated_401` — no bearer token; expect HTTP 401 from `auth_middleware`
    - Implement `test_put_hosting_mode_admin_local_pc_persists_and_audits` — admin PUT `{"hosting_mode": "local_pc"}`; expect 200, freshly-read `config.json["hosting_mode"] == "local_pc"`, and one new `audit_log.json` entry whose category is `CONFIG_CHANGE` and whose action text contains `local_pc`
    - Implement `test_put_hosting_mode_admin_cloud_persists` — admin PUT `{"hosting_mode": "cloud"}`; expect 200, `config.json` updated
    - Implement `test_put_hosting_mode_admin_invalid_value_400` — admin PUT `{"hosting_mode": "on-prem"}`; expect 400, `config.json` unchanged, no new audit-log entry
    - Implement `test_put_hosting_mode_admin_missing_field_400` — admin PUT with `{}`; expect 400
    - Implement `test_put_hosting_mode_admin_empty_string_400` — admin PUT with `{"hosting_mode": ""}`; expect 400
    - Implement `test_put_hosting_mode_tenant_403` — tenant session PUTs `local_pc`; expect 403, `config.json` unchanged
    - Implement `test_put_hosting_mode_unauthenticated_401` — no bearer; expect 401
    - Implement `test_get_status_includes_hosting_mode` — seed `cloud`; `GET /api/status` JSON body contains `"hosting_mode": "cloud"` alongside the existing fields
    - Implement `test_get_status_hosting_mode_null_when_unset` — empty seed; `GET /api/status` body contains `"hosting_mode": null`
    - Implement `test_put_hosting_mode_audit_entry_names_old_and_new` — pre-seed `local_pc`, PUT `cloud`; the audit-log entry text contains both `local_pc` and `cloud`
    - _Validates: Requirements 5.1, 5.2, 5.3, 5.4, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
    - _Design: §Testing Strategy — "Backend unit tests (FastAPI handlers)"_

  - [x]* 8.2 Append `AEGIS_HOSTING_MODE` lifespan bootstrap tests to `tests/test_hosting_mode_selector.py`
    - Use `pytest`'s `monkeypatch` for the env var and `tmp_path` for an isolated `config.json`; call the bootstrap helper directly via the module-level entry point added in task 2.1
    - Implement `test_bootstrap_writes_local_pc_when_unset_and_env_valid` — env=`local_pc`, config unset; after bootstrap, `config.json["hosting_mode"] == "local_pc"`
    - Implement `test_bootstrap_writes_cloud_when_unset_and_env_valid` — env=`cloud`, config unset; after bootstrap, `config.json["hosting_mode"] == "cloud"`
    - Implement `test_bootstrap_ignores_invalid_env_value` — env=`onprem`, config unset; after bootstrap, `config.json["hosting_mode"]` is still empty AND `caplog` contains a WARNING-level record naming `onprem`
    - Implement `test_bootstrap_does_not_overwrite_persisted_value` — env=`cloud`, config pre-seeded to `local_pc`; after bootstrap, `config.json["hosting_mode"] == "local_pc"` (Req 6.3)
    - Implement `test_bootstrap_no_env_var_no_change` — env unset, config unset; after bootstrap, `config.json["hosting_mode"]` is still empty
    - Implement `test_bootstrap_case_insensitive_env_value` — env=`LOCAL_PC`, config unset; after bootstrap, `config.json["hosting_mode"] == "local_pc"` (the implementation lowercases before validating)
    - _Validates: Requirements 6.1, 6.2, 6.3_
    - _Design: §Testing Strategy — "Backend unit tests (lifespan bootstrap)"; §Components and Interfaces — "Modified lifespan startup"_

  - [x]* 8.3 Append managed-hosting invariant + content-drift regression tests to `tests/test_hosting_mode_selector.py`
    - Implement `test_no_setup_wizard_in_index_html` — read `static/index.html`; assert `id="setup-wizard"`, `id="wizard-token"`, `id="wizard-client-id"`, `id="btn-save-wizard"`, `id="btn-bot-toggle"`, `id="btn-reconfigure"` substrings are all absent (Req 11.1)
    - Implement `test_config_model_has_no_bot_token` — introspect `web_server.ConfigModel.model_fields`; assert `"bot_token"` is absent (Req 11.2)
    - Implement `test_no_bot_start_stop_routes` — iterate `app.routes`; assert no route's `path` equals `/api/bot/start` or `/api/bot/stop` (Req 11.3)
    - Implement `test_hosting_mode_not_in_secret_store` — after a successful PUT, read `.env` and (if present) `.env.enc` raw bytes; assert neither contains the substring `HOSTING_MODE` or `hosting_mode` (Req 5.6, 9.2)
    - Implement `test_warning_panel_feature_lists_match_readme` — read `static/index.html` and `README.md`; for each impacted feature listed in Requirement 3.2 and each unaffected feature listed in Requirement 3.3, assert the feature name appears in BOTH files so the dashboard panel and the README cannot drift apart (Req 10.4)
    - Implement `test_readme_has_hosting_modes_section` — read `README.md`; assert it contains a `Hosting Modes` heading, the literal substring `AEGIS_HOSTING_MODE`, the words `Railway`, `Render`, `Docker`, the words `Local PC`, `Cloud`, and `intermittent uptime` (Req 10.1, 10.2, 10.3, 10.5)
    - Implement `test_readme_preserves_pairing_and_secrets_sections` — assert `README.md` still contains the `🤖 Discord Bot Setup` heading and the `🔐 Secrets at Rest` heading unchanged (Req 10.6, 10.7)
    - Implement `test_warning_panel_has_no_dismiss_control` — read `static/index.html`; locate the `#feature-availability-warning` block and assert it contains no `data-action="dismiss"` attribute, no `id="dismiss-warning"`, and no `do not show again` text (Req 3.6)
    - Implement `test_selector_has_no_third_party_credential_inputs` — read `static/index.html`; locate the `#hosting-mode-selector-overlay` block and assert it contains no `<input>` element whose `name`, `id`, or `placeholder` references `railway`, `render`, `api_token`, `api_key`, `billing`, or `credentials` (Req 2.4)
    - Implement `test_no_outbound_provider_urls_in_frontend` — read `static/index.html` and `static/app.js`; assert neither contains `api.railway.app`, `api.render.com`, or any other provider API hostname (Req 2.3); the only allowed Railway / Render references are documentation links pointing at `README.md` or the providers' marketing sites
    - _Validates: Requirements 2.3, 2.4, 3.2, 3.3, 3.6, 5.6, 9.2, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 11.1, 11.2, 11.3_
    - _Design: §Testing Strategy — "Regression tests for managed-hosting-migration invariants", "README content tests"_

- [x] 9. Final checkpoint — full regression suite
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. The hosting-mode UX is observable by hand even without them, but they encode the acceptance criteria as code and should be retained for the deploy workflow's `test` job.
- Property-based tests are intentionally NOT included. Per the design's "Why this feature does not use property-based testing" subsection, the entire valid input space for `hosting_mode` is exactly two enum values, the dashboard surface is static DOM, and the persisted state is a single string in `config.json` — categories the workflow rules list as not appropriate for PBT. The existing `tests/test_hardening.py` PBT-style regression suite (covering JWT tampering, session revocation, sliding-window rate limiter, idempotent purge) continues to run unchanged via `verify.yml` and `deploy.yml`, which preserves the Requirement 11 invariants from the previous spec.
- Wave 0 contains every implementation task. They write to disjoint files (`utils.py` + `config.example.json`, `web_server.py`, `static/index.html`, `static/style.css`, `static/app.js`, `README.md`) and can run fully in parallel. Test sub-tasks 8.1–8.3 all write to the same new file `tests/test_hosting_mode_selector.py` and are therefore staggered across waves 1–3 — 8.1 creates the file, 8.2 and 8.3 append additional test functions. The checkpoint tasks 7 and 9 are not in the dependency graph because they are checkpoints, not leaf coding tasks.
- Each leaf task references both the granular requirements clauses it satisfies and the design section that specifies its contract, so an executor can pick up any single task without re-reading the entire spec.
- Requirement 11 invariants 11.4 (DISCORD_BOT_TOKEN sourced via `utils.get_bot_token`), 11.5 (`/linkdashboard` is the only Tenant entry point), and 11.6 (preserved JWT / rate-limiter / `on_guild_remove` / ReDoS / XSS guards) are not directly implemented by any task in this plan because they are pre-existing behaviors. The task-level `Do NOT` constraints in tasks 2.1, 3.1, and 5.1 ensure those behaviors are not regressed; the existing `tests/test_hardening.py` and `tests/test_managed_hosting.py` suites continue to run them as part of the verify and deploy workflows.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 1, "tasks": ["8.1"] },
    { "id": 2, "tasks": ["8.2"] },
    { "id": 3, "tasks": ["8.3"] }
  ]
}
```

## Workflow Completion

This workflow created the design and planning artifacts only — `requirements.md`, `design.md`, and this `tasks.md`. To begin execution, open `tasks.md` and click **Start task** next to the task you want to dispatch. Wave 0 sub-tasks (1.1, 2.1, 3.1, 4.1, 5.1, 6.1) are independent and can be dispatched in parallel.
