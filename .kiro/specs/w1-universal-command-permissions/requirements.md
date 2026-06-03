# Aegis Suite V2.1 — Requirements Specification

This document defines the functional, non-functional, security, and release requirements for Aegis Suite V2.1.

---

## 1. Universal Command Permission Framework (W1)

### FR-1.1: Unified Permission Modes
- The permission resolver MUST evaluate per-command authorizations using the following hierarchy:
  1. `everyone`: Accessible to all guild members.
  2. `moderator`: Gated to users holding the configured `moderator_role_id` or higher.
  3. `admin`: Gated to users holding the configured `admin_role_id` or higher.
  4. `owner`: Gated to the Guild Owner or users holding the Discord `Administrator` permission.
  5. `role`: Gated to a specific role ID.
  6. `roles`: Gated to at least one role matching a list of role IDs.

### FR-1.2: Owner & Admin Bypass
- The Guild Owner (`user.id == guild.owner_id`) and any member holding the Discord `Administrator` permission MUST always bypass all authorization checks (evaluating to `True`).

### FR-1.3: Centralized Command Naming Registry
- All permission checks and mappings MUST reference command names using centralized, uppercase registry constants. No raw strings are allowed in permission lookups. The registry MUST contain:
  - **Music:** `MUSIC_PLAY`, `MUSIC_PAUSE`, `MUSIC_RESUME`, `MUSIC_SKIP`, `MUSIC_STOP`, `MUSIC_QUEUE`, `MUSIC_VOLUME`, `MUSIC_NOWPLAYING`, `MUSIC_SHUFFLE`, `MUSIC_CLEARQUEUE`, `MUSIC_LYRICS`.
  - **Giveaways:** `GIVEAWAY_CREATE`, `GIVEAWAY_REROLL`, `GIVEAWAY_STOP`.
  - **Welcomer:** `WELCOME_SET`.
  - **Tickets:** `TICKET_PANEL`, `TICKET_CLOSE`.
  - **Leveling:** `LEVEL_RANK`, `LEVEL_LEADERBOARD`, `LEVEL_SET_ROLE`, `LEVEL_RESET`.
  - **System:** `LINK_DASHBOARD`, `UNLINK`, `AUDIT_SERVER`, `OPTIMIZE_SERVER`.

### FR-1.4: Fail-Closed Destructive Commands
- Unconfigured destructive commands (e.g., `LEVEL_RESET`, `UNLINK`, `MUSIC_STOP`, `GIVEAWAY_STOP`) MUST default to `admin` or `owner` authorization.
- If the configuration load fails, is unreadable, or is corrupted, access to all destructive commands MUST be blocked (fail-closed).

---

## 2. Music Authorization & Voice Channel Solo Bypass

### FR-2.1: Music Permission Separation
- Playback commands MUST be segmented into distinct access profiles:
  - **Public Commands:** `MUSIC_PLAY`, `MUSIC_QUEUE`, `MUSIC_NOWPLAYING`, `MUSIC_LYRICS` (defaulting to `everyone`).
  - **Playback Control Commands:** `MUSIC_SKIP`, `MUSIC_STOP`, `MUSIC_PAUSE`, `MUSIC_RESUME`, `MUSIC_VOLUME`, `MUSIC_SHUFFLE`, `MUSIC_CLEARQUEUE` (defaulting to `moderator`).

### FR-2.2: Voice Channel Solo Bypass Check
- If exactly one human (non-bot) user is present in the bot's voice channel, and that user issued a playback command, they MUST be allowed to control playback.
- If multiple human users are present, permissions MUST resolve normally using the standard permission resolution pipeline.
- The voice-channel solo bypass check MUST reside entirely within the Music module permission wrapper before querying the permission engine. The universal authorization engine (`PermissionResolver`) MUST remain generic and free of feature-specific exceptions.

---

## 3. Template System Safety Layer & Expansion Rules

### FR-3.1: Data-Driven JSON Templates
- Future and existing templates (Gaming, Community, Creator, Streamer, Esports, Anime, Study/Academic, Business/Professional, Support Server, Clan/Guild, Minimal Starter) MUST be data-driven.
- No server template configurations may be hardcoded in Python files. All definitions MUST be loaded from JSON template schema files, enabling community-created template uploads in future releases.

### FR-3.2: Customization & Deployment Preview Stage
- Users MUST be presented with an interactive preview listing the proposed layout of the template prior to execution.
- The deployment summary MUST show:
  - Categories to create
  - Text channels to create
  - Voice channels to create
  - Roles to create
  - Existing resources that will be skipped (no duplicate creation allowed)
- Deployment MUST NOT execute immediately upon pressing "Apply" or selecting a template; it requires explicit user confirmation via a "Confirm and Deploy" action.

---

## 4. Diagnostics ZIP Hardening

### FR-4.1: Downloadable ZIP Payload
- The diagnostics package MUST export a downloadable ZIP archive containing system state and logs rather than rendering plain text.

### SR-4.2: Automated Redaction Hardening
- The generated archive MUST NEVER contain:
  - Discord bot token
  - OAuth secrets / client secrets
  - Session cookies
  - Dashboard API tokens
  - Password hashes
  - Encrypted secret blobs
  - `.env` files or secret variables
- An automated redaction audit test MUST be executed to verify that no known secret patterns are present inside the generated ZIP archive.

---

## 5. AutoMod Validation Required Before Release

### SR-5.1: Live Verification Release Gate
- The AutoMod functionality cannot be marked as functional or approved for release until live verification is successfully completed on a staging guild.
- The release checklist blocker list MUST require passing tests for:
  - **Link Blocking:** Detect HTTP, HTTPS, protocol-less, and markdown links.
  - **Invite Blocking:** Detect Discord invite structures (discord.gg, discord.com/invite).
  - **Whitelist Bypass:** Ensure configured whitelisted domains and invite codes are allowed.
  - **Moderator Bypass:** Verify moderators bypass link and invite restrictions.
  - **Administrator Bypass:** Verify administrators bypass restrictions.
  - **Owner Bypass:** Verify the guild owner bypasses restrictions.

---

## 6. Guild Config Persistence Audit

### SR-6.1: Config Persistence Gating
- The permission configurations (`command_permissions`, `permission_roles`) and music configurations (`music_settings`) MUST only be updated and saved using the existing guild configuration persistence path (`utils.save_config`) under thread-safe file locks.
- An automated regression test MUST verify that loading, editing, saving, and reloading configurations results in zero data loss or structural schema corruption.
