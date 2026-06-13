import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, Date
from sqlalchemy.orm import declarative_base

AnalyticsBase = declarative_base()

def get_utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


class MessageEvent(AnalyticsBase):
    __tablename__ = "message_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    channel_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=get_utcnow, index=True)
    word_count = Column(Integer, nullable=False, default=0)


class MemberEvent(AnalyticsBase):
    __tablename__ = "member_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    event_type = Column(String, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=get_utcnow, index=True)
    invite_code = Column(String, nullable=True)


class VoiceSession(AnalyticsBase):
    __tablename__ = "voice_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False, index=True)
    channel_id = Column(String, nullable=False)
    joined_at = Column(DateTime, nullable=False, default=get_utcnow)
    left_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Integer, nullable=True)


class ModerationEvent(AnalyticsBase):
    __tablename__ = "moderation_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    moderator_id = Column(String, nullable=True)
    event_type = Column(String, nullable=False)
    reason = Column(String, nullable=True)
    automod_category = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False, default=get_utcnow, index=True)
    details = Column(Text, nullable=True)


class DailySnapshot(AnalyticsBase):
    __tablename__ = "daily_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    total_messages = Column(Integer, nullable=False, default=0)
    unique_active_users = Column(Integer, nullable=False, default=0)
    voice_minutes = Column(Integer, nullable=False, default=0)
    new_members = Column(Integer, nullable=False, default=0)
    left_members = Column(Integer, nullable=False, default=0)
    tickets_opened = Column(Integer, nullable=False, default=0)
    tickets_closed = Column(Integer, nullable=False, default=0)
    mod_actions = Column(Integer, nullable=False, default=0)
    commands_used = Column(Integer, nullable=False, default=0)
    server_health_score = Column(Integer, nullable=True)


class ServerBenchmark(AnalyticsBase):
    __tablename__ = "server_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    avg_messages_per_day = Column(Integer, nullable=False, default=0)
    avg_active_users = Column(Integer, nullable=False, default=0)
    avg_voice_minutes = Column(Integer, nullable=False, default=0)
    mod_actions_per_week = Column(Integer, nullable=False, default=0)


class ServerScore(AnalyticsBase):
    __tablename__ = "server_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, default=get_utcnow)
    overall = Column(Integer, nullable=False, default=0)
    security = Column(Integer, nullable=False, default=0)
    moderation = Column(Integer, nullable=False, default=0)
    structure = Column(Integer, nullable=False, default=0)
    engagement = Column(Integer, nullable=False, default=0)
    automation = Column(Integer, nullable=False, default=0)
    details_json = Column(Text, nullable=True)
