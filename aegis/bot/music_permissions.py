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
