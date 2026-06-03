# Aegis Suite V2.1 — Task Breakdown

This document presents the detailed checklist of implementation tasks for Workstream W1 and Aegis Suite V2.1.

---

## 1. Workstream Checklists & Implementation Progress

### Phase 1: Storage Schema & Pydantic Config Models
- [ ] **Task 1.1: Extend Config Schema**
  - Add `CommandPermissionRule` and `PermissionRoles` models to `aegis/config/schema.py`.
  - Attach `command_permissions` and `permission_roles` to the parent `ConfigModel`.
- [ ] **Task 1.2: Add Feature Gating Flags**
  - Create `aegis/core/flags.py` and declare `ENABLE_CLOUD_MODE = False`.
  - Ensure Pydantic schemas and database structures for Cloud Mode are kept intact.
- [ ] **Task 1.3: Update System Defaults**
  - Update `utils.DEFAULT_CONFIG` with empty mappings for permissions schema.
  - Implement config upgrade/backfilling logic in `utils.load_config` to populate defaults on load.

### Phase 2: Central Registry & Core PermissionResolver
- [ ] **Task 2.1: Centralized Command Registry**
  - Create `aegis/core/permissions/registry.py` and implement `CommandRegistry` containing uppercase constant command strings.
  - Ensure all modules import and utilize these constants.
- [ ] **Task 2.2: Implement PermissionResolver**
  - Create `aegis/core/permissions/resolver.py` containing the thread-safe resolver logic.
  - Ensure no music or voice channel logic is present in the resolver (must remain generic).
- [ ] **Task 2.3: Core resolver Unit Tests**
  - Write tests under `tests/test_permissions_resolver.py` asserting role checks, admin/owner overrides, hierarchy levels, and fail-closed fallbacks for destructive commands.

### Phase 3: Bot Commands Gate & Music Module Wrapper
- [ ] **Task 3.1: Music Module Permissions wrapper**
  - Create `aegis/bot/music_permissions.py` (or within the music cog) containing the voice channel solo human member count bypass logic.
  - Implement the flow: Command -> Music Permission Wrapper -> Solo VC check -> PermissionResolver -> Execution.
- [ ] **Task 3.2: Universal Decorator Integration**
  - Implement the `universal_permission_check` command decorator wrapper mapping bot context parameters to resolver checks.
  - Attach decorators and split music commands into public vs playback controls.
- [ ] **Task 3.3: UI Bot Error Handler**
  - Update command execution failure router inside `bot_manager.py` to politely notify users when universal permission verification blocks command execution.

### Phase 4: Template System Customizer & Safety Layer
- [ ] **Task 4.1: Data-Driven JSON Templates**
  - Remove all hardcoded templates from `web_server.py`.
  - Load gaming, community, creator, and all other 8 presets from dynamic JSON files inside a designated templates folder.
- [ ] **Task 4.2: Preview and Skip Analysis API**
  - Create a preview endpoint `/api/templates/{name}/preview` which compiles a comparison payload mapping template requirements against the active guild's roles/channels.
  - Detect and count matching structures to identify skipped items.
- [ ] **Task 4.3: Secure Confirmation Endpoint**
  - Create `/api/guilds/{guild_id}/templates/apply` requiring explicit UI confirmation payload.
- [ ] **Task 4.4: Frontend Preview Wizard**
  - Build UI layout panel displaying the tree view summary of elements to create and elements to skip.
  - Block application until the user checks/clicks "Confirm and Deploy".

### Phase 5: Diagnostics ZIP & Redaction Hardening
- [ ] **Task 5.1: Secrets Redaction Scanners**
  - Implement custom regex scanners identifying Discord client bot tokens, session cookies, database hashes, OAuth tokens, and `.env` properties.
  - Replace matches with `[REDACTED]` when generating the payload.
- [ ] **Task 5.2: Downloadable ZIP Endpoint**
  - Implement `/api/diagnostics/download` generating an in-memory zip containing redacted config, system info, alembic schemas, and active logs.

### Phase 6: E2E Verification & Audit Tests
- [ ] **Task 6.1: Config Persistence Regression Test**
  - Create `tests/test_config_persistence.py` verifying config loads, updates, saves via `utils.save_config`, and reloads without data loss or corruption.
- [ ] **Task 6.2: Diagnostics Redaction Audit Test**
  - Create `tests/test_diagnostics_redaction.py` which triggers a mock archive export, unpacks the zip, and fails if any secret patterns remain.
- [ ] **Task 6.3: AutoMod Staging Release Checklist Validation**
  - Perform live execution of the release gate tests: standard link blocking, invite blocking, whitelist domain exceptions, moderator bypass, admin bypass, and owner bypass.
- [ ] **Task 6.4: Compilation Validation**
  - Execute a clean build run using PyInstaller (`build_exe.py`) ensuring binary executable packages run and load configurations properly.
