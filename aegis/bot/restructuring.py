import logging
import discord
from typing import Optional
import aegis.core.utils as utils

logger = logging.getLogger("aegis.bot.restructuring")

def audit_guild_data(guild: discord.Guild, online_count: int = None, member_count: int = None):
    """Scans guild settings, roles, channels and computes a health/optimization score."""
    config = utils.load_config()
    
    score = 100
    checklist = []
    
    # 1. Verification level
    v_level = str(guild.verification_level)
    if guild.verification_level == discord.VerificationLevel.none:
        score -= 15
        checklist.append({
            "name": "Verification Level",
            "status": "FAIL",
            "message": "No verification level set. Anyone can join and type immediately, leaving the server vulnerable to raid bots.",
            "value": v_level
        })
    elif guild.verification_level in (discord.VerificationLevel.low, discord.VerificationLevel.medium):
        score -= 5
        checklist.append({
            "name": "Verification Level",
            "status": "WARNING",
            "message": "Low/Medium verification. Recommended to set to High (must have verified phone/email or be member for 10m).",
            "value": v_level
        })
    else:
        checklist.append({
            "name": "Verification Level",
            "status": "SUCCESS",
            "message": "Verification level is secure.",
            "value": v_level
        })

    # 2. Explicit Content Filter
    f_level = str(guild.explicit_content_filter)
    if guild.explicit_content_filter == discord.ContentFilter.disabled:
        score -= 15
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "FAIL",
            "message": "Content filter is disabled. Highly recommended to scan messages from all members to block explicit content.",
            "value": f_level
        })
    elif guild.explicit_content_filter == discord.ContentFilter.all_members:
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "SUCCESS",
            "message": "Explicit content filter scans all messages.",
            "value": f_level
        })
    else:
        score -= 5
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "WARNING",
            "message": "Content filter only scans users without roles. Recommended to scan all members.",
            "value": f_level
        })

    # 3. Log channel check
    log_cfg = utils.get_guild_automod_settings(config, guild.id)
    has_log_channel = False
    log_ch_name = ""
    if log_cfg.get("log_channel_id"):
        ch = guild.get_channel(int(log_cfg["log_channel_id"]))
        if ch:
            has_log_channel = True
            log_ch_name = ch.name
    
    if not has_log_channel:
        # Search by name
        log_name = log_cfg.get("log_channel_name", "mod-logs").lstrip("#").lower()
        for ch in guild.text_channels:
            if ch.name.lower() == log_name:
                has_log_channel = True
                log_ch_name = ch.name
                break

    if not has_log_channel:
        score -= 15
        checklist.append({
            "name": "Moderation Logs Channel",
            "status": "FAIL",
            "message": "No dedicated moderation logs channel found. Staff actions & infractions will not be recorded.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Moderation Logs Channel",
            "status": "SUCCESS",
            "message": f"Mod logs will be sent to #{log_ch_name}.",
            "value": f"#{log_ch_name}"
        })

    # 4. Welcome channel check
    welcome_cfg = utils.get_guild_welcome_settings(config, guild.id)
    has_welcome_channel = False
    welcome_ch_name = ""
    if welcome_cfg.get("channel_id"):
        ch = guild.get_channel(int(welcome_cfg["channel_id"]))
        if ch:
            has_welcome_channel = True
            welcome_ch_name = ch.name
            
    if not has_welcome_channel:
        welcome_name = welcome_cfg.get("channel_name", "welcome").lower()
        for ch in guild.text_channels:
            if ch.name.lower() == welcome_name:
                has_welcome_channel = True
                welcome_ch_name = ch.name
                break

    if not has_welcome_channel:
        score -= 10
        checklist.append({
            "name": "Welcome Channel",
            "status": "FAIL",
            "message": "No welcome channel detected. New members will not receive greeting guides.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Welcome Channel",
            "status": "SUCCESS",
            "message": f"Welcome messages will be posted in #{welcome_ch_name}.",
            "value": f"#{welcome_ch_name}"
        })

    # 5. Check @everyone permissions
    everyone_role = guild.default_role
    danger_perms = []
    if everyone_role.permissions.administrator:
        danger_perms.append("Administrator")
    if everyone_role.permissions.manage_guild:
        danger_perms.append("Manage Server")
    if everyone_role.permissions.manage_channels:
        danger_perms.append("Manage Channels")
    if everyone_role.permissions.manage_roles:
        danger_perms.append("Manage Roles")
    if everyone_role.permissions.mention_everyone:
        danger_perms.append("Mention @everyone")

    if danger_perms:
        score -= 25
        checklist.append({
            "name": "@everyone Insecure Permissions",
            "status": "FAIL",
            "message": f"Standard users (@everyone) have powerful permissions: {', '.join(danger_perms)}. This is a severe safety risk!",
            "value": "Vulnerable"
        })
    else:
        checklist.append({
            "name": "@everyone Permissions",
            "status": "SUCCESS",
            "message": "@everyone permissions are safe and restricted.",
            "value": "Secure"
        })

    # 6. Insecure Roles / Admin Bloat
    admin_bloat = False
    insecure_roles = []
    for role in guild.roles:
        if role.is_default():
            continue
        if role.permissions.administrator:
            member_percentage = (len(role.members) / max(1, guild.member_count)) * 100
            if member_percentage > 20 and guild.member_count > 5:
                admin_bloat = True
                insecure_roles.append(f"{role.name} ({member_percentage:.1f}% of users have Admin)")

    if admin_bloat:
        score -= 10
        checklist.append({
            "name": "Administrator Overload",
            "status": "WARNING",
            "message": f"Too many users have Administrator access via these roles: {', '.join(insecure_roles)}.",
            "value": "Over-privileged"
        })
    else:
        checklist.append({
            "name": "Administrator Overload",
            "status": "SUCCESS",
            "message": "Admin privileges are limited to a small, secure subset of users.",
            "value": "Healthy"
        })

    # 7. Bot Commands Channel Check
    has_bot_cmd = False
    for ch in guild.text_channels:
        if "bot" in ch.name.lower() and ("command" in ch.name.lower() or "cmd" in ch.name.lower() or "play" in ch.name.lower()):
            has_bot_cmd = True
            break
            
    if not has_bot_cmd:
        score -= 5
        checklist.append({
            "name": "Bot Commands Channel",
            "status": "WARNING",
            "message": "No channel dedicated to bot commands found. Members might clutter general chat with bot commands.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Bot Commands Channel",
            "status": "SUCCESS",
            "message": "A bot commands channel is available to contain bot spam.",
            "value": "Available"
        })

    # 8. AutoMod Bot Activation
    if not utils.get_guild_automod_settings(config, guild.id).get("enabled", False):
        score -= 10
        checklist.append({
            "name": "AutoMod Configuration",
            "status": "WARNING",
            "message": "Auto-moderation is disabled in the bot dashboard settings.",
            "value": "Disabled"
        })
    else:
        checklist.append({
            "name": "AutoMod Configuration",
            "status": "SUCCESS",
            "message": "Auto-moderation filters are active.",
            "value": "Enabled"
        })

    score = max(0, score)

    # Compile server statistics
    text_count = len(guild.text_channels)
    voice_count = len(guild.voice_channels)
    category_count = len(guild.categories)
    role_count = len(guild.roles)
    
    if online_count is None:
        online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
    if member_count is None:
        member_count = guild.member_count
    
    return {
        "score": score,
        "checklist": checklist,
        "guild_info": {
            "name": guild.name,
            "id": str(guild.id),
            "member_count": member_count,
            "online_count": online_count if online_count > 0 else 1,
            "owner": str(guild.owner),
            "owner_id": str(guild.owner_id) if guild.owner_id else "Unknown",
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "boost_tier": guild.premium_tier,
            "boost_count": guild.premium_subscription_count,
            "verification_level": str(guild.verification_level),
            "explicit_filter": str(guild.explicit_content_filter),
            "text_channels": text_count,
            "voice_channels": voice_count,
            "categories": category_count,
            "roles": role_count
        }
    }

async def optimize_guild_structure(guild: discord.Guild, preset: str, handling: str):
    """Executes preset layouts, configures roles, sets permissions."""
    logger.info(f"Starting server optimization for '{guild.name}' using preset '{preset}' (handling: {handling})...")
    
    # 1. Create Roles
    roles_to_create = {
        "Server Admin": {"permissions": discord.Permissions(administrator=True), "color": discord.Color.teal()},
        "Moderator": {"permissions": discord.Permissions(
            kick_members=True,
            ban_members=True,
            manage_messages=True,
            manage_nicknames=True,
            mute_members=True,
            deafen_members=True,
            move_members=True,
            read_message_history=True,
            view_audit_log=True,
            view_channel=True,
            send_messages=True
        ), "color": discord.Color.blue()},
        "Verified Member": {"permissions": discord.Permissions(
            send_messages=True,
            read_message_history=True,
            view_channel=True,
            connect=True,
            speak=True
        ), "color": discord.Color.green()}
    }

    created_roles = {}
    for role_name, data in roles_to_create.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=data["permissions"],
                    color=data["color"],
                    hoist=True,
                    reason="Server Optimizer Setup"
                )
                logger.info(f"Created role '{role_name}'")
            except Exception as e:
                logger.error(f"Failed to create role '{role_name}': {e}")
        created_roles[role_name] = role

    # Set up restriction for @everyone
    try:
        everyone_role = guild.default_role
        everyone_perms = everyone_role.permissions
        everyone_perms.update(
            administrator=False,
            manage_guild=False,
            manage_channels=False,
            manage_roles=False,
            mention_everyone=False
        )
        await everyone_role.edit(permissions=everyone_perms, reason="Secure default permissions")
        logger.info("Restricted dangerous @everyone default permissions.")
    except Exception as e:
        logger.error(f"Failed to edit @everyone role: {e}")

    # 2. Handle existing channels
    if handling == "archive":
        logger.info("Archiving existing channels...")
        archive_category = discord.utils.get(guild.categories, name="📦 ARCHIVED CHANNELS")
        if not archive_category:
            try:
                admin_role = created_roles.get("Server Admin")
                mod_role = created_roles.get("Moderator")
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                }
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
                    
                archive_category = await guild.create_category(
                    name="📦 ARCHIVED CHANNELS",
                    overwrites=overwrites,
                    reason="Archive existing layout"
                )
                logger.info("Created '📦 ARCHIVED CHANNELS' category.")
            except Exception as e:
                logger.error(f"Failed to create archive category: {e}")

        if archive_category:
            for channel in list(guild.channels):
                if channel.category == archive_category or channel == archive_category:
                    continue
                if isinstance(channel, discord.CategoryChannel):
                    continue
                try:
                    await channel.edit(category=archive_category, reason="Archiving old structure")
                    logger.info(f"Archived channel #{channel.name}")
                except Exception as e:
                    logger.warning(f"Could not archive channel #{channel.name}: {e}")

            # Clean up old empty categories
            for category in list(guild.categories):
                if category == archive_category:
                    continue
                if len(category.channels) == 0:
                    try:
                        await category.delete(reason="Deleting empty category after archiving channels")
                        logger.info(f"Deleted empty category: {category.name}")
                    except Exception as e:
                        logger.warning(f"Could not delete empty category {category.name}: {e}")

    elif handling == "delete":
        logger.info("Deleting existing categories and channels...")
        for channel in list(guild.channels):
            try:
                await channel.delete(reason="Server Optimizer layout clean")
                logger.info(f"Deleted channel/category: {channel.name}")
            except Exception as e:
                logger.warning(f"Could not delete channel {channel.name}: {e}")

    # 3. Create Preset layout
    presets = {
        "gaming": [
            {
                "category": "🏆 INFORMATION",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-info", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 TEXT CHANNELS",
                "channels": [
                    {"name": "general", "type": "text", "readonly": False},
                    {"name": "gaming-lobby", "type": "text", "readonly": False},
                    {"name": "clips-and-highlights", "type": "text", "readonly": False},
                    {"name": "memes", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "General Voice", "type": "voice"},
                    {"name": "Squad Room 1", "type": "voice"},
                    {"name": "Squad Room 2", "type": "voice"},
                    {"name": "Chill Lounge", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ STAFF ONLY",
                "channels": [
                    {"name": "staff-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ],
        "community": [
            {
                "category": "📢 WELCOME & INFO",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-roles", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 DISCUSSION",
                "channels": [
                    {"name": "general-chat", "type": "text", "readonly": False},
                    {"name": "introductions", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🎭 INTERESTS",
                "channels": [
                    {"name": "hobbies", "type": "text", "readonly": False},
                    {"name": "media-and-art", "type": "text", "readonly": False},
                    {"name": "memes", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "General Lounge", "type": "voice"},
                    {"name": "Gaming", "type": "voice"},
                    {"name": "Music Room", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ MODERATION",
                "channels": [
                    {"name": "mod-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ],
        "developer": [
            {
                "category": "📚 INFO & RULES",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-resources", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 TECH DISCUSSION",
                "channels": [
                    {"name": "general-dev", "type": "text", "readonly": False},
                    {"name": "questions-and-help", "type": "text", "readonly": False},
                    {"name": "resources", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "💻 PROJECT HUB",
                "channels": [
                    {"name": "showcase", "type": "text", "readonly": False},
                    {"name": "ideas-and-feedback", "type": "text", "readonly": False},
                    {"name": "github-feed", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 COLLABORATION",
                "channels": [
                    {"name": "Dev Desk 1", "type": "voice"},
                    {"name": "Dev Desk 2", "type": "voice"},
                    {"name": "Standup Room", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ STAFF ONLY",
                "channels": [
                    {"name": "staff-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ]
    }

    selected_preset = presets.get(preset.lower(), presets["community"])
    welcome_channel_created = None
    log_channel_created = None

    admin_role = created_roles.get("Server Admin")
    mod_role = created_roles.get("Moderator")

    for cat_data in selected_preset:
        cat_name = cat_data["category"]
        
        cat_overwrites = {}
        if cat_name.startswith("🛡️"):
            cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            if admin_role:
                cat_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
            if mod_role:
                cat_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)

        try:
            category = await guild.create_category(
                name=cat_name,
                overwrites=cat_overwrites,
                reason="Optimization Preset Category Setup"
            )
            logger.info(f"Created category '{cat_name}'")
        except Exception as e:
            logger.error(f"Failed to create category '{cat_name}': {e}")
            continue

        for chan_data in cat_data["channels"]:
            chan_name = chan_data["name"]
            chan_type = chan_data["type"]
            
            chan_overwrites = {}
            if chan_data.get("readonly", False):
                chan_overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False, add_reactions=True)
                if admin_role:
                    chan_overwrites[admin_role] = discord.PermissionOverwrite(send_messages=True)
                if mod_role:
                    chan_overwrites[mod_role] = discord.PermissionOverwrite(send_messages=True)
            elif chan_data.get("staff_only", False):
                chan_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                if admin_role:
                    chan_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                if mod_role:
                    chan_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)

            try:
                if chan_type == "text":
                    channel = await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        reason="Optimization Preset Channel Setup"
                    )
                    logger.info(f"Created text channel #{chan_name} inside '{cat_name}'")
                    
                    if chan_name == "welcome":
                        welcome_channel_created = channel
                    elif chan_name == "mod-logs":
                        log_channel_created = channel
                else:
                    channel = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        reason="Optimization Preset Channel Setup"
                    )
                    logger.info(f"Created voice channel '{chan_name}' inside '{cat_name}'")
            except Exception as e:
                logger.error(f"Failed to create channel '{chan_name}': {e}")

    guild_conf = utils.get_guild_config(str(guild.id))
    if welcome_channel_created:
        guild_conf["welcome_settings"]["channel_id"] = str(welcome_channel_created.id)
        guild_conf["welcome_settings"]["channel_name"] = str(welcome_channel_created.name)
    if log_channel_created:
        guild_conf["automod_settings"]["log_channel_id"] = str(log_channel_created.id)
        guild_conf["automod_settings"]["log_channel_name"] = str(log_channel_created.name)
    utils.save_guild_config(str(guild.id), guild_conf)

    logger.info(f"Server optimization complete for guild '{guild.name}'. preset={preset}")
    return True

def backup_guild_layout(guild: discord.Guild):
    """Generates a JSON-compatible layout of the guild structure (categories, channels, roles, overwrites)."""
    backup_data = {
        "name": guild.name,
        "verification_level": str(guild.verification_level),
        "explicit_content_filter": str(guild.explicit_content_filter),
        "roles": [],
        "categories": [],
        "uncategorized_channels": []
    }
    
    for r in guild.roles:
        if r.is_default() or r.managed:
            continue
        backup_data["roles"].append({
            "name": r.name,
            "color": r.color.value,
            "hoist": r.hoist,
            "permissions": r.permissions.value,
            "position": r.position
        })
        
    def serialize_overwrites(channel):
        serialized = []
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Role):
                target_type = "role"
                target_name = target.name
            else:
                target_type = "member"
                target_name = target.name
            
            allow, deny = overwrite.pair()
            serialized.append({
                "target_type": target_type,
                "target_name": target_name,
                "target_id": target.id,
                "allow": allow.value,
                "deny": deny.value
            })
        return serialized
        
    for cat in guild.categories:
        cat_data = {
            "name": cat.name,
            "position": cat.position,
            "overwrites": serialize_overwrites(cat),
            "channels": []
        }
        
        for ch in cat.channels:
            chan_data = {
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "overwrites": serialize_overwrites(ch)
            }
            cat_data["channels"].append(chan_data)
            
        backup_data["categories"].append(cat_data)
        
    for ch in guild.channels:
        if ch.category is None and not isinstance(ch, discord.CategoryChannel):
            backup_data["uncategorized_channels"].append({
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "overwrites": serialize_overwrites(ch)
            })
            
    return backup_data

active_deployments = set()

def generate_template_preview(guild: discord.Guild, template_data: dict, handling: str = "keep") -> dict:
    roles_to_create = []
    roles_to_skip = []
    categories_to_create = []
    categories_to_skip = []
    channels_to_create = []
    channels_to_skip = []
    
    guild_role_names = {r.name.lower() for r in guild.roles}
    for r_data in template_data.get("roles", []):
        r_name = r_data.get("name")
        if r_name.lower() in guild_role_names:
            roles_to_skip.append(r_name)
        else:
            roles_to_create.append(r_name)
            
    guild_channels = {(ch.name.lower(), "text" if isinstance(ch, discord.TextChannel) else "voice" if isinstance(ch, discord.VoiceChannel) else "category") for ch in guild.channels}
    
    for cat_data in template_data.get("categories", []):
        cat_name = cat_data.get("name")
        if (cat_name.lower(), "category") in guild_channels:
            categories_to_skip.append(cat_name)
        else:
            categories_to_create.append(cat_name)
            
        for ch_data in cat_data.get("channels", []):
            ch_name = ch_data.get("name")
            ch_type = ch_data.get("type", "text")
            ch_full = f"{ch_name} ({ch_type})"
            if (ch_name.lower(), ch_type) in guild_channels:
                channels_to_skip.append(ch_full)
            else:
                channels_to_create.append(ch_full)
                
    for ch_data in template_data.get("uncategorized_channels", []):
        ch_name = ch_data.get("name")
        ch_type = ch_data.get("type", "text")
        ch_full = f"{ch_name} ({ch_type})"
        if (ch_name.lower(), ch_type) in guild_channels:
            channels_to_skip.append(ch_full)
        else:
            channels_to_create.append(ch_full)
            
    objects_to_modify = []
    objects_to_delete = []
    
    if handling == "archive":
        for cat in guild.categories:
            if cat.name != "📦 ARCHIVED CHANNELS":
                objects_to_modify.append(f"Category: {cat.name}")
        for ch in guild.channels:
            if not isinstance(ch, discord.CategoryChannel):
                if ch.category is None or ch.category.name != "📦 ARCHIVED CHANNELS":
                    objects_to_modify.append(f"Channel: #{ch.name} ({ch.type})")
    elif handling == "delete":
        for cat in guild.categories:
            objects_to_delete.append(f"Category: {cat.name}")
        for ch in guild.channels:
            if not isinstance(ch, discord.CategoryChannel):
                objects_to_delete.append(f"Channel: #{ch.name} ({ch.type})")
                
    if handling == "delete":
        # Move all skipped items to create items since everything existing is wiped
        roles_to_create.extend(roles_to_skip)
        roles_to_skip.clear()
        categories_to_create.extend(categories_to_skip)
        categories_to_skip.clear()
        channels_to_create.extend(channels_to_skip)
        channels_to_skip.clear()
            
    return {
        "summary": {
            "roles_to_create": roles_to_create,
            "roles_to_skip": roles_to_skip,
            "categories_to_create": categories_to_create,
            "categories_to_skip": categories_to_skip,
            "channels_to_create": channels_to_create,
            "channels_to_skip": channels_to_skip,
            "objects_to_modify": objects_to_modify,
            "objects_to_delete": objects_to_delete
        },
        "template_data": template_data
    }


async def restore_guild_layout(guild: discord.Guild, backup_data: dict, customizations: Optional[dict] = None, handling: Optional[str] = "keep"):
    """Rebuilds the guild channels, categories, roles and overrides from backup data (idempotently)."""
    logger.info(f"Starting server layout restore on '{guild.name}' (handling: {handling})...")
    
    if guild.id in active_deployments:
        raise ValueError("A template deployment is already in progress on this server.")
        
    active_deployments.add(guild.id)
    errors = []
    
    try:
        if not guild.me.guild_permissions.manage_channels:
            raise PermissionError("Bot is missing the required 'Manage Channels' permission to apply templates or backups.")
        if not guild.me.guild_permissions.manage_roles:
            raise PermissionError("Bot is missing the required 'Manage Roles' permission to apply templates or backups.")
            
        # 1. Handle existing channels (Archive / Delete)
        if handling == "archive":
            logger.info("Archiving existing channels...")
            archive_category = discord.utils.get(guild.categories, name="📦 ARCHIVED CHANNELS")
            if not archive_category:
                try:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    }
                    archive_category = await guild.create_category(
                        name="📦 ARCHIVED CHANNELS",
                        overwrites=overwrites,
                        reason="Archive existing layout"
                    )
                    logger.info("Created '📦 ARCHIVED CHANNELS' category.")
                except Exception as e:
                    logger.error(f"Failed to create archive category: {e}")
                    errors.append(f"Failed to create archive category: {e}")

            if archive_category:
                for channel in list(guild.channels):
                    if channel.category == archive_category or channel == archive_category:
                        continue
                    if isinstance(channel, discord.CategoryChannel):
                        continue
                    try:
                        await channel.edit(category=archive_category, reason="Archiving old structure")
                        logger.info(f"Archived channel #{channel.name}")
                    except Exception as e:
                        logger.warning(f"Could not archive channel #{channel.name}: {e}")

                # Clean up old empty categories
                for category in list(guild.categories):
                    if category == archive_category:
                        continue
                    if len(category.channels) == 0:
                        try:
                            await category.delete(reason="Deleting empty category after archiving channels")
                            logger.info(f"Deleted empty category: {category.name}")
                        except Exception as e:
                            logger.warning(f"Could not delete empty category {category.name}: {e}")

        elif handling == "delete":
            logger.info("Deleting existing categories and channels...")
            for channel in list(guild.channels):
                try:
                    await channel.delete(reason="Server Layout Delete Before Restore")
                    logger.info(f"Deleted channel/category: {channel.name}")
                except Exception as e:
                    logger.warning(f"Could not delete channel {channel.name}: {e}")

        created_roles = {}
        created_roles["@everyone"] = guild.default_role
        
        logger.info("Stage: Applying role modifications...")
        permission_lost = False
        
        for r_data in backup_data.get("roles", []):
            role_name = r_data["name"]
            key = f"role:{role_name}"
            if customizations and key in customizations.get("disabled_elements", []):
                logger.info(f"Skipping disabled role: '{role_name}'")
                continue
            if customizations and key in customizations.get("renames", {}):
                role_name = customizations["renames"][key]
                
            role = discord.utils.find(lambda r: r.name.lower() == role_name.lower(), guild.roles)
            if not role:
                try:
                    role = await guild.create_role(
                        name=role_name,
                        permissions=discord.Permissions(r_data["permissions"]),
                        color=discord.Color(r_data["color"]),
                        hoist=r_data["hoist"],
                        reason="Server Layout Restore"
                    )
                    logger.info(f"Restored role: '{role_name}'")
                except Exception as e:
                    logger.error(f"Failed to restore role '{role_name}': {e}")
                    errors.append(f"Failed to create role '{role_name}': {e}")
                    if isinstance(e, discord.Forbidden) and not guild.me.guild_permissions.manage_roles:
                        logger.error("Permissions revoked mid-execution (Manage Roles). Aborting template apply.")
                        errors.append("Critical: Bot missing 'Manage Roles' permission mid-execution. Aborted.")
                        permission_lost = True
                        break
                    continue
            created_roles[r_data["name"]] = role
            
        if permission_lost:
            return False, errors
            
        def deserialize_overwrites(overwrites_data):
            overwrites = {}
            for ow in overwrites_data:
                target_name = ow["target_name"]
                target_type = ow["target_type"]
                target_id = ow.get("target_id")
                
                target = None
                if target_type == "role":
                    if target_id:
                        target = guild.get_role(int(target_id))
                    if not target:
                        target = created_roles.get(target_name) or discord.utils.find(lambda r: r.name.lower() == target_name.lower(), guild.roles)
                else:
                    if target_id:
                        target = guild.get_member(int(target_id))
                    if not target:
                        target = discord.utils.find(lambda m: m.name.lower() == target_name.lower(), guild.members)
                    
                if target:
                    allow_perms = discord.Permissions(ow["allow"])
                    deny_perms = discord.Permissions(ow["deny"])
                    overwrites[target] = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
            return overwrites

        archive_category = discord.utils.get(guild.categories, name="📦 PRE-RESTORE ARCHIVE")
        if not archive_category:
            try:
                archive_category = await guild.create_category(
                    name="📦 PRE-RESTORE ARCHIVE",
                    overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                    reason="Archive before restore"
                )
            except Exception as e:
                logger.error(f"Failed to create archive category: {e}")
                errors.append(f"Failed to create archive category: {e}")
                
        if archive_category:
            for ch in list(guild.channels):
                if ch.category == archive_category or ch == archive_category:
                    continue
                if isinstance(ch, discord.CategoryChannel):
                    continue
                try:
                    await ch.edit(category=archive_category)
                except Exception:
                    pass

            # Clean up old empty categories
            for category in list(guild.categories):
                if category == archive_category:
                    continue
                if len(category.channels) == 0:
                    try:
                        await category.delete(reason="Deleting empty category after archiving channels")
                    except Exception:
                        pass

        logger.info("Stage: Deploying category and channel modifications...")
        for cat_data in backup_data.get("categories", []):
            if permission_lost:
                break
                
            cat_name = cat_data["name"]
            key = f"category:{cat_name}"
            if customizations and key in customizations.get("disabled_elements", []):
                logger.info(f"Skipping disabled category: '{cat_name}'")
                continue
            if customizations and key in customizations.get("renames", {}):
                cat_name = customizations["renames"][key]
                
            cat_overwrites = deserialize_overwrites(cat_data.get("overwrites", []))
            
            category = discord.utils.find(lambda c: c.name.lower() == cat_name.lower() and c.name != "📦 PRE-RESTORE ARCHIVE", guild.categories)
            if not category:
                try:
                    category = await guild.create_category(
                        name=cat_name,
                        overwrites=cat_overwrites,
                        position=cat_data.get("position"),
                        reason="Layout Restore"
                    )
                    logger.info(f"Restored category: '{cat_name}'")
                except Exception as e:
                    logger.error(f"Failed to restore category '{cat_name}': {e}")
                    errors.append(f"Failed to create category '{cat_name}': {e}")
                    if isinstance(e, discord.Forbidden):
                        logger.error("Permissions revoked mid-execution. Aborting template apply.")
                        errors.append("Critical: Bot missing 'Manage Channels' permission mid-execution. Aborted.")
                        permission_lost = True
                        break
                    continue
                    
            for ch_data in cat_data.get("channels", []):
                chan_name = ch_data["name"]
                chan_type = ch_data["type"]
                ch_key = f"channel:{chan_name}"
                if customizations and ch_key in customizations.get("disabled_elements", []):
                    logger.info(f"Skipping disabled channel: '{chan_name}'")
                    continue
                if customizations and ch_key in customizations.get("renames", {}):
                    chan_name = customizations["renames"][ch_key]
                    
                chan_overwrites = deserialize_overwrites(ch_data.get("overwrites", []))
                
                channel = discord.utils.find(
                    lambda ch: ch.name.lower() == chan_name.lower() and (
                        (chan_type == "text" and isinstance(ch, discord.TextChannel)) or 
                        (chan_type == "voice" and isinstance(ch, discord.VoiceChannel))
                    ), 
                    category.channels
                )
                if channel:
                    logger.info(f"Channel '{chan_name}' already exists in category '{cat_name}'. Skipping creation.")
                    continue
                    
                try:
                    if chan_type == "text":
                        await guild.create_text_channel(
                            name=chan_name,
                            category=category,
                            overwrites=chan_overwrites,
                            position=ch_data.get("position"),
                            reason="Layout Restore"
                        )
                        logger.info(f"Restored text channel #{chan_name}")
                    else:
                        await guild.create_voice_channel(
                            name=chan_name,
                            category=category,
                            overwrites=chan_overwrites,
                            position=ch_data.get("position"),
                            reason="Layout Restore"
                        )
                        logger.info(f"Restored voice channel '{chan_name}'")
                except Exception as e:
                    logger.error(f"Failed to restore channel '{chan_name}': {e}")
                    errors.append(f"Failed to create channel '{chan_name}': {e}")
                    if isinstance(e, discord.Forbidden):
                        logger.error("Permissions revoked mid-execution. Aborting template apply.")
                        errors.append("Critical: Bot missing 'Manage Channels' permission mid-execution. Aborted.")
                        permission_lost = True
                        break
                        
        if not permission_lost:
            logger.info("Stage: Deploying uncategorized channels...")
            for ch_data in backup_data.get("uncategorized_channels", []):
                chan_name = ch_data["name"]
                chan_type = ch_data["type"]
                ch_key = f"channel:{chan_name}"
                if customizations and ch_key in customizations.get("disabled_elements", []):
                    logger.info(f"Skipping disabled uncategorized channel: '{chan_name}'")
                    continue
                if customizations and ch_key in customizations.get("renames", {}):
                    chan_name = customizations["renames"][ch_key]
                    
                chan_overwrites = deserialize_overwrites(ch_data.get("overwrites", []))
                
                channel = discord.utils.find(
                    lambda ch: ch.category is None and ch.name.lower() == chan_name.lower() and (
                        (chan_type == "text" and isinstance(ch, discord.TextChannel)) or 
                        (chan_type == "voice" and isinstance(ch, discord.VoiceChannel))
                    ), 
                    guild.channels
                )
                if channel:
                    logger.info(f"Uncategorized channel '{chan_name}' already exists. Skipping creation.")
                    continue
                    
                try:
                    if chan_type == "text":
                        await guild.create_text_channel(
                            name=chan_name,
                            overwrites=chan_overwrites,
                            position=ch_data.get("position"),
                            reason="Layout Restore"
                        )
                        logger.info(f"Restored uncategorized text channel #{chan_name}")
                    else:
                        await guild.create_voice_channel(
                            name=chan_name,
                            overwrites=chan_overwrites,
                            position=ch_data.get("position"),
                            reason="Layout Restore"
                        )
                        logger.info(f"Restored uncategorized voice channel '{chan_name}'")
                except Exception as e:
                    logger.error(f"Failed to restore uncategorized channel '{chan_name}': {e}")
                    errors.append(f"Failed to create uncategorized channel '{chan_name}': {e}")
                    if isinstance(e, discord.Forbidden):
                        logger.error("Permissions revoked mid-execution. Aborting template apply.")
                        errors.append("Critical: Bot missing 'Manage Channels' permission mid-execution. Aborted.")
                        break

        logger.info("Server layout restore process complete.")
        return len(errors) == 0, errors
    finally:
        active_deployments.discard(guild.id)
