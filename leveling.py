import json
import os
import time
import math
import threading
import utils

LEVELING_DATA_PATH = utils.get_writeable_path("leveling_data.json")

class LevelingSystem:
    def __init__(self):
        self.xp_data = {}
        self.lock = threading.RLock()
        self.dirty = False
        self.load()
        # Start periodic background saver (Tier 4.13)
        self._save_thread = threading.Thread(target=self._periodic_save, daemon=True)
        self._save_thread.start()

    def load(self):
        with self.lock:
            if os.path.exists(LEVELING_DATA_PATH):
                try:
                    with open(LEVELING_DATA_PATH, "r", encoding="utf-8") as f:
                        self.xp_data = json.load(f)
                except Exception as e:
                    print(f"Error loading leveling data: {e}")
                    self.xp_data = {}
            else:
                self.xp_data = {}

    def save(self):
        with self.lock:
            try:
                with open(LEVELING_DATA_PATH, "w", encoding="utf-8") as f:
                    json.dump(self.xp_data, f, indent=2)
                self.dirty = False
            except Exception as e:
                print(f"Error saving leveling data: {e}")

    def _periodic_save(self):
        while True:
            time.sleep(30)
            if self.dirty:
                self.save()

    def get_level(self, xp: int) -> int:
        """Calculates level based on total XP using the formula: level = floor(sqrt(xp / 100))."""
        if xp <= 0:
            return 0
        return int(math.floor((xp / 100) ** 0.5))

    def get_xp_for_level(self, level: int) -> int:
        """Returns the total XP needed to reach a specific level."""
        return 100 * (level ** 2)

    def add_xp(self, guild_id: str, user_id: str, amount: int, cooldown_seconds: int = 60) -> tuple:
        """
        Adds XP to a user with a cooldown, checking for level-up.
        Returns (new_level, leveled_up, current_xp, total_messages)
        """
        now = time.time()
        g_id = str(guild_id)
        u_id = str(user_id)
        
        with self.lock:
            if g_id not in self.xp_data:
                self.xp_data[g_id] = {}
                
            if u_id not in self.xp_data[g_id]:
                self.xp_data[g_id][u_id] = {
                    "xp": 0,
                    "level": 0,
                    "messages": 0,
                    "last_xp_time": 0
                }
                
            user_stats = self.xp_data[g_id][u_id]
            last_xp_time = user_stats.get("last_xp_time", 0)
            
            # Increment message count on every message
            user_stats["messages"] = user_stats.get("messages", 0) + 1
            
            leveled_up = False
            old_level = user_stats.get("level", 0)
            
            # Check cooldown for XP gain
            if now - last_xp_time >= cooldown_seconds:
                user_stats["xp"] = user_stats.get("xp", 0) + amount
                user_stats["last_xp_time"] = now
                
                new_level = self.get_level(user_stats["xp"])
                user_stats["level"] = new_level
                
                if new_level > old_level:
                    leveled_up = True
                    
                self.dirty = True
                
            return user_stats["level"], leveled_up, user_stats["xp"], user_stats["messages"]

    def get_user_rank(self, guild_id: str, user_id: str) -> dict:
        """Returns the user's rank, level, XP, messages, and progress to next level."""
        g_id = str(guild_id)
        u_id = str(user_id)
        
        if g_id not in self.xp_data or u_id not in self.xp_data[g_id]:
            return {
                "xp": 0,
                "level": 0,
                "messages": 0,
                "rank": 0,
                "xp_needed_for_next": 100,
                "xp_progress": 0
            }
            
        guild_users = self.xp_data[g_id]
        # Sort users by XP descending to determine rank
        sorted_users = sorted(guild_users.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
        
        rank = 0
        for idx, (usr_id, stats) in enumerate(sorted_users):
            if usr_id == u_id:
                rank = idx + 1
                break
                
        user_stats = guild_users[u_id]
        level = user_stats.get("level", 0)
        xp = user_stats.get("xp", 0)
        
        xp_current_lvl_start = self.get_xp_for_level(level)
        xp_next_lvl_start = self.get_xp_for_level(level + 1)
        
        xp_needed_for_next = xp_next_lvl_start - xp_current_lvl_start
        xp_progress = xp - xp_current_lvl_start
        
        return {
            "xp": xp,
            "level": level,
            "messages": user_stats.get("messages", 0),
            "rank": rank,
            "xp_needed_for_next": xp_needed_for_next,
            "xp_progress": xp_progress
        }

    def get_leaderboard(self, guild_id: str, limit: int = 20) -> list:
        """Returns the top users in the guild by XP."""
        g_id = str(guild_id)
        if g_id not in self.xp_data:
            return []
            
        guild_users = self.xp_data[g_id]
        sorted_users = sorted(guild_users.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
        
        leaderboard = []
        for idx, (usr_id, stats) in enumerate(sorted_users[:limit]):
            leaderboard.append({
                "user_id": usr_id,
                "xp": stats.get("xp", 0),
                "level": stats.get("level", 0),
                "messages": stats.get("messages", 0),
                "rank": idx + 1
            })
        return leaderboard

    def reset_guild(self, guild_id: str):
        """Resets leveling data for a specific guild."""
        g_id = str(guild_id)
        if g_id in self.xp_data:
            del self.xp_data[g_id]
            self.save()
            return True
        return False

# Global instance
leveling_system = LevelingSystem()
