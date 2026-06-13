import datetime
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aegis.db.analytics_models import AnalyticsBase, MessageEvent, MemberEvent, VoiceSession, ModerationEvent, DailySnapshot


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    AnalyticsBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def engine(db_session):
    from aegis.analytics.engine import AnalyticsEngine
    factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
    return AnalyticsEngine(factory, batch_size=10, flush_interval=999)


class TestAnalyticsEngineRecord:
    def test_record_message_enqueues(self, engine):
        engine.record_message("111", "222", "333", 5)
        assert len(engine._buffer) == 1
        event = engine._buffer[0]
        assert event["kind"] == "message"
        assert event["guild_id"] == "111"
        assert event["word_count"] == 5

    def test_record_member_event_enqueues(self, engine):
        engine.record_member_event("111", "333", "join", invite_code="abc")
        assert len(engine._buffer) == 1
        event = engine._buffer[0]
        assert event["kind"] == "member"
        assert event["event_type"] == "join"
        assert event["invite_code"] == "abc"

    def test_record_voice_join_enqueues(self, engine):
        engine.record_voice_join("111", "333", "444")
        assert len(engine._buffer) == 1
        event = engine._buffer[0]
        assert event["kind"] == "voice_join"
        assert event["channel_id"] == "444"
        assert engine._voice_sessions["111:333"] == "444"

    def test_record_voice_leave_enqueues(self, engine):
        engine.record_voice_sessions = {}
        engine.record_voice_leave("111", "333", "444")
        assert len(engine._buffer) == 1
        event = engine._buffer[0]
        assert event["kind"] == "voice_leave"
        assert event["left_at"] is not None

    def test_record_mod_action_enqueues(self, engine):
        engine.record_mod_action("111", "333", "444", "warning", "spam", "profanity")
        assert len(engine._buffer) == 1
        event = engine._buffer[0]
        assert event["kind"] == "moderation"
        assert event["event_type"] == "warning"
        assert event["automod_category"] == "profanity"


class TestAnalyticsEngineFlush:
    def test_flush_writes_messages(self, engine, db_session):
        engine.record_message("111", "222", "333", 5)
        engine.record_message("111", "222", "444", 3)
        engine._flush_now()
        rows = db_session.query(MessageEvent).all()
        assert len(rows) == 2
        assert rows[0].word_count == 5

    def test_flush_writes_member_events(self, engine, db_session):
        engine.record_member_event("111", "333", "join")
        engine._flush_now()
        rows = db_session.query(MemberEvent).all()
        assert len(rows) == 1
        assert rows[0].event_type == "join"

    def test_flush_writes_voice_sessions(self, engine, db_session):
        engine.record_voice_join("111", "333", "444")
        engine._flush_now()
        rows = db_session.query(VoiceSession).all()
        assert len(rows) == 1
        assert rows[0].left_at is None

    def test_flush_calculates_voice_duration(self, engine, db_session):
        engine.record_voice_join("111", "333", "444")
        engine._flush_now()
        session = db_session.get_bind()
        Session = sessionmaker(bind=session)
        s = Session()
        vs = s.query(VoiceSession).first()
        assert vs is not None
        joined = vs.joined_at
        s.close()

        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        engine.record_voice_leave("111", "333", "444")
        engine._flush_now()

        s2 = Session()
        vs2 = s2.query(VoiceSession).first()
        assert vs2.left_at is not None
        assert vs2.duration_seconds is not None
        assert vs2.duration_seconds >= 0
        s2.close()

    def test_flush_writes_moderation_events(self, engine, db_session):
        engine.record_mod_action("111", "333", "444", "automod_block", "spam", "profanity")
        engine._flush_now()
        rows = db_session.query(ModerationEvent).all()
        assert len(rows) == 1
        assert rows[0].automod_category == "profanity"

    def test_flush_clears_buffer(self, engine, db_session):
        engine.record_message("111", "222", "333", 1)
        engine._flush_now()
        assert len(engine._buffer) == 0

    def test_flush_empty_buffer_is_noop(self, engine, db_session):
        engine._flush_now()
        assert db_session.query(MessageEvent).count() == 0


class TestAnalyticsEngineQueries:
    def _seed_messages(self, db_session, guild_id, count=5, user_id="100"):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        for i in range(count):
            db_session.add(MessageEvent(
                guild_id=guild_id, channel_id="200", user_id=user_id,
                word_count=i, timestamp=now - datetime.timedelta(hours=i),
            ))
        db_session.commit()

    def test_get_channel_activity(self, engine, db_session):
        self._seed_messages(db_session, "111", 3, "100")
        db_session.add(MessageEvent(
            guild_id="111", channel_id="300", user_id="100", word_count=1,
        ))
        db_session.commit()
        result = engine.get_channel_activity("111", days=7)
        assert "200" in result
        assert "300" in result
        assert result["200"] == 3
        assert result["300"] == 1

    def test_get_top_users(self, engine, db_session):
        self._seed_messages(db_session, "111", 3, "100")
        self._seed_messages(db_session, "111", 1, "200")
        result = engine.get_top_users("111", days=7)
        assert len(result) == 2
        assert result[0]["user_id"] == "100"
        assert result[0]["message_count"] == 3

    def test_get_mod_summary(self, engine, db_session):
        engine.record_mod_action("111", "333", event_type="automod_block", automod_category="profanity")
        engine.record_mod_action("111", "333", event_type="automod_block", automod_category="invite_link")
        engine.record_mod_action("111", "333", event_type="warning", automod_category="spam")
        engine._flush_now()
        result = engine.get_mod_summary("111", days=7)
        assert result.get("automod_block", 0) == 2
        assert result.get("warning", 0) == 1

    def test_get_voice_leaders(self, engine, db_session):
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        db_session.add(VoiceSession(
            guild_id="111", user_id="100", channel_id="200",
            joined_at=now, left_at=now, duration_seconds=600,
        ))
        db_session.add(VoiceSession(
            guild_id="111", user_id="200", channel_id="200",
            joined_at=now, left_at=now, duration_seconds=300,
        ))
        db_session.commit()
        result = engine.get_voice_leaders("111", days=7)
        assert len(result) == 2
        assert result[0]["user_id"] == "100"
        assert result[0]["total_seconds"] == 600

    def test_get_member_retention(self, engine, db_session):
        engine.record_member_event("111", "100", "join")
        engine.record_member_event("111", "100", "join")
        engine.record_member_event("111", "200", "leave")
        engine._flush_now()
        result = engine.get_member_retention("111", days=30)
        assert result["joins"] == 2
        assert result["leaves"] == 1
        assert result["net"] == 1

    def test_get_overview(self, engine, db_session):
        self._seed_messages(db_session, "111", 2, "100")
        result = engine.get_overview("111")
        assert "today" in result
        assert "top_users_7d" in result
        assert "mod_actions_7d" in result
        assert "retention_30d" in result


class TestAnalyticsAggregator:
    def _seed_events_for_aggregation(self, db_session):
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        yesterday = (now_utc - datetime.timedelta(days=1)).date()
        yesterday_start = datetime.datetime.combine(yesterday, datetime.time.min)
        db_session.add(MessageEvent(
            guild_id="111", channel_id="200", user_id="100",
            word_count=5, timestamp=yesterday_start + datetime.timedelta(hours=12),
        ))
        db_session.add(MemberEvent(
            guild_id="111", user_id="100", event_type="join",
            timestamp=yesterday_start + datetime.timedelta(hours=6),
        ))
        db_session.add(MemberEvent(
            guild_id="111", user_id="200", event_type="leave",
            timestamp=yesterday_start + datetime.timedelta(hours=18),
        ))
        db_session.add(ModerationEvent(
            guild_id="111", user_id="100", event_type="automod_block",
            timestamp=yesterday_start + datetime.timedelta(hours=14),
        ))
        db_session.commit()

    def test_aggregate_creates_snapshot(self, db_session):
        from aegis.analytics.aggregator import AnalyticsAggregator
        self._seed_events_for_aggregation(db_session)
        factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
        agg = AnalyticsAggregator(factory)
        agg._aggregate_all()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        yesterday = (now_utc - datetime.timedelta(days=1)).date()
        snap = db_session.query(DailySnapshot).filter(
            DailySnapshot.guild_id == "111",
            DailySnapshot.date == yesterday,
        ).first()
        assert snap is not None
        assert snap.total_messages == 1
        assert snap.unique_active_users == 1
        assert snap.new_members == 1
        assert snap.left_members == 1
        assert snap.mod_actions == 1

    def test_aggregate_skips_existing_snapshot(self, db_session):
        from aegis.analytics.aggregator import AnalyticsAggregator
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        yesterday = (now_utc - datetime.timedelta(days=1)).date()
        db_session.add(DailySnapshot(
            guild_id="111", date=yesterday, total_messages=99,
            unique_active_users=0, voice_minutes=0, new_members=0,
            left_members=0, tickets_opened=0, tickets_closed=0,
            mod_actions=0, commands_used=0,
        ))
        db_session.commit()
        factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
        agg = AnalyticsAggregator(factory)
        agg._aggregate_all()
        snap = db_session.query(DailySnapshot).filter(
            DailySnapshot.guild_id == "111", DailySnapshot.date == yesterday,
        ).first()
        assert snap.total_messages == 99

    def test_prune_old_events(self, db_session):
        from aegis.analytics.aggregator import AnalyticsAggregator, RETENTION_RAW_DAYS
        old_time = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(days=RETENTION_RAW_DAYS + 5)
        db_session.add(MessageEvent(
            guild_id="111", channel_id="200", user_id="100",
            word_count=1, timestamp=old_time,
        ))
        db_session.add(ModerationEvent(
            guild_id="111", user_id="100", event_type="warning",
            timestamp=old_time,
        ))
        db_session.add(VoiceSession(
            guild_id="111", user_id="100", channel_id="200",
            joined_at=old_time, left_at=old_time, duration_seconds=60,
        ))
        db_session.commit()
        factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
        agg = AnalyticsAggregator(factory)
        agg._prune_old_events(db_session)
        db_session.commit()
        assert db_session.query(MessageEvent).count() == 0
        assert db_session.query(ModerationEvent).count() == 0
        assert db_session.query(VoiceSession).count() == 0

    def test_prune_keeps_fresh_events(self, db_session):
        from aegis.analytics.aggregator import AnalyticsAggregator
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        db_session.add(MessageEvent(
            guild_id="111", channel_id="200", user_id="100",
            word_count=1, timestamp=now,
        ))
        db_session.commit()
        factory = sessionmaker(bind=db_session.get_bind(), autoflush=False, autocommit=False)
        agg = AnalyticsAggregator(factory)
        agg._prune_old_events(db_session)
        db_session.commit()
        assert db_session.query(MessageEvent).count() == 1

    def test_voice_channel_switch(self, engine, db_session):
        engine.record_voice_join("111", "333", "chan_a")
        engine._flush_now()
        engine.record_voice_leave("111", "333", "chan_a")
        engine._flush_now()
        engine.record_voice_join("111", "333", "chan_b")
        engine._flush_now()
        sessions = db_session.query(VoiceSession).filter(
            VoiceSession.guild_id == "111",
            VoiceSession.user_id == "333",
        ).all()
        assert len(sessions) == 2
        closed = [s for s in sessions if s.left_at is not None]
        open_sessions = [s for s in sessions if s.left_at is None]
        assert len(closed) == 1
        assert len(open_sessions) == 1
        assert closed[0].channel_id == "chan_a"
        assert open_sessions[0].channel_id == "chan_b"
