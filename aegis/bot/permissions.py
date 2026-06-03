from discord.ext import commands
from aegis.core.permissions.resolver import PermissionResolver

def universal_permission_check(command_name: str):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            return False
            
        user_roles = [str(role.id) for role in ctx.author.roles]
        is_owner = ctx.author.id == ctx.guild.owner_id
        has_admin = ctx.author.guild_permissions.administrator
        
        allowed = await PermissionResolver.has_permission(
            guild_id=str(ctx.guild.id),
            user_id=str(ctx.author.id),
            command_name=command_name,
            user_roles=user_roles,
            is_owner=is_owner,
            has_discord_admin=has_admin
        )
        if not allowed:
            # We raise MissingPermissions to be handled by on_command_error politer warning
            raise commands.MissingPermissions([f"Missing permissions to run command {command_name}"])
        return True
    return commands.check(predicate)
