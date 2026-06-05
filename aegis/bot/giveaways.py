import time
import random
import logging
import discord
import utils

logger = logging.getLogger("aegis.bot.giveaways")

class GiveawayJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 Join Giveaway (0)", style=discord.ButtonStyle.blurple, custom_id="giveaway_join_btn")
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = str(interaction.message.id)
        
        async with utils.giveaways_lock:
            giveaways = await utils.load_giveaways()
            
            if msg_id not in giveaways:
                button.disabled = True
                button.label = "🎉 Join Giveaway"
                await interaction.message.edit(view=self)
                await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
                return
                
            giveaway = giveaways[msg_id]
            if giveaway.get("ended", False):
                button.disabled = True
                await interaction.message.edit(view=self)
                await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
                return
                
            user_id = interaction.user.id
            entrants = giveaway.get("entrants", [])
            
            if user_id in entrants:
                entrants.remove(user_id)
                msg = "❌ You have left the giveaway."
            else:
                entrants.append(user_id)
                msg = "✅ You have successfully entered the giveaway!"
                
            giveaway["entrants"] = entrants
            giveaways[msg_id] = giveaway
            await utils.save_giveaways(giveaways)
        
        button.label = f"🎉 Join Giveaway ({len(entrants)})"
        
        embeds = interaction.message.embeds
        if embeds:
            embed = embeds[0]
            entrants_field_idx = -1
            for idx, field in enumerate(embed.fields):
                if "Participants" in field.name or "Entrants" in field.name:
                    entrants_field_idx = idx
                    break
            
            new_embed = discord.Embed.from_dict(embed.to_dict())
            if entrants_field_idx != -1:
                new_embed.set_field_at(
                    entrants_field_idx,
                    name=f"👥 Participants ({len(entrants)})",
                    value=f"Click the button below to join!\nTotal: **{len(entrants)}** entrant(s)",
                    inline=True
                )
            else:
                new_embed.set_footer(text=f"Total Entrants: {len(entrants)}")
                
            await interaction.message.edit(embed=new_embed, view=self)
        else:
            await interaction.message.edit(view=self)
            
        await interaction.response.send_message(msg, ephemeral=True)

async def start_giveaway_bot(channel, prize, winners_count, duration_seconds, host_id, host_name_custom=None):
    end_time = time.time() + duration_seconds
    
    if host_name_custom:
        host_name = host_name_custom
    else:
        host_name = "Aegis Suite"
        if host_id:
            try:
                host_member = await channel.guild.fetch_member(int(host_id))
                host_name = host_member.display_name
            except Exception:
                host_member = channel.guild.get_member(int(host_id))
                if host_member:
                    host_name = host_member.display_name
                elif int(host_id) == channel.guild.me.id:
                    host_name = channel.guild.me.display_name
                else:
                    host_name = f"User (ID: {host_id})"
    
    embed = discord.Embed(
        title="🎁 GIVEAWAY START 🎁",
        description="Click the button below to join the giveaway!",
        color=discord.Color.from_str("#6366F1")
    )
    embed.add_field(name="🎁 Prize", value=prize, inline=True)
    embed.add_field(name="🏆 Winners", value=str(winners_count), inline=True)
    embed.add_field(name="⏳ Ends", value=f"<t:{int(end_time)}:R> (<t:{int(end_time)}:f>)", inline=False)
    embed.add_field(name="👥 Participants (0)", value="Click the button below to join!\nTotal: **0** entrant(s)", inline=True)
    embed.set_footer(text=f"Hosted by {host_name}")
    
    view = GiveawayJoinView()
    message = await channel.send(embed=embed, view=view)
    
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        giveaways[str(message.id)] = {
            "guild_id": str(channel.guild.id),
            "channel_id": str(channel.id),
            "prize": prize,
            "winners_count": winners_count,
            "end_time": end_time,
            "entrants": [],
            "winners": [],
            "ended": False,
            "host_id": str(host_id),
            "host_name": host_name
        }
        await utils.save_giveaways(giveaways)
        
    return str(message.id)

active_rerolls = set()

async def reroll_giveaway_bot(channel, message_id):
    msg_id_str = str(message_id)
    if msg_id_str in active_rerolls:
        return "A reroll is already in progress for this giveaway."
        
    active_rerolls.add(msg_id_str)
    try:
        async with utils.giveaways_lock:
            giveaways = await utils.load_giveaways()
            if msg_id_str not in giveaways:
                return "Giveaway not found in record."
                
            gw = giveaways[msg_id_str]
            if not gw.get("ended", False):
                return "Giveaway is still active. End it first before rerolling."
                
            entrants = gw.get("entrants", [])
            if not entrants:
                return "No entrants to roll from."
                
            winners_count = gw.get("winners_count", 1)
            prize = gw.get("prize", "Unknown Prize")
            
            actual_winners_count = min(len(entrants), winners_count)
            winners = random.sample(entrants, actual_winners_count)
            
            gw["winners"] = winners
            giveaways[msg_id_str] = gw
            await utils.save_giveaways(giveaways)
            
        try:
            message = await channel.fetch_message(message_id)
            embeds = message.embeds
            if embeds:
                embed = embeds[0]
                new_embed = discord.Embed.from_dict(embed.to_dict())
                new_embed.clear_fields()
                new_embed.add_field(name="🎁 Prize", value=prize, inline=True)
                
                winners_mentions = ", ".join([f"<@{w}>" for w in winners])
                new_embed.add_field(name="🏆 Rerolled Winners", value=winners_mentions, inline=True)
                new_embed.add_field(name="👥 Total Participants", value=f"**{len(entrants)}** entrant(s)", inline=True)
                
                await message.edit(embed=new_embed)
        except discord.NotFound:
            logger.warning(f"Giveaway message {message_id} not found during reroll. Skipping edit.")
        except Exception as e:
            logger.error(f"Failed to edit message during reroll: {e}")
            
        winners_mentions = ", ".join([f"<@{w}>" for w in winners])
        await channel.send(
            f"🔄 **Giveaway Rerolled!**\n"
            f"Congratulations to the new winner(s): {winners_mentions}! You won **{prize}**! 🎁"
        )
        return "success"
    finally:
        active_rerolls.discard(msg_id_str)
