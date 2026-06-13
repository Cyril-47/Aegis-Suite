import logging
from typing import List, Dict, Any
from aegis.core.utils import load_config, get_guild_config

logger = logging.getLogger("aegis.analytics.recommender")


RECOMMENDATION_RULES = [
    {
        "id": "enable_raid_protection",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("anti_raid_settings", {}).get("enabled", False),
        "title": "Enable Raid Protection",
        "description": "Protect your server from mass-join attacks",
        "impact": "+5 Security",
        "category": "security",
        "priority": 1,
    },
    {
        "id": "create_welcome_messages",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("welcome_settings", {}).get("enabled", False),
        "title": "Create Welcome Messages",
        "description": "Greet new members and auto-assign roles",
        "impact": "+8 Health",
        "category": "engagement",
        "priority": 2,
    },
    {
        "id": "set_up_mod_log",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("automod_settings", {}).get("log_channel_id"),
        "title": "Set Up Mod-Log Channel",
        "description": "Create a channel for moderation action logs",
        "impact": "+5 Moderation",
        "category": "moderation",
        "priority": 2,
    },
    {
        "id": "configure_automod",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("automod_settings", {}).get("enabled", False),
        "title": "Enable Auto-Moderation",
        "description": "Activate spam, link, and profanity filters",
        "impact": "+7 Moderation",
        "category": "moderation",
        "priority": 2,
    },
    {
        "id": "enable_ticket_sla",
        "check": lambda cfg, guild_cfg: guild_cfg.get("ticket_settings") and not guild_cfg.get("ticket_settings", {}).get("sla_hours"),
        "title": "Set Ticket SLA",
        "description": "Auto-close tickets that exceed time limits",
        "impact": "+3 Support",
        "category": "support",
        "priority": 4,
    },
    {
        "id": "setup_tickets",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("ticket_settings") or not guild_cfg.get("ticket_settings", {}).get("enabled", False),
        "title": "Enable Support Tickets",
        "description": "Set up a ticket system for member support",
        "impact": "+5 Support",
        "category": "support",
        "priority": 3,
    },
    {
        "id": "enable_leveling",
        "check": lambda cfg, guild_cfg: not guild_cfg.get("leveling_settings") or not guild_cfg.get("leveling_settings", {}).get("enabled", False),
        "title": "Enable Leveling System",
        "description": "Boost engagement with XP rewards and ranks",
        "impact": "+6 Engagement",
        "category": "engagement",
        "priority": 3,
    },
]


def get_recommendations(guild_id: str) -> List[Dict[str, Any]]:
    """Get active recommendations for a guild."""
    try:
        config = load_config()
        guild_cfg = get_guild_config(guild_id)
        results = []
        for rule in RECOMMENDATION_RULES:
            try:
                if rule["check"](config, guild_cfg):
                    results.append({
                        "id": rule["id"],
                        "title": rule["title"],
                        "description": rule["description"],
                        "impact": rule["impact"],
                        "category": rule["category"],
                        "priority": rule["priority"],
                    })
            except Exception:
                logger.warning(f"Recommendation rule {rule['id']} check failed")
        results.sort(key=lambda r: r["priority"])
        return results
    except Exception:
        logger.exception("Failed to get recommendations")
        return []


def get_recommendation_summary(guild_id: str) -> Dict[str, Any]:
    """Get a summary of recommendations with potential health impact."""
    recs = get_recommendations(guild_id)
    impact_map = {
        "+5 Security": 5, "+8 Health": 8, "+5 Moderation": 5,
        "+7 Moderation": 7, "+3 Support": 3, "+5 Support": 5, "+6 Engagement": 6,
    }
    total_impact = sum(impact_map.get(r["impact"], 0) for r in recs)
    return {
        "recommendations": recs,
        "total_count": len(recs),
        "potential_health_boost": total_impact,
        "categories": list(set(r["category"] for r in recs)),
    }
