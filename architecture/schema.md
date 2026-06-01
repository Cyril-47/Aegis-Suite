# 🏛️ Architecture Specification: Guild Configuration Domain

This document defines the canonical database schemas, ownership, and lifecycle rules for the **Guild Configuration** domain in the Aegis bot system. This establishes the structural foundation before migrating legacy JSON configurations to SQLite.

---

## 1. Domain Properties & Governance

The Guild Configuration domain governs how individual Discord guilds customize bot behaviors (Welcome embeds, AutoMod rules, and Ticket setups).

| Property | Rule / Behavior |
| --- | --- |
| **Owner** | Guild (Tenant Context) |
| **Mutable By** | Guild administrators (via Dashboard with tenant tokens or via Discord slash commands) |
| **Lifetime** | Permanent (retained until the guild is unlinked with `purge=True` or the bot leaves the server) |
| **Cacheability** | High (read-heavy, write-light; should be cached in-memory by the bot on event handlers to avoid SQL queries on every text message) |
| **Reconciliation Strategy** | If Discord API configuration fails (e.g., cannot find log channel), the DB remains authoritative, but a warning flag is updated in-memory and logged to the audit log. |

---

## 2. Table Definitions

### Table: `guilds`
Main register of connected Discord servers. This acts as the parent record for all guild-scoped configuration and settings tables.

| Field Name | Data Type | Constraints | Description |
| --- | --- | --- | --- |
| `guild_id` | VARCHAR | PRIMARY KEY | Snowflake ID of the Discord server (e.g., `"1155366164634013727"`) |
| `guild_name` | VARCHAR | NOT NULL | Readable name of the guild |
| `joined_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Date and time when the bot joined the guild |
| `is_active` | BOOLEAN | DEFAULT 1 | Activation state. Set to `0` if the bot is kicked or server link is revoked. |

```sql
CREATE TABLE guilds (
    guild_id TEXT PRIMARY KEY,
    guild_name TEXT NOT NULL,
    joined_at TEXT DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now', 'utc')),
    is_active INTEGER DEFAULT 1
);
```

---

### Table: `welcome_configs`
Configures greeting behaviors when new members join the server.

| Field Name | Data Type | Constraints | Description |
| --- | --- | --- | --- |
| `guild_id` | VARCHAR | PRIMARY KEY, FK -> `guilds(guild_id)` ON DELETE CASCADE | Scoped guild ID |
| `enabled` | BOOLEAN | DEFAULT 1 | Whether welcome message triggers are active |
| `channel_id` | VARCHAR | NULLABLE | Snowflake ID of text channel where welcomes are sent |
| `channel_name` | VARCHAR | NOT NULL | Fallback name used during auto-creation/matching |
| `embed_title` | VARCHAR | NOT NULL | Header template string (supports `{user}` variable) |
| `embed_description` | TEXT | NOT NULL | Body template string (supports `{user}` variable) |
| `embed_color` | VARCHAR | NOT NULL (Hex Code) | Border color of welcome message cards |
| `auto_assign_roles` | TEXT (JSON) | DEFAULT `'[]'` | JSON list of role snowflake IDs to auto-assign |

```sql
CREATE TABLE welcome_configs (
    guild_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    channel_id TEXT,
    channel_name TEXT NOT NULL,
    embed_title TEXT NOT NULL,
    embed_description TEXT NOT NULL,
    embed_color TEXT NOT NULL,
    auto_assign_roles TEXT DEFAULT '[]',
    FOREIGN KEY(guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);
```

---

### Table: `automod_configs`
Configures spam, link, and word filters for real-time chat moderation.

| Field Name | Data Type | Constraints | Description |
| --- | --- | --- | --- |
| `guild_id` | VARCHAR | PRIMARY KEY, FK -> `guilds(guild_id)` ON DELETE CASCADE | Scoped guild ID |
| `enabled` | BOOLEAN | DEFAULT 1 | Whether automod event filters are active |
| `block_profanity` | BOOLEAN | DEFAULT 1 | Blocks words found in the profanity word list |
| `block_links` | BOOLEAN | DEFAULT 0 | Automatically deletes invite and external URLs |
| `max_mentions` | INTEGER | DEFAULT 5 | Maximum allowed user mentions in a single message |
| `log_channel_id` | VARCHAR | NULLABLE | Target channel for moderation incident logs |
| `log_channel_name` | VARCHAR | NOT NULL | Name of moderation logging channel |
| `profanity_words` | TEXT (JSON) | DEFAULT `'[]'` | JSON list of custom restricted terms |

```sql
CREATE TABLE automod_configs (
    guild_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    block_profanity INTEGER DEFAULT 1,
    block_links INTEGER DEFAULT 0,
    max_mentions INTEGER DEFAULT 5,
    log_channel_id TEXT,
    log_channel_name TEXT NOT NULL,
    profanity_words TEXT DEFAULT '[]',
    FOREIGN KEY(guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);
```

---

### Table: `ticket_configs`
Configures interactive support channel panels and category targets.

| Field Name | Data Type | Constraints | Description |
| --- | --- | --- | --- |
| `guild_id` | VARCHAR | PRIMARY KEY, FK -> `guilds(guild_id)` ON DELETE CASCADE | Scoped guild ID |
| `enabled` | BOOLEAN | DEFAULT 1 | Whether support ticket panels can deploy/trigger |
| `category_name` | VARCHAR | NOT NULL | Category name under which tickets are opened |
| `staff_role_name` | VARCHAR | NOT NULL | Discord role permitted to view and close tickets |
| `ticket_channel_id` | VARCHAR | NULLABLE | Channel where ticket panels are deployed |
| `panel_message_id` | VARCHAR | NULLABLE | Message snowflake of active interactive panels |

```sql
CREATE TABLE ticket_configs (
    guild_id TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 1,
    category_name TEXT NOT NULL,
    staff_role_name TEXT NOT NULL,
    ticket_channel_id TEXT,
    panel_message_id TEXT,
    FOREIGN KEY(guild_id) REFERENCES guilds(guild_id) ON DELETE CASCADE
);
```
