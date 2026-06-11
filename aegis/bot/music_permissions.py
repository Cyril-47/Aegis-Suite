from discord.ext import commands
from aegis.core.permissions.resolver import PermissionResolver, MUSIC_CONTROL_PERMISSIONS
from aegis.core.permissions.registry import CommandRegistry
import utils

async def check_music_permission(ctx: commands.Context, command_name: str) -> bool:
    # 1. Bot Owner, Guild Owner, Discord Admin, Configured Admin role, Configured Moderator role checks
    is_authorized = False
    
    # 1.1 Bot owner check
    if ctx.bot.owner_id:
        is_authorized = ctx.author.id == ctx.bot.owner_id
    elif ctx.bot.owner_ids:
        is_authorized = ctx.author.id in ctx.bot.owner_ids
    else:
        try:
            is_authorized = await ctx.bot.is_owner(ctx.author)
        except Exception:
            pass

    # 1.2 Guild owner & Discord Administrator check
    if not is_authorized:
        is_authorized = ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator

    # 1.3 Configured Admin & Moderator role check
    if not is_authorized:
        try:
            config = utils.load_config()
            guild_conf = config.get("guild_configs", {}).get(str(ctx.guild.id), {})
            roles_mapping = guild_conf.get("permission_roles", {})
            admin_role_id = roles_mapping.get("admin_role_id")
            mod_role_id = roles_mapping.get("moderator_role_id")
            
            user_roles_str = [str(r.id) for r in ctx.author.roles]
            if (admin_role_id and str(admin_role_id) in user_roles_str) or (mod_role_id and str(mod_role_id) in user_roles_str):
                is_authorized = True
        except Exception:
            pass

    if is_authorized:
        return True

    # 2. VC checking for commands that require voice channel presence
    vc_required_commands = {
        CommandRegistry.MUSIC_PLAY,
        CommandRegistry.MUSIC_PAUSE,
        CommandRegistry.MUSIC_RESUME,
        CommandRegistry.MUSIC_SKIP,
        CommandRegistry.MUSIC_STOP,
        CommandRegistry.MUSIC_VOLUME,
        CommandRegistry.MUSIC_SHUFFLE,
        CommandRegistry.MUSIC_CLEARQUEUE
    }
    
    if command_name in vc_required_commands:
        # User must be in a voice channel
        author_voice = getattr(ctx.author, "voice", None)
        if not author_voice or not author_voice.channel:
            return False
            
        # User must be in the same voice channel as the bot if the bot is connected
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.channel:
            if author_voice.channel.id != voice_client.channel.id:
                return False

    # 3. Requester and Solo VC check for control commands
    if command_name in MUSIC_CONTROL_PERMISSIONS:
        # 3.1 User who started the currently playing track
        player = None
        if hasattr(ctx.bot, "get_music_player"):
            player = ctx.bot.get_music_player(ctx.guild.id)
        if player and player.current:
            requester_id = player.current.get("requester_id")
            if requester_id and requester_id == ctx.author.id:
                return True

        # 3.2 Voice Channel Solo Bypass Check (only non-bot humans)
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.channel:
            humans = [m for m in voice_client.channel.members if not m.bot]
            if len(humans) == 1 and humans[0].id == ctx.author.id:
                return True

    # 4. Fallback to standard PermissionResolver
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
