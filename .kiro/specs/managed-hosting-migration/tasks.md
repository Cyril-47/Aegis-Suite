# Implementation Plan: Managed Hosting Migration

## Overview

This plan migrates Aegis Suite from the self-hosted bot-token model to the managed-hosting model and lands the bundled cloud-deployability deliverables (single-file Windows build with Desktop shortcut, headless launcher guard, pinned `requirements.txt`, Railway deploy workflow, README rewrite). The work is intentionally subtractive: remove every browser-facing surface that touches `DISCORD_BOT_TOKEN`, then make the existing `/linkdashboard` flow the only tenant entry point. Implementation language is **Python 3.12** (matches the existing codebase). Per the design's testing strategy, no property-based tests are added — the migration is dominated by DOM/source removals, configuration files, and deterministic build tooling.

Each parent task groups edits to a single file (or related new file) so independent sub-tasks can execute in parallel without write conflicts. All test sub-tasks are marked optional (`*`) and target a single new file `tests/test_managed_hosting.py`; they are split into waves so the file is created once and then appended.

## Tasks

- [x] 1. Pin runtime dependencies for cloud install
  - [x] 1.1 Create `requirements.txt` at the repository root
    - Pin `discord.py==2.4.0`, `fastapi==0.115.5`, `uvicorn[standard]==0.32.1`, `websockets==13.1`, `yt-dlp==2024.12.13`, `PyNaCl==1.5.0`, `pydantic==2.10.3`
    - Pin build-only dep `Pillow==11.0.0` under a separate comment-delimited section
    - Do NOT include `winshell` or `pywin32` (Windows-only; build script handles their absence)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_
    - _Design: §Components and Interfaces — "8. requirements.txt (new file at repo root)"_

- [x] 2. Strip credential entry UI from the frontend
  - [x] 2.1 Remove credential HTML and rewrite the offline notice in `static/index.html`
    - Delete the entire `#setup-wizard` block (`#wizard-token`, `#wizard-client-id`, `#btn-save-wizard`, password-toggle buttons, helper text)
    - Delete the `info-row` containing `#btn-reconfigure` and its "Setup Configuration" / "Change Credentials" label
    - Delete the `#btn-bot-toggle` button from the sidebar bot badge
    - Rewrite the `#offline-notice-overlay` body to a single static maintenance message ("This dashboard is temporarily unavailable. Please try again later."); keep the overlay's `id`, root classes, and `hidden` initial state so JS can still toggle it
    - Remove every `<a>`, `<button>`, `<input>`, `<form>` tag inside the rewritten overlay
    - Leave the `%%BOT_API_URL%%` script block and the existing `#auth-login-overlay` onboarding list unchanged
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.7, 3.1, 3.2, 3.3, 3.4, 4.3, 2.10_
    - _Design: §Components and Interfaces — "1. static/index.html"_

  - [x] 2.2 Refactor `static/app.js` to remove credential handling
    - Delete `saveWizardCredentials`, `startBot`, `stopBot` functions and every call site
    - Delete `addEventListener` registrations for `#btn-save-wizard`, `#btn-bot-toggle`, `#btn-reconfigure`
    - Delete the `setupWizard` constant and every reference to it
    - In `checkStatus()`: remove the `data.role === 'user'` branch that toggled now-deleted IDs; replace the `if (!data.has_token)` branch with `if (data.status === 'stopped' || data.status === 'connecting')` showing the offline overlay
    - At the top of the `DOMContentLoaded` handler (before `checkAuthentication()`), add `localStorage.removeItem('bot_token')` and `localStorage.removeItem('client_id')` for one-shot cleanup of residual keys
    - Leave `escapeHtml`, the fetch interceptor that prepends `window.BOT_API_URL` and the `Authorization: Bearer` header, and the `auth_token` / `admin_role` / `admin_guild_id` storage usage unchanged
    - _Requirements: 1.5, 1.6, 4.1, 4.2, 11.8_
    - _Design: §Components and Interfaces — "2. static/app.js"_

- [x] 3. Remove server-side bot-token surface from `web_server.py`
  - [x] 3.1 Strip token endpoints, model field, and lifespan prompt from `web_server.py`
    - Delete the `bot_token: str` field from `class ConfigModel`
    - Delete the `@app.post("/api/bot/start")` and `@app.post("/api/bot/stop")` route handlers entirely so FastAPI returns 404 for those paths
    - In `GET /api/config`: remove the `config["bot_token"] = "********" if utils.get_bot_token(config) else ""` line
    - In `POST /api/config` admin branch: delete the `old_token` / `token_changed` / `.env` read-write block and the `os.environ["DISCORD_BOT_TOKEN"]` mutation; defensively `new_data.pop("bot_token", None)` before merging; drop the `token_changed` field from the response (or hard-code `False`)
    - In the FastAPI `lifespan` startup: keep the `if token: bot_manager.start_bot_service(token)` arm; replace the `else` branch with a single `logger.error("DISCORD_BOT_TOKEN is missing from environment. Set it in the server's .env. Bot will not start.")` and continue startup so `/api/status` keeps serving the maintenance overlay
    - Leave `auth_middleware`, `check_login_rate_limit`, the per-guild rate limiter, `prune_stale_rate_limiters`, the `%%BOT_API_URL%%` injection in the root HTML handler, and every `/api/auth/*` route untouched
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 11.4, 11.5_
    - _Design: §Components and Interfaces — "3. web_server.py"; §Error Handling — "Deleted /api/bot/start and /api/bot/stop", "POST /api/config with stray bot_token field", "web_server.py lifespan with missing token"_

- [x] 4. Make `run.py` safe to start on headless cloud hosts
  - [x] 4.1 Add `is_headless_cloud` guard around `webbrowser.open` in `run.py`
    - Define `def is_headless_cloud() -> bool:` returning `bool(os.getenv("RAILWAY_ENVIRONMENT")) or bool(os.getenv("RENDER"))`
    - Wrap the existing browser-opening thread block in `if not is_headless_cloud():` so the daemon thread is never spawned on Railway/Render
    - Inside `open_browser`, wrap `webbrowser.open(...)` in `try / except Exception` that logs a warning and lets uvicorn keep running
    - In the headless branch, print a single informational line stating the cloud env was detected and the browser step was skipped
    - Leave the local `.venv` bootstrap block and the uvicorn invocation on `127.0.0.1:8000` unchanged
    - _Requirements: 7.1, 7.2, 7.3, 7.4_
    - _Design: §Components and Interfaces — "7. run.py"; §Error Handling — "run.py with webbrowser.open raising"_

- [x] 5. Repair `build_exe.py` for single-file Windows build with Desktop shortcut
  - [x] 5.1 Rewrite `build_exe.py` PyInstaller invocation and add Desktop shortcut creation
    - Replace the PyInstaller command with `["pyinstaller", "--onefile", "--name=AegisOptimizer", "--add-data", "static;static", "--add-data", "templates;templates"]`, append `--icon logo.ico` when `logo.ico` exists, and end with `run.py`
    - Capture the PyInstaller subprocess stdout/stderr; on non-zero return code print both streams and `sys.exit(returncode)` BEFORE any shortcut step runs
    - After a successful build, compute `exe_path = os.path.abspath(os.path.join("dist", "AegisOptimizer.exe"))` and `ico_path = os.path.abspath(logo_ico)`
    - Implement `create_desktop_shortcut(exe_path, ico_path) -> bool`: import `winshell` and `win32com.client.Dispatch` inside a `try/except ImportError` that prints a warning naming both packages plus the `pip install winshell pywin32` hint and returns `False`
    - Resolve the Desktop folder via `winshell.desktop()` (OneDrive-aware); if `os.path.isdir(desktop)` is `False`, log the resolved path and return `False`
    - Build the shortcut at `os.path.join(desktop, "Aegis Optimizer.lnk")` with `Targetpath=exe_path`, `WorkingDirectory=os.path.dirname(exe_path)`, `IconLocation=ico_path`
    - In the caller, treat both the import-missing branch and the folder-missing branch as non-fatal (`sys.exit(0)`); wrap the COM dispatch call in a try/except so unexpected COM errors do not fail the overall build
    - Delete every print statement that mentions "Inno Setup" or "shortcut creation is deferred"
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_
    - _Design: §Components and Interfaces — "6. build_exe.py" (subsections 6.1 PyInstaller invocation, 6.2 Resolve the executable path, 6.3 Desktop shortcut creation, 6.4 Inno Setup references); §Error Handling — "build_exe.py with winshell / pywin32 missing", "build_exe.py with a missing Desktop folder"_

- [x] 6. Rewrite the Discord Bot Setup section of `README.md`
  - [x] 6.1 Replace the "🤖 Discord Bot Setup Instructions" section in `README.md`
    - Delete the existing 7-step Discord Developer Portal walkthrough
    - Insert the four-step Pairing_Onboarding_Flow: (1) click Invite Bot on the dashboard at `https://[your domain]/`, (2) run `/linkdashboard` in the user's Discord server to receive a 6-digit code valid 10 minutes, (3) paste the code and click Unlock Dashboard, (4) confirmation that the server panel is now unlocked and codes are single-use
    - Use `[your domain]` exactly as the placeholder for the maintainer's hosted dashboard URL
    - Do NOT mention Discord Developer Portal, Privileged Gateway Intents, Reset Token, copying a Bot Token, or pasting credentials anywhere in the rewritten section
    - Leave "🚀 Features", "⚙️ Deployment Targets", "🚀 Getting Started (Run from Source)", and "⚠️ Known Technical Debt & Limits" sections unchanged
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_
    - _Design: §Components and Interfaces — "10. README.md"_

- [x] 7. Add the Railway deploy workflow
  - [x] 7.1 Create `.github/workflows/deploy.yml`
    - Trigger on `push` events to the `main` branch only
    - Define a `test` job on `ubuntu-latest` with Python 3.12 that runs `pip install -r requirements.txt`, `pip install pytest pyyaml`, then `pytest tests/ -v`
    - Define a `deploy` job with `needs: test` that checks out the repo, runs a "Verify RAILWAY_TOKEN" step which exits 1 with a `::error::` annotation when `secrets.RAILWAY_TOKEN` is empty, installs the Railway CLI via `npm install -g @railway/cli`, then runs `railway up --detach` with `RAILWAY_TOKEN: ${{ secrets.RAILWAY_TOKEN }}` in the environment
    - Do NOT modify, replace, or delete `.github/workflows/verify.yml`
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
    - _Design: §Components and Interfaces — "9. .github/workflows/deploy.yml"; §Error Handling — "deploy.yml with RAILWAY_TOKEN unset"_

- [x] 8. Add automated regression tests for the migration
  - [x]* 8.1 Create `tests/test_managed_hosting.py` with frontend asset tests
    - Implement T1: read `static/index.html`; assert `id="setup-wizard"` substring is absent
    - Implement T2: assert `id="btn-reconfigure"` and `id="btn-bot-toggle"` substrings are absent
    - Implement T3: assert `id="wizard-token"`, `id="wizard-client-id"`, `name="bot-token"` are all absent
    - Implement T4: locate the `#offline-notice-overlay` block, assert it contains the maintenance phrase ("temporarily unavailable") and contains no `<a `, `<button `, `<input `, `<form ` tags inside the overlay
    - Implement T5: read `static/app.js`; assert `saveWizardCredentials`, `function startBot`, `function stopBot`, `'/api/bot/start'`, `'/api/bot/stop'`, `getElementById('btn-save-wizard')`, `getElementById('btn-bot-toggle')`, `getElementById('btn-reconfigure')` substrings are all absent
    - Implement T6: assert `static/app.js` contains both `localStorage.removeItem('bot_token')` and `localStorage.removeItem('client_id')`
    - _Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 3.2, 3.3, 3.4, 4.2, 4.3, 2.1, 2.2_
    - _Design: §Testing Strategy — "Unit and file-state tests" T1–T6_

  - [x]* 8.2 Add `web_server.py` route tests using `fastapi.testclient.TestClient`
    - Implement T7: read `web_server.py` source; assert the `class ConfigModel` body does not contain `bot_token:`
    - Implement T8: spin up FastAPI via `TestClient(app)` with a stubbed bot; assert `POST /api/bot/start` and `POST /api/bot/stop` both return HTTP 404
    - Implement T9: authenticate as admin via the existing login flow; assert `GET /api/config` returns a JSON body whose top-level keys do not include `bot_token`
    - Implement T10: authenticate as admin; capture `os.environ.get("DISCORD_BOT_TOKEN")` and the on-disk `.env` contents; `POST /api/config` with body containing `"bot_token": "FAKE.TOKEN.VALUE"` returns 200; assert `os.environ["DISCORD_BOT_TOKEN"]` is unchanged, the freshly re-read `.env` does not contain `FAKE.TOKEN.VALUE`, and `config.json["bot_token"]` is empty
    - _Validates: Requirements 2.3, 2.4, 2.5, 2.6_
    - _Design: §Testing Strategy — "Unit and file-state tests" T7–T10_

  - [x]* 8.3 Add config, workflow, README, and `run.py` tests
    - Implement T11: read `requirements.txt`; assert each of `discord.py`, `fastapi`, `uvicorn`, `websockets`, `yt-dlp`, `PyNaCl`, `pydantic` is present and pinned via `==` or `~=` (regex `^[A-Za-z0-9_.-]+(\[[a-z]+\])?(==|~=)\d`)
    - Implement T12: parse `.github/workflows/deploy.yml` with PyYAML; assert `on.push.branches == ['main']`, jobs include `test` and `deploy`, `jobs.deploy.needs == 'test'`, the deploy job references `secrets.RAILWAY_TOKEN`, and `.github/workflows/verify.yml` still exists on disk
    - Implement T13: read `README.md`; locate the rewritten "Discord Bot Setup" section by splitting on the next `##` header; assert it contains `/linkdashboard` and `[your domain]` and does NOT contain `Discord Developer Portal`, `Privileged Gateway Intents`, or `Reset Token` (case-insensitive); assert "Known Technical Debt & Limits" section is present and contains both `JSON` and `SQLite`
    - Implement T14: import the `run` module; with `monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)` and `monkeypatch.delenv("RENDER", raising=False)`, assert `run.is_headless_cloud()` returns `False`
    - Implement T15: with `monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")`, assert `run.is_headless_cloud()` returns `True`; reset, then with `monkeypatch.setenv("RENDER", "true")`, assert it returns `True`
    - _Validates: Requirements 7.1, 7.2, 8.1, 8.2, 8.3, 9.1, 9.2, 9.4, 9.5, 9.7, 10.1, 10.2, 10.3, 10.4, 10.5_
    - _Design: §Testing Strategy — "Unit and file-state tests" T11–T15_

- [-] 9. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP. The migration's correctness is observable by hand even without them, but they encode the acceptance criteria as code and should be retained for the deploy workflow's `test` job.
- Property-based tests are intentionally NOT included. Per the design's "Property-based testing applicability" subsection, this feature is dominated by DOM/source removals, configuration validation, side-effect-only environment guards, and infrastructure-as-code — categories the workflow rules list as not appropriate for PBT. The existing `tests/test_hardening.py` PBT-style regression suite continues to run via `verify.yml` and now also via the new `deploy.yml` test job, which covers the Requirement 11 preservation invariants (JWT tampering, session revocation, sliding-window rate limiter, idempotent purge).
- The build-script artifacts (R5, R6) are verified by the maintainer's manual release checklist documented in §Testing Strategy — "Build-script integration test (manual, documented in the spec)" because PyInstaller `--onefile` is Windows-only and would add 60–120 s to every CI run.
- Each leaf task references both the granular requirements clauses it satisfies and the design section that specifies its contract, so an executor can pick up any single task without re-reading the entire spec.
- Wave 0 contains every implementation task. They write to disjoint files (`requirements.txt`, `static/index.html`, `static/app.js`, `web_server.py`, `run.py`, `build_exe.py`, `README.md`, `.github/workflows/deploy.yml`) and can run fully in parallel. Test sub-tasks 8.1–8.3 all write to the same new file `tests/test_managed_hosting.py` and are therefore staggered across waves 1–3 — 8.1 creates the file, 8.2 and 8.3 append additional test functions.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "2.2", "3.1", "4.1", "5.1", "6.1", "7.1"] },
    { "id": 1, "tasks": ["8.1"] },
    { "id": 2, "tasks": ["8.2"] },
    { "id": 3, "tasks": ["8.3"] }
  ]
}
```

## Workflow Completion

This workflow created the design and planning artifacts only — `requirements.md`, `design.md`, and this `tasks.md`. To begin execution, open `tasks.md` and click **Start task** next to the task you want to dispatch. Wave 0 sub-tasks (1.1, 2.1, 2.2, 3.1, 4.1, 5.1, 6.1, 7.1) are independent and can be dispatched in parallel.
