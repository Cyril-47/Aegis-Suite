import logging
import datetime
import json
from sqlalchemy.orm import Session
import discord
from aegis.db.models import Server, Template, ApplyHistory
from aegis.templates_engine.model import TemplateModel, validate, RoleModel, CategoryModel, ChannelModel, OverwriteModel

logger = logging.getLogger("aegis.templates_engine.apply")

async def apply_to_server(bot, guild_id: int, template_id: int, session: Session) -> None:
    """Diffs the template against the target guild and creates missing structure sequentially."""
    # 1. Fetch template
    db_template = session.query(Template).filter(Template.id == template_id).first()
    if not db_template:
        raise ValueError(f"Template with id {template_id} not found")

    # Parse template JSON
    template_data = json.loads(db_template.json)
    tmpl = validate(template_data)

    # 2. Fetch guild
    guild = bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await bot.fetch_guild(guild_id)
        except Exception:
            guild = None
    if not guild:
        raise ValueError(f"Guild with id {guild_id} not found")

    # 3. Create missing roles
    existing_roles = {r.name.lower(): r for r in guild.roles}
    role_map = {}  # maps template role name -> live role object
    for r_tmpl in tmpl.roles:
        if r_tmpl.name.lower() not in existing_roles:
            try:
                perms = discord.Permissions(r_tmpl.permissions)
                color = discord.Color(r_tmpl.color)
                new_role = await guild.create_role(
                    name=r_tmpl.name,
                    color=color,
                    hoist=r_tmpl.hoist,
                    permissions=perms,
                    reason="Aegis Template Apply"
                )
                role_map[r_tmpl.name.lower()] = new_role
            except Exception as e:
                logger.warning(f"Failed to create role {r_tmpl.name}: {e}")
        else:
            role_map[r_tmpl.name.lower()] = existing_roles[r_tmpl.name.lower()]

    # Helper to construct overwrites
    def make_overwrites(tmpl_overwrites):
        overwrites = {}
        for ov in tmpl_overwrites:
            target = None
            if ov.target_type == "role":
                if ov.target_name == "@everyone":
                    target = guild.default_role
                else:
                    target = role_map.get(ov.target_name.lower())
                    if not target:
                        for r in guild.roles:
                            if r.name.lower() == ov.target_name.lower():
                                target = r
                                break
            if target:
                allow_perms = discord.Permissions(ov.allow)
                deny_perms = discord.Permissions(ov.deny)
                overwrites[target] = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
        return overwrites

    # 4. Create categories and their channels
    existing_categories = {c.name.lower(): c for c in guild.categories}
    for cat_tmpl in tmpl.categories:
        live_cat = existing_categories.get(cat_tmpl.name.lower())
        if not live_cat:
            try:
                cat_overwrites = make_overwrites(cat_tmpl.overwrites)
                live_cat = await guild.create_category(
                    name=cat_tmpl.name,
                    overwrites=cat_overwrites,
                    position=cat_tmpl.position,
                    reason="Aegis Template Apply"
                )
            except Exception as e:
                logger.warning(f"Failed to create category {cat_tmpl.name}: {e}")
                continue

        existing_channels = {ch.name.lower(): ch for ch in live_cat.channels}
        for ch_tmpl in cat_tmpl.channels:
            if ch_tmpl.name.lower() not in existing_channels:
                try:
                    ch_overwrites = make_overwrites(ch_tmpl.overwrites)
                    if ch_tmpl.type == "voice":
                        await live_cat.create_voice_channel(
                            name=ch_tmpl.name,
                            overwrites=ch_overwrites,
                            position=ch_tmpl.position,
                            reason="Aegis Template Apply"
                        )
                    else:
                         await live_cat.create_text_channel(
                            name=ch_tmpl.name,
                            overwrites=ch_overwrites,
                            position=ch_tmpl.position,
                            reason="Aegis Template Apply"
                        )
                except Exception as e:
                    logger.warning(f"Failed to create channel {ch_tmpl.name} in category {cat_tmpl.name}: {e}")

    # 5. Create uncategorized channels
    guild_channels = [ch for ch in guild.channels if ch.category is None]
    existing_uncat = {ch.name.lower(): ch for ch in guild_channels}
    for ch_tmpl in tmpl.uncategorized_channels:
        if ch_tmpl.name.lower() not in existing_uncat:
            try:
                ch_overwrites = make_overwrites(ch_tmpl.overwrites)
                if ch_tmpl.type == "voice":
                    await guild.create_voice_channel(
                        name=ch_tmpl.name,
                        overwrites=ch_overwrites,
                        position=ch_tmpl.position,
                        reason="Aegis Template Apply"
                    )
                else:
                    await guild.create_text_channel(
                        name=ch_tmpl.name,
                        overwrites=ch_overwrites,
                        position=ch_tmpl.position,
                        reason="Aegis Template Apply"
                    )
            except Exception as e:
                logger.warning(f"Failed to create uncategorized channel {ch_tmpl.name}: {e}")

    # 6. Log result in database
    db_server = session.query(Server).filter(Server.guild_id == str(guild_id)).first()
    if not db_server:
        db_server = Server(guild_id=str(guild_id), name=guild.name, mode="beginner")
        session.add(db_server)
        session.flush()

    try:
        history = ApplyHistory(
            server_id=db_server.id,
            template_id=db_template.id,
            applied_at=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
            result="Success"
        )
        session.add(history)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"OBSERVABLE FAILURE: Failed to write apply history to DB: {e}")
        # Note: Do not reverse Discord edits. We raise an error so testing can verify it.
        raise RuntimeError("ApplyHistory write failure") from e

async def clone_from_server(bot, guild_id: int) -> TemplateModel:
    """Fetches structure of live server and constructs a validated TemplateModel."""
    guild = bot.get_guild(guild_id)
    if not guild:
        try:
            guild = await bot.fetch_guild(guild_id)
        except Exception:
            guild = None
    if not guild:
        raise ValueError(f"Guild with id {guild_id} not found")

    roles = []
    for r in guild.roles:
        if r.is_default():
            continue
        roles.append(RoleModel(
            name=r.name,
            color=r.color.value,
            hoist=r.hoist,
            permissions=r.permissions.value,
            position=r.position
        ))

    def convert_overwrites(overwrites_dict):
        ov_list = []
        for target, ov in overwrites_dict.items():
            target_type = "role" if isinstance(target, discord.Role) else "member"
            target_name = "@everyone" if isinstance(target, discord.Role) and target.is_default() else target.name
            
            allow_val, deny_val = ov.pair()
            ov_list.append(OverwriteModel(
                target_type=target_type,
                target_name=target_name,
                allow=allow_val.value,
                deny=deny_val.value
            ))
        return ov_list

    categories = []
    for cat in guild.categories:
        channels = []
        for ch in cat.channels:
            ch_type = "voice" if isinstance(ch, discord.VoiceChannel) else "text"
            channels.append(ChannelModel(
                name=ch.name,
                type=ch_type,
                position=ch.position,
                overwrites=convert_overwrites(ch.overwrites)
            ))
        
        categories.append(CategoryModel(
            name=cat.name,
            position=cat.position,
            overwrites=convert_overwrites(cat.overwrites),
            channels=channels
        ))

    uncategorized = []
    for ch in guild.channels:
        if ch.category is None:
            ch_type = "voice" if isinstance(ch, discord.VoiceChannel) else "text"
            uncategorized.append(ChannelModel(
                name=ch.name,
                type=ch_type,
                position=ch.position,
                overwrites=convert_overwrites(ch.overwrites)
            ))

    # Safely convert verification level and content filter name
    v_level = guild.verification_level.name if hasattr(guild.verification_level, "name") else str(guild.verification_level)
    c_filter = guild.explicit_content_filter.name if hasattr(guild.explicit_content_filter, "name") else str(guild.explicit_content_filter)

    tmpl = TemplateModel(
        name=guild.name,
        verification_level=v_level,
        explicit_content_filter=c_filter,
        roles=roles,
        categories=categories,
        uncategorized_channels=uncategorized
    )
    return tmpl
