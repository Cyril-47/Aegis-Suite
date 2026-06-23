import logging
from aegis.intelligence.raid_detector import AdaptiveRaidDetector
from aegis.intelligence.sentiment import SmartSentimentAnalyzer
from aegis.intelligence.spam_detector import FuzzySpamDetector
from aegis.intelligence.activity import ActivityIntelligence
from aegis.intelligence.automation import AutomationEngine

logger = logging.getLogger("aegis.intelligence.registry")

_local_raid_detector = None
_local_sentiment_analyzer = None
_local_spam_detector = None
_local_activity_intelligence = None
_local_automation_engine = None

def get_bot():
    try:
        from aegis.bot.bot_manager import get_bot as get_active_bot
        return get_active_bot()
    except Exception:
        return None

def get_raid_detector():
    global _local_raid_detector
    bot = get_bot()
    if bot:
        if not hasattr(bot, "raid_detector"):
            bot.raid_detector = AdaptiveRaidDetector()
        return bot.raid_detector
    if _local_raid_detector is None:
        _local_raid_detector = AdaptiveRaidDetector()
    return _local_raid_detector

def get_sentiment_analyzer():
    global _local_sentiment_analyzer
    bot = get_bot()
    if bot:
        if not hasattr(bot, "sentiment_analyzer"):
            bot.sentiment_analyzer = SmartSentimentAnalyzer()
        return bot.sentiment_analyzer
    if _local_sentiment_analyzer is None:
        _local_sentiment_analyzer = SmartSentimentAnalyzer()
    return _local_sentiment_analyzer

def get_spam_detector():
    global _local_spam_detector
    bot = get_bot()
    if bot:
        if not hasattr(bot, "spam_detector"):
            bot.spam_detector = FuzzySpamDetector()
        return bot.spam_detector
    if _local_spam_detector is None:
        _local_spam_detector = FuzzySpamDetector()
    return _local_spam_detector

def get_activity_intelligence():
    global _local_activity_intelligence
    bot = get_bot()
    if bot:
        if not hasattr(bot, "activity_intelligence"):
            bot.activity_intelligence = ActivityIntelligence()
        return bot.activity_intelligence
    if _local_activity_intelligence is None:
        _local_activity_intelligence = ActivityIntelligence()
    return _local_activity_intelligence

def get_automation_engine():
    global _local_automation_engine
    bot = get_bot()
    if bot:
        if not hasattr(bot, "automation_engine"):
            bot.automation_engine = AutomationEngine()
        return bot.automation_engine
    if _local_automation_engine is None:
        _local_automation_engine = AutomationEngine()
    return _local_automation_engine
