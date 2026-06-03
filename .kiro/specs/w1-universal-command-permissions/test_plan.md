# Aegis Suite V2.1 — Test Plan

This document defines the verification strategy, test scenarios, and automated gates for Aegis Suite V2.1.

---

## 1. Unit Tests (`tests/test_permissions_resolver.py`)

Unit tests verify the core logic of the permission resolution engine without mock connections to Discord or Web servers.

### UT-1: Permission resolver Modes
- **Goal:** Validate basic authorization modes: `everyone`, `owner`, `admin`, `moderator`, `role`, `roles`.
- **Method:** Instantiate `PermissionResolver` with mock config datasets.
- **Assertions:**
  - `everyone` resolves to `True` for any member.
  - `owner` resolves to `False` unless bypassed.
  - `admin` requires `admin_role_id`.
  - `moderator` requires `moderator_role_id`.
  - `role` requires the matching `role_id`.
  - `roles` requires at least one matching ID from the `role_ids` list.

### UT-2: Privilege Hierarchy Inheritance
- **Goal:** Verify role hierarchies evaluate correctly.
- **Assertions:**
  - A user with the `admin` role must pass when a command requires `moderator` mode.
  - A user with the `moderator` role must fail when a command requires `admin` mode.

### UT-3: Destructive Commands Fail-Closed
- **Goal:** Ensure destructive actions default to a highly restrictive gate if config loads are corrupted or unconfigured.
- **Assertions:**
  - Running a destructive command (e.g. `LEVEL_RESET`, `UNLINK`, `MUSIC_STOP`) without rules in `command_permissions` returns `False` for normal users and requires admin role or owner bypass.
  - Failing to load `config.json` yields a fallback default which locks down destructive commands.

### UT-4: Command Registry Integration
- **Goal:** Assert that only command registry constants are checked, and invalid commands fail resolver checks.

---

## 2. Integration Tests

### IT-1: Music Module Solo VC Bypass
- **Goal:** Test voice channel solo human member bypass logic.
- **Method:**
  - Mock `discord.ext.commands.Context`.
  - Assert that when the bot is in a voice channel with exactly one human (the caller), control playback commands execute bypassing `PermissionResolver`.
  - Assert that when multiple humans are present, the call falls back to `PermissionResolver`.

### IT-2: Universal Decorator Gate
- **Goal:** Verify bot command gate raises `MissingPermissions` when permission validation fails.

---

## 3. Automated Security & Auditing Tests

### ST-1: Diagnostics ZIP Redaction Audit (`tests/test_diagnostics_redaction.py`)
- **Goal:** Ensure the generated zip diagnostics archive never leaks credentials or configuration secrets.
- **Method:**
  - Trigger diagnostics export using code wrapper to write test archives.
  - Unpack the ZIP programmatically and inspect file structures.
  - Search all logs, redacted configs, and metadata JSON files for:
    - Discord client bot tokens (regex matching `[a-zA-Z0-9_\-\.]{24,36}\.[a-zA-Z0-9_\-\.]{6}\.[a-zA-Z0-9_\-\.]{27,43}`).
    - Client secrets, session cookies, database passwords, and `.env` files.
- **Assertions:** If any credential format matches, the test fails.

### ST-2: Guild Config Persistence Audit (`tests/test_config_persistence.py`)
- **Goal:** Validate save pathways and prevent database degradation or data loss.
- **Method:**
  - Load active `config.json` via `utils.load_config`.
  - Modify `command_permissions`, `permission_roles`, and `music_settings` fields.
  - Invoke `utils.save_config()` under `config_lock` lock.
  - Clear in-memory caches, reload from disk, and assert values are preserved exactly.

---

## 4. AutoMod Validation Required Before Release

Live staging tests must verify the AutoMod release gate before markings can change to "functional".

| Check Target | Input Vector | Expected Staging Outcome |
|---|---|---|
| **Link Blocking** | `http://google.com`, `https://example.com`, `google.com`, `[Link](http://google.com)` | Message deleted instantly |
| **Invite Blocking**| `discord.gg/inv`, `discord.com/invite/code` | Message deleted instantly |
| **Whitelist bypass**| Whitelisted domain/invite (e.g. `github.com`) | Message allowed through |
| **Moderator bypass**| Member with Moderator Role sends link | Message allowed through |
| **Admin bypass** | Member with Admin Role sends link | Message allowed through |
| **Owner bypass** | Guild Owner sends link | Message allowed through |

---

## 5. Template Safety Layer Preview & Customizer Tests

- **Preview verification:** Assert that the preview API lists the counts of categories, text channels, voice channels, and roles to create.
- **Duplicate handling:** Assert that if a role or channel already exists in the server under the same name, it is flagged as "skipped" and duplicate creation is blocked.
- **Confirmation verification:** Assert that POST requests to apply template schemas fail if the confirmation payload check is missing.
