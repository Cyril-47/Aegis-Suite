from pydantic import BaseModel, Field, ValidationError, ConfigDict
from typing import List, Optional, Dict, Any

class WelcomeSettingsModel(BaseModel):
    enabled: bool
    channel_id: Optional[str] = None
    channel_name: str
    message_title: str
    message_description: str
    embed_color: str
    auto_assign_roles: List[str] = Field(default_factory=list)

class AutomodSettingsModel(BaseModel):
    enabled: bool
    block_profanity: bool
    block_links: bool
    max_mentions: int
    log_channel_id: Optional[str] = None
    log_channel_name: str
    profanity_words: List[str] = Field(default_factory=list)

class TicketSettingsModel(BaseModel):
    enabled: bool
    category_name: str
    staff_role_name: str
    ticket_channel_id: Optional[str] = None
    panel_message_id: Optional[str] = None

class ConfigModel(BaseModel):
    model_config = ConfigDict(extra='allow')
    client_id: str
    setup_complete: bool = False  # Persisted setup complete flag (Req 5.5, Req 8.11)
    ui_mode: str = "beginner"     # Presentation flag defaults to "beginner" (Req 14.1)
    welcome_settings: WelcomeSettingsModel
    automod_settings: AutomodSettingsModel
    ticket_settings: Optional[TicketSettingsModel] = None
    custom_commands: Optional[Dict[str, Any]] = Field(default_factory=dict)
    admin_password_hash: Optional[str] = ""
    hosting_mode: Optional[str] = ""

def validate_config(data: Dict[str, Any]) -> ConfigModel:
    """Validates configuration dictionary against the schema."""
    return ConfigModel(**data)

