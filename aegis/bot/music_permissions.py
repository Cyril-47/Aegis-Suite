from discord.ext import commands
from aegis.core.permissions.resolver import PermissionResolver
from aegis.core.permissions.registry import CommandRegistry
import utils

async def check_music_permission(ctx: commands.Context, command_name: str) -> bool:
    # 1. Guild Owner & Discord Admin bypass (fast path)
    is_admin_or_owner = ctx.author.id == ctx.guild.owner_id or ctx.author.guild_permissions.administrator
    
    # Check if the user has the configured admin/moderator role
    if not is_admin_or_owner:
        try:
            config = utils.load_config()
            guild_conf = config.get("guild_configs", {}).get(str(ctx.guild.id), {})
            roles_mapping = guild_conf.get("permission_roles", {})
            admin_role_id = roles_mapping.get("admin_role_id")
            mod_role_id = roles_mapping.get("moderator_role_id")
            
            user_roles_str = [str(r.id) for r in ctx.author.roles]
            if (admin_role_id and str(admin_role_id) in user_roles_str) or (mod_role_id and str(mod_role_id) in user_roles_str):
                is_admin_or_owner = True
        except Exception:
            pass

    if is_admin_or_owner:
        return True

    # 2. VC checking for playback control commands
    control_commands = {
        CommandRegistry.MUSIC_PLAY,
        CommandRegistry.MUSIC_PAUSE,
        CommandRegistry.MUSIC_RESUME,
        CommandRegistry.MUSIC_SKIP,
        CommandRegistry.MUSIC_STOP,
        CommandRegistry.MUSIC_VOLUME,
        CommandRegistry.MUSIC_SHUFFLE,
        CommandRegistry.MUSIC_CLEARQUEUE
    }
    
    if command_name in control_commands:
        # User must be in a voice channel
        author_voice = getattr(ctx.author, "voice", None)
        if not author_voice or not author_voice.channel:
            return False
            
        # User must be in the same voice channel as the bot if the bot is connected
        voice_client = ctx.guild.voice_client
        if voice_client and voice_client.channel:
            if author_voice.channel.id != voice_client.channel.id:
                return False

    # 3. Voice Channel Solo Bypass Check
    # If the user is the only non-bot human in the voice channel, they can control playback
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
