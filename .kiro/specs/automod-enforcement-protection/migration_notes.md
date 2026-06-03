# AutoMod Enforcement Migration Notes — Link & Discord Invite Protection

## 1. Schema Additions

Three new fields are introduced into the `automod_settings` object within the JSON configuration (`config.json`):
- `block_invites` (boolean, defaults to `false`)
- `whitelisted_domains` (array of strings, defaults to `[]`)
- `whitelisted_invites` (array of strings, defaults to `[]`)

---

## 2. Backward Compatibility

To ensure seamless upgrades for existing installations:
1. **Default Handlers**: The Pydantic model parses legacy configurations lacking the new fields and assigns safe defaults (`false` and `[]`).
2. **First Save Backfill**: On the first subsequent dashboard settings save or boot configuration cycle, the system automatically writes these three keys to the JSON database file without corrupting other settings.
3. **No Schema Migration Required**: The SQLite database baseline schema maps to JSON settings config, so no database-level Alembic migrations are required.

---

## 3. Rollback Strategy

In case of a rollback:
1. **Reverting Code**: Revert the codebase to the baseline commit (v2.0.2).
2. **Schema Behavior**: The baseline Pydantic model will ignore `block_invites`, `whitelisted_domains`, and `whitelisted_invites` during validation due to standard model mapping constraints.
3. **Data Retention**: Under our shallow overlay merge policy in `ConfigStore.save()`, the newly added keys will persist in `config.json` without causing errors, allowing re-upgrades to occur later.
