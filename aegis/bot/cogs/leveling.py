"""
Leveling Cog - Handles XP and leveling commands.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
from aegis.core.permissions.registry import CommandRegistry
from aegis.bot.permissions import universal_permission_check

logger = logging.getLogger("aegis.bot.leveling")


class LevelingCog(commands.Cog, name="Leveling"):
    """XP and leveling system commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rank", description="Shows rank information.")
    @app_commands.describe(member="Select a member (optional)")
    @universal_permission_check(CommandRegistry.LEVEL_RANK)
    async def rank_command(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        """Check rank for a member."""
        target = member or ctx.author
        from aegis.bot.leveling import leveling_system
        rank_data = leveling_system.get_user_rank(ctx.guild.id, target.id)
        
        embed = discord.Embed(title=f"🏆 Rank Card for {target.name}", color=discord.Color.gold())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=f"**{rank_data['level']}**", inline=True)
        embed.add_field(name="Server Rank", value=f"**#{rank_data['rank']}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{rank_data['xp']}**", inline=True)
        embed.add_field(name="Messages", value=f"**{rank_data['messages']}**", inline=True)
        
        pct = int((rank_data['xp_progress'] / max(1, rank_data['xp_needed_for_next'])) * 100)
        filled = int(pct / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        embed.add_field(name="XP Progress", value=f"{bar} ({pct}%)", inline=False)
        
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="Shows the server XP leaderboard.")
    @universal_permission_check(CommandRegistry.LEVEL_LEADERBOARD)
    async def leaderboard_command(self, ctx: commands.Context):
        """Show the server leaderboard."""
        from aegis.bot.leveling import leveling_system
        leaderboard = leveling_system.get_leaderboard(ctx.guild.id, 10)
        if not leaderboard:
            await ctx.send("📭 Leaderboard is empty. Start typing to earn XP!")
            return
            
        embed = discord.Embed(title=f"🏆 Server Leaderboard - {ctx.guild.name}", color=discord.Color.gold())
        desc = []
        for item in leaderboard:
            member = ctx.guild.get_member(int(item["user_id"]))
            m_name = member.name if member else f"User ID {item['user_id']}"
            desc.append(f"`#{item['rank']}` **{m_name}** - Level {item['level']} (XP: {item['xp']}, Messages: {item['messages']})")
            
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="setlevelrole", description="Configures role reward for reaching a level.")
    @app_commands.describe(level="Level required", role="Role to reward")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.LEVEL_SET_ROLE)
    async def setlevelrole_command(self, ctx: commands.Context, level: int, role: discord.Role):
        """Configure level roles rewards."""
        import aegis.core.utils as utils
        guild_id = str(ctx.guild.id)
        guild_conf = utils.get_guild_config(guild_id)
        leveling_settings = guild_conf.setdefault("leveling_settings", {})
        level_roles = leveling_settings.setdefault("level_roles", {})
        level_roles[str(level)] = str(role.id)
        utils.save_guild_config(guild_id, guild_conf)
        
        self.bot.config = utils.load_config()
        
        await ctx.send(f"✅ Users reaching Level **{level}** will now automatically receive the **{role.name}** role!")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(LevelingCog(bot))
