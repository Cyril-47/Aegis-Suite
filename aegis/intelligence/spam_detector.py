"""
Feature 3: Fuzzy Spam Detection

Uses Levenshtein similarity to detect spam campaigns.
Tracks recent messages and detects repeated/similar content.
"""

import logging
import datetime
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass

logger = logging.getLogger("aegis.intelligence.spam")


@dataclass
class MessageRecord:
    """A recorded message for spam analysis."""
    user_id: str
    channel_id: str
    content: str
    timestamp: datetime.datetime


class FuzzySpamDetector:
    """
    Fuzzy spam detection using Levenshtein similarity.
    Detects repeated messages, slight variations, and raid spam.
    """

    def __init__(self):
        self._recent_messages: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._detected_campaigns: List[Dict[str, Any]] = []
        self.SIMILARITY_THRESHOLD = 0.9  # 90% similarity
        self.TIME_WINDOW = 300  # 5 minutes

    def record_message(self, user_id: str, channel_id: str, content: str):
        """Record a message for spam analysis."""
        message = MessageRecord(
            user_id=user_id,
            channel_id=channel_id,
            content=content.strip(),
            timestamp=datetime.datetime.now(datetime.timezone.utc),
        )
        
        self._recent_messages[channel_id].append(message)
        
        # Cleanup old messages
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=self.TIME_WINDOW * 2)
        while self._recent_messages[channel_id] and self._recent_messages[channel_id][0].timestamp < cutoff:
            self._recent_messages[channel_id].popleft()

    def analyze(self, user_id: str, channel_id: str, content: str) -> Dict[str, Any]:
        """
        Analyze a message for spam patterns.
        
        Returns:
            Dict with spam detection results.
        """
        content_lower = content.strip().lower()
        
        # Check for exact duplicates
        exact_matches = self._find_exact_matches(channel_id, content_lower)
        
        # Single pass: compute fuzzy matches and raid pattern simultaneously
        fuzzy_matches, raid_pattern = self._analyze_recent_messages(channel_id, content_lower)
        
        # Determine spam score
        spam_score = 0
        reasons = []
        
        if exact_matches >= 3:
            spam_score += 0.8
            reasons.append(f"Exact duplicate sent {exact_matches} times")
        elif exact_matches >= 2:
            spam_score += 0.5
            reasons.append(f"Exact duplicate sent {exact_matches} times")
        
        if len(fuzzy_matches) >= 3:
            spam_score += 0.7
            reasons.append(f"{len(fuzzy_matches)} similar messages detected")
        elif len(fuzzy_matches) >= 2:
            spam_score += 0.4
            reasons.append(f"{len(fuzzy_matches)} similar messages detected")
        
        if raid_pattern["detected"]:
            spam_score += 0.9
            reasons.append(f"Raid pattern: {raid_pattern['user_count']} users sent similar messages")
            
            # Populate detected campaigns
            self._detected_campaigns.append({
                "channel_id": channel_id,
                "user_count": raid_pattern["user_count"],
                "content": content[:80],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "active": True,
                "user_id": user_id,
            })
        
        is_spam = spam_score >= 0.6
        
        return {
            "is_spam": is_spam,
            "spam_score": round(spam_score, 2),
            "exact_matches": exact_matches,
            "fuzzy_matches": len(fuzzy_matches),
            "raid_detected": raid_pattern["detected"],
            "reasons": reasons,
            "suggested_actions": self._get_suggested_actions(spam_score, raid_pattern),
        }

    def _find_exact_matches(self, channel_id: str, content: str) -> int:
        """Count exact duplicate messages in the time window."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=self.TIME_WINDOW)
        count = 0
        for msg in self._recent_messages.get(channel_id, []):
            if msg.timestamp >= cutoff and msg.content.lower() == content:
                count += 1
        return count

    def _analyze_recent_messages(self, channel_id: str, content: str) -> tuple[list, dict]:
        """Single pass: compute fuzzy matches and raid pattern simultaneously.
        
        For production use, replace _levenshtein_similarity() with difflib.SequenceMatcher 
        or the python-Levenshtein package for ~10x speed improvement.
        """
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=self.TIME_WINDOW)
        fuzzy_matches = []
        users_similar: Set[str] = set()

        for msg in self._recent_messages.get(channel_id, []):
            if msg.timestamp < cutoff:
                continue
            similarity = self._levenshtein_similarity(content, msg.content.lower())
            if similarity >= self.SIMILARITY_THRESHOLD:
                if content != msg.content.lower():
                    fuzzy_matches.append({
                        "user_id": msg.user_id,
                        "content": msg.content,
                        "similarity": round(similarity, 3),
                        "timestamp": msg.timestamp.isoformat(),
                    })
                users_similar.add(msg.user_id)

        raid = {
            "detected": len(users_similar) >= 3,
            "user_count": len(users_similar),
            "users": list(users_similar),
        }
        return fuzzy_matches, raid

    def _levenshtein_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate Levenshtein similarity between two strings.
        Returns a value between 0 (completely different) and 1 (identical).
        """
        if s1 == s2:
            return 1.0
        
        len1, len2 = len(s1), len(s2)
        if len1 == 0 or len2 == 0:
            return 0.0
        
        # Create matrix
        matrix = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        
        # Initialize first row and column
        for i in range(len1 + 1):
            matrix[i][0] = i
        for j in range(len2 + 1):
            matrix[0][j] = j
        
        # Fill matrix
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i-1] == s2[j-1] else 1
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
        
        # Calculate similarity
        max_len = max(len1, len2)
        distance = matrix[len1][len2]
        
        return 1.0 - (distance / max_len)

    def _get_suggested_actions(self, spam_score: float, raid_pattern: Dict) -> List[Dict[str, str]]:
        """Get suggested actions based on spam analysis."""
        actions = []
        
        if raid_pattern["detected"]:
            actions.append({"label": "Mute All Spammers", "action": "mute_spammers", "params": {"users": raid_pattern["users"]}})
            actions.append({"label": "Lock Channel", "action": "lock_channel"})
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode"})
        elif spam_score >= 0.6:
            actions.append({"label": "Mute User", "action": "mute_user"})
            actions.append({"label": "Delete Messages", "action": "delete_campaign"})
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode"})
        elif spam_score >= 0.4:
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode"})
        
        return actions

    def get_campaign_summary(self) -> Dict[str, Any]:
        """Get summary of detected spam campaigns."""
        return {
            "total_campaigns": len(self._detected_campaigns),
            "active_campaigns": len([c for c in self._detected_campaigns if c.get("active", False)]),
            "affected_users": list(set(c.get("user_id", "") for c in self._detected_campaigns)),
            "affected_channels": list(set(c.get("channel_id", "") for c in self._detected_campaigns)),
        }

    def get_spam_intelligence(self, guild_id: str) -> Dict[str, Any]:
        """Get comprehensive spam intelligence."""
        all_campaigns = []
        
        for channel_id, messages in self._recent_messages.items():
            if messages:
                # Analyze recent messages for campaigns
                content_groups = defaultdict(list)
                for msg in messages:
                    content_groups[msg.content.lower()].append(msg)
                
                for content, group in content_groups.items():
                    if len(group) >= 3:
                        all_campaigns.append({
                            "content": content[:50] + "..." if len(content) > 50 else content,
                            "user_count": len(set(m.user_id for m in group)),
                            "message_count": len(group),
                            "channel_id": channel_id,
                        })
        
        return {
            "campaigns": all_campaigns[:10],  # Top 10 campaigns
            "total_campaigns": len(all_campaigns),
            "affected_channels": len(set(c["channel_id"] for c in all_campaigns)),
        }
