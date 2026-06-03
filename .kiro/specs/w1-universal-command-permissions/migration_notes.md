# W1 Migration Notes — Universal Command Permission Framework

## 1. Interaction with Current Configurations

The universal permission system stores authorization parameters directly inside the existing `guild_configs` block of the JSON configuration storage file (`config.json`). 

To prevent data loss and ensure a smooth migration, the framework respects the following rules:
1. **Shallow Top-Level Overlays**: Updates to command permissions are written under `utils.config_lock` using a shallow top-level dictionary merge, preserving unrelated configuration blocks (like automod settings or leveling rules) intact.
2. **Schema Separation**: The permission configurations reside under the newly added keys `command_permissions` and `permission_roles`. These do not overlap with existing features.

---

## 2. Backward Compatibility

For existing installations upgrade to W1, compatibility is maintained via **schema defaults** and **legacy fallbacks**:

### 2.1 Configuration Backfilling (Pydantic Defaults)
When loading an old `config.json` file that lacks the permission fields, Pydantic's model-level default factories dynamically populate:
- `command_permissions` with an empty dictionary (`{}`).
- `permission_roles` with empty admin/moderator IDs (`None`).

### 2.2 Default Authorization Resolution (Fallback Policy)
If a guild has not configured permissions yet, the engine resolves commands using these default mappings:
- **Destructive Commands** (`clear`, `stop`, `reroll`, `delete`, `restore`, `leveling_reset`): Requires `admin` privileges (or Owner/Discord Admin bypass).
- **All Other Commands**: Permitted for `everyone` by default, mimicking standard public configuration.

---

## 3. Rollback Strategy

If a critical blocker is discovered in production, the system can be rolled back safely without configuration corruption:

### 3.1 Codebase Rollback
1. Revert the repository to the stable baseline tag (prior to W1 integration).
2. The legacy code loads `config.json` ignoring the extra `command_permissions` and `permission_roles` keys (due to Pydantic's default behavior ignoring extra fields or extra field allowance depending on the version's Pydantic config).
3. On the next save cycle, these unmodeled permission keys will either be preserved verbatim (due to our V2.0.2 shallow overlay saving logic) or ignored, depending on the baseline configuration structure.

### 3.2 Configuration Cleanup (Optional)
If a complete purge of the permission configuration is desired, the following Python snippet can be executed to remove the keys safely under lock:
```python
import utils

async def purge_permission_keys():
    async with utils.config_lock:
        config = utils.load_config()
        for guild_id, guild_conf in config.get("guild_configs", {}).items():
            guild_conf.pop("command_permissions", None)
            guild_conf.pop("permission_roles", None)
        utils.save_config(config)
```
This script runs in under 10ms and completely clears the schema additions without affecting welcome, ticketing, or leveling settings.
