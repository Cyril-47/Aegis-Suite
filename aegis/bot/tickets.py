import asyncio
import logging
import discord
import re
import utils

logger = logging.getLogger("DiscordBot.tickets")

def get_bot():
    from aegis.bot.bot_manager import get_bot as _get_bot
    return _get_bot()

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="persistent_close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        await channel.send("🔒 *This ticket is being closed and deleted in 5 seconds...*")
        
        async def delete_channel():
            await asyncio.sleep(5)
            try:
                await channel.delete(reason="Ticket closed")
                logger.info(f"Ticket channel #{channel.name} deleted.")
            except Exception as e:
                logger.error(f"Failed to delete ticket channel: {e}")
        asyncio.create_task(delete_channel())

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Support Ticket", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="persistent_ticket_button")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        bot = get_bot()
        if bot:
            bot.check_stats_reset()
            bot.stats["tickets_today"] = bot.stats.get("tickets_today", 0) + 1
        guild = interaction.guild
        member = interaction.user
        
        config = utils.load_config()
        ticket_cfg = utils.get_guild_ticket_settings(config, guild.id)
        
        category_name = ticket_cfg.get("category_name", "🎟️ SUPPORT TICKETS")
        category = discord.utils.get(guild.categories, name=category_name)
        
        staff_role_name = ticket_cfg.get("staff_role_name", "Moderator")
        staff_role = discord.utils.get(guild.roles, name=staff_role_name)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        if not category:
            try:
                category = await guild.create_category(name=category_name, overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)})
                logger.info(f"Created ticket category '{category_name}'")
            except Exception as e:
                logger.error(f"Failed to create ticket category: {e}")
        
        try:
            channel_name = f"ticket-{member.name.lower()}"
            channel_name = re.sub(r'[^a-zA-Z0-9-]', '', channel_name)
            
            # Check for existing ticket channel to prevent duplicates (Tier 3.7)
            existing = discord.utils.get(guild.text_channels, name=channel_name, category=category)
            if existing:
                await interaction.followup.send(f"❌ You already have an open ticket: {existing.mention}", ephemeral=True)
                return
                
            ticket_channel = await guild.create_text_channel(
                name=channel_name[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Support ticket opened by {member.name}"
            )
            
            embed = discord.Embed(
                title="🎟️ Support Ticket Created",
                description=f"Welcome {member.mention} to your private support channel.\n\n"
                            f"Please describe your issue in detail. A staff member ({staff_role.mention if staff_role else 'Moderator'}) will be with you shortly.\n\n"
                            f"Click the button below to **Close** this ticket.",
                color=discord.Color.blue()
            )
            await ticket_channel.send(content=f"{member.mention} | Support Staff", embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"✅ Ticket created! Head over to {ticket_channel.mention} to speak with staff.", ephemeral=True)
            logger.info(f"Ticket channel #{channel_name} created for {member.name}")
        except Exception as e:
            logger.error(f"Failed to create support ticket channel: {e}")
            await interaction.followup.send("❌ Failed to create support ticket. Please check bot permissions.", ephemeral=True)

# Ticket panel deployment
async def deploy_ticket_panel_message(guild_id: int, channel_id: int):
    bot = get_bot()
    if not bot:
        return False
    guild = bot.get_guild(guild_id)
    if not guild:
        return False
    channel = guild.get_channel(channel_id)
    if not channel:
        return False
        
    try:
        embed = discord.Embed(
            title="🎟️ Support Helpdesk",
            description="Need assistance? Click the button below to open a private support ticket.\n\n"
                        "Our moderation staff will be notified and will assist you inside your private channel.",
            color=discord.Color.blurple()
        )
        view = TicketPanelView()
        msg = await channel.send(embed=embed, view=view)
        
        # Save deployed panel ID in config (Tier 5.7)
        guild_conf = utils.get_guild_config(str(channel.guild.id))
        guild_conf["ticket_settings"]["ticket_channel_id"] = str(channel_id)
        guild_conf["ticket_settings"]["panel_message_id"] = str(msg.id)
        utils.save_guild_config(str(channel.guild.id), guild_conf)
        
        logger.info(f"Ticket support panel deployed in #{channel.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to deploy ticket panel: {e}")
        return False
