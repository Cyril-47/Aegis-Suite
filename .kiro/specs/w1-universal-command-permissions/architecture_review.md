# Aegis Suite — V2.1 Architecture Review (Revised)

This document presents the revised V2.1 Architecture Review for Aegis Suite, incorporating updated architectural decisions.

---

## 1. System Components & Flow

The Aegis Suite V2.1 permission and template customization architecture consists of the following components:

```
                            [ User Browser / UI ]
                                      │
                                      ▼
                        [ Template Preview Component ]
                                      │
                                      ▼
                       [ Template Customization Layer ]
                                      │
                                      ▼
                            [ Command Execution ]
                                      │
                     ┌────────────────┴────────────────┐
                     ▼                                 ▼
             [ Music Command ]                 [ General Command ]
                     │                                 │
                     ▼                                 │
           [ Music Permission Layer ]                  │
                     │                                 │
                     ▼                                 │
            [ Solo VC Check ]                          │
                     │                                 │
                     └────────────────┬────────────────┘
                                      │
                                      ▼
                           [ PermissionResolver ]
                                      │
                      ┌───────────────┴───────────────┐
                      ▼                               ▼
               [ Bot Commands ]               [ Web Dashboard ]
              (Registry constants)            (Persistence path)
```

---

## 2. Technical Decisions & Architectural Layout

### 2.1 Centralized Command Registry
All command names are standardized as uppercase string constants in a central registry (`CommandRegistry`), preventing typos and keeping web-to-bot dashboard mappings stable:
- Example constants: `MUSIC_PLAY`, `MUSIC_SKIP`, `MUSIC_STOP`, `GIVEAWAY_CREATE`, `TICKET_CLOSE`.
- All permission evaluations, config serialization, and API communication MUST use these constants.

### 2.2 Decoupled PermissionResolver Scope
The `PermissionResolver` is a generic, feature-agnostic authorization engine.
- It evaluates roles, owner, administrator, and configured permission rules only.
- It contains NO feature-specific business logic (such as checking voice channels or active music players).
- **Music-Specific Bypasses:** The Voice Channel Solo Bypass lives entirely in the Music module layer. When a playback control command is invoked:
  1. The Music module checks if the user is the sole human in the voice channel. If yes, it bypasses the permission engine.
  2. If multiple humans are in the voice channel, the Music module calls the generic `PermissionResolver` to evaluate configured rules.

### 2.3 Template System Safety Layer & Expansion Rules
- **Data-driven Templates:** All templates (Gaming, Community, Creator, Streamer, Esports, Anime, Study/Academic, Business/Professional, Support Server, Clan/Guild, Minimal Starter) are data-driven and loaded from JSON definitions instead of Python files.
- **Safety Preview Wizard:** Prior to template deployment, the user dashboard MUST fetch and render an interactive preview showing:
  - Categories to create
  - Text channels to create
  - Voice channels to create
  - Roles to create
  - Existing resources that will be skipped (no duplicate creation)
- **Confirmation Gate:** Deployment requires explicit confirmation. No template will apply immediately upon pressing "Apply" without explicit approval.

### 2.4 Diagnostics ZIP Hardening & Auditing
- The diagnostics package generates a downloadable `.zip` file containing logs and system metadata.
- **Secret Redaction:** The exporter actively redacts bot client tokens, OAuth secrets, session cookies, dashboard tokens, password hashes, and `.env` files.
- **Verification Gate:** An automated audit scanner test extracts and scans the generated zip archive, failing if any unredacted secret patterns are detected.

### 2.5 AutoMod Validation Required Before Release
- AutoMod link-blocking and invite-blocking filters are marked as **Validation Required**.
- Release cannot proceed until live validation checks succeed on a staging environment. The release checklist MUST contain:
  1. Link blocking test (HTTP, HTTPS, protocol-less, markdown).
  2. Invite blocking test (Discord invites).
  3. Whitelist test (allowing whitelisted domains/invites).
  4. Moderator bypass test.
  5. Administrator bypass test.
  6. Owner bypass test.

### 2.6 Cloud Mode UI Gating
- Cloud hosting features are hidden behind the top-level flag `flags.ENABLE_CLOUD_MODE = False`.
- Cloud infrastructure code (including abstractions, schemas, database tenant schemas) is preserved in the backend to ensure backward and forward compatibility.

### 2.7 Guild Config Persistence Audit
- The configuration blocks `command_permissions`, `permission_roles`, and `music_settings` must ONLY be mutated and written through the existing thread-safe and lock-guarded configuration path (`utils.save_config`).
- An automated regression test verifies that loading, editing, saving, and reloading configuration data results in zero data loss.
