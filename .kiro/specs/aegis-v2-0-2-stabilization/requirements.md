# Requirements Document

## Introduction

This specification defines **Aegis Suite V2.0.2 — Stabilization Patch**. It is a small, low-risk maintenance release whose sole purpose is to **lock in correctness fixes that already landed in the working tree** and to **close a short list of remaining low-severity stabilization residuals**. It introduces no features and no new architecture.

### Scope assumption (read first)

There is no separate enumerated "V2.0.2 plan" document in the repository; this spec was assembled from the outcome of the prior V2.0 review and the subsequent code audits. Crucially, a re-review of the current `K:\Aegis` code found that several items previously called out are **already remediated**:

- `aegis/config/loader.py` `ConfigStore.save()` already uses the V2.0-specified **shallow top-level overlay** (`merged_data.update(model_data)`), and `tests/test_config_preservation.py` already covers unmodeled-key preservation, nested extra-field retention, atomic-write-failure integrity, and dict-field delete/clear semantics.
- `aegis/db/maintenance.py` `rotate_backups()` already sorts by filesystem modification time (the earlier lexical-sort defect is fixed) — **but it has no regression test**.
- `aegis/db/maintenance.py` `run_migrations()` already resolves the Alembic config and `script_location` via `sys._MEIPASS` for the frozen executable.

Therefore V2.0.2 does **not** re-implement those fixes. It (a) adds the missing regression tests so they cannot silently regress, and (b) closes three remaining residuals. **If the approving party intended a different V2.0.2 scope, stop and reconcile before implementation.**

### What V2.0.2 covers

1. **Regression lock for backup rotation ordering** — add the missing test for the mtime-based `rotate_backups()` so the lexical-sort defect cannot return.
2. **Single-instance guard cleanup on hard exit** — when a second shutdown signal forces an immediate `os._exit`, the single-instance lock/URL files are currently left on disk, which can make the next launch falsely believe another instance is running.
3. **Dead-code removal** — remove the unused `AppCore._bot_task_placeholder` left over from an earlier phase.
4. **Verification gate** — confirm (and document, not change) that the no-downgrade guard `is_db_ahead()` behaves acceptably for the linear single-head migration model, and that the already-landed config/rotation/Alembic fixes hold.

This release deliberately excludes anything that changes data formats, authorization behavior, the bot, the dashboard, or the build/installer beyond the items above.

## Glossary

- **Aegis_Suite**: The single-process application comprising the Discord bot, the FastAPI dashboard, and the recovery/wizard web surface.
- **ConfigStore**: The configuration accessor in `aegis/config/loader.py`.
- **Shallow_Overlay**: The config merge contract in which modeled top-level keys replace their on-disk counterparts wholesale and unmodeled top-level keys are preserved verbatim (no recursive descent into modeled dict values).
- **Backup_Rotation**: The `rotate_backups(paths, keep)` function in `aegis/db/maintenance.py` that retains the newest `keep` database backups and deletes older ones.
- **DB_Backup**: A database backup file named `aegis_<rev>_<timestamp>.db` under `backups/db`.
- **Single_Instance_Guard**: `SingleInstanceGuard` in `aegis/core/single_instance.py`, which acquires a named mutex (Windows) or lock file and records the running dashboard URL.
- **Guard_Files**: The `aegis.lock` and `aegis.url` files the Single_Instance_Guard writes under the data directory root.
- **Hard_Exit**: The `os._exit(0)` path taken in `AppCore.request_shutdown()` when a second shutdown signal arrives during teardown.
- **AppCore**: The orchestrator in `aegis/core/app_core.py`.
- **No_Downgrade_Guard**: `is_db_ahead(engine, head_rev, alembic_cfg)` in `aegis/db/maintenance.py`, intended to refuse running against a database created by a newer build.
- **Migration_Engine**: `run_migrations()` in `aegis/db/maintenance.py`.
- **Baseline_Test_Suite**: The existing pytest suite under `tests/`.

## Requirements

### Requirement 1: Backup rotation ordering is regression-locked

**User Story:** As a Maintainer, I want backup rotation to always delete the oldest backups and keep the newest, so that a recovery never finds my most recent good backup has been pruned.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL retain, after Backup_Rotation with retention count `keep`, exactly the `min(N, keep)` newest DB_Backup files by modification time, where `N` is the number of DB_Backup files present before rotation.
2. WHEN DB_Backup filenames embed revision identifiers of differing lengths (for example `empty` versus a revision hash), THE Backup_Rotation SHALL still order by modification time and SHALL NOT delete a newer backup in preference to an older one.
3. THE Baseline_Test_Suite SHALL include a test that fails if Backup_Rotation is changed back to lexical-filename ordering.
4. WHEN fewer than `keep` DB_Backup files exist, THE Backup_Rotation SHALL delete nothing.

### Requirement 2: Single-instance guard is released on hard exit

**User Story:** As a Maintainer, I want a force-quit (double shutdown signal) to leave no stale lock behind, so that my next launch is not blocked by a false "another instance is already running" condition.

#### Acceptance Criteria

1. WHEN a Hard_Exit is triggered by a second shutdown signal, THE Aegis_Suite SHALL release the Single_Instance_Guard before the process terminates.
2. WHEN the Single_Instance_Guard is released during a Hard_Exit, THE Aegis_Suite SHALL remove the Guard_Files it owns.
3. WHILE releasing the Single_Instance_Guard during a Hard_Exit, IF the release operation raises, THEN THE Aegis_Suite SHALL still terminate the process and SHALL NOT hang.
4. THE Aegis_Suite SHALL NOT change the normal (single-signal) graceful shutdown teardown ordering as part of this change.

### Requirement 3: Removal of dead placeholder code

**User Story:** As a maintainer of the codebase, I want leftover placeholder code removed, so that the orchestrator contains only code that is actually reachable.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL remove the unused `AppCore._bot_task_placeholder` method.
2. THE Aegis_Suite SHALL NOT remove or alter any method that is referenced by a production execution path.
3. THE Baseline_Test_Suite SHALL remain green after the removal.

### Requirement 4: Stabilization verification gate

**User Story:** As a release manager, I want the already-landed correctness fixes confirmed and the no-downgrade guard's behavior documented, so that V2.0.2 ships with explicit assurance rather than assumption.

#### Acceptance Criteria

1. THE Aegis_Suite SHALL retain the Shallow_Overlay behavior in ConfigStore, verified by the existing config preservation and merge-contract tests passing.
2. THE Migration_Engine SHALL resolve its Alembic configuration and script location from the frozen-bundle directory when running as a frozen executable, verified by inspection or test.
3. THE No_Downgrade_Guard SHALL be confirmed to return a refusal verdict when the database's current revision is unknown to the running build, and its known limitation for the linear single-head model SHALL be documented in code comments.
4. IF the No_Downgrade_Guard is found to permit running against a genuinely newer-build database without refusal, THEN the implementer SHALL report the finding and SHALL NOT expand scope to a redesign within this patch release.
5. THE full Baseline_Test_Suite plus all V2.0.2 tests SHALL pass as the release exit condition.

## Out of Scope

The following are explicitly excluded from V2.0.2:

1. Any new feature (moderation enforcement, analytics, marketplace, plugins, cloud sync, auto-update).
2. Any change to the configuration data format, the database schema, or migrations beyond the verification in Requirement 4.
3. Any change to authentication, authorization, recovery, or wizard behavior.
4. Any change to the dashboard, the Discord bot, or the installer/build beyond the items in Requirements 1–3.
5. Redesign of the No_Downgrade_Guard or the migration framework.
6. Decomposition of legacy modules or removal of legacy compatibility layers (deferred to V2.1+).
