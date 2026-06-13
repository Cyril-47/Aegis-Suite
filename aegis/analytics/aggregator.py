import asyncio
import logging
import datetime
from typing import Optional

logger = logging.getLogger("aegis.analytics.aggregator")

RETENTION_RAW_DAYS = 30
RETENTION_MEMBER_DAYS = 90


class AnalyticsAggregator:
    """Background task that aggregates raw events into daily snapshots and prunes old data."""

    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop):
        self._running = True
        try:
            self._task = loop.create_task(self._run_loop())
        except RuntimeError:
            logger.warning("Analytics aggregator could not start (no running event loop)")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run_loop(self):
        while self._running:
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                next_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)
                wait_seconds = (next_midnight - now).total_seconds()
                if wait_seconds < 60:
                    wait_seconds += 60
                await asyncio.sleep(wait_seconds)
                await asyncio.get_event_loop().run_in_executor(None, self._aggregate_all)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Analytics aggregator loop error")
                await asyncio.sleep(300)

    def _aggregate_all(self):
        session = self._session_factory()
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            today = now_utc.date()
            from aegis.db.analytics_models import (
                MessageEvent, MemberEvent, VoiceSession, ModerationEvent,
                DailySnapshot,
            )

            guilds = set()
            for model in [MessageEvent, MemberEvent, VoiceSession, ModerationEvent]:
                rows = session.query(model.guild_id).distinct().all()
                for (gid,) in rows:
                    guilds.add(gid)

            yesterday = today - datetime.timedelta(days=1)
            yesterday_start = datetime.datetime.combine(yesterday, datetime.time.min)
            yesterday_end = datetime.datetime.combine(today, datetime.time.min)

            for guild_id in guilds:
                existing = session.query(DailySnapshot).filter(
                    DailySnapshot.guild_id == guild_id,
                    DailySnapshot.date == yesterday,
                ).first()
                if existing:
                    continue

                msg_count = session.query(MessageEvent).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= yesterday_start,
                    MessageEvent.timestamp < yesterday_end,
                ).count()

                from sqlalchemy import func
                unique_users = session.query(func.count(func.distinct(MessageEvent.user_id))).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= yesterday_start,
                    MessageEvent.timestamp < yesterday_end,
                ).scalar() or 0

                voice = session.query(VoiceSession).filter(
                    VoiceSession.guild_id == guild_id,
                    VoiceSession.joined_at >= yesterday_start,
                    VoiceSession.joined_at < yesterday_end,
                    VoiceSession.duration_seconds.isnot(None),
                ).all()
                voice_minutes = sum(v.duration_seconds or 0 for v in voice) // 60

                joins = session.query(MemberEvent).filter(
                    MemberEvent.guild_id == guild_id,
                    MemberEvent.event_type == "join",
                    MemberEvent.timestamp >= yesterday_start,
                    MemberEvent.timestamp < yesterday_end,
                ).count()

                leaves = session.query(MemberEvent).filter(
                    MemberEvent.guild_id == guild_id,
                    MemberEvent.event_type == "leave",
                    MemberEvent.timestamp >= yesterday_start,
                    MemberEvent.timestamp < yesterday_end,
                ).count()

                mod_count = session.query(ModerationEvent).filter(
                    ModerationEvent.guild_id == guild_id,
                    ModerationEvent.timestamp >= yesterday_start,
                    ModerationEvent.timestamp < yesterday_end,
                    ModerationEvent.event_type != "command_used",
                ).count()

                cmd_count = session.query(ModerationEvent).filter(
                    ModerationEvent.guild_id == guild_id,
                    ModerationEvent.timestamp >= yesterday_start,
                    ModerationEvent.timestamp < yesterday_end,
                    ModerationEvent.event_type == "command_used",
                ).count()

                snapshot = DailySnapshot(
                    guild_id=guild_id,
                    date=yesterday,
                    total_messages=msg_count,
                    unique_active_users=unique_users,
                    voice_minutes=voice_minutes,
                    new_members=joins,
                    left_members=leaves,
                    tickets_opened=0,
                    tickets_closed=0,
                    mod_actions=mod_count,
                    commands_used=cmd_count,
                )
                session.add(snapshot)

            self._prune_old_events(session)
            session.commit()
            logger.info(f"Analytics aggregation completed for {len(guilds)} guilds")

            # Compute benchmarks after commit (non-fatal, separate transaction)
            try:
                from aegis.analytics.engine import get_analytics_engine
                ae = get_analytics_engine()
                if ae:
                    for guild_id in guilds:
                        try:
                            benchmark = ae.compute_benchmark(guild_id)
                            if benchmark:
                                ae.save_benchmark(guild_id, benchmark)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            session.rollback()
            logger.exception("Analytics aggregation failed")
        finally:
            session.close()

    def _prune_old_events(self, session):
        from aegis.db.analytics_models import MessageEvent, VoiceSession, ModerationEvent, MemberEvent
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        raw_cutoff = now - datetime.timedelta(days=RETENTION_RAW_DAYS)
        member_cutoff = now - datetime.timedelta(days=RETENTION_MEMBER_DAYS)
        for model in [MessageEvent, ModerationEvent]:
            session.query(model).filter(model.timestamp < raw_cutoff).delete(synchronize_session="fetch")
        session.query(VoiceSession).filter(VoiceSession.joined_at < raw_cutoff).delete(synchronize_session="fetch")
        session.query(MemberEvent).filter(MemberEvent.timestamp < member_cutoff).delete(synchronize_session="fetch")


_aggregator: Optional[AnalyticsAggregator] = None


def get_aggregator() -> Optional[AnalyticsAggregator]:
    return _aggregator


def init_aggregator(session_factory) -> AnalyticsAggregator:
    global _aggregator
    _aggregator = AnalyticsAggregator(session_factory)
    return _aggregator
