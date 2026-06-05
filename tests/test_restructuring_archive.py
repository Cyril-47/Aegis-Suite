import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from aegis.bot.restructuring import optimize_guild_structure, restore_guild_layout

@pytest.mark.asyncio
async def test_optimize_guild_structure_archive_handling():
    # Mock discord channels and categories
    archive_category = MagicMock(spec=discord.CategoryChannel)
    archive_category.name = "📦 ARCHIVED CHANNELS"
    archive_category.channels = []
    
    regular_category = MagicMock(spec=discord.CategoryChannel)
    regular_category.name = "General Category"
    regular_category.channels = []
    
    text_channel = MagicMock(spec=discord.TextChannel)
    text_channel.name = "general"
    text_channel.category = regular_category
    text_channel.edit = AsyncMock()
    
    guild = MagicMock(spec=discord.Guild)
    guild.name = "Test Guild"
    guild.default_role = MagicMock()
    guild.roles = []
    
    guild.channels = [archive_category, regular_category, text_channel]
    guild.categories = [archive_category, regular_category]
    
    # Mock create_category to return our archive_category
    guild.create_category = AsyncMock(return_value=archive_category)
    guild.create_role = AsyncMock()
    
    # Mock edit/delete for category
    regular_category.edit = AsyncMock()
    regular_category.delete = AsyncMock()
    
    await optimize_guild_structure(guild, preset="gaming", handling="archive")
    
    # Verify that text_channel.edit was called with category=archive_category
    text_channel.edit.assert_called_once_with(category=archive_category, reason="Archiving old structure")
    
    # Verify that regular_category.edit was NOT called (i.e. we did not try to put a category under a category)
    assert not regular_category.edit.called
    
    # Verify that regular_category.delete was called because it was empty
    regular_category.delete.assert_called_once_with(reason="Deleting empty category after archiving channels")


@pytest.mark.asyncio
async def test_restore_guild_layout_archive_handling():
    archive_category_1 = MagicMock(spec=discord.CategoryChannel)
    archive_category_1.name = "📦 ARCHIVED CHANNELS"
    archive_category_1.channels = []
    
    archive_category_2 = MagicMock(spec=discord.CategoryChannel)
    archive_category_2.name = "📦 PRE-RESTORE ARCHIVE"
    archive_category_2.channels = []
    
    regular_category = MagicMock(spec=discord.CategoryChannel)
    regular_category.name = "General Category"
    regular_category.channels = []
    
    text_channel = MagicMock(spec=discord.TextChannel)
    text_channel.name = "general"
    text_channel.category = regular_category
    text_channel.edit = AsyncMock()
    
    guild = MagicMock(spec=discord.Guild)
    guild.name = "Test Guild"
    guild.default_role = MagicMock()
    guild.roles = []
    guild.channels = [archive_category_1, archive_category_2, regular_category, text_channel]
    guild.categories = [archive_category_1, archive_category_2, regular_category]
    guild.me = MagicMock()
    guild.me.guild_permissions = MagicMock()
    guild.me.guild_permissions.manage_channels = True
    guild.me.guild_permissions.manage_roles = True
    
    guild.create_category = AsyncMock(side_effect=[archive_category_1, archive_category_2])
    guild.create_role = AsyncMock()
    
    regular_category.edit = AsyncMock()
    regular_category.delete = AsyncMock()
    
    backup_data = {
        "roles": [],
        "categories": [
            {
                "name": "General Category",
                "channels": [
                    {"name": "general", "type": "text", "overwrites": []}
                ]
            }
        ]
    }
    
    original_get = discord.utils.get
    def mock_get(iterable, **attrs):
        if attrs.get("name") == "📦 ARCHIVED CHANNELS":
            return None
        if attrs.get("name") == "📦 PRE-RESTORE ARCHIVE":
            return None
        return original_get(iterable, **attrs)
    
    import unittest.mock
    with unittest.mock.patch('discord.utils.get', side_effect=mock_get):
        success, errors = await restore_guild_layout(guild, backup_data, handling="archive")
    
    assert success is True
    # Verify that text_channel was moved twice: once to ARCHIVED CHANNELS and once to PRE-RESTORE ARCHIVE
    assert text_channel.edit.call_count == 2
    
    calls = text_channel.edit.call_args_list
    assert calls[0][1].get("category") == archive_category_1
    assert calls[1][1].get("category") == archive_category_2
    
    # Verify that regular_category edit was not called
    assert not regular_category.edit.called
    # Verify that regular_category delete was called twice (once for each archive category deletion phase)
    assert regular_category.delete.call_count == 2
    regular_category.delete.assert_any_call(reason="Deleting empty category after archiving channels")
