"""
Smart Features Engine - Rules-based intelligence for Aegis Suite.

Implements 12 smart features using heuristics, scoring, pattern detection,
and statistical analysis. No AI models, no cloud dependencies.
"""

import logging
import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("aegis.smart_features")


# =============================================================================
# Data Models
# =============================================================================

class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Impact(Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Recommendation:
    id: str
    title: str
    description: str
    severity: str
    impact_score: int  # 1-10
    confidence: float  # 0.0-1.0
    category: str
    auto_fix_available: bool
    auto_fix_action: Optional[str] = None
    auto_fix_params: Optional[Dict] = None


@dataclass
class HealthScore:
    dimension: str
    score: int  # 0-100
    max_score: int = 100
    findings: List[Dict] = field(default_factory=list)
    recommendations: List[Recommendation] = field(default_factory=list)


@dataclass
class AutoFixResult:
    success: bool
    action: str
    details: str
    rollback_available: bool
    rollback_data: Optional[Dict] = None
    error: Optional[str] = None


# =============================================================================
# Recommendation Engine (Feature 1)
# =============================================================================

class RecommendationEngine:
    """Rule-based recommendation engine that analyzes server state."""

    def __init__(self, bot):
        self.bot = bot
        self._rules = self._build_rules()

    def _build_rules(self) -> List[Dict]:
        """Define all recommendation rules."""
        return [
            {
                "id": "verification_disabled",
                "check": self._check_verification,
                "title": "Verification Level is None",
                "description": "Server has no verification level, making it vulnerable to spam and raids.",
                "severity": Severity.CRITICAL.value,
                "impact": 9,
                "category": "security",
                "auto_fix": True,
                "fix_action": "set_verification_level",
            },
            {
                "id": "no_mod_log",
                "check": self._check_mod_log,
                "title": "No Mod Log Channel",
                "description": "No channel named 'mod-log' or similar found. Moderation actions won't be logged.",
                "severity": Severity.HIGH.value,
                "impact": 7,
                "category": "moderation",
                "auto_fix": True,
                "fix_action": "create_mod_log_channel",
            },
            {
                "id": "no_automod",
                "check": self._check_automod,
                "title": "AutoMod Not Configured",
                "description": "Discord AutoMod is not enabled. Spam and inappropriate content may go unchecked.",
                "severity": Severity.HIGH.value,
                "impact": 8,
                "category": "moderation",
                "auto_fix": False,
                "fix_action": None,
            },
            {
                "id": "backup_stale",
                "check": self._check_backup_staleness,
                "title": "Backup Not Created Recently",
                "description": "No backup has been created in the last 7 days.",
                "severity": Severity.HIGH.value,
                "impact": 8,
                "category": "reliability",
                "auto_fix": True,
                "fix_action": "create_backup",
            },
            {
                "id": "inactive_channels",
                "check": self._check_inactive_channels,
                "title": "Inactive Channels Detected",
                "description": "{count} channels have had no messages in 30+ days.",
                "severity": Severity.MEDIUM.value,
                "impact": 5,
                "category": "structure",
                "auto_fix": True,
                "fix_action": "archive_inactive_channels",
            },
            {
                "id": "unused_roles",
                "check": self._check_unused_roles,
                "title": "Unused Roles Detected",
                "description": "{count} roles have no members assigned.",
                "severity": Severity.MEDIUM.value,
                "impact": 4,
                "category": "structure",
                "auto_fix": True,
                "fix_action": "remove_unused_roles",
            },
            {
                "id": "no_welcome_channel",
                "check": self._check_welcome_channel,
                "title": "No Welcome Channel",
                "description": "No welcome or general channel found for new members.",
                "severity": Severity.MEDIUM.value,
                "impact": 6,
                "category": "growth",
                "auto_fix": True,
                "fix_action": "create_welcome_channel",
            },
            {
                "id": "low_role_hierarchy",
                "check": self._check_role_hierarchy,
                "title": "Role Hierarchy Issues",
                "description": "Some roles may have dangerous permissions at the same level.",
                "severity": Severity.MEDIUM.value,
                "impact": 5,
                "category": "security",
                "auto_fix": False,
                "fix_action": None,
            },
            {
                "id": "no_rules_channel",
                "check": self._check_rules_channel,
                "title": "No Rules Channel",
                "description": "No channel named 'rules' found. New members won't see server rules.",
                "severity": Severity.MEDIUM.value,
                "impact": 6,
                "category": "moderation",
                "auto_fix": True,
                "fix_action": "create_rules_channel",
            },
            {
                "id": "excessive_permissions",
                "check": self._check_excessive_permissions,
                "title": "Excessive Permissions Detected",
                "description": "{count} roles have Administrator permission.",
                "severity": Severity.HIGH.value,
                "impact": 8,
                "category": "security",
                "auto_fix": False,
                "fix_action": None,
            },
        ]

    def analyze(self, guild) -> List[Recommendation]:
        """Run all rules and return recommendations."""
        recommendations = []
        for rule in self._rules:
            try:
                result = rule["check"](guild)
                if result:
                    count = result.get("count", 0) if isinstance(result, dict) else 0
                    rec = Recommendation(
                        id=rule["id"],
                        title=rule["title"],
                        description=rule["description"].format(count=count) if count else rule["description"],
                        severity=rule["severity"],
                        impact_score=rule["impact"],
                        confidence=result.get("confidence", 0.9) if isinstance(result, dict) else 0.9,
                        category=rule["category"],
                        auto_fix_available=rule["auto_fix"],
                        auto_fix_action=rule["fix_action"],
                        auto_fix_params=result.get("params", {}) if isinstance(result, dict) else {},
                    )
                    recommendations.append(rec)
            except Exception as e:
                logger.error(f"Rule {rule['id']} failed: {e}")
        return sorted(recommendations, key=lambda r: r.impact_score, reverse=True)

    def _check_verification(self, guild) -> Optional[Dict]:
        if guild.verification_level.value == 0:
            return {"confidence": 1.0}
        return None

    def _check_mod_log(self, guild) -> Optional[Dict]:
        mod_log_names = ["mod-log", "modlog", "moderation-log", "audit-log"]
        for channel in guild.text_channels:
            if channel.name.lower() in mod_log_names:
                return None
        return {"confidence": 0.95}

    def _check_automod(self, guild) -> Optional[Dict]:
        try:
            rules = guild.auto_moderation_rules if hasattr(guild, 'auto_moderation_rules') else []
            if not rules:
                return {"confidence": 0.9}
        except Exception:
            pass
        return None

    def _check_backup_staleness(self, guild) -> Optional[Dict]:
        from aegis.core.utils import load_config
        config = load_config()
        last_backup = config.get(f"last_backup_{guild.id}")
        if not last_backup:
            return {"confidence": 1.0}
        try:
            last_date = datetime.datetime.fromisoformat(last_backup)
            days_since = (datetime.datetime.now(datetime.timezone.utc) - last_date).days
            if days_since > 7:
                return {"confidence": min(0.95, 0.7 + days_since * 0.02)}
        except (ValueError, TypeError):
            pass
        return None

    def _check_inactive_channels(self, guild) -> Optional[Dict]:
        inactive = []
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
        for channel in guild.text_channels:
            try:
                # Use last_message_id instead of last_message (which is cached)
                if channel.last_message_id:
                    # Compute timestamp from snowflake ID
                    import discord
                    created_at = discord.utils.snowflake_time(channel.last_message_id)
                    if created_at < cutoff:
                        inactive.append(channel.name)
                else:
                    # No messages ever sent
                    inactive.append(channel.name)
            except Exception:
                pass
        if len(inactive) >= 3:
            return {"count": len(inactive), "confidence": 0.85, "params": {"channels": inactive[:10]}}
        return None

    def _check_unused_roles(self, guild) -> Optional[Dict]:
        unused = []
        for role in guild.roles:
            if role.name == "@everyone":
                continue
            if len(role.members) == 0 and not role.managed:
                unused.append(role.name)
        if len(unused) >= 2:
            return {"count": len(unused), "confidence": 0.9, "params": {"roles": unused[:10]}}
        return None

    def _check_welcome_channel(self, guild) -> Optional[Dict]:
        welcome_names = ["welcome", "general", "chat", "lobby", "introductions"]
        for channel in guild.text_channels:
            if channel.name.lower() in welcome_names:
                return None
        return {"confidence": 0.8}

    def _check_role_hierarchy(self, guild) -> Optional[Dict]:
        admin_roles = [r for r in guild.roles if r.permissions.administrator]
        if len(admin_roles) > 3:
            return {"count": len(admin_roles), "confidence": 0.7}
        return None

    def _check_rules_channel(self, guild) -> Optional[Dict]:
        rules_names = ["rules", "server-rules", "guidelines", "faq"]
        for channel in guild.text_channels:
            if channel.name.lower() in rules_names:
                return None
        return {"confidence": 0.85}

    def _check_excessive_permissions(self, guild) -> Optional[Dict]:
        admin_roles = []
        for role in guild.roles:
            if role.permissions.administrator and role.name != "@everyone" and not role.managed:
                admin_roles.append(role.name)
        if len(admin_roles) > 2:
            return {"count": len(admin_roles), "confidence": 0.9}
        return None


# =============================================================================
# Config Doctor (Feature 3)
# =============================================================================

class ConfigDoctor:
    """Analyzes server configuration and generates health scores."""

    def __init__(self, bot):
        self.bot = bot

    def diagnose(self, guild) -> Dict[str, Any]:
        """Run full diagnosis and return scores."""
        security = self._score_security(guild)
        moderation = self._score_moderation(guild)
        growth = self._score_growth(guild)
        automation = self._score_automation(guild)
        reliability = self._score_reliability(guild)

        overall = int((security + moderation + growth + automation + reliability) / 5)

        return {
            "overall": overall,
            "dimensions": {
                "security": {"score": security, "max": 100, "findings": self._get_security_findings(guild)},
                "moderation": {"score": moderation, "max": 100, "findings": self._get_moderation_findings(guild)},
                "growth": {"score": growth, "max": 100, "findings": self._get_growth_findings(guild)},
                "automation": {"score": automation, "max": 100, "findings": self._get_automation_findings(guild)},
                "reliability": {"score": reliability, "max": 100, "findings": self._get_reliability_findings(guild)},
            },
        }

    def _score_security(self, guild) -> int:
        score = 100
        if guild.verification_level.value == 0:
            score -= 30
        if guild.mfa_level == 0:
            score -= 15
        admin_count = sum(1 for r in guild.roles if r.permissions.administrator and not r.managed)
        if admin_count > 3:
            score -= (admin_count - 3) * 10
        if not guild.explicit_content_filter:
            score -= 10
        return max(0, score)

    def _score_moderation(self, guild) -> int:
        score = 100
        mod_log_names = ["mod-log", "modlog", "moderation-log"]
        has_mod_log = any(c.name.lower() in mod_log_names for c in guild.text_channels)
        if not has_mod_log:
            score -= 25
        try:
            rules = guild.auto_moderation_rules if hasattr(guild, 'auto_moderation_rules') else []
            if not rules:
                score -= 30
        except Exception:
            score -= 30
        mod_roles = [r for r in guild.roles if "mod" in r.name.lower() or "admin" in r.name.lower()]
        if len(mod_roles) < 1:
            score -= 15
        return max(0, score)

    def _score_growth(self, guild) -> int:
        score = 100
        welcome_names = ["welcome", "general", "chat"]
        has_welcome = any(c.name.lower() in welcome_names for c in guild.text_channels)
        if not has_welcome:
            score -= 25
        if guild.premium_tier == 0:
            score -= 10
        if guild.member_count < 50:
            score -= 20
        return max(0, score)

    def _score_automation(self, guild) -> int:
        score = 100
        try:
            rules = guild.auto_moderation_rules if hasattr(guild, 'auto_moderation_rules') else []
            if not rules:
                score -= 40
        except Exception:
            score -= 40
        rules_names = ["rules", "server-rules"]
        has_rules = any(c.name.lower() in rules_names for c in guild.text_channels)
        if not has_rules:
            score -= 20
        return max(0, score)

    def _score_reliability(self, guild) -> int:
        score = 100
        from aegis.core.utils import load_config
        config = load_config()
        last_backup = config.get(f"last_backup_{guild.id}")
        if not last_backup:
            score -= 40
        else:
            try:
                last_date = datetime.datetime.fromisoformat(last_backup)
                days_since = (datetime.datetime.now(datetime.timezone.utc) - last_date).days
                if days_since > 7:
                    score -= min(30, days_since * 3)
            except (ValueError, TypeError):
                score -= 20
        return max(0, score)

    def _get_security_findings(self, guild) -> List[Dict]:
        findings = []
        if guild.verification_level.value == 0:
            findings.append({"type": "critical", "message": "Verification level is None"})
        if guild.mfa_level == 0:
            findings.append({"type": "warning", "message": "2FA not required for moderators"})
        admin_count = sum(1 for r in guild.roles if r.permissions.administrator and not r.managed)
        if admin_count > 3:
            findings.append({"type": "warning", "message": f"{admin_count} roles have Administrator permission"})
        return findings

    def _get_moderation_findings(self, guild) -> List[Dict]:
        findings = []
        mod_log_names = ["mod-log", "modlog", "moderation-log"]
        if not any(c.name.lower() in mod_log_names for c in guild.text_channels):
            findings.append({"type": "warning", "message": "No mod-log channel found"})
        try:
            rules = guild.auto_moderation_rules if hasattr(guild, 'auto_moderation_rules') else []
            if not rules:
                findings.append({"type": "critical", "message": "AutoMod not configured"})
        except Exception:
            findings.append({"type": "critical", "message": "AutoMod not configured"})
        return findings

    def _get_growth_findings(self, guild) -> List[Dict]:
        findings = []
        welcome_names = ["welcome", "general", "chat"]
        if not any(c.name.lower() in welcome_names for c in guild.text_channels):
            findings.append({"type": "warning", "message": "No welcome channel found"})
        return findings

    def _get_automation_findings(self, guild) -> List[Dict]:
        findings = []
        try:
            rules = guild.auto_moderation_rules if hasattr(guild, 'auto_moderation_rules') else []
            if not rules:
                findings.append({"type": "warning", "message": "No AutoMod rules configured"})
        except Exception:
            findings.append({"type": "warning", "message": "No AutoMod rules configured"})
        return findings

    def _get_reliability_findings(self, guild) -> List[Dict]:
        findings = []
        from aegis.core.utils import load_config
        config = load_config()
        last_backup = config.get(f"last_backup_{guild.id}")
        if not last_backup:
            findings.append({"type": "critical", "message": "No backup found"})
        return findings


# =============================================================================
# Permission Doctor (Feature 4)
# =============================================================================

class PermissionDoctor:
    """Analyzes role permissions for risks and issues."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild) -> Dict[str, Any]:
        """Analyze all roles and return findings."""
        findings = []
        for role in guild.roles:
            if role.name == "@everyone":
                continue
            perms = role.permissions

            # Check for Administrator
            if perms.administrator:
                findings.append({
                    "role": role.name,
                    "role_id": str(role.id),
                    "type": "critical",
                    "message": f"Role '{role.name}' has Administrator permission",
                    "member_count": len(role.members),
                    "severity": "critical",
                })

            # Check for dangerous combinations
            if perms.manage_guild and perms.manage_roles:
                findings.append({
                    "role": role.name,
                    "role_id": str(role.id),
                    "type": "warning",
                    "message": f"Role '{role.name}' can manage server AND roles (escalation risk)",
                    "member_count": len(role.members),
                    "severity": "high",
                })

            if perms.ban_members and perms.kick_members:
                findings.append({
                    "role": role.name,
                    "role_id": str(role.id),
                    "type": "info",
                    "message": f"Role '{role.name}' has both ban and kick permissions",
                    "member_count": len(role.members),
                    "severity": "medium",
                })

            # Check for public roles with dangerous permissions
            if len(role.members) > 10 and perms.manage_channels:
                findings.append({
                    "role": role.name,
                    "role_id": str(role.id),
                    "type": "warning",
                    "message": f"Public role '{role.name}' ({len(role.members)} members) can manage channels",
                    "member_count": len(role.members),
                    "severity": "high",
                })

        return {
            "total_roles": len([r for r in guild.roles if r.name != "@everyone"]),
            "findings": findings,
            "critical_count": len([f for f in findings if f["severity"] == "critical"]),
            "warning_count": len([f for f in findings if f["severity"] == "high"]),
            "info_count": len([f for f in findings if f["severity"] == "medium"]),
        }


# =============================================================================
# Smart Raid Detector (Feature 5)
# =============================================================================

class SmartRaidDetector:
    """Detects suspicious join patterns and raid activity."""

    def __init__(self, bot):
        self.bot = bot
        self._join_history: Dict[str, List[datetime.datetime]] = {}

    def analyze(self, guild_id: str, recent_joins: List[Dict]) -> Dict[str, Any]:
        """Analyze recent joins for raid patterns."""
        if not recent_joins:
            return {"threat_level": "low", "confidence": 0.5, "indicators": [], "recent_joins_count": 0, "suggested_actions": []}

        indicators = []
        threat_score = 0

        # Check join rate (joins per minute)
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_5min = []
        for j in recent_joins:
            ts = j.get("timestamp")
            if ts is None:
                ts = now
            elif isinstance(ts, str):
                try:
                    ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = now
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=datetime.timezone.utc)
            else:
                ts = ts.astimezone(datetime.timezone.utc)
            if (now - ts).total_seconds() < 300:
                recent_5min.append(j)
        if len(recent_5min) > 10:
            indicators.append({
                "type": "high_join_rate",
                "message": f"{len(recent_5min)} joins in the last 5 minutes",
                "severity": "high",
            })
            threat_score += 40

        # Check for new accounts
        new_accounts = [j for j in recent_joins if j.get("account_age_days", 999) < 7]
        if len(new_accounts) > 5:
            indicators.append({
                "type": "new_accounts",
                "message": f"{len(new_accounts)} accounts less than 7 days old",
                "severity": "medium",
            })
            threat_score += 20

        # Check for similar usernames
        usernames = [j.get("username", "").lower() for j in recent_joins]
        if len(usernames) > 5:
            unique_chars = set()
            for name in usernames:
                unique_chars.update(set(name))
            if len(unique_chars) < 20:
                indicators.append({
                    "type": "similar_usernames",
                    "message": "Joins have similar username patterns",
                    "severity": "medium",
                })
                threat_score += 15

        # Determine threat level
        if threat_score >= 60:
            threat_level = "critical"
        elif threat_score >= 40:
            threat_level = "high"
        elif threat_score >= 20:
            threat_level = "medium"
        else:
            threat_level = "low"

        return {
            "threat_level": threat_level,
            "threat_score": threat_score,
            "confidence": min(0.95, 0.5 + len(indicators) * 0.1),
            "indicators": indicators,
            "recent_joins_count": len(recent_joins),
            "suggested_actions": self._get_suggested_actions(threat_level),
        }

    def _get_suggested_actions(self, threat_level: str) -> List[Dict]:
        actions = []
        if threat_level in ("critical", "high"):
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode", "params": {"duration": 60}})
            actions.append({"label": "Lock Server", "action": "lock_server"})
            actions.append({"label": "Enable Verification", "action": "enable_verification"})
        elif threat_level == "medium":
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode", "params": {"duration": 30}})
            actions.append({"label": "Enable Verification", "action": "enable_verification"})
        return actions


# =============================================================================
# Smart Growth Advisor (Feature 6)
# =============================================================================

class SmartGrowthAdvisor:
    """Analyzes growth patterns and provides recommendations."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild, growth_data: Dict) -> Dict[str, Any]:
        """Analyze growth and provide recommendations."""
        recommendations = []

        # Check retention
        retention = growth_data.get("retention", {})
        if retention.get("retention_7d", 100) < 50:
            recommendations.append({
                "type": "retention",
                "title": "Low 7-Day Retention",
                "description": f"Only {retention.get('retention_7d', 0)}% of new members stay 7 days",
                "impact": "high",
                "suggestions": ["Add welcome channel", "Create onboarding flow", "Add role selection"],
            })

        # Check activity
        if growth_data.get("avg_active_users", 0) < guild.member_count * 0.1:
            recommendations.append({
                "type": "activity",
                "title": "Low Activity Rate",
                "description": "Less than 10% of members are active",
                "impact": "medium",
                "suggestions": ["Create more channels", "Add events", "Enable leveling"],
            })

        # Check channels
        if len(guild.text_channels) < 5:
            recommendations.append({
                "type": "structure",
                "title": "Few Text Channels",
                "description": "Server has fewer than 5 text channels",
                "impact": "medium",
                "suggestions": ["Add topic-specific channels", "Create categories"],
            })

        # Check welcome
        welcome_names = ["welcome", "general", "chat"]
        if not any(c.name.lower() in welcome_names for c in guild.text_channels):
            recommendations.append({
                "type": "onboarding",
                "title": "No Welcome Channel",
                "description": "New members have nowhere to introduce themselves",
                "impact": "high",
                "suggestions": ["Create #welcome channel", "Add welcome message"],
            })

        return {
            "recommendations": recommendations,
            "score": self._compute_score(guild, growth_data),
        }

    def _compute_score(self, guild, growth_data: Dict) -> int:
        score = 100
        if growth_data.get("retention", {}).get("retention_7d", 100) < 50:
            score -= 30
        if growth_data.get("avg_active_users", 0) < guild.member_count * 0.1:
            score -= 20
        if len(guild.text_channels) < 5:
            score -= 15
        return max(0, score)


# =============================================================================
# Smart Welcome Analyzer (Feature 7)
# =============================================================================

class SmartWelcomeAnalyzer:
    """Analyzes onboarding setup and recommends improvements."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild, config: Dict) -> Dict[str, Any]:
        """Analyze welcome/onboarding setup."""
        findings = []

        # Check for welcome message
        welcome_config = config.get("welcome", {})
        if not welcome_config.get("enabled"):
            findings.append({
                "type": "missing",
                "title": "Welcome Message Disabled",
                "description": "New members won't receive a welcome message",
                "auto_fix": True,
                "fix_action": "enable_welcome_message",
            })

        # Check for rules channel
        rules_names = ["rules", "server-rules", "guidelines"]
        has_rules = any(c.name.lower() in rules_names for c in guild.text_channels)
        if not has_rules:
            findings.append({
                "type": "missing",
                "title": "No Rules Channel",
                "description": "New members won't see server rules",
                "auto_fix": True,
                "fix_action": "create_rules_channel",
            })

        # Check for auto-role
        if not config.get("autorole", {}).get("enabled"):
            findings.append({
                "type": "missing",
                "title": "Auto-Role Not Enabled",
                "description": "New members won't get assigned a role automatically",
                "auto_fix": True,
                "fix_action": "enable_autorole",
            })

        # Check for verification
        if guild.verification_level.value == 0:
            findings.append({
                "type": "security",
                "title": "No Verification",
                "description": "Server has no verification level for new members",
                "auto_fix": True,
                "fix_action": "set_verification_level",
            })

        return {
            "findings": findings,
            "score": max(0, 100 - len(findings) * 20),
        }


# =============================================================================
# Smart Role Cleaner (Feature 8)
# =============================================================================

class SmartRoleCleaner:
    """Detects unused, duplicate, or obsolete roles."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild) -> Dict[str, Any]:
        """Analyze roles for cleanup opportunities."""
        unused = []
        duplicates = []
        obsolete = []

        role_names = {}
        for role in guild.roles:
            if role.name == "@everyone":
                continue

            # Check for unused (0 members, not managed)
            if len(role.members) == 0 and not role.managed:
                unused.append({
                    "id": str(role.id),
                    "name": role.name,
                    "color": role.color.value,
                    "member_count": 0,
                })

            # Check for duplicates (same name)
            name_lower = role.name.lower()
            if name_lower in role_names:
                duplicates.append({
                    "ids": [role_names[name_lower]["id"], str(role.id)],
                    "names": [role_names[name_lower]["name"], role.name],
                })
            else:
                role_names[name_lower] = {"id": str(role.id), "name": role.name}

            # Check for obsolete (very old, no special perms)
            if (len(role.members) == 0 and not role.permissions.administrator
                    and not role.permissions.manage_guild and role.created_at):
                days_old = (datetime.datetime.now(datetime.timezone.utc) - role.created_at.replace(tzinfo=datetime.timezone.utc)).days
                if days_old > 90:
                    obsolete.append({
                        "id": str(role.id),
                        "name": role.name,
                        "days_old": days_old,
                    })

        return {
            "unused": unused,
            "duplicates": duplicates,
            "obsolete": obsolete,
            "total_suggestions": len(unused) + len(duplicates) + len(obsolete),
        }


# =============================================================================
# Smart Channel Cleaner (Feature 9)
# =============================================================================

class SmartChannelCleaner:
    """Detects dead, duplicate, or archived channels."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild) -> Dict[str, Any]:
        """Analyze channels for cleanup opportunities."""
        dead = []
        duplicates = []

        channel_names = {}
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)

        for channel in guild.text_channels:
            # Check for dead channels (no activity in 30+ days)
            # Use last_message_id instead of last_message (which is cached)
            # Calculate actual channel age since creation
            created_at = getattr(channel, "created_at", None)
            if not isinstance(created_at, datetime.datetime):
                channel_age = 999
            else:
                try:
                    tz_created = created_at
                    if tz_created.tzinfo is None:
                        tz_created = tz_created.replace(tzinfo=datetime.timezone.utc)
                    channel_age = (datetime.datetime.now(datetime.timezone.utc) - tz_created).days
                except Exception:
                    channel_age = 999

            if not channel.last_message_id:
                if channel_age >= 30:
                    dead.append({
                        "id": str(channel.id),
                        "name": channel.name,
                        "type": "text",
                        "last_activity": None,
                        "days_inactive": channel_age,
                    })
            else:
                import discord
                created_at = discord.utils.snowflake_time(channel.last_message_id)
                if created_at < cutoff:
                    days_inactive = (datetime.datetime.now(datetime.timezone.utc) - created_at.replace(tzinfo=datetime.timezone.utc)).days
                    dead.append({
                        "id": str(channel.id),
                        "name": channel.name,
                        "type": "text",
                        "last_activity": created_at.isoformat(),
                        "days_inactive": days_inactive,
                    })

            # Check for duplicates (same name in different categories)
            name_lower = channel.name.lower()
            if name_lower in channel_names:
                duplicates.append({
                    "ids": [channel_names[name_lower]["id"], str(channel.id)],
                    "names": [channel_names[name_lower]["name"], channel.name],
                })
            else:
                channel_names[name_lower] = {"id": str(channel.id), "name": channel.name}

        return {
            "dead": dead,
            "duplicates": duplicates,
            "total_suggestions": len(dead) + len(duplicates),
        }


# =============================================================================
# Smart Backup Advisor (Feature 10)
# =============================================================================

class SmartBackupAdvisor:
    """Tracks backup health and recommends improvements."""

    def __init__(self, bot):
        self.bot = bot

    def analyze(self, guild_id: str) -> Dict[str, Any]:
        """Analyze backup status and provide recommendations."""
        from aegis.core.utils import load_config
        config = load_config()

        last_backup = config.get(f"last_backup_{guild_id}")
        findings = []

        if not last_backup:
            findings.append({
                "type": "critical",
                "title": "No Backup Found",
                "description": "No backup has been created for this server",
                "auto_fix": True,
                "fix_action": "create_backup",
            })
        else:
            try:
                last_date = datetime.datetime.fromisoformat(last_backup)
                days_since = (datetime.datetime.now(datetime.timezone.utc) - last_date).days

                if days_since > 14:
                    findings.append({
                        "type": "critical",
                        "title": "Backup Stale",
                        "description": f"Last backup was {days_since} days ago",
                        "auto_fix": True,
                        "fix_action": "create_backup",
                    })
                elif days_since > 7:
                    findings.append({
                        "type": "warning",
                        "title": "Backup Aging",
                        "description": f"Last backup was {days_since} days ago",
                        "auto_fix": True,
                        "fix_action": "create_backup",
                    })
            except (ValueError, TypeError):
                findings.append({
                    "type": "warning",
                    "title": "Invalid Backup Date",
                    "description": "Could not parse last backup date",
                    "auto_fix": False,
                })

        return {
            "findings": findings,
            "last_backup": last_backup,
            "protection_score": max(0, 100 - len(findings) * 30),
        }


# =============================================================================
# Smart Incident Timeline (Feature 11)
# =============================================================================

class SmartIncidentTimeline:
    """Correlates events into a unified incident timeline."""

    def __init__(self, bot):
        self.bot = bot

    def build_timeline(self, guild_id: str, hours: int = 24) -> Dict[str, Any]:
        """Build a correlated timeline of events."""
        from aegis.analytics.engine import get_analytics_engine

        engine = get_analytics_engine()
        if not engine:
            return {"events": [], "incidents": []}

        events = []
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)

        # Get moderation events
        try:
            from aegis.db.analytics_models import ModerationEvent
            session = engine._session_factory()
            try:
                mod_events = session.query(ModerationEvent).filter(
                    ModerationEvent.guild_id == guild_id,
                    ModerationEvent.timestamp >= cutoff,
                ).order_by(ModerationEvent.timestamp).all()

                for e in mod_events:
                    events.append({
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                        "type": e.event_type,
                        "category": e.automod_category or "moderation",
                        "user_id": e.user_id,
                        "moderator_id": e.moderator_id,
                        "details": e.reason or "",
                    })
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Error building timeline: {e}")

        # Group events into incidents
        incidents = self._correlate_incidents(events)

        return {
            "events": events[-50:],  # Last 50 events
            "incidents": incidents,
            "event_count": len(events),
            "incident_count": len(incidents),
        }

    def _correlate_incidents(self, events: List[Dict]) -> List[Dict]:
        """Group related events into incidents."""
        if not events:
            return []

        incidents = []
        current_incident = None

        for event in events:
            ts = event.get("timestamp")
            if not ts:
                continue

            event_time = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))

            if current_incident is None:
                current_incident = {
                    "start": ts,
                    "end": ts,
                    "events": [event],
                    "types": [event.get("type", "unknown")],
                }
            else:
                last_time = datetime.datetime.fromisoformat(current_incident["end"].replace("Z", "+00:00"))
                gap = (event_time - last_time).total_seconds()

                if gap < 300:  # 5 minutes = same incident
                    current_incident["end"] = ts
                    current_incident["events"].append(event)
                    if event.get("type", "unknown") not in current_incident["types"]:
                        current_incident["types"].append(event.get("type", "unknown"))
                else:
                    if len(current_incident["events"]) > 1:
                        incidents.append(current_incident)
                    current_incident = {
                        "start": ts,
                        "end": ts,
                        "events": [event],
                        "types": [event.get("type", "unknown")],
                    }

        if current_incident and len(current_incident["events"]) > 1:
            incidents.append(current_incident)

        return incidents


# =============================================================================
# Server Maturity Score (Feature 12)
# =============================================================================

class ServerMaturityScore:
    """Computes overall server maturity across multiple dimensions."""

    def __init__(self, bot):
        self.bot = bot
        self.config_doctor = ConfigDoctor(bot)
        self.permission_doctor = PermissionDoctor(bot)

    def compute(self, guild, analytics_engine=None) -> Dict[str, Any]:
        """Compute full maturity score."""
        config_score = self.config_doctor.diagnose(guild)
        perm_analysis = self.permission_doctor.analyze(guild)

        # Community health from analytics
        community_health = self._compute_community_health(guild, analytics_engine)

        # Compute final scores
        dimensions = {
            "security": config_score["dimensions"]["security"]["score"],
            "moderation": config_score["dimensions"]["moderation"]["score"],
            "growth": config_score["dimensions"]["growth"]["score"],
            "automation": config_score["dimensions"]["automation"]["score"],
            "reliability": config_score["dimensions"]["reliability"]["score"],
            "community_health": community_health,
        }

        overall = int(sum(dimensions.values()) / len(dimensions))

        # Penalty for permission issues
        if perm_analysis["critical_count"] > 0:
            overall = max(0, overall - perm_analysis["critical_count"] * 5)

        return {
            "overall": overall,
            "dimensions": dimensions,
            "permission_findings": perm_analysis["findings"],
            "recommendations": self._generate_recommendations(dimensions, perm_analysis),
        }

    def _compute_community_health(self, guild, analytics_engine) -> int:
        """Compute community health score from analytics."""
        score = 70  # Base score

        if analytics_engine:
            try:
                overview = analytics_engine.get_overview(str(guild.id))
                if overview:
                    active = overview.get("active_users_7d", 0)
                    total = guild.member_count
                    if total > 0:
                        activity_ratio = active / total
                        if activity_ratio > 0.3:
                            score += 20
                        elif activity_ratio > 0.1:
                            score += 10
                        elif activity_ratio < 0.05:
                            score -= 20
            except Exception:
                pass

        return max(0, min(100, score))

    def _generate_recommendations(self, dimensions: Dict, perm_analysis: Dict) -> List[Dict]:
        """Generate recommendations based on scores."""
        recs = []
        for dim, score in dimensions.items():
            if score < 60:
                recs.append({
                    "dimension": dim,
                    "score": score,
                    "message": f"{dim.replace('_', ' ').title()} needs improvement (score: {score}/100)",
                })
        if perm_analysis["critical_count"] > 0:
            recs.append({
                "dimension": "permissions",
                "score": 0,
                "message": f"{perm_analysis['critical_count']} critical permission issues found",
            })
        return recs


# =============================================================================
# One-Click Auto Fix (Feature 2)
# =============================================================================

class AutoFixEngine:
    """Executes one-click fixes for recommendations."""

    def __init__(self, bot):
        self.bot = bot

    async def execute_fix(self, guild, action: str, params: Dict = None) -> AutoFixResult:
        """Execute an auto-fix action."""
        params = params or {}

        try:
            if action == "set_verification_level":
                return await self._fix_verification(guild, params)
            elif action == "create_mod_log_channel":
                return await self._fix_create_channel(guild, "mod-log", "Moderation logs")
            elif action == "create_backup":
                return await self._fix_create_backup(guild)
            elif action == "archive_inactive_channels":
                return await self._fix_archive_channels(guild, params)
            elif action == "remove_unused_roles":
                return await self._fix_remove_roles(guild, params)
            elif action == "create_welcome_channel":
                return await self._fix_create_channel(guild, "welcome", "Welcome new members!")
            elif action == "create_rules_channel":
                return await self._fix_create_channel(guild, "rules", "Server Rules")
            elif action == "enable_welcome_message":
                return await self._fix_enable_welcome(guild)
            elif action == "enable_autorole":
                return await self._fix_enable_autorole(guild)
            elif action == "enable_raid_mode":
                return await self._fix_enable_raid_mode(guild)
            elif action == "slowmode_all_channels":
                return await self._fix_slowmode_all_channels(guild, params)
            elif action == "restrict_new_members":
                return await self._fix_restrict_new_members(guild)
            elif action == "lock_server":
                return await self._fix_lock_server(guild)
            elif action == "enable_slowmode":
                return await self._fix_slowmode_all_channels(guild, {"duration": params.get("duration", 5)})
            elif action == "mute_spammers":
                return await self._fix_mute_users(guild, params.get("users", []))
            elif action == "lock_channel":
                return await self._fix_lock_channel(guild, params)
            elif action == "mute_user":
                return await self._fix_mute_users(guild, [params.get("user_id")] if params.get("user_id") else [])
            elif action == "delete_campaign":
                return await self._fix_delete_campaign(guild, params)
            else:
                return AutoFixResult(
                    success=False,
                    action=action,
                    details=f"Unknown action: {action}",
                    rollback_available=False,
                )
        except Exception as e:
            return AutoFixResult(
                success=False,
                action=action,
                details=f"Error: {str(e)}",
                rollback_available=False,
                error=str(e),
            )

    async def _fix_verification(self, guild, params: Dict) -> AutoFixResult:
        import discord
        old_level = guild.verification_level
        try:
            await guild.edit(verification_level=discord.VerificationLevel.LOW)
            return AutoFixResult(
                success=True,
                action="set_verification_level",
                details=f"Verification level set to LOW (was {old_level.name})",
                rollback_available=True,
                rollback_data={"old_level": old_level.value},
            )
        except Exception as e:
            return AutoFixResult(success=False, action="set_verification_level", details=str(e), rollback_available=False, error=str(e))

    async def _fix_create_channel(self, guild, name: str, topic: str) -> AutoFixResult:
        try:
            await guild.create_text_channel(name, topic=topic)
            return AutoFixResult(
                success=True,
                action=f"create_{name}_channel",
                details=f"Created #{name} channel",
                rollback_available=True,
                rollback_data={"channel_name": name},
            )
        except Exception as e:
            return AutoFixResult(success=False, action=f"create_{name}_channel", details=str(e), rollback_available=False, error=str(e))

    async def _fix_create_backup(self, guild) -> AutoFixResult:
        from aegis.bot.restructuring import backup_guild_layout
        try:
            backup = backup_guild_layout(guild)
            from aegis.core.utils import load_config, save_config
            config = load_config()
            config[f"last_backup_{guild.id}"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_config(config)
            return AutoFixResult(
                success=True,
                action="create_backup",
                details="Backup created successfully",
                rollback_available=False,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="create_backup", details=str(e), rollback_available=False, error=str(e))

    async def _fix_archive_channels(self, guild, params: Dict) -> AutoFixResult:
        channels = params.get("channels", [])
        removed = []
        errors = []
        
        # Find or create archive category
        archive_category = None
        for cat in guild.categories:
            if "archive" in cat.name.lower():
                archive_category = cat
                break
        
        if not archive_category:
            try:
                archive_category = await guild.create_category("📦 ARCHIVED CHANNELS")
            except Exception as e:
                return AutoFixResult(success=False, action="archive_channels", details=f"Failed to create archive category: {e}", rollback_available=False, error=str(e))
        
        async def archive_one(channel):
            try:
                await channel.edit(category=archive_category)
                return channel.name, None
            except Exception as e:
                return channel.name, str(e)

        tasks = []
        for channel_name in channels:
            for channel in guild.text_channels:
                if channel.name == channel_name:
                    tasks.append(archive_one(channel))
                    break

        if tasks:
            import asyncio
            results = await asyncio.gather(*tasks)
            for name, err in results:
                if err:
                    errors.append(f"{name}: {err}")
                else:
                    removed.append(name)
        
        success = len(removed) > 0
        details = f"Archived {len(removed)} channels" + (f", {len(errors)} failed" if errors else "")
        return AutoFixResult(
            success=success,
            action="archive_inactive_channels",
            details=details,
            rollback_available=True,
            rollback_data={"archived": removed, "errors": errors},
            error=errors[0] if errors and not success else None
        )

    async def _fix_remove_roles(self, guild, params: Dict) -> AutoFixResult:
        roles = params.get("roles", [])
        removed = []
        errors = []
        
        async def remove_one(role):
            try:
                await role.delete(reason="Smart Features: Removing unused role")
                return role.name, None
            except Exception as e:
                return role.name, str(e)

        tasks = []
        for role_name in roles:
            for role in guild.roles:
                if role.name == role_name and len(role.members) == 0:
                    tasks.append(remove_one(role))
                    break

        if tasks:
            import asyncio
            results = await asyncio.gather(*tasks)
            for name, err in results:
                if err:
                    errors.append(f"{name}: {err}")
                else:
                    removed.append(name)
        
        success = len(removed) > 0
        details = f"Removed {len(removed)} unused roles" + (f", {len(errors)} failed" if errors else "")
        return AutoFixResult(
            success=success,
            action="remove_unused_roles",
            details=details,
            rollback_available=False,
            rollback_data={"removed": removed, "errors": errors},
            error=errors[0] if errors and not success else None
        )

    async def _fix_enable_welcome(self, guild) -> AutoFixResult:
        from aegis.core.utils import load_config, save_config
        try:
            config = load_config()
            guild_config = config.get("guild_configs", {}).get(str(guild.id), {})
            guild_config["welcome"] = {"enabled": True}
            if "guild_configs" not in config:
                config["guild_configs"] = {}
            config["guild_configs"][str(guild.id)] = guild_config
            save_config(config)
            return AutoFixResult(
                success=True,
                action="enable_welcome_message",
                details="Welcome message enabled in config",
                rollback_available=True,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="enable_welcome_message", details=str(e), rollback_available=False, error=str(e))

    async def _fix_enable_autorole(self, guild) -> AutoFixResult:
        from aegis.core.utils import load_config, save_config
        try:
            config = load_config()
            guild_config = config.get("guild_configs", {}).get(str(guild.id), {})
            guild_config["autorole"] = {"enabled": True}
            if "guild_configs" not in config:
                config["guild_configs"] = {}
            config["guild_configs"][str(guild.id)] = guild_config
            save_config(config)
            return AutoFixResult(
                success=True,
                action="enable_autorole",
                details="Auto-role enabled in config",
                rollback_available=True,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="enable_autorole", details=str(e), rollback_available=False, error=str(e))

    async def _fix_enable_raid_mode(self, guild) -> AutoFixResult:
        import discord
        try:
            await guild.edit(verification_level=discord.VerificationLevel.HIGH)
            return AutoFixResult(
                success=True,
                action="enable_raid_mode",
                details="Raid mode enabled (verification level set to HIGH)",
                rollback_available=False,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="enable_raid_mode", details=str(e), rollback_available=False, error=str(e))

    async def _fix_slowmode_all_channels(self, guild, params: Dict) -> AutoFixResult:
        duration = params.get("duration", 15)
        updated = []
        errors = []
        for channel in guild.text_channels:
            try:
                await channel.edit(slowmode_delay=duration)
                updated.append(channel.name)
            except Exception as e:
                errors.append(f"{channel.name}: {e}")
        success = len(updated) > 0
        return AutoFixResult(
            success=success,
            action="slowmode_all_channels",
            details=f"Slowmode set to {duration}s on {len(updated)} channels" + (f", {len(errors)} failed" if errors else ""),
            rollback_available=False,
            error=errors[0] if errors and not success else None
        )

    async def _fix_restrict_new_members(self, guild) -> AutoFixResult:
        import discord
        try:
            await guild.edit(verification_level=discord.VerificationLevel.MEDIUM)
            return AutoFixResult(
                success=True,
                action="restrict_new_members",
                details="New members restricted (verification level set to MEDIUM)",
                rollback_available=False,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="restrict_new_members", details=str(e), rollback_available=False, error=str(e))

    async def _fix_lock_server(self, guild) -> AutoFixResult:
        """Lock server by setting verification to highest and denying send for @everyone."""
        import discord
        try:
            await guild.edit(verification_level=discord.VerificationLevel.HIGH)
            overwrites = guild.default_role.overwrites
            overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False)
            await guild.default_role.edit(overwrites=overwrites)
            return AutoFixResult(
                success=True,
                action="lock_server",
                details="Server locked: verification HIGH, @everyone cannot send messages",
                rollback_available=True,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="lock_server", details=str(e), rollback_available=False, error=str(e))

    async def _fix_mute_users(self, guild, user_ids: list) -> AutoFixResult:
        """Timeout multiple users for 10 minutes."""
        import discord
        muted = []
        errors = []
        for uid in user_ids:
            try:
                member = guild.get_member(int(uid))
                if member:
                    await member.timeout(datetime.timedelta(minutes=10), reason="Spam/raid auto-mute")
                    muted.append(str(uid))
            except Exception as e:
                errors.append(f"{uid}: {e}")
        return AutoFixResult(
            success=len(muted) > 0,
            action="mute_spammers",
            details=f"Muted {len(muted)} users for 10 minutes" + (f", {len(errors)} failed" if errors else ""),
            rollback_available=False,
            error=errors[0] if errors and not muted else None,
        )

    async def _fix_lock_channel(self, guild, params: Dict) -> AutoFixResult:
        """Deny send_messages for @everyone on a specific channel."""
        import discord
        channel_id = params.get("channel_id")
        if not channel_id:
            return AutoFixResult(success=False, action="lock_channel", details="No channel_id provided", rollback_available=False)
        try:
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return AutoFixResult(success=False, action="lock_channel", details=f"Channel {channel_id} not found", rollback_available=False)
            overwrites = channel.overwrites
            overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False)
            await channel.edit(overwrites=overwrites, reason="Auto-fix: lock channel due to spam")
            return AutoFixResult(
                success=True,
                action="lock_channel",
                details=f"Locked #{channel.name} — @everyone cannot send messages",
                rollback_available=True,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="lock_channel", details=str(e), rollback_available=False, error=str(e))

    async def _fix_delete_campaign(self, guild, params: Dict) -> AutoFixResult:
        """Delete recent messages from spam campaign users."""
        channel_id = params.get("channel_id")
        user_ids = params.get("users", [])
        if not channel_id:
            return AutoFixResult(success=False, action="delete_campaign", details="No channel_id provided", rollback_available=False)
        try:
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return AutoFixResult(success=False, action="delete_campaign", details=f"Channel {channel_id} not found", rollback_available=False)
            deleted = 0
            async for msg in channel.history(limit=100):
                if str(msg.author.id) in [str(u) for u in user_ids]:
                    try:
                        await msg.delete()
                        deleted += 1
                    except Exception:
                        pass
            return AutoFixResult(
                success=True,
                action="delete_campaign",
                details=f"Deleted {deleted} spam messages from #{channel.name}",
                rollback_available=False,
            )
        except Exception as e:
            return AutoFixResult(success=False, action="delete_campaign", details=str(e), rollback_available=False, error=str(e))
