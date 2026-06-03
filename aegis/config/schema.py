from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any, Literal

class WelcomeSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    channel_id: Optional[str] = None
    channel_name: str
    message_title: str
    message_description: str
    embed_color: str
    auto_assign_roles: List[str] = Field(default_factory=list)

class AutomodSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    block_profanity: bool
    block_links: bool
    max_mentions: int
    log_channel_id: Optional[str] = None
    log_channel_name: str
    profanity_words: List[str] = Field(default_factory=list)
    block_invites: bool = False
    whitelisted_domains: List[str] = Field(default_factory=list)
    whitelisted_invites: List[str] = Field(default_factory=list)

class TicketSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    category_name: str
    staff_role_name: str
    ticket_channel_id: Optional[str] = None
    panel_message_id: Optional[str] = None

class CommandPermissionRule(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: Literal["everyone", "moderator", "admin", "owner", "role", "roles"]
    role_id: Optional[str] = None      # Used if mode == "role"
    role_ids: List[str] = Field(default_factory=list)  # Used if mode == "roles"

class PermissionRoles(BaseModel):
    model_config = ConfigDict(extra="allow")
    admin_role_id: Optional[str] = None
    moderator_role_id: Optional[str] = None

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
    command_permissions: Dict[str, CommandPermissionRule] = Field(default_factory=dict)
    permission_roles: PermissionRoles = Field(default_factory=PermissionRoles)

def validate_config(data: Dict[str, Any]) -> ConfigModel:
    """Validates configuration dictionary against the schema."""
    return ConfigModel(**data)


