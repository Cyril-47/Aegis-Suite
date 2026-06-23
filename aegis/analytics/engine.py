import asyncio
import logging
import datetime
import threading
from typing import List, Dict, Optional, Any
from collections import deque

logger = logging.getLogger("aegis.analytics.engine")


class AnalyticsEngine:
    """Thread-safe analytics engine with write batching for SQLite event storage."""

    def __init__(self, session_factory, batch_size=100, flush_interval=5.0):
        self._session_factory = session_factory
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer: deque = deque()
        self._lock = threading.Lock()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._voice_sessions: Dict[str, int] = {}

    def start(self, loop: asyncio.AbstractEventLoop):
        self._running = True
        self._loop = loop
        try:
            self._flush_task = loop.create_task(self._flush_loop())
        except RuntimeError:
            logger.warning("Analytics flush loop could not start (no running event loop)")

    def stop(self):
        self._running = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_now()

    def _flush_now(self):
        with self._lock:
            batch = list(self._buffer)
            self._buffer.clear()
        if not batch:
            return
        try:
            from aegis.db.analytics_models import (
                MessageEvent, MemberEvent, VoiceSession, ModerationEvent,
            )
            session = self._session_factory()
            try:
                for event in batch:
                    kind = event.pop("kind")
                    if kind == "message":
                        session.add(MessageEvent(**event))
                    elif kind == "member":
                        session.add(MemberEvent(**event))
                    elif kind == "voice_join":
                        session.add(VoiceSession(**event))
                    elif kind == "voice_leave":
                        vs = session.query(VoiceSession).filter(
                            VoiceSession.guild_id == event["guild_id"],
                            VoiceSession.user_id == event["user_id"],
                            VoiceSession.channel_id == event["channel_id"],
                            VoiceSession.left_at.is_(None),
                        ).order_by(VoiceSession.joined_at.desc()).first()
                        if vs:
                            vs.left_at = event["left_at"]
                            vs.duration_seconds = int((event["left_at"] - vs.joined_at).total_seconds())
                    elif kind == "moderation":
                        session.add(ModerationEvent(**event))
                session.commit()
            except Exception:
                session.rollback()
                logger.exception("Failed to flush analytics batch")
            finally:
                session.close()
        except Exception:
            logger.exception("Analytics flush error")

    async def _flush_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self._flush_interval)
                await asyncio.get_event_loop().run_in_executor(None, self._flush_now)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Analytics flush loop error")

    def _enqueue(self, event: dict):
        with self._lock:
            self._buffer.append(event)
        if len(self._buffer) >= self._batch_size and self._loop is not None:
            self._loop.call_soon_threadsafe(self._flush_now)

    def record_message(self, guild_id: int, channel_id: int, user_id: int, word_count: int):
        self._enqueue({
            "kind": "message",
            "guild_id": str(guild_id),
            "channel_id": str(channel_id),
            "user_id": str(user_id),
            "word_count": word_count,
        })

    def record_member_event(self, guild_id: int, user_id: int, event_type: str, invite_code: str = None):
        self._enqueue({
            "kind": "member",
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "event_type": event_type,
            "invite_code": invite_code,
        })

    def record_voice_join(self, guild_id: int, user_id: int, channel_id: int):
        key = f"{guild_id}:{user_id}"
        self._voice_sessions[key] = channel_id
        self._enqueue({
            "kind": "voice_join",
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "channel_id": str(channel_id),
        })

    def record_voice_leave(self, guild_id: int, user_id: int, channel_id: int):
        key = f"{guild_id}:{user_id}"
        self._voice_sessions.pop(key, None)
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        self._enqueue({
            "kind": "voice_leave",
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "channel_id": str(channel_id),
            "left_at": now,
            "duration_seconds": None,
        })

    def record_mod_action(self, guild_id: int, user_id: int, moderator_id: str = None,
                          event_type: str = "automod_block", reason: str = None,
                          automod_category: str = None):
        self._enqueue({
            "kind": "moderation",
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "moderator_id": moderator_id,
            "event_type": event_type,
            "reason": reason,
            "automod_category": automod_category,
        })

    def record_command(self, guild_id: int, user_id: int, command_name: str = ""):
        self._enqueue({
            "kind": "moderation",
            "guild_id": str(guild_id),
            "user_id": str(user_id),
            "moderator_id": None,
            "event_type": "command_used",
            "reason": command_name,
            "automod_category": None,
        })

    def get_daily_stats(self, guild_id: str, days: int = 30) -> List[Dict[str, Any]]:
        from aegis.db.analytics_models import MessageEvent, DailySnapshot
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            snapshots = session.query(DailySnapshot).filter(
                DailySnapshot.guild_id == guild_id,
                DailySnapshot.date >= cutoff.date(),
            ).order_by(DailySnapshot.date).all()
            # Query today's live stats
            today_start = datetime.datetime.combine(
                datetime.datetime.now(datetime.timezone.utc).date(),
                datetime.time.min
            )
            from sqlalchemy import func
            msgs_today = session.query(MessageEvent).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= today_start
            ).count()
            
            unique_users_today = session.query(func.count(func.distinct(MessageEvent.user_id))).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= today_start
            ).scalar() or 0
            
            from aegis.db.analytics_models import MemberEvent
            new_members_today = session.query(MemberEvent).filter(
                MemberEvent.guild_id == guild_id,
                MemberEvent.timestamp >= today_start,
                MemberEvent.event_type == "join"
            ).count()
            
            left_members_today = session.query(MemberEvent).filter(
                MemberEvent.guild_id == guild_id,
                MemberEvent.timestamp >= today_start,
                MemberEvent.event_type == "leave"
            ).count()
            
            from aegis.db.analytics_models import VoiceSession
            voice_minutes_today = session.query(func.sum(VoiceSession.duration_seconds)).filter(
                VoiceSession.guild_id == guild_id,
                VoiceSession.joined_at >= today_start
            ).scalar() or 0
            voice_minutes_today = int(voice_minutes_today / 60)
            
            from aegis.db.analytics_models import ModerationEvent
            commands_today = session.query(ModerationEvent).filter(
                ModerationEvent.guild_id == guild_id,
                ModerationEvent.timestamp >= today_start,
                ModerationEvent.event_type == "command_used"
            ).count()

            if snapshots:
                result = [
                    {
                        "date": s.date.isoformat(),
                        "total_messages": s.total_messages,
                        "unique_active_users": s.unique_active_users,
                        "voice_minutes": s.voice_minutes,
                        "new_members": s.new_members,
                        "left_members": s.left_members,
                        "commands_used": s.commands_used,
                    }
                    for s in snapshots
                ]
                
                today_str = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
                if not any(s["date"] == today_str for s in result):
                    result.append({
                        "date": today_str,
                        "total_messages": msgs_today,
                        "unique_active_users": unique_users_today,
                        "voice_minutes": voice_minutes_today,
                        "new_members": new_members_today,
                        "left_members": left_members_today,
                        "commands_used": commands_today,
                    })
                return result
            raw = session.query(MessageEvent).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= cutoff,
            ).all()
            daily: Dict[str, Dict] = {}
            for msg in raw:
                d = msg.timestamp.strftime("%Y-%m-%d")
                if d not in daily:
                    daily[d] = {"date": d, "total_messages": 0, "unique_users": set()}
                daily[d]["total_messages"] += 1
                daily[d]["unique_users"].add(msg.user_id)
            return [
                {
                    "date": d,
                    "total_messages": v["total_messages"],
                    "unique_active_users": len(v["unique_users"]),
                    "voice_minutes": 0,
                    "new_members": 0,
                    "left_members": 0,
                    "commands_used": 0,
                }
                for d, v in sorted(daily.items())
            ]
        finally:
            session.close()

    def get_channel_activity(self, guild_id: str, days: int = 7) -> Dict[str, int]:
        from aegis.db.analytics_models import MessageEvent
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            rows = session.query(
                MessageEvent.channel_id,
                func.count(MessageEvent.id).label("cnt"),
            ).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= cutoff,
            ).group_by(MessageEvent.channel_id).all()
            return {ch_id: cnt for ch_id, cnt in rows}
        finally:
            session.close()

    def get_top_users(self, guild_id: str, days: int = 7, limit: int = 20) -> List[Dict[str, Any]]:
        from aegis.db.analytics_models import MessageEvent
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            rows = session.query(
                MessageEvent.user_id,
                func.count(MessageEvent.id).label("message_count"),
                func.sum(MessageEvent.word_count).label("word_count"),
            ).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= cutoff,
            ).group_by(
                MessageEvent.user_id
            ).order_by(
                func.count(MessageEvent.id).desc()
            ).limit(limit).all()
            return [
                {"user_id": r.user_id, "message_count": r.message_count, "word_count": r.word_count or 0}
                for r in rows
            ]
        finally:
            session.close()

    def get_mod_summary(self, guild_id: str, days: int = 7) -> Dict[str, int]:
        from aegis.db.analytics_models import ModerationEvent
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            rows = session.query(
                ModerationEvent.event_type,
                func.count(ModerationEvent.id),
            ).filter(
                ModerationEvent.guild_id == guild_id,
                ModerationEvent.timestamp >= cutoff,
            ).group_by(ModerationEvent.event_type).all()
            return {r[0]: r[1] for r in rows}
        finally:
            session.close()

    def get_voice_leaders(self, guild_id: str, days: int = 7, limit: int = 20) -> List[Dict[str, Any]]:
        from aegis.db.analytics_models import VoiceSession
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            rows = session.query(
                VoiceSession.user_id,
                func.sum(VoiceSession.duration_seconds).label("total_seconds"),
                func.count(VoiceSession.id).label("session_count"),
            ).filter(
                VoiceSession.guild_id == guild_id,
                VoiceSession.joined_at >= cutoff,
                VoiceSession.duration_seconds.isnot(None),
            ).group_by(
                VoiceSession.user_id
            ).order_by(
                func.sum(VoiceSession.duration_seconds).desc()
            ).limit(limit).all()
            return [
                {"user_id": r.user_id, "total_seconds": r.total_seconds or 0, "session_count": r.session_count}
                for r in rows
            ]
        finally:
            session.close()

    def get_member_retention(self, guild_id: str, days: int = 30) -> Dict[str, Any]:
        from aegis.db.analytics_models import MemberEvent
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            joins = session.query(func.count(MemberEvent.id)).filter(
                MemberEvent.guild_id == guild_id,
                MemberEvent.event_type == "join",
                MemberEvent.timestamp >= cutoff,
            ).scalar() or 0
            leaves = session.query(func.count(MemberEvent.id)).filter(
                MemberEvent.guild_id == guild_id,
                MemberEvent.event_type == "leave",
                MemberEvent.timestamp >= cutoff,
            ).scalar() or 0
            return {"joins": joins, "leaves": leaves, "net": joins - leaves}
        finally:
            session.close()

    def get_health_timeline(self, guild_id: str, days: int = 30) -> List[Dict[str, Any]]:
        """Get health score over time from daily snapshots."""
        from aegis.db.analytics_models import DailySnapshot
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            snapshots = session.query(DailySnapshot).filter(
                DailySnapshot.guild_id == guild_id,
                DailySnapshot.date >= cutoff.date(),
            ).order_by(DailySnapshot.date).all()
            
            if snapshots:
                return [
                    {
                        "date": s.date.isoformat(),
                        "total_messages": s.total_messages,
                        "unique_active_users": s.unique_active_users,
                        "voice_minutes": s.voice_minutes,
                        "new_members": s.new_members,
                        "left_members": s.left_members,
                        "mod_actions": s.mod_actions,
                    }
                    for s in snapshots
                ]
            else:
                # Fallback: Query raw events and group them by date
                from aegis.db.analytics_models import MessageEvent, ModerationEvent, MemberEvent, VoiceSession
                from sqlalchemy import func
                
                # Query messages per day
                msg_rows = session.query(
                    func.date(MessageEvent.timestamp).label("d"),
                    func.count(MessageEvent.id).label("cnt"),
                    func.count(func.distinct(MessageEvent.user_id)).label("uniq")
                ).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= cutoff
                ).group_by(func.date(MessageEvent.timestamp)).all()
                
                # Query mod actions per day
                mod_rows = session.query(
                    func.date(ModerationEvent.timestamp).label("d"),
                    func.count(ModerationEvent.id).label("cnt")
                ).filter(
                    ModerationEvent.guild_id == guild_id,
                    ModerationEvent.timestamp >= cutoff
                ).group_by(func.date(ModerationEvent.timestamp)).all()

                # Query member joins/leaves
                join_rows = session.query(
                    func.date(MemberEvent.timestamp).label("d"),
                    func.count(MemberEvent.id).label("cnt")
                ).filter(
                    MemberEvent.guild_id == guild_id,
                    MemberEvent.event_type == "join",
                    MemberEvent.timestamp >= cutoff
                ).group_by(func.date(MemberEvent.timestamp)).all()

                leave_rows = session.query(
                    func.date(MemberEvent.timestamp).label("d"),
                    func.count(MemberEvent.id).label("cnt")
                ).filter(
                    MemberEvent.guild_id == guild_id,
                    MemberEvent.event_type == "leave",
                    MemberEvent.timestamp >= cutoff
                ).group_by(func.date(MemberEvent.timestamp)).all()

                # Query voice minutes
                voice_rows = session.query(
                    func.date(VoiceSession.joined_at).label("d"),
                    func.sum(VoiceSession.duration_seconds).label("dur")
                ).filter(
                    VoiceSession.guild_id == guild_id,
                    VoiceSession.joined_at >= cutoff,
                    VoiceSession.duration_seconds.isnot(None)
                ).group_by(func.date(VoiceSession.joined_at)).all()

                # Build dictionary by date
                stats_by_date = {}
                now_date = datetime.datetime.now(datetime.timezone.utc).date()
                for i in range(days):
                    d = (now_date - datetime.timedelta(days=i))
                    stats_by_date[d] = {
                        "date": d.isoformat(),
                        "total_messages": 0,
                        "unique_active_users": 0,
                        "voice_minutes": 0,
                        "new_members": 0,
                        "left_members": 0,
                        "mod_actions": 0
                    }
                
                def to_date(val):
                    if isinstance(val, str):
                        try:
                            return datetime.date.fromisoformat(val)
                        except Exception:
                            return None
                    return val

                for r in msg_rows:
                    dt = to_date(r.d)
                    if dt in stats_by_date:
                        stats_by_date[dt]["total_messages"] = r.cnt
                        stats_by_date[dt]["unique_active_users"] = r.uniq
                for r in mod_rows:
                    dt = to_date(r.d)
                    if dt in stats_by_date:
                        stats_by_date[dt]["mod_actions"] = r.cnt
                for r in join_rows:
                    dt = to_date(r.d)
                    if dt in stats_by_date:
                        stats_by_date[dt]["new_members"] = r.cnt
                for r in leave_rows:
                    dt = to_date(r.d)
                    if dt in stats_by_date:
                        stats_by_date[dt]["left_members"] = r.cnt
                for r in voice_rows:
                    dt = to_date(r.d)
                    if dt in stats_by_date:
                        stats_by_date[dt]["voice_minutes"] = (r.dur or 0) // 60

                timeline = [stats_by_date[d] for d in sorted(stats_by_date.keys())]
                return timeline
        finally:
            session.close()

    def compute_benchmark(self, guild_id: str) -> Dict[str, Any]:
        """Compute a benchmark profile for a guild based on recent data."""
        daily = self.get_daily_stats(guild_id, days=7)
        if not daily:
            return {}
        avg_msgs = sum(d.get("total_messages", 0) for d in daily) / len(daily)
        avg_users = sum(d.get("unique_active_users", 0) for d in daily) / len(daily)
        avg_voice = sum(d.get("voice_minutes", 0) for d in daily) / len(daily)
        total_mod = sum(d.get("mod_actions", 0) for d in daily)
        return {
            "guild_id": guild_id,
            "avg_messages_per_day": round(avg_msgs, 1),
            "avg_active_users": round(avg_users, 1),
            "avg_voice_minutes": round(avg_voice, 1),
            "mod_actions_per_week": total_mod,
        }

    def save_benchmark(self, guild_id: str, benchmark: Dict[str, Any]):
        """Save a benchmark profile to the database."""
        from aegis.db.analytics_models import ServerBenchmark
        session = self._session_factory()
        try:
            sb = ServerBenchmark(
                guild_id=guild_id,
                date=datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None),
                avg_messages_per_day=int(benchmark.get("avg_messages_per_day", 0)),
                avg_active_users=int(benchmark.get("avg_active_users", 0)),
                avg_voice_minutes=int(benchmark.get("avg_voice_minutes", 0)),
                mod_actions_per_week=benchmark.get("mod_actions_per_week", 0),
            )
            session.add(sb)
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    def get_benchmark_comparison(self, guild_id: str) -> Dict[str, Any]:
        """Compare this guild's benchmark against all guilds."""
        from aegis.db.analytics_models import ServerBenchmark
        from sqlalchemy import func
        session = self._session_factory()
        try:
            my = session.query(ServerBenchmark).filter(
                ServerBenchmark.guild_id == guild_id
            ).order_by(ServerBenchmark.date.desc()).first()
            if not my:
                return {"available": False}

            # Query only the latest benchmark per unique guild_id
            subq = session.query(
                ServerBenchmark.guild_id,
                func.max(ServerBenchmark.date).label("max_date")
            ).group_by(ServerBenchmark.guild_id).subquery()

            latest_benchmarks = session.query(ServerBenchmark).join(
                subq,
                (ServerBenchmark.guild_id == subq.c.guild_id) &
                (ServerBenchmark.date == subq.c.max_date)
            ).all()

            if len(latest_benchmarks) < 2:
                return {
                    "available": True,
                    "my_profile": {
                        "avg_messages_per_day": my.avg_messages_per_day,
                        "avg_active_users": my.avg_active_users,
                        "avg_voice_minutes": my.avg_voice_minutes,
                    },
                    "percentile": 50,
                    "total_servers": len(latest_benchmarks),
                }

            all_msgs = [b.avg_messages_per_day for b in latest_benchmarks]
            my_msgs = my.avg_messages_per_day
            percentile = sum(1 for v in all_msgs if v <= my_msgs) / len(all_msgs) * 100

            return {
                "available": True,
                "my_profile": {
                    "avg_messages_per_day": my.avg_messages_per_day,
                    "avg_active_users": my.avg_active_users,
                    "avg_voice_minutes": my.avg_voice_minutes,
                },
                "percentile": round(percentile),
                "total_servers": len(latest_benchmarks),
            }
        finally:
            session.close()

    def get_unique_active_users_count(self, guild_id: str, days: int = 7) -> int:
        from aegis.db.analytics_models import MessageEvent
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            unique_users = session.query(func.count(func.distinct(MessageEvent.user_id))).filter(
                MessageEvent.guild_id == guild_id,
                MessageEvent.timestamp >= cutoff,
            ).scalar() or 0
            return unique_users
        finally:
            session.close()

    def get_voice_minutes_sum(self, guild_id: str, days: int = 7) -> int:
        from aegis.db.analytics_models import VoiceSession
        from sqlalchemy import func
        session = self._session_factory()
        try:
            cutoff = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=days)
            total_seconds = session.query(func.sum(VoiceSession.duration_seconds)).filter(
                VoiceSession.guild_id == guild_id,
                VoiceSession.joined_at >= cutoff,
                VoiceSession.duration_seconds.isnot(None),
            ).scalar() or 0
            return int(total_seconds // 60)
        finally:
            session.close()

    def get_overview(self, guild_id: str) -> Dict[str, Any]:
        daily = self.get_daily_stats(guild_id, days=1)
        top_users = self.get_top_users(guild_id, days=7, limit=5)
        mod = self.get_mod_summary(guild_id, days=7)
        retention = self.get_member_retention(guild_id, days=30)
        
        active_users_7d = self.get_unique_active_users_count(guild_id, days=7)
        voice_minutes_7d = self.get_voice_minutes_sum(guild_id, days=7)
        
        return {
            "today": daily[-1] if daily else {},
            "top_users_7d": top_users,
            "mod_actions_7d": mod,
            "retention_30d": retention,
            "active_users_7d": active_users_7d,
            "voice_minutes_7d": voice_minutes_7d,
        }


_analytics_engine: Optional[AnalyticsEngine] = None


def get_analytics_engine() -> Optional[AnalyticsEngine]:
    return _analytics_engine


def init_analytics_engine(session_factory) -> AnalyticsEngine:
    global _analytics_engine
    _analytics_engine = AnalyticsEngine(session_factory)
    return _analytics_engine
