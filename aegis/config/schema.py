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


class AntiRaidSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    response_mode: str = "alert"  # passive, alert, lockdown, auto_verify
    join_rate_threshold: int = 5
    join_rate_window_seconds: int = 30
    min_account_age_days: int = 7
    suspicious_score_threshold: int = 70
    auto_verify_channel: Optional[str] = None
    raid_alert_channel: Optional[str] = None
    dm_owner_on_raid: bool = True
    lockdown_duration_seconds: int = 300


class TicketSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool
    category_name: str
    staff_role_name: str
    ticket_channel_id: Optional[str] = None
    panel_message_id: Optional[str] = None
    sla_hours: Optional[int] = None


class CommandPermissionRule(BaseModel):
    model_config = ConfigDict(extra="allow")
    mode: Literal["everyone", "moderator", "admin", "owner", "role", "roles"]
    role_id: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)


class PermissionRoles(BaseModel):
    model_config = ConfigDict(extra="allow")
    admin_role_id: Optional[str] = None
    moderator_role_id: Optional[str] = None


class LevelingSettingsModel(BaseModel):
    model_config = ConfigDict(extra="allow")
    enabled: bool = False
    xp_per_message: int = 15
    xp_cooldown_seconds: int = 60
    level_up_channel: Optional[str] = None
    level_roles: Dict[str, Any] = Field(default_factory=dict)
    ignored_channels: List[str] = Field(default_factory=list)
    ignored_roles: List[str] = Field(default_factory=list)


class ConfigModel(BaseModel):
    model_config = ConfigDict(extra='allow')
    client_id: str
    setup_complete: bool = False
    ui_mode: str = "beginner"
    welcome_settings: WelcomeSettingsModel
    automod_settings: AutomodSettingsModel
    anti_raid_settings: Optional[AntiRaidSettingsModel] = None
    ticket_settings: Optional[TicketSettingsModel] = None
    custom_commands: Optional[Dict[str, Any]] = Field(default_factory=dict)
    admin_password_hash: Optional[str] = ""
    hosting_mode: Optional[str] = ""
    command_permissions: Dict[str, CommandPermissionRule] = Field(default_factory=dict)
    permission_roles: PermissionRoles = Field(default_factory=PermissionRoles)
    leveling_settings: Optional[LevelingSettingsModel] = None
    scheduled_messages: List[Dict[str, Any]] = Field(default_factory=list)
    auto_responders: List[Dict[str, Any]] = Field(default_factory=list)
    guild_configs: Dict[str, Any] = Field(default_factory=dict)
    revoked_guilds: List[str] = Field(default_factory=list)
    pending_pairings: Dict[str, Any] = Field(default_factory=dict)
    sync_commands: bool = False


def validate_config(data: Dict[str, Any]) -> ConfigModel:
    """Validates configuration dictionary against the schema."""
    return ConfigModel(**data)


