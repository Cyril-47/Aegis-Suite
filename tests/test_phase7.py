import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from aegis.db.models import Base, Template, ApplyHistory
from aegis.templates_engine.model import validate, TemplateInvalid
from aegis.templates_engine.io import import_json, export_json
from aegis.templates_engine.apply import apply_to_server, clone_from_server
from aegis.templates_engine.registry import TEMPLATE_REGISTRY

# Sample valid template data
VALID_TMPL_DICT = {
    "name": "test-template",
    "verification_level": "medium",
    "explicit_content_filter": "all_members",
    "roles": [
        {
            "name": "Admin",
            "color": 255,
            "hoist": True,
            "permissions": 8,
            "position": 2
        },
        {
            "name": "Member",
            "color": 0,
            "hoist": False,
            "permissions": 1,
            "position": 1
        }
    ],
    "categories": [
        {
            "name": "GENERAL",
            "position": 1,
            "overwrites": [
                {
                    "target_type": "role",
                    "target_name": "@everyone",
                    "allow": 0,
                    "deny": 2048
                }
            ],
            "channels": [
                {
                    "name": "general",
                    "type": "text",
                    "position": 1,
                    "overwrites": []
                }
            ]
        }
    ],
    "uncategorized_channels": [
        {
            "name": "lobby",
            "type": "voice",
            "position": 1,
            "overwrites": []
        }
    ]
}

def test_template_validation_success():
    # Verify a valid template dict parses correctly
    model = validate(VALID_TMPL_DICT)
    assert model.name == "test-template"
    assert len(model.roles) == 2
    assert model.categories[0].name == "GENERAL"
    assert model.uncategorized_channels[0].type == "voice"

def test_template_validation_failure():
    # Verify an invalid template dict (missing fields, wrong types) raises TemplateInvalid
    invalid_dict = {
        "name": 1234,  # should be string, but Pydantic might coerce it; let's omit required roles or channels structure
        "roles": "not-a-list"
    }
    with pytest.raises(TemplateInvalid):
        validate(invalid_dict)

def test_builtin_templates_validate(paths_tmp):
    # Relocate builtin templates to paths_tmp.templates_builtin to simulate first boot
    import shutil
    from pathlib import Path
    
    # Path to repo templates directory
    repo_templates_dir = Path("templates/builtin")
    for kind, filename in TEMPLATE_REGISTRY.items():
        src = repo_templates_dir / filename
        dest = paths_tmp.templates_builtin / filename
        shutil.copy(src, dest)
        
        # Verify it exists and validates
        with open(dest, "r", encoding="utf-8") as f:
            doc = json.load(f)
            validate(doc)

def test_template_import_export_round_trip(paths_tmp):
    # Set up in-memory SQLite for test
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Import
        db_tmpl = import_json(VALID_TMPL_DICT, session)
        assert db_tmpl.id is not None
        assert db_tmpl.source == "imported"
        
        # Export
        export_path = export_json(db_tmpl.id, paths_tmp, session)
        assert export_path.exists()
        
        # Read exported and assert parity
        with open(export_path, "r", encoding="utf-8") as f:
            exported_doc = json.load(f)
            
        assert exported_doc["name"] == VALID_TMPL_DICT["name"]
        assert len(exported_doc["roles"]) == len(VALID_TMPL_DICT["roles"])

@pytest.mark.asyncio
async def test_apply_to_server():
    # Setup test database
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Seed templates table with test template
        db_tmpl = Template(
            name="test-template",
            kind="gaming",
            json=json.dumps(VALID_TMPL_DICT),
            source="builtin"
        )
        session.add(db_tmpl)
        session.commit()
        
        # Mock Discord constructs
        mock_bot = MagicMock()
        mock_guild = AsyncMock()
        mock_bot.get_guild.return_value = mock_guild
        
        # Set up guild properties
        mock_guild.name = "Test Guild"
        mock_everyone_role = MagicMock()
        mock_everyone_role.name = "@everyone"
        mock_guild.default_role = mock_everyone_role
        
        # Mock role and channel creation methods
        mock_role = MagicMock()
        mock_role.name = "Admin"
        mock_guild.create_role.return_value = mock_role
        mock_guild.roles = [mock_everyone_role]
        
        mock_category = AsyncMock()
        mock_category.name = "GENERAL"
        mock_category.channels = []
        mock_guild.create_category.return_value = mock_category
        mock_guild.categories = []
        
        mock_guild.channels = []
        
        # Apply template
        await apply_to_server(mock_bot, 98765, db_tmpl.id, session)
        
        # Assert Discord API calls were made
        assert mock_guild.create_role.call_count == 2
        mock_guild.create_category.assert_called_once()
        mock_category.create_text_channel.assert_called_once_with(
            name="general",
            overwrites={},
            position=1,
            reason="Aegis Template Apply"
        )
        mock_guild.create_voice_channel.assert_called_once_with(
            name="lobby",
            overwrites={},
            position=1,
            reason="Aegis Template Apply"
        )
        
        # Verify history written
        history = session.query(ApplyHistory).first()
        assert history is not None
        assert history.result == "Success"

@pytest.mark.asyncio
async def test_apply_to_server_history_write_failure():
    # Setup test database
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Seed templates table with test template
        db_tmpl = Template(
            name="test-template",
            kind="gaming",
            json=json.dumps(VALID_TMPL_DICT),
            source="builtin"
        )
        session.add(db_tmpl)
        session.commit()
        
        # Mock Discord constructs
        mock_bot = MagicMock()
        mock_guild = AsyncMock()
        mock_bot.get_guild.return_value = mock_guild
        mock_guild.name = "Test Guild"
        mock_everyone_role = MagicMock()
        mock_everyone_role.name = "@everyone"
        mock_guild.default_role = mock_everyone_role
        mock_guild.roles = [mock_everyone_role]
        mock_guild.categories = []
        mock_guild.channels = []
        
        # We intercept/mock the session commit or add to raise an exception for ApplyHistory
        orig_commit = session.commit
        def failing_commit():
            # If we are saving apply history, raise exception
            # We can check if any ApplyHistory objects are in the session
            for obj in session.new:
                if isinstance(obj, ApplyHistory):
                    raise RuntimeError("Database connection lost during history write")
            return orig_commit()
            
        session.commit = failing_commit
        
        # Apply template - should raise exception
        with pytest.raises(RuntimeError, match="ApplyHistory write failure"):
            await apply_to_server(mock_bot, 98765, db_tmpl.id, session)
            
        # Assert that structure creation WAS called (was not reversed)
        assert mock_guild.create_role.called
        assert mock_guild.create_category.called

@pytest.mark.asyncio
async def test_clone_from_server():
    # Mock Discord constructs
    mock_bot = MagicMock()
    mock_guild = AsyncMock()
    mock_bot.get_guild.return_value = mock_guild
    
    mock_guild.name = "Cloned Guild"
    
    # Mock Verification Level / Explicit Content Filter
    mock_verification = MagicMock()
    mock_verification.name = "high"
    mock_guild.verification_level = mock_verification
    
    mock_filter = MagicMock()
    mock_filter.name = "all_members"
    mock_guild.explicit_content_filter = mock_filter
    
    # Roles
    mock_everyone = MagicMock()
    mock_everyone.is_default.return_value = True
    
    mock_role = MagicMock()
    mock_role.name = "Staff"
    mock_role.color.value = 12345
    mock_role.hoist = True
    mock_role.permissions.value = 8
    mock_role.position = 2
    mock_role.is_default.return_value = False
    
    mock_guild.roles = [mock_everyone, mock_role]
    
    # Channels & Categories
    mock_channel = MagicMock()
    mock_channel.name = "welcome"
    mock_channel.position = 1
    mock_channel.overwrites = {}
    
    # Setup channel types
    import discord
    mock_channel.__class__ = discord.TextChannel
    
    mock_cat = MagicMock()
    mock_cat.name = "WELCOME & INFO"
    mock_cat.position = 1
    mock_cat.overwrites = {}
    mock_cat.channels = [mock_channel]
    
    mock_guild.categories = [mock_cat]
    
    # Uncategorized channels
    mock_uncat_ch = MagicMock()
    mock_uncat_ch.name = "general"
    mock_uncat_ch.position = 2
    mock_uncat_ch.overwrites = {}
    mock_uncat_ch.__class__ = discord.TextChannel
    mock_uncat_ch.category = None
    
    # Add category backlink or check how channels are enumerated
    # In apply.py: "for ch in guild.channels: if ch.category is None:"
    mock_guild.channels = [mock_uncat_ch]
    
    # Clone
    tmpl = await clone_from_server(mock_bot, 1111)
    
    # Assertions
    assert tmpl.name == "Cloned Guild"
    assert tmpl.verification_level == "high"
    assert tmpl.explicit_content_filter == "all_members"
    assert len(tmpl.roles) == 1
    assert tmpl.roles[0].name == "Staff"
    assert len(tmpl.categories) == 1
    assert tmpl.categories[0].name == "WELCOME & INFO"
    assert tmpl.categories[0].channels[0].name == "welcome"
    assert len(tmpl.uncategorized_channels) == 1
    assert tmpl.uncategorized_channels[0].name == "general"
