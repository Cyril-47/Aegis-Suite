"""
Feature 2: Smart Sentiment Moderation

Uses vaderSentiment for local sentiment analysis.
Detects harassment, aggressive behavior, and repeated hostility.
"""

import logging
import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict
from dataclasses import dataclass

logger = logging.getLogger("aegis.intelligence.sentiment")

# Try to import vaderSentiment, fall back to basic analysis if not available
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    VADER_AVAILABLE = True
except ImportError:
    VADER_AVAILABLE = False
    logger.warning("vaderSentiment not installed. Using basic sentiment analysis.")


@dataclass
class SentimentEvent:
    """A single sentiment event."""
    user_id: str
    channel_id: str
    guild_id: str
    message: str
    score: float  # -1 to 1
    negativity: float  # 0 to 1
    timestamp: datetime.datetime

    @property
    def is_toxic(self) -> bool:
        return self.negativity > 0.3



class SmartSentimentAnalyzer:
    """
    Local sentiment analysis using vaderSentiment.
    Detects harassment, aggression, and repeated hostility.
    """

    MIN_MESSAGES_FOR_STABLE_SCORE = 20

    def __init__(self):
        self._analyzer = SentimentIntensityAnalyzer() if VADER_AVAILABLE else None
        self._user_sentiment: Dict[str, List[SentimentEvent]] = defaultdict(list)
        self._channel_sentiment: Dict[str, List[SentimentEvent]] = defaultdict(list)
        self._guild_sentiment: Dict[str, List[SentimentEvent]] = defaultdict(list)

    def _normalize_text(self, message: str) -> str:
        """Normalize shortcut words, leetspeak, and slang before analysis."""
        import re

        text = message.lower().strip()

        # Expand common abbreviations
        abbreviations = {
            "kys": "kill yourself",
            "stfu": "shut the fuck up",
            "idgaf": "i don't give a fuck",
            "gtfo": "get the fuck out",
            "smh": "shaking my head",
            "tbh": "to be honest",
            "imo": "in my opinion",
            "ngl": "not gonna lie",
            "stg": "swear to god",
            "istg": "i swear to god",
            "wtf": "what the fuck",
            "lmao": "",
            "lol": "",
            "rofl": "",
            "brb": "",
            "afk": "",
            "gg": "",
            "ez": "easy",
            "noob": "newbie",
            "rekt": "wrecked",
            "ur": "you are",
            "u": "you",
            "r": "are",
            "y": "why",
            "pos": "piece of shit",
            "fos": "full of shit",
            "stg": "swear to god",
        }

        # F-U spacing normalization (before abbreviation expansion)
        text = re.sub(r'\bf\s+u\b', 'fuck you', text)
        text = re.sub(r'\bf\s+off\b', 'fuck off', text)
        text = re.sub(r'\bs\s+u\s+c\s+k\b', 'suck', text)
        text = re.sub(r'\bh\s+a\s+t\s+e\b', 'hate', text)

        for abbr, expanded in abbreviations.items():
            text = re.sub(r'\b' + re.escape(abbr) + r'\b', expanded, text)

        # H8 normalization (h8 = hate)
        text = re.sub(r'\bh8\b', 'hate', text)
        text = re.sub(r'\bh8ful\b', 'hateful', text)
        text = re.sub(r'\bh8ing\b', 'hating', text)

        # Apostrophe normalization
        text = text.replace("youre", "you're")
        text = text.replace("dont", "don't")
        text = text.replace("cant", "can't")
        text = text.replace("wont", "won't")
        text = text.replace("isnt", "isn't")
        text = text.replace("doesnt", "doesn't")

        # Leetspeak normalization
        leet_map = {
            "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
            "7": "t", "8": "b", "@": "a", "$": "s", "!": "i",
        }
        for leet, char in leet_map.items():
            text = text.replace(leet, char)

        # Normalize repeated characters (e.g., "stuuuuupid" -> "stupid", "dieee" -> "die")
        # Only reduce 3+ repeats to prevent breaking normal words like "kill"
        text = re.sub(r'(.)\1{2,}', r'\1', text)

        # Remove extra spaces
        text = re.sub(r'\s+', ' ', text).strip()

        return text

    def analyze_message(self, user_id: str, channel_id: str, message: str, guild_id: str = "") -> Dict[str, Any]:
        """
        Analyze sentiment of a single message.
        
        Returns:
            Dict with sentiment score, negativity, and flags.
        """
        normalized = self._normalize_text(message)

        if self._analyzer:
            scores = self._analyzer.polarity_scores(normalized)
            compound = scores["compound"]
            negativity = scores["neg"]

            # Post-vader boost for words vader misses
            boost_words = [
                "trash", "garbage", "worthless", "useless", "pathetic",
                "disgusting", "terrible", "horrible", "awful", "worst",
                "loser", "noob", "trashy", "cringe", "toxic",
                "fuck", "fucking", "fucked", "damn",
            ]
            words = normalized.split()
            boost_count = sum(1 for w in words if w in boost_words)
            if boost_count > 0:
                negativity = min(1.0, negativity + boost_count * 0.35)
                if compound >= 0:
                    compound = max(-1.0, compound - boost_count * 0.4)
        else:
            # Basic fallback analysis
            compound, negativity = self._basic_sentiment(normalized)
        
        # Scale compound score from range [-1, 1] to [0, 1]
        scaled_score = (compound + 1.0) / 2.0

        # Create event
        event = SentimentEvent(
            user_id=user_id,
            channel_id=channel_id,
            guild_id=guild_id,
            message=message,
            score=scaled_score,
            negativity=negativity,
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        
        # Store event
        self._user_sentiment[user_id].append(event)
        self._channel_sentiment[channel_id].append(event)
        if guild_id:
            self._guild_sentiment[guild_id].append(event)
        
        # Cleanup old events (keep last 24 hours)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        self._user_sentiment[user_id] = [e for e in self._user_sentiment[user_id] if e.timestamp > cutoff]
        self._channel_sentiment[channel_id] = [e for e in self._channel_sentiment[channel_id] if e.timestamp > cutoff]
        if guild_id:
            self._guild_sentiment[guild_id] = [e for e in self._guild_sentiment[guild_id] if e.timestamp > cutoff]
        
        # Detect flags
        flags = []
        if negativity > 0.7:
            flags.append("high_negativity")
        if negativity > 0.5 and self._check_repeated_hostility(user_id):
            flags.append("repeated_hostility")
        if self._check_aggressive_pattern(user_id):
            flags.append("aggressive_pattern")
        
        return {
            "score": scaled_score,
            "negativity": negativity,
            "flags": flags,
            "is_negative": compound < -0.1,
            "is_toxic": negativity > 0.3,
        }

    def _basic_sentiment(self, message: str) -> tuple:
        """Basic sentiment analysis without vaderSentiment."""
        negative_words = [
            "hate", "stupid", "idiot", "loser", "suck", "terrible", "awful",
            "worst", "trash", "garbage", "die", "kill", "annoying", "boring",
            "ugly", "fat", "dumb", "moron", "pathetic", "disgusting",
            "shut", "damn", "hell", "cringe", "toxic", "spam", "noob",
            "worthless", "useless", "idiots", "haters", "losers",
            "stupidity", "idiotic", "loser", "sucks", "hating", "killed",
        ]

        positive_words = [
            "love", "great", "awesome", "amazing", "wonderful", "fantastic",
            "excellent", "best", "happy", "thank", "appreciate", "good",
            "nice", "beautiful", "brilliant", "perfect", "enjoy", "fun",
        ]

        words = message.lower().split()
        neg_count = sum(1 for w in words if w in negative_words)
        pos_count = sum(1 for w in words if w in positive_words)

        if neg_count > 0:
            score = -min(1.0, neg_count * 0.3)
            negativity = min(1.0, neg_count * 0.35)
        elif pos_count > 0:
            score = min(1.0, pos_count * 0.25)
            negativity = 0.0
        else:
            score = 0.0
            negativity = 0.0

        return score, negativity

    def _check_repeated_hostility(self, user_id: str) -> bool:
        """Check if user has repeated negative messages."""
        events = self._user_sentiment.get(user_id, [])
        if len(events) < 3:
            return False
        
        # Check last 10 messages
        recent = events[-10:]
        negative_count = sum(1 for e in recent if e.negativity > 0.3)
        
        return negative_count >= 3

    def _check_aggressive_pattern(self, user_id: str) -> bool:
        """Check for aggressive message patterns."""
        events = self._user_sentiment.get(user_id, [])
        if len(events) < 5:
            return False
        
        # Check for rapid negative messages
        recent = events[-5:]
        now = datetime.datetime.now(datetime.timezone.utc)
        
        rapid_negative = 0
        for e in recent:
            if e.negativity > 0.3 and (now - e.timestamp).total_seconds() < 300:
                rapid_negative += 1
        
        return rapid_negative >= 3

    def get_user_sentiment(self, user_id: str, days: int = 7) -> Dict[str, Any]:
        """Get aggregated sentiment for a user."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        events = [e for e in self._user_sentiment.get(user_id, []) if e.timestamp > cutoff]
        
        if not events:
            return {"user_id": user_id, "message_count": 0, "avg_score": 0.85, "toxicity_rate": 0}
        
        avg_score = sum(e.score for e in events) / len(events)
        toxicity_rate = sum(1 for e in events if e.is_toxic) / len(events) if events else 0
        
        return {
            "user_id": user_id,
            "message_count": len(events),
            "avg_score": round(avg_score, 3),
            "toxicity_rate": round(toxicity_rate, 3),
            "is_repeatedly_hostile": self._check_repeated_hostility(user_id),
        }

    def get_channel_sentiment(self, channel_id: str, days: int = 7) -> Dict[str, Any]:
        """Get aggregated sentiment for a channel."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        events = [e for e in self._channel_sentiment.get(channel_id, []) if e.timestamp > cutoff]
        
        if not events:
            return {"channel_id": channel_id, "message_count": 0, "avg_score": 0.85, "toxicity_rate": 0}
        
        avg_score = sum(e.score for e in events) / len(events)
        toxicity_rate = sum(1 for e in events if e.is_toxic) / len(events) if events else 0
        
        return {
            "channel_id": channel_id,
            "message_count": len(events),
            "avg_score": round(avg_score, 3),
            "toxicity_rate": round(toxicity_rate, 3),
        }

    def get_most_toxic_channels(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Get channels with the highest average toxicity."""
        channel_toxicity = []
        for cid, events in self._channel_sentiment.items():
            if not events:
                continue
            toxic_count = sum(1 for e in events if e.is_toxic)
            rate = toxic_count / len(events)
            channel_toxicity.append({
                "channel_id": cid,
                "toxicity_rate": round(rate, 3),
                "message_count": len(events)
            })
        channel_toxicity.sort(key=lambda x: x["toxicity_rate"], reverse=True)
        return channel_toxicity[:limit]

    def get_community_health(self, guild_id: str) -> Dict[str, Any]:
        """Get overall community health metrics with stability threshold."""
        all_events = self._guild_sentiment.get(str(guild_id), [])

        if not all_events:
            return {
                "overall_score": 0.85,
                "positivity_rate": 0.85,
                "toxicity_rate": 0.0,
                "harassment_detected": False,
                "hostile_users": [],
                "trend": "stable",
                "message_count": 0,
                "status": "empty",
            }

        if len(all_events) < self.MIN_MESSAGES_FOR_STABLE_SCORE:
            return {
                "overall_score": 0.80,
                "positivity_rate": 0.80,
                "toxicity_rate": 0.0,
                "harassment_detected": False,
                "hostile_users": [],
                "trend": "stable",
                "message_count": len(all_events),
                "status": "learning",
            }

        avg_score = sum(e.score for e in all_events) / len(all_events)
        positivity_rate = sum(1 for e in all_events if e.score > 0.55) / len(all_events)
        toxicity_rate = sum(1 for e in all_events if e.negativity > 0.3) / len(all_events)

        hostile_users = set()
        for user_id, events in self._user_sentiment.items():
            if self._check_repeated_hostility(user_id):
                hostile_users.add(user_id)

        now = datetime.datetime.now(datetime.timezone.utc)
        recent_events = [e for e in all_events if (now - e.timestamp).total_seconds() < 3600]
        older_events = [e for e in all_events if (now - e.timestamp).total_seconds() >= 3600]

        recent_avg = sum(e.score for e in recent_events) / len(recent_events) if recent_events else 0.85
        older_avg = sum(e.score for e in older_events) / len(older_events) if older_events else 0.85

        if recent_avg > older_avg + 0.05:
            trend = "improving"
        elif recent_avg < older_avg - 0.05:
            trend = "declining"
        else:
            trend = "stable"

        return {
            "overall_score": round(avg_score, 3),
            "positivity_rate": round(positivity_rate, 3),
            "toxicity_rate": round(toxicity_rate, 3),
            "harassment_detected": len(hostile_users) >= 2,
            "hostile_users": list(hostile_users),
            "trend": trend,
            "message_count": len(all_events),
            "status": "stable",
        }

