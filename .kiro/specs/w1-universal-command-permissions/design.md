# Aegis Suite V2.1 — Technical Design Document

This document defines the software design, data models, class contracts, and API routes for Aegis Suite V2.1.

---

## 1. Centralized Command Registry (`aegis/core/permissions/registry.py`)

A centralized registry class provides string constants to prevent typos and ensure dashboard mappings remain stable when commands are renamed.

```python
class CommandRegistry:
    # Music Module
    MUSIC_PLAY = "MUSIC_PLAY"
    MUSIC_PAUSE = "MUSIC_PAUSE"
    MUSIC_RESUME = "MUSIC_RESUME"
    MUSIC_SKIP = "MUSIC_SKIP"
    MUSIC_STOP = "MUSIC_STOP"
    MUSIC_QUEUE = "MUSIC_QUEUE"
    MUSIC_VOLUME = "MUSIC_VOLUME"
    MUSIC_NOWPLAYING = "MUSIC_NOWPLAYING"
    MUSIC_SHUFFLE = "MUSIC_SHUFFLE"
    MUSIC_CLEARQUEUE = "MUSIC_CLEARQUEUE"
    MUSIC_LYRICS = "MUSIC_LYRICS"

    # Giveaway Module
    GIVEAWAY_CREATE = "GIVEAWAY_CREATE"
    GIVEAWAY_REROLL = "GIVEAWAY_REROLL"
    GIVEAWAY_STOP = "GIVEAWAY_STOP"

    # Welcomer Module
    WELCOME_SET = "WELCOME_SET"

    # Tickets Module
    TICKET_PANEL = "TICKET_PANEL"
    TICKET_CLOSE = "TICKET_CLOSE"

    # Leveling Module
    LEVEL_RANK = "LEVEL_RANK"
    LEVEL_LEADERBOARD = "LEVEL_LEADERBOARD"
    LEVEL_SET_ROLE = "LEVEL_SET_ROLE"
    LEVEL_RESET = "LEVEL_RESET"

    # System/Admin Modules
    LINK_DASHBOARD = "LINK_DASHBOARD"
    UNLINK = "UNLINK"
    AUDIT_SERVER = "AUDIT_SERVER"
    OPTIMIZE_SERVER = "OPTIMIZE_SERVER"

    @classmethod
    def get_all_commands(cls) -> list[str]:
        return [
            v for k, v in cls.__dict__.items() 
            if not k.startswith("__") and isinstance(v, str)
        ]
```

---

## 2. Generic Permission Resolver (`aegis/core/permissions/resolver.py`)

The `PermissionResolver` is a generic authorization engine. It evaluates only roles, owner, administrator, and configured permission rules. It does not contain any feature-specific business logic (such as voice channel counts).

```python
import utils
from typing import List, Dict, Any

class PermissionResolver:
    @staticmethod
    def is_destructive(command_name: str) -> bool:
        destructive = {
            "UNLINK", "OPTIMIZE_SERVER", "MUSIC_STOP", 
            "MUSIC_CLEARQUEUE", "LEVEL_RESET", "GIVEAWAY_STOP"
        }
        return command_name in destructive

    @staticmethod
    async def has_permission(
        guild_id: str,
        user_id: str,
        command_name: str,
        user_roles: List[str],
        is_owner: bool = False,
        has_discord_admin: bool = False
    ) -> bool:
        # 1. Guild Owner & Discord Administrator bypasses
        if is_owner or has_discord_admin:
            return True

        # 2. Retrieve thread-safe configuration cache
        config = utils.load_config()
        guild_conf = config.get("guild_configs", {}).get(str(guild_id), {})
        
        # Load permission role mappings
        roles_mapping = guild_conf.get("permission_roles", {})
        admin_role = str(roles_mapping.get("admin_role_id", ""))
        mod_role = str(roles_mapping.get("moderator_role_id", ""))
        
        user_roles_str = [str(r) for r in user_roles]
        cmd_rules = guild_conf.get("command_permissions", {})
        
        # Default fallback for unconfigured commands
        if command_name not in cmd_rules:
            if PermissionResolver.is_destructive(command_name):
                return admin_role in user_roles_str if admin_role else False
            return True

        rule = cmd_rules[command_name]
        mode = rule.get("mode", "everyone")
        
        if mode == "everyone":
            return True
        elif mode == "owner":
            return False  # Only bypassed by step 1 (Owner/Admin)
        elif mode == "admin":
            return admin_role in user_roles_str if admin_role else False
        elif mode == "moderator":
            return (mod_role in user_roles_str) or (admin_role in user_roles_str)
        elif mode == "role":
            return str(rule.get("role_id", "")) in user_roles_str
        elif mode == "roles":
            target_roles = [str(r) for r in rule.get("role_ids", [])]
            return any(r in user_roles_str for r in target_roles)
            
        return False
```

---

## 3. Decoupled Music Permissions Wrapper (`aegis/bot/music_permissions.py`)

Music-specific checks (e.g., the Voice Channel Solo Bypass) must live inside the Music module wrapper before calling `PermissionResolver`.

```python
import discord
from discord.ext import commands
from aegis.core.permissions.resolver import PermissionResolver

async def check_music_permission(ctx: commands.Context, command_name: str) -> bool:
    # 1. Guild Owner & Discord Admin bypass (fast path)
    if ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator:
        return True

    # 2. Voice Channel Solo Bypass Check
    # If the user is the only non-bot human in the voice channel, they can control playback
    voice_client = ctx.guild.voice_client
    if voice_client and voice_client.channel:
        humans = [m for m in voice_client.channel.members if not m.bot]
        if len(humans) == 1 and humans[0].id == ctx.author.id:
            return True

    # 3. Fallback to standard PermissionResolver
    user_roles = [str(role.id) for role in ctx.author.roles]
    return await PermissionResolver.has_permission(
        guild_id=str(ctx.guild.id),
        user_id=str(ctx.author.id),
        command_name=command_name,
        user_roles=user_roles
    )

def music_permission_gate(command_name: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
        allowed = await check_music_permission(ctx, command_name)
        if not allowed:
            raise commands.MissingPermissions([f"Missing permissions to run command {command_name}"])
        return True
    return commands.check(predicate)
```

---

## 4. Template System Preview & Safety Layer

Templates are loaded from external JSON files stored inside `/templates/builtin/*.json` or `/templates/*.json`.

### 4.1 Schema Representation (`templates/builtin/gaming.json`)
```json
{
  "name": "Gaming preset",
  "roles": [
    { "name": "Gamer", "color": "#FF5555", "permissions": ["send_messages", "view_channel"] }
  ],
  "categories": [
    {
      "name": "🎮 GAMING ZONE",
      "channels": [
        { "name": "general-gaming", "type": "text" },
        { "name": "Squad Room 1", "type": "voice", "user_limit": 5 }
      ]
    }
  ]
}
```

### 4.2 Web API Preview & Confirmation Endpoints
1. **GET `/api/templates/{name}/preview`**
   - Parses the target template file and returns the structure (Categories, Text Channels, Voice Channels, Roles) along with duplicate checks against the target server (e.g. `roles_to_skip`, `categories_to_skip`, `channels_to_skip`).
2. **POST `/api/guilds/{guild_id}/templates/apply`**
   - Applies the validated template customization parameters.
   - Body includes exact lists of roles, channels, and categories to create, along with the user's modifications (channel rename/exclusions).
   - This endpoint operates sequentially under thread locks and ensures that no modifications are committed without explicit client confirmation.

---

## 5. Diagnostics Redaction & Hardening

### 5.1 Redaction Pipeline
The diagnostics generator (`aegis/diagnostics/exporter.py`) collects logs, system state, and active configuration. Before generating the ZIP archive, the following variables must be scanned and replaced with `[REDACTED]`:
- Bot client token regex: `[a-zA-Z0-9_\-\.]{24,36}\.[a-zA-Z0-9_\-\.]{6}\.[a-zA-Z0-9_\-\.]{27,43}`
- Client secrets, session cookies, password hashes, and `.env` variable values.

### 5.2 Redaction Scanner Test
An automated scanner test (`tests/test_diagnostics_redaction.py`) will unpack the generated archive and inspect all textual contents (logs, redacted configs, system JSON). If any token, cookie, password hash, or unredacted token pattern is detected, the test fails.

---

## 6. Cloud Mode Future Compatibility

To preserve cloud compatibility in V2.1, all cloud abstractions, models, and databases remain intact.
- **Top-level feature flag:** `ENABLE_CLOUD_MODE = False` in `aegis/core/flags.py`.
- **UI Gating:**
  ```javascript
  if (!config.ENABLE_CLOUD_MODE) {
      document.getElementById("cloud-hosting-toggle").style.display = "none";
  }
  ```

---

## 7. Guild Config Persistence Audit

The new sections (`command_permissions`, `permission_roles`, `music_settings`) must only be written to `config.json` via the thread-safe `utils.save_config()` helper.
- **Safe Persistence Workflow:**
  ```python
  with utils.config_lock:
      config = utils.load_config()
      # Mutate the configuration object safely
      config["guild_configs"][guild_id]["command_permissions"] = updated_permissions
      utils.save_config(config)
  ```
- **Auditing Test:** An automated test verifies that configuration updates from the dashboard API merge cleanly, with reload validations showing zero data loss.
