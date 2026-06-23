"""
Feature 5: Automation Engine

Safe rule-based automation system.
No eval(), no arbitrary Python execution.
Only safe, predefined operations.
"""

import logging
import datetime
import json
from typing import Dict, List, Any, Optional
from collections import deque
from dataclasses import dataclass, asdict

logger = logging.getLogger("aegis.intelligence.automation")


# Safe operators for conditions
SAFE_OPERATORS = {
    "equals": lambda a, b: a == b,
    "not_equals": lambda a, b: a != b,
    "contains": lambda a, b: b.lower() in str(a).lower() if isinstance(a, str) else False,
    "greater_than": lambda a, b: float(a) > float(b) if a is not None and b is not None else False,
    "less_than": lambda a, b: float(a) < float(b) if a is not None and b is not None else False,
    "in": lambda a, b: a in b if isinstance(b, (list, set, str)) else False,
    "not_in": lambda a, b: a not in b if isinstance(b, (list, set, str)) else False,
}

# Safe actions
SAFE_ACTIONS = {
    "assign_role": {"params": ["role_name"]},
    "remove_role": {"params": ["role_name"]},
    "send_message": {"params": ["channel_id", "message"]},
    "mute_user": {"params": ["user_id", "duration_minutes"]},
    "timeout_user": {"params": ["user_id", "duration_minutes"]},
    "kick_user": {"params": ["user_id", "reason"]},
    "ban_user": {"params": ["user_id", "reason"]},
    "log_event": {"params": ["event_type", "details"]},
    "set_slowmode": {"params": ["channel_id", "seconds"]},
    "lock_channel": {"params": ["channel_id"]},
    "unlock_channel": {"params": ["channel_id"]},
}

# Safe triggers
SAFE_TRIGGERS = [
    "member_join",
    "member_leave",
    "message_sent",
    "message_deleted",
    "role_created",
    "role_deleted",
    "channel_created",
    "channel_deleted",
    "moderation_action",
    "voice_join",
    "voice_leave",
    "reaction_added",
    "reaction_removed",
]


@dataclass
class AutomationRule:
    """A single automation rule."""
    id: str
    name: str
    enabled: bool
    trigger: str
    conditions: List[Dict[str, Any]]
    actions: List[Dict[str, Any]]
    created_at: str
    last_triggered: Optional[str] = None
    trigger_count: int = 0


class AutomationEngine:
    """
    Safe rule-based automation engine.
    No eval(), no arbitrary Python execution.
    """

    def __init__(self):
        self._rules: Dict[str, Dict[str, AutomationRule]] = {}  # guild_id -> {rule_id -> AutomationRule}
        self._loaded_guilds = set()
        self._execution_log: deque = deque(maxlen=500)

    def _ensure_guild_loaded(self, guild_id: str):
        guild_id = str(guild_id)
        if guild_id in self._loaded_guilds:
            return
        
        self._rules[guild_id] = {}
        try:
            from aegis.core.config_manager import get_guild_config
            cfg = get_guild_config(guild_id)
            rules_list = cfg.get("automation_rules", [])
            
            for rdata in rules_list:
                try:
                    rule = AutomationRule(
                        id=rdata["id"],
                        name=rdata.get("name", "Unnamed Rule"),
                        enabled=rdata.get("enabled", True),
                        trigger=rdata["trigger"],
                        conditions=rdata.get("conditions", []),
                        actions=rdata.get("actions", []),
                        created_at=rdata.get("created_at", datetime.datetime.now(datetime.timezone.utc).isoformat()),
                        last_triggered=rdata.get("last_triggered"),
                        trigger_count=rdata.get("trigger_count", 0),
                    )
                    self._rules[guild_id][rule.id] = rule
                except Exception as e:
                    logger.error(f"Error parsing rule for guild {guild_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to load rules for guild {guild_id} from config: {e}")
        
        self._loaded_guilds.add(guild_id)

    def invalidate_guild_cache(self, guild_id: str):
        """Force re-load of guild rules from config on next access."""
        guild_id = str(guild_id)
        self._loaded_guilds.discard(guild_id)

    def _save_guild_rules(self, guild_id: str):
        guild_id = str(guild_id)
        try:
            from aegis.core.config_manager import get_guild_config, set_guild_config
            cfg = get_guild_config(guild_id)
            
            rules_list = []
            for r in self._rules.get(guild_id, {}).values():
                rules_list.append(asdict(r))
                
            cfg["automation_rules"] = rules_list
            set_guild_config(guild_id, cfg)
        except Exception as e:
            logger.error(f"Failed to save rules for guild {guild_id} to config: {e}")

    def create_rule(self, guild_id: str, rule_data: Dict[str, Any]) -> AutomationRule:
        """Create a new automation rule. guild_id is always required."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        
        rule_id = rule_data.get("id")
        if not rule_id:
            import uuid
            rule_id = f"rule_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
        
        rule = AutomationRule(
            id=rule_id,
            name=rule_data.get("name", "Unnamed Rule"),
            enabled=rule_data.get("enabled", True),
            trigger=rule_data["trigger"],
            conditions=rule_data.get("conditions", []),
            actions=rule_data.get("actions", []),
            created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        
        self._rules[guild_id][rule_id] = rule
        self._save_guild_rules(guild_id)
        return rule

    def update_rule(self, guild_id: str, rule_id: str, rule_data: Dict[str, Any]) -> Optional[AutomationRule]:
        """Update an existing automation rule."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        
        if rule_id not in self._rules.get(guild_id, {}):
            return None
        
        rule = self._rules[guild_id][rule_id]
        if "name" in rule_data:
            rule.name = rule_data["name"]
        if "enabled" in rule_data:
            rule.enabled = rule_data["enabled"]
        if "trigger" in rule_data:
            rule.trigger = rule_data["trigger"]
        if "conditions" in rule_data:
            rule.conditions = rule_data["conditions"]
        if "actions" in rule_data:
            rule.actions = rule_data["actions"]
        
        self._save_guild_rules(guild_id)
        return rule

    def delete_rule(self, guild_id: str, rule_id: str) -> bool:
        """Delete an automation rule."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        
        if rule_id in self._rules.get(guild_id, {}):
            del self._rules[guild_id][rule_id]
            self._save_guild_rules(guild_id)
            return True
        return False

    def get_rule(self, guild_id: str, rule_id: str) -> Optional[AutomationRule]:
        """Get a specific automation rule."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        return self._rules.get(guild_id, {}).get(rule_id)

    def get_all_rules(self, guild_id: str) -> List[AutomationRule]:
        """Get all automation rules."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        return list(self._rules.get(guild_id, {}).values())

    def evaluate_trigger(self, guild_id: str, trigger: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate all rules for a given trigger.
        
        Returns list of actions to execute.
        """
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        actions_to_execute = []
        fired = False
        
        for rule in self._rules.get(guild_id, {}).values():
            if not rule.enabled:
                continue
            if rule.trigger != trigger:
                continue
            
            # Check conditions
            if self._evaluate_conditions(rule.conditions, context):
                actions_to_execute.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "actions": rule.actions,
                })
                
                # Update rule stats
                rule.last_triggered = datetime.datetime.now(datetime.timezone.utc).isoformat()
                rule.trigger_count += 1
                
                # Log execution
                self._execution_log.append({
                    "rule_id": rule.id,
                    "rule_name": rule.name,
                    "trigger": trigger,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "actions_count": len(rule.actions),
                })
                fired = True
        
        if fired:
            self._save_guild_rules(guild_id)
        return actions_to_execute

    def _evaluate_conditions(self, conditions: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        """Evaluate all conditions (AND logic)."""
        if not conditions:
            return True
        
        for condition in conditions:
            field = condition.get("field")
            operator = condition.get("operator")
            value = condition.get("value")
            
            if not field or not operator:
                continue
            
            field_value = self._get_field_value(field, context)
            
            # Coerce form string value to match field type for numeric comparisons
            if isinstance(field_value, (int, float)):
                try:
                    value = type(field_value)(value)
                except (ValueError, TypeError):
                    pass
            
            if operator in SAFE_OPERATORS:
                if not SAFE_OPERATORS[operator](field_value, value):
                    return False
            else:
                logger.warning(f"Unknown operator: {operator}")
                return False
        
        return True

    def _get_field_value(self, field: str, context: Dict[str, Any]) -> Any:
        """Get field value from context using safe dot notation."""
        parts = field.split(".")
        value = context
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        
        return value

    def validate_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a rule before creation."""
        errors = []
        
        # Check trigger
        if "trigger" not in rule_data:
            errors.append("Trigger is required")
        elif rule_data["trigger"] not in SAFE_TRIGGERS:
            errors.append(f"Invalid trigger: {rule_data['trigger']}")
        
        # Check conditions
        for i, condition in enumerate(rule_data.get("conditions", [])):
            if "field" not in condition:
                errors.append(f"Condition {i}: field is required")
            if "operator" not in condition:
                errors.append(f"Condition {i}: operator is required")
            elif condition["operator"] not in SAFE_OPERATORS:
                errors.append(f"Condition {i}: invalid operator '{condition['operator']}'")
        
        # Check actions
        for i, action in enumerate(rule_data.get("actions", [])):
            if "action" not in action:
                errors.append(f"Action {i}: action type is required")
            elif action["action"] not in SAFE_ACTIONS:
                errors.append(f"Action {i}: invalid action '{action['action']}'")
        
        return {
            "valid": len(errors) == 0,
            "errors": errors,
        }

    def get_execution_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent execution log."""
        return list(self._execution_log)[-limit:]

    def get_rule_stats(self, guild_id: str) -> Dict[str, Any]:
        """Get statistics for all rules."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        rules_dict = self._rules.get(guild_id, {})
        total = len(rules_dict)
        enabled = sum(1 for r in rules_dict.values() if r.enabled)
        total_triggers = sum(r.trigger_count for r in rules_dict.values())
        
        return {
            "total_rules": total,
            "enabled_rules": enabled,
            "disabled_rules": total - enabled,
            "total_triggers": total_triggers,
        }

    def export_rules(self, guild_id: str) -> List[Dict[str, Any]]:
        """Export all rules as JSON-serializable dicts."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        return [asdict(rule) for rule in self._rules.get(guild_id, {}).values()]

    def import_rules(self, guild_id: str, rules_data: List[Dict[str, Any]]) -> int:
        """Import rules from JSON-serializable dicts."""
        guild_id = str(guild_id)
        self._ensure_guild_loaded(guild_id)
        count = 0
        existing_ids = set(self._rules.get(guild_id, {}).keys())
        for rule_data in rules_data:
            try:
                source_id = rule_data.get("id")
                if source_id and source_id in existing_ids:
                    self.update_rule(guild_id, source_id, rule_data)  # upsert
                else:
                    self.create_rule(guild_id, rule_data)
                count += 1
            except Exception as e:
                logger.error(f"Failed to import rule: {e}")
        return count


async def execute_automation_rule_actions(bot, guild, rule_actions: List[Dict[str, Any]], trigger_context: Dict[str, Any]):
    """Execute the list of actions from a triggered automation rule."""
    import discord
    for act_wrap in rule_actions:
        actions = act_wrap.get("actions", [])
        rule_name = act_wrap.get("rule_name", "Automation Rule")
        rule_id = act_wrap.get("rule_id", "unknown")
        
        for action_dict in actions:
            action_type = action_dict.get("action")
            if not action_type:
                continue
            
            logger.info(f"Executing automation action '{action_type}' for rule '{rule_name}' (ID: {rule_id})")
            try:
                if action_type == "assign_role":
                    role_name = action_dict.get("role_name")
                    member_data = trigger_context.get("member") or trigger_context.get("author")
                    if member_data and role_name:
                        member_id = int(member_data.get("id"))
                        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
                        role = discord.utils.get(guild.roles, name=role_name)
                        if member and role:
                            await member.add_roles(role, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Assigned role '{role_name}' to {member.name}")
                            
                elif action_type == "remove_role":
                    role_name = action_dict.get("role_name")
                    member_data = trigger_context.get("member") or trigger_context.get("author")
                    if member_data and role_name:
                        member_id = int(member_data.get("id"))
                        member = guild.get_member(member_id) or await guild.fetch_member(member_id)
                        role = discord.utils.get(guild.roles, name=role_name)
                        if member and role:
                            await member.remove_roles(role, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Removed role '{role_name}' from {member.name}")
                            
                elif action_type == "send_message":
                    channel_id = action_dict.get("channel_id")
                    message_text = action_dict.get("message")
                    if channel_id and message_text:
                        channel = guild.get_channel(int(channel_id)) or await bot.fetch_channel(int(channel_id))
                        if channel:
                            from aegis.bot.bot_manager import resolve_embed_variables
                            member_data = trigger_context.get("member") or trigger_context.get("author")
                            member = None
                            if member_data:
                                member = guild.get_member(int(member_data.get("id")))
                            resolved_text = await resolve_embed_variables(message_text, member=member, guild=guild)
                            await channel.send(resolved_text)
                            logger.info(f"Sent automation message to channel {channel_id}")
                            
                elif action_type in ("mute_user", "timeout_user"):
                    user_id_str = action_dict.get("user_id") or (trigger_context.get("member") or {}).get("id") or (trigger_context.get("author") or {}).get("id")
                    duration_min = float(action_dict.get("duration_minutes") or 10)
                    if user_id_str:
                        member = guild.get_member(int(user_id_str)) or await guild.fetch_member(int(user_id_str))
                        if member:
                            duration = datetime.timedelta(minutes=duration_min)
                            await member.timeout(duration, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Timed out user {member.name} for {duration_min} minutes")
                            
                elif action_type == "kick_user":
                    user_id_str = action_dict.get("user_id") or (trigger_context.get("member") or {}).get("id") or (trigger_context.get("author") or {}).get("id")
                    reason = action_dict.get("reason", f"Automation rule: {rule_name}")
                    if user_id_str:
                        member = guild.get_member(int(user_id_str)) or await guild.fetch_member(int(user_id_str))
                        if member:
                            await member.kick(reason=reason)
                            logger.info(f"Kicked user {member.name} by automation")
                            
                elif action_type == "ban_user":
                    user_id_str = action_dict.get("user_id") or (trigger_context.get("member") or {}).get("id") or (trigger_context.get("author") or {}).get("id")
                    reason = action_dict.get("reason", f"Automation rule: {rule_name}")
                    if user_id_str:
                        user_id = int(user_id_str)
                        await guild.ban(discord.Object(id=user_id), reason=reason)
                        logger.info(f"Banned user ID {user_id} by automation")
                        
                elif action_type == "set_slowmode":
                    channel_id = action_dict.get("channel_id") or (trigger_context.get("channel") or {}).get("id")
                    seconds = int(action_dict.get("seconds") or 0)
                    if channel_id:
                        channel = guild.get_channel(int(channel_id))
                        if channel and hasattr(channel, "edit"):
                            await channel.edit(slowmode_delay=seconds, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Set slowmode to {seconds}s on channel {channel_id}")
                            
                elif action_type == "lock_channel":
                    channel_id = action_dict.get("channel_id") or (trigger_context.get("channel") or {}).get("id")
                    if channel_id:
                        channel = guild.get_channel(int(channel_id))
                        if channel and hasattr(channel, "set_permissions"):
                            await channel.set_permissions(guild.default_role, send_messages=False, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Locked channel {channel_id}")
                            
                elif action_type == "unlock_channel":
                    channel_id = action_dict.get("channel_id") or (trigger_context.get("channel") or {}).get("id")
                    if channel_id:
                        channel = guild.get_channel(int(channel_id))
                        if channel and hasattr(channel, "set_permissions"):
                            await channel.set_permissions(guild.default_role, send_messages=None, reason=f"Automation rule: {rule_name}")
                            logger.info(f"Unlocked channel {channel_id}")
                            
                elif action_type == "log_event":
                    event_type = action_dict.get("event_type", "automation_info")
                    details = action_dict.get("details", "")
                    logger.info(f"[Automation Log] Type: {event_type} | Details: {details}")
                    
            except Exception as e:
                logger.error(f"Error executing automation action {action_type} for rule {rule_id}: {e}", exc_info=True)

