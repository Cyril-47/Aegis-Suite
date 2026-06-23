"""Aggressive real-world scenario tests for Raid Logging DB.

Simulates actual database conditions:
- Rapid raid event inserts
- Large payloads (500+ users)
- Query performance under load
- Concurrent guild operations
"""
import pytest
import json
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aegis.db.models import Base, RaidEvent


@pytest.fixture
def raid_session():
    """Create an in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def test_create_and_query(raid_session):
    """Create a raid event and query it back."""
    event = RaidEvent(
        guild_id="123456",
        join_count=25,
        window_seconds=60,
        response_action="lock_server",
        members_affected=json.dumps(["u1", "u2", "u3"]),
    )
    raid_session.add(event)
    raid_session.commit()

    result = raid_session.query(RaidEvent).filter_by(guild_id="123456").first()
    assert result is not None
    assert result.join_count == 25
    assert result.response_action == "lock_server"
    assert json.loads(result.members_affected) == ["u1", "u2", "u3"]


def test_multiple_events_per_guild(raid_session):
    """Multiple raid events for same guild."""
    for i in range(10):
        raid_session.add(RaidEvent(
            guild_id="999",
            join_count=10 + i,
            window_seconds=60,
            response_action="slowmode",
        ))
    raid_session.commit()

    events = raid_session.query(RaidEvent).filter_by(guild_id="999").all()
    assert len(events) == 10


def test_guild_index_exists():
    """guild_id column is indexed."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(RaidEvent)
    for col in mapper.columns:
        if col.name == "guild_id":
            assert col.index is True
            break
    else:
        raise AssertionError("guild_id column not found")


def test_resolved_default(raid_session):
    """resolved defaults to 0."""
    event = RaidEvent(
        guild_id="777",
        join_count=15,
        window_seconds=30,
        response_action="alert",
    )
    raid_session.add(event)
    raid_session.commit()
    assert event.resolved == 0


def test_large_payload_500_users(raid_session):
    """500 users in members_affected."""
    users = [f"user_{i}" for i in range(500)]
    event = RaidEvent(
        guild_id="big_raid",
        join_count=500,
        window_seconds=120,
        response_action="lock_server",
        members_affected=json.dumps(users),
    )
    raid_session.add(event)
    raid_session.commit()

    result = raid_session.query(RaidEvent).filter_by(guild_id="big_raid").first()
    assert len(json.loads(result.members_affected)) == 500


def test_1000_entries_across_10_guilds(raid_session):
    """1000 raid events across 10 guilds."""
    start = time.perf_counter()
    for i in range(1000):
        raid_session.add(RaidEvent(
            guild_id=f"guild_{i % 10}",
            join_count=i,
            window_seconds=60,
            response_action="slowmode",
        ))
    raid_session.commit()
    elapsed = time.perf_counter() - start

    for g in range(10):
        count = raid_session.query(RaidEvent).filter_by(guild_id=f"guild_{g}").count()
        assert count == 100

    print(f"\n  [PERF] 1000 inserts in {elapsed*1000:.1f}ms")


def test_query_ordering(raid_session):
    """Events ordered by detected_at descending."""
    for i in range(20):
        raid_session.add(RaidEvent(
            guild_id="g1",
            join_count=i,
            window_seconds=60,
            response_action="alert",
        ))
    raid_session.commit()

    events = raid_session.query(RaidEvent).filter_by(guild_id="g1").order_by(
        RaidEvent.detected_at.desc()
    ).all()
    assert len(events) == 20
    assert events[0].join_count >= events[-1].join_count


def test_large_join_count(raid_session):
    """Very large join count (10000 users)."""
    event = RaidEvent(
        guild_id="mega_raid",
        join_count=10000,
        window_seconds=300,
        response_action="lock_server",
        members_affected=json.dumps([f"user_{i}" for i in range(10000)]),
    )
    raid_session.add(event)
    raid_session.commit()

    result = raid_session.query(RaidEvent).filter_by(guild_id="mega_raid").first()
    assert result.join_count == 10000
    assert len(json.loads(result.members_affected)) == 10000


def test_concurrent_guild_queries(raid_session):
    """Query performance across multiple guilds."""
    for i in range(50):
        for j in range(10):
            raid_session.add(RaidEvent(
                guild_id=f"guild_{i}",
                join_count=j,
                window_seconds=60,
                response_action="alert",
            ))
    raid_session.commit()

    start = time.perf_counter()
    for i in range(50):
        events = raid_session.query(RaidEvent).filter_by(guild_id=f"guild_{i}").all()
        assert len(events) == 10
    elapsed = time.perf_counter() - start

    print(f"\n  [PERF] 50 guild queries in {elapsed*1000:.1f}ms")


def test_10000_events_insert(raid_session):
    """10000 events inserted and queried."""
    start = time.perf_counter()
    for i in range(10000):
        raid_session.add(RaidEvent(
            guild_id=f"guild_{i % 100}",
            join_count=i % 1000,
            window_seconds=60,
            response_action="alert",
        ))
    raid_session.commit()
    insert_time = time.perf_counter() - start

    start = time.perf_counter()
    total = raid_session.query(RaidEvent).count()
    query_time = time.perf_counter() - start

    assert total == 10000
    print(f"\n  [PERF] 10000 inserts: {insert_time*1000:.1f}ms, count query: {query_time*1000:.1f}ms")


def test_json_payload_various_sizes(raid_session):
    """Various payload sizes."""
    sizes = [1, 10, 50, 100, 500, 1000]
    for size in sizes:
        users = [f"user_{i}" for i in range(size)]
        event = RaidEvent(
            guild_id=f"size_{size}",
            join_count=size,
            window_seconds=60,
            response_action="lock_server",
            members_affected=json.dumps(users),
        )
        raid_session.add(event)
    raid_session.commit()

    for size in sizes:
        result = raid_session.query(RaidEvent).filter_by(guild_id=f"size_{size}").first()
        assert len(json.loads(result.members_affected)) == size


def test_500_guilds_isolation(raid_session):
    """500 guilds with independent events."""
    for i in range(500):
        raid_session.add(RaidEvent(
            guild_id=f"guild_{i}",
            join_count=i,
            window_seconds=60,
            response_action="alert",
        ))
    raid_session.commit()

    for i in range(500):
        events = raid_session.query(RaidEvent).filter_by(guild_id=f"guild_{i}").all()
        assert len(events) == 1
        assert events[0].join_count == i
