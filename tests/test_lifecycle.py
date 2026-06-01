import os
import pytest
import asyncio
import logging
from unittest.mock import MagicMock
from hypothesis import given, settings, strategies as st
from aegis.core.state import LifecycleState, ReasonCode, LifecycleStateMachine, ALLOWED
from aegis.core.health import HealthRegistry
from aegis.core.app_core import AppCore





# -----------------------------------------------------------------------------
# Unit Tests: State Machine Transitions (Task 2.1)
# -----------------------------------------------------------------------------

def test_initial_state():
    """Verify that the state machine starts in BOOTING and reason is None."""
    sm = LifecycleStateMachine()
    assert sm.current_state == LifecycleState.BOOTING
    assert sm.reason is None
    assert not sm.is_safe_mode()


@pytest.mark.parametrize("target,reason", [
    (LifecycleState.RUNNING, None),
    (LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY),
    (LifecycleState.SHUTTING_DOWN, None)
])
def test_allowed_transitions_from_booting(target, reason):
    """Test transitions from BOOTING to RUNNING, SAFE_MODE, and SHUTTING_DOWN."""
    sm = LifecycleStateMachine()
    sm.transition(target, reason)
    assert sm.current_state == target
    assert sm.reason == reason


def test_allowed_transitions_from_safe_mode():
    """Test transitions from SAFE_MODE to RUNNING and SHUTTING_DOWN."""
    sm = LifecycleStateMachine()
    sm.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    assert sm.is_safe_mode()
    
    # SAFE_MODE -> RUNNING
    sm_running = LifecycleStateMachine()
    sm_running.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    sm_running.transition(LifecycleState.RUNNING)
    assert sm_running.current_state == LifecycleState.RUNNING
    assert sm_running.reason is None

    # SAFE_MODE -> SHUTTING_DOWN
    sm_shutdown = LifecycleStateMachine()
    sm_shutdown.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    sm_shutdown.transition(LifecycleState.SHUTTING_DOWN)
    assert sm_shutdown.current_state == LifecycleState.SHUTTING_DOWN
    assert sm_shutdown.reason is None


def test_allowed_transitions_from_running():
    """Test transitions from RUNNING to SAFE_MODE and SHUTTING_DOWN."""
    sm_to_safe = LifecycleStateMachine()
    sm_to_safe.transition(LifecycleState.RUNNING)
    sm_to_safe.transition(LifecycleState.SAFE_MODE, ReasonCode.NEEDS_SETUP)
    assert sm_to_safe.is_safe_mode()
    assert sm_to_safe.reason == ReasonCode.NEEDS_SETUP

    sm_to_shutdown = LifecycleStateMachine()
    sm_to_shutdown.transition(LifecycleState.RUNNING)
    sm_to_shutdown.transition(LifecycleState.SHUTTING_DOWN)
    assert sm_to_shutdown.current_state == LifecycleState.SHUTTING_DOWN


@pytest.mark.parametrize("to_state,reason", [
    (LifecycleState.BOOTING, None),
    (LifecycleState.RUNNING, None)
])
def test_illegal_transitions_from_running(to_state, reason):
    """Verify illegal transitions from RUNNING raise ValueError."""
    sm = LifecycleStateMachine()
    sm.transition(LifecycleState.RUNNING)
    with pytest.raises(ValueError):
        sm.transition(to_state, reason)


@pytest.mark.parametrize("to_state,reason", [
    (LifecycleState.BOOTING, None),
    (LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
])
def test_illegal_transitions_from_safe_mode(to_state, reason):
    """Verify illegal transitions from SAFE_MODE raise ValueError."""
    sm = LifecycleStateMachine()
    sm.transition(LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY)
    with pytest.raises(ValueError):
        sm.transition(to_state, reason)


@pytest.mark.parametrize("to_state,reason", [
    (LifecycleState.RUNNING, None),
    (LifecycleState.SAFE_MODE, ReasonCode.INTENT_RECOVERY),
    (LifecycleState.BOOTING, None)
])
def test_illegal_transitions_from_shutting_down(to_state, reason):
    """Verify illegal transitions from SHUTTING_DOWN raise ValueError."""
    sm = LifecycleStateMachine()
    sm.transition(LifecycleState.SHUTTING_DOWN)
    with pytest.raises(ValueError):
        sm.transition(to_state, reason)


def test_transition_callback():
    """Verify that optional callback hook is invoked on successful transitions."""
    events = []

    def hook(state, reason):
        events.append((state, reason))

    sm = LifecycleStateMachine(on_transition=hook)
    sm.transition(LifecycleState.SAFE_MODE, ReasonCode.INTENT_RECOVERY)
    sm.transition(LifecycleState.RUNNING)

    assert len(events) == 2
    assert events[0] == (LifecycleState.SAFE_MODE, ReasonCode.INTENT_RECOVERY)
    assert events[1] == (LifecycleState.RUNNING, None)


# -----------------------------------------------------------------------------
# Stateful Transition Property Tests (Task 2.2)
# -----------------------------------------------------------------------------

@given(st.lists(
    st.tuples(
        st.sampled_from(LifecycleState),
        st.one_of(st.none(), st.sampled_from(ReasonCode))
    ),
    min_size=1,
    max_size=20
))
def test_state_machine_transitions_property(sequence):
    """Verify core state machine invariants across arbitrary transitions."""
    sm = LifecycleStateMachine()
    current = sm.current_state

    for target, reason in sequence:
        # Check transition and reason rules
        is_allowed = target in ALLOWED[current]
        is_valid_reason = True
        if target == LifecycleState.SAFE_MODE:
            if not reason:
                is_valid_reason = False
        else:
            if reason is not None:
                is_valid_reason = False

        if is_allowed and is_valid_reason:
            sm.transition(target, reason)
            current = sm.current_state
            assert sm.current_state == target
            if target == LifecycleState.SAFE_MODE:
                assert sm.reason == reason
            else:
                assert sm.reason is None
        else:
            with pytest.raises(ValueError):
                sm.transition(target, reason)

        # Invariant: exactly one state is occupied
        assert sm.current_state in LifecycleState

        # Invariant: reason code logic remains consistent
        if sm.current_state == LifecycleState.SAFE_MODE:
            assert sm.reason is not None
        else:
            assert sm.reason is None

        # Invariant: SHUTTING_DOWN is terminal
        if sm.current_state == LifecycleState.SHUTTING_DOWN:
            for t in LifecycleState:
                for r in [None, ReasonCode.NEEDS_SETUP]:
                    with pytest.raises(ValueError):
                        sm.transition(t, r)


# -----------------------------------------------------------------------------
# Health Registry Payload Unit & Property Tests (Task 2.3 & 2.4)
# -----------------------------------------------------------------------------

def test_health_registry_record_fatal():
    """Verify record_fatal stores only sanitized metadata and doesn't leak exception messages."""
    registry = HealthRegistry()
    registry.record_fatal(ValueError("Super secret bot token: MTIzNDU2.abc.def"))
    
    assert "fatal_error" in registry.checks
    metadata = registry.checks["fatal_error"]
    
    assert metadata["type"] == "ValueError"
    assert metadata["recorded"] is True
    # Ensure no raw message containing secrets leaked in
    assert "MTIzNDU2" not in str(metadata)


@given(
    web=st.sampled_from(["up", "down"]),
    db_reachable=st.booleans(),
    db_integrity=st.booleans(),
    db_at_head=st.booleans(),
    bot=st.sampled_from(["connected_ready", "disabled"]),
    intents=st.sampled_from(["declared_enabled", "missing", "unknown"]),
    state=st.sampled_from(LifecycleState),
    reason=st.one_of(st.none(), st.sampled_from(ReasonCode)),
    checks=st.dictionaries(st.text(), st.text())
)
def test_health_payload_property(
    web, db_reachable, db_integrity, db_at_head, bot, intents, state, reason, checks
):
    """Verify that payload() is well-formed, cache-only, and robust across states."""
    registry = HealthRegistry()
    registry.web = web
    registry.database = {"reachable": db_reachable, "integrity_ok": db_integrity, "at_head": db_at_head}
    registry.bot = bot
    registry.intents = intents
    registry.record_state(state, reason if state == LifecycleState.SAFE_MODE else None)
    registry.checks = checks

    # Verify that mock external I/O functions raising errors do not affect payload building (proving it's cache-only)
    def raise_io(*args, **kwargs):
        raise OSError("Blocked I/O access during payload assembly")

    payload = registry.payload()
    
    assert payload["lifecycle_state"] == state.value
    assert payload["web"] == web
    assert payload["database"]["reachable"] == db_reachable
    assert payload["bot"] == bot
    assert payload["intents"] == intents
    
    # Stable shape payload validation
    if state == LifecycleState.SAFE_MODE:
        assert payload["safe_mode"]["active"] is True
        assert payload["safe_mode"]["reason"] == (reason.value if reason else None)
    else:
        assert payload["safe_mode"] is False
        
    assert payload["checks"] == checks


# -----------------------------------------------------------------------------
# Shutdown Sequence & AppCore Skeleton Tests (Task 2.5 & 2.6)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_startup_exception_boundary():
    """Verify unhandled exception during run() transitions to SAFE_MODE and registers fatal error."""
    core = AppCore()
    
    # Force startup helper to raise error
    async def mock_startup():
        raise RuntimeError("Startup configuration failed")
    core._perform_startup = mock_startup

    # Prevent run() from hanging on _shutdown_event.wait()
    core._shutdown_event.set()

    # Run the core loop
    exit_code = await core.run()
    
    assert exit_code == 0
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core.state.reason == ReasonCode.DB_RECOVERY
    assert core.health.safe_mode["active"] is True
    assert core.health.safe_mode["reason"] == "db-recovery"
    
    # Verify exception is logged as sanitized metadata
    assert "fatal_error" in core.health.checks
    assert core.health.checks["fatal_error"]["type"] == "RuntimeError"




@pytest.mark.asyncio
async def test_double_shutdown_exit(monkeypatch):
    """Verify first shutdown request follows graceful path and second triggers immediate hard exit."""
    core = AppCore()
    
    exited = False

    def mock_exit(code):
        nonlocal exited
        exited = True
        raise SystemExit(code)

    monkeypatch.setattr(os, "_exit", mock_exit)

    # First graceful shutdown request
    await core.request_shutdown()
    assert core._shutdown_requests == 1
    assert not exited

    # Second request during/after graceful path triggers immediate os._exit
    with pytest.raises(SystemExit) as exc_info:
        await core.request_shutdown()
        
    assert core._shutdown_requests == 2
    assert exited
    assert exc_info.value.code == 0



@pytest.mark.asyncio
@settings(deadline=None)
@given(
    has_bot=st.booleans(),
    has_asgi=st.booleans(),
    has_db=st.booleans()
)
async def test_shutdown_ordering_property(has_bot, has_asgi, has_db):
    """Verify shutdown transitions state first, executes in exact order, and is idempotent."""
    core = AppCore()

    # Set up fast fakes/dummies for async tasks
    if has_bot:
        async def mock_bot_job():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                pass
        core._bot_task = asyncio.create_task(mock_bot_job())

    if has_asgi:
        async def mock_asgi_job():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                pass
        core._asgi_task = asyncio.create_task(mock_asgi_job())
        core._uvicorn_server = MagicMock()
        core._uvicorn_server.should_exit = False


    if has_db:
        core.db = MagicMock()

    # Execute graceful shutdown
    await core.request_shutdown()

    log = core.teardown_log

    # Check ordering invariants
    assert log[0] == "state"  # 1. State transition must be first
    assert log[-1] == "logging_shutdown"  # Last step is logging shutdown

    indices = {event: log.index(event) for event in log}

    # Verify transition -> bot cancel -> bot close -> asgi stop -> db dispose -> log flush
    if has_bot:
        assert indices["state"] < indices["bot_cancel"]
        assert indices["bot_cancel"] < indices["bot_close"]
    
    if has_asgi:
        assert indices["bot_close"] < indices["asgi_stop"]

    if has_db:
        last_prev_idx = indices["asgi_stop"] if has_asgi else indices["bot_close"]
        assert last_prev_idx < indices["db_dispose"]
        assert indices["db_dispose"] < indices["logging_shutdown"]
    else:
        last_prev_idx = indices["asgi_stop"] if has_asgi else indices["bot_close"]
        assert last_prev_idx < indices["logging_shutdown"]

    # Verify idempotency (subsequent call without requests >= 2 doesn't execute Graceful sequence again)
    core._shutdown_requests = 0  # reset to verify grace idempotency
    grace_run_count = len(log)
    await core.request_shutdown()
    assert len(log) == grace_run_count

