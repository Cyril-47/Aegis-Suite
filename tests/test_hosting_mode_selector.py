"""REST endpoint regression tests for the Hosting Mode Selector feature.

This module asserts the contract for ``GET /api/hosting-mode``,
``PUT /api/hosting-mode``, and the ``hosting_mode`` field appended to
``GET /api/status``. Tests boot the FastAPI ``app`` via
``fastapi.testclient.TestClient`` so the lifespan runs (with the Discord
bot service stubbed out via ``monkeypatch``) and mint admin / tenant JWTs
directly through ``auth.create_session`` for speed.

Each test seeds ``config.json`` to a known state, exercises the route,
and the ``config_state_snapshot`` / ``audit_log_state_snapshot`` fixtures
restore the on-disk files afterwards so the developer's real config and
audit log are not mutated.

Validates: Requirements 5.1, 5.2, 5.3, 5.4, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4,
           8.5, 8.6
Design:    §Testing Strategy — "Backend unit tests (FastAPI handlers)"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Resolve repository paths relative to this file so the tests are independent
# of the current working directory. Mirror the import bootstrapping pattern
# used by ``tests/test_managed_hosting.py`` so ``import web_server`` resolves
# to the project module rather than any unrelated package on the global path.
REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT_STR = str(REPO_ROOT)
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)

import aegis.core.auth as auth  # noqa: E402
import aegis.core.utils as utils  # noqa: E402
from aegis.web.app import build_app
from aegis.config.schema import ConfigModel
from aegis.core.lifecycle import _bootstrap_hosting_mode_from_env

CONFIG_JSON = Path(utils.get_writeable_path("config.json"))
AUDIT_LOG_JSON = Path(utils.get_writeable_path("audit_log.json"))



# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_config() -> dict:
    """Read ``config.json`` as a dict, bypassing the ``DEFAULT_CONFIG`` merge.

    ``utils.load_config`` injects every missing default key into the returned
    dict, which would mask the difference between "field absent on disk" and
    "field present but empty". The handler's behavior depends on the literal
    on-disk value, so the tests need a raw view.
    """
    if not CONFIG_JSON.is_file():
        return {}
    with CONFIG_JSON.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_config(cfg: dict) -> None:
    """Overwrite ``config.json`` with ``cfg`` as pretty-printed JSON."""
    with CONFIG_JSON.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def _seed_hosting_mode(value) -> None:
    """Seed ``config.json`` so the ``hosting_mode`` key carries ``value``.

    Pass ``None`` (or omit) to remove the key entirely. Pass an empty string
    to keep the key present but unset. Pass ``"local_pc"`` / ``"cloud"`` to
    seed a valid value.
    """
    cfg = _read_config()
    if value is None:
        cfg.pop("hosting_mode", None)
    else:
        cfg["hosting_mode"] = value
    _write_config(cfg)


def _read_audit_log() -> list:
    """Return the parsed ``audit_log.json`` list (or ``[]`` when absent)."""
    if not AUDIT_LOG_JSON.is_file():
        return []
    try:
        with AUDIT_LOG_JSON.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_state_snapshot():
    """Snapshot ``config.json`` on disk and restore it after the test.

    Tests in this module mutate ``hosting_mode`` and exercise the full
    PUT round-trip which calls ``utils.save_config``. The fixture captures
    the original byte contents and writes them back unconditionally on
    teardown so the repo state is preserved.
    """
    original = CONFIG_JSON.read_bytes() if CONFIG_JSON.is_file() else None
    yield
    if original is not None:
        CONFIG_JSON.write_bytes(original)
    elif CONFIG_JSON.is_file():
        CONFIG_JSON.unlink()


@pytest.fixture
def audit_log_state_snapshot():
    """Snapshot ``audit_log.json`` and restore it after the test.

    The PUT handler calls ``audit_log.log_action`` on success which prepends
    a new entry. The fixture restores the original file so each test sees a
    clean log surface and the developer's real audit history is preserved.
    """
    original = AUDIT_LOG_JSON.read_bytes() if AUDIT_LOG_JSON.is_file() else None
    yield
    if original is not None:
        AUDIT_LOG_JSON.write_bytes(original)
    elif AUDIT_LOG_JSON.is_file():
        AUDIT_LOG_JSON.unlink()


@pytest.fixture
def stubbed_app(monkeypatch):
    """Return the FastAPI app with the Discord bot service stubbed out.

    The lifespan startup in ``web_server.py`` calls
    ``bot_manager.start_bot_service(token)`` whenever ``DISCORD_BOT_TOKEN``
    is present in the environment. Tests must not actually open a websocket
    to Discord, so ``start_bot_service`` and ``stop_bot_service`` are
    replaced with async no-ops before the ``TestClient`` enters its context
    manager (which triggers the lifespan).

    The fixture also clears ``AEGIS_HOSTING_MODE`` so the lifespan's
    env-var bootstrap helper does not silently overwrite the
    test-controlled ``hosting_mode`` value in ``config.json``, and pins
    ``ADMIN_PASSWORD_HASH`` to a known value so ``auth_middleware`` does
    not 403 every request through the password-not-yet-set branch.
    """
    import aegis.bot.bot_manager as bot_manager
    from unittest.mock import MagicMock
    from aegis.core.paths import Paths
    from aegis.core.state import LifecycleStateMachine

    async def _noop_start(_token):  # pragma: no cover - trivial stub
        return None

    async def _noop_stop():  # pragma: no cover - trivial stub
        return None

    monkeypatch.setattr(bot_manager, "start_bot_service", _noop_start)
    monkeypatch.setattr(bot_manager, "stop_bot_service", _noop_stop)
    monkeypatch.setattr(bot_manager, "bot_instance", None, raising=False)

    # The bootstrap helper is opt-in via AEGIS_HOSTING_MODE. Tests control
    # config.json directly, so the env-var path must stay dormant.
    monkeypatch.delenv("AEGIS_HOSTING_MODE", raising=False)

    # auth_middleware short-circuits with 403 when ADMIN_PASSWORD_HASH is
    # missing (the "complete password setup first" branch). Pin a hash so
    # the middleware reaches the JWT-validation path the tests are
    # actually exercising.
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", auth.hash_password("test-pw"))

    mock_core = MagicMock()
    mock_core.paths = Paths()
    mock_core.state = LifecycleStateMachine()
    mock_core.config = None

    return build_app(mock_core)


@pytest.fixture
def client(stubbed_app):
    """Return a ``TestClient`` whose lifespan has been entered."""
    from fastapi.testclient import TestClient

    with TestClient(stubbed_app) as test_client:
        yield test_client


@pytest.fixture
def admin_token():
    """Mint a signed admin JWT directly without going through ``/api/auth/login``.

    Round-tripping through the login route works but is slower and depends
    on the rate limiter, the password hash, and the audit log. Calling
    ``auth.create_session`` directly is the documented shortcut for
    handler-level tests.
    """
    return auth.create_session("global", "admin")


@pytest.fixture
def tenant_token():
    """Mint a signed tenant JWT scoped to a fixed throwaway guild id."""
    return auth.create_session("123456789012345678", "tenant")


# ===========================================================================
# GET /api/hosting-mode
# ===========================================================================


def test_get_hosting_mode_returns_null_when_unset(
    client, admin_token, config_state_snapshot
):
    """Empty / missing ``hosting_mode`` reads back as JSON ``null``.

    Validates: Requirements 5.4, 8.1
    """
    _seed_hosting_mode("")  # explicit empty string — most common on-disk shape

    resp = client.get(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"hosting_mode": None}, (
        "An empty hosting_mode in config.json must surface as null in the "
        "API response so the frontend can use a strict ``=== null`` check "
        "to drive the first-launch Selector (R5.4, R8.1)."
    )


def test_get_hosting_mode_returns_local_pc(
    client, admin_token, config_state_snapshot
):
    """A persisted ``local_pc`` is echoed by the GET handler.

    Validates: Requirements 8.1
    """
    _seed_hosting_mode("local_pc")

    resp = client.get(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"hosting_mode": "local_pc"}


def test_get_hosting_mode_returns_cloud(
    client, tenant_token, config_state_snapshot
):
    """Tenants are allowed to read the persisted hosting mode.

    The Hosting Mode Badge is intentionally visible to Tenants so they can
    see at a glance whether the installation is 24/7 or intermittent.

    Validates: Requirements 8.1
    """
    _seed_hosting_mode("cloud")

    resp = client.get(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {tenant_token}"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"hosting_mode": "cloud"}


def test_get_hosting_mode_unauthenticated_401(client, config_state_snapshot):
    """No bearer token must yield HTTP 401 from ``auth_middleware``.

    Validates: Requirements 8.5
    """
    _seed_hosting_mode("local_pc")

    resp = client.get("/api/hosting-mode")

    assert resp.status_code == 401, (
        f"GET /api/hosting-mode without a bearer token should return 401 "
        f"from auth_middleware, got {resp.status_code}: {resp.text!r} "
        "(R8.5)."
    )


# ===========================================================================
# PUT /api/hosting-mode — happy paths
# ===========================================================================


def test_put_hosting_mode_admin_local_pc(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """Admin can persist ``local_pc`` and a ``CONFIG_CHANGE`` audit entry is appended.

    The audit entry text must name both the previous value and the new value
    so the operator can read the audit log and tell what changed (R7.6).

    Validates: Requirements 5.1, 5.2, 7.6, 8.2
    """
    # Pre-seed a known previous value so the audit-entry check has a stable
    # ``from`` token to look for.
    _seed_hosting_mode("cloud")
    audit_before = _read_audit_log()

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "local_pc"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("status") == "success", body
    assert body.get("hosting_mode") == "local_pc", body

    # config.json now carries the new value.
    cfg = _read_config()
    assert cfg.get("hosting_mode") == "local_pc", (
        f"config.json was not persisted: hosting_mode={cfg.get('hosting_mode')!r}"
    )

    # A new CONFIG_CHANGE audit entry was prepended naming both values.
    audit_after = _read_audit_log()
    expected_len = len(audit_before) + 1
    if len(audit_before) >= 1000:
        expected_len = 1000
    assert len(audit_after) == expected_len, (
        "Exactly one audit entry should have been appended by a successful "
        "PUT. Before: {} entries; after: {} entries.".format(
            len(audit_before), len(audit_after)
        )
    )
    latest = audit_after[0]
    assert latest.get("category") == "CONFIG_CHANGE", latest
    action_text = latest.get("action", "")
    assert "local_pc" in action_text, (
        f"Audit entry action text should mention 'local_pc' (the new value); "
        f"got {action_text!r}"
    )
    assert "cloud" in action_text, (
        f"Audit entry action text should mention 'cloud' (the previous "
        f"value) per R7.6; got {action_text!r}"
    )


def test_put_hosting_mode_admin_cloud(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """Admin can persist ``cloud``; ``config.json`` reflects the new value.

    Validates: Requirements 5.1, 5.2, 8.2
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "cloud"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("hosting_mode") == "cloud", body
    assert _read_config().get("hosting_mode") == "cloud"


def test_put_hosting_mode_admin_strips_whitespace_around_valid_value(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """Whitespace around an otherwise-valid value is stripped before persistence.

    The handler calls ``new_raw.strip()`` before validation and persistence,
    so ``"  local_pc  "`` is accepted and stored as the canonical
    ``"local_pc"`` (no leading or trailing spaces in ``config.json``).

    Validates: Requirement 5.2
    """
    _seed_hosting_mode("")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "  local_pc  "},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json().get("hosting_mode") == "local_pc"

    persisted = _read_config().get("hosting_mode")
    assert persisted == "local_pc", (
        f"Persisted hosting_mode should be the stripped canonical value "
        f"'local_pc', got {persisted!r}"
    )


# ===========================================================================
# PUT /api/hosting-mode — 400 paths (invalid bodies must NOT mutate config.json)
# ===========================================================================


def test_put_hosting_mode_admin_invalid_value_400(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """An unknown enum value yields 400 and leaves ``config.json`` untouched.

    Validates: Requirements 5.2, 8.3
    """
    _seed_hosting_mode("local_pc")
    audit_before = _read_audit_log()

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "on-prem"},
    )

    assert resp.status_code == 400, resp.text
    detail = resp.json().get("detail", "")
    assert "local_pc" in detail and "cloud" in detail, (
        f"400 detail should name the two valid values to help the caller "
        f"correct the request; got {detail!r}"
    )

    # config.json is unchanged on a 400 (handler must not touch disk).
    assert _read_config().get("hosting_mode") == "local_pc"
    # No audit-log entry is created for a rejected PUT.
    assert _read_audit_log() == audit_before


def test_put_hosting_mode_admin_missing_field_400(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """An empty body ``{}`` is rejected as a 400.

    Validates: Requirements 8.3
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={},
    )

    assert resp.status_code == 400, resp.text
    assert _read_config().get("hosting_mode") == "local_pc"


def test_put_hosting_mode_admin_empty_string_400(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """An empty string ``""`` is not a valid hosting mode.

    Validates: Requirements 8.3
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": ""},
    )

    assert resp.status_code == 400, resp.text
    assert _read_config().get("hosting_mode") == "local_pc"


def test_put_hosting_mode_admin_whitespace_only_400(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """A whitespace-only string is rejected by the strip + enum check.

    The handler calls ``new_raw.strip()`` before validating, so ``"   "``
    collapses to ``""`` which is not in the valid pair (R5.2 + R8.3).

    Validates: Requirements 5.2, 8.3
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "   "},
    )

    assert resp.status_code == 400, resp.text
    assert _read_config().get("hosting_mode") == "local_pc"


# ===========================================================================
# PUT /api/hosting-mode — auth paths (403 / 401)
# ===========================================================================


def test_put_hosting_mode_tenant_403(
    client, tenant_token, config_state_snapshot, audit_log_state_snapshot
):
    """A tenant session attempting PUT is rejected with HTTP 403.

    Validates: Requirements 7.7, 8.4
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {tenant_token}"},
        json={"hosting_mode": "cloud"},
    )

    assert resp.status_code == 403, resp.text
    # config.json must be unchanged on a 403 — only admins write hosting_mode.
    assert _read_config().get("hosting_mode") == "local_pc"


def test_put_hosting_mode_unauthenticated_401(
    client, config_state_snapshot, audit_log_state_snapshot
):
    """No bearer token yields HTTP 401 and ``config.json`` is unchanged.

    Validates: Requirements 8.5
    """
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        json={"hosting_mode": "cloud"},
    )

    assert resp.status_code == 401, resp.text
    assert _read_config().get("hosting_mode") == "local_pc"


# ===========================================================================
# GET /api/status — hosting_mode field round-trip
# ===========================================================================


def test_get_status_includes_hosting_mode_local_pc(
    client, admin_token, config_state_snapshot
):
    """``GET /api/status`` exposes ``hosting_mode: local_pc`` alongside the
    pre-existing ``status`` / ``has_token`` / ``role`` / ``guild_id`` fields.

    Validates: Requirements 8.6
    """
    _seed_hosting_mode("local_pc")

    resp = client.get(
        "/api/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("hosting_mode") == "local_pc", body
    # The shape of the existing fields is preserved.
    for key in ("status", "has_token", "role", "guild_id"):
        assert key in body, (
            f"GET /api/status response is missing the pre-existing field "
            f"{key!r}; the hosting_mode addition must not regress the "
            f"existing payload (R8.6). Body: {body!r}"
        )


def test_get_status_includes_hosting_mode_cloud(
    client, admin_token, config_state_snapshot
):
    """``GET /api/status`` reflects ``cloud`` when that is the persisted value.

    Validates: Requirements 8.6
    """
    _seed_hosting_mode("cloud")

    resp = client.get(
        "/api/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json().get("hosting_mode") == "cloud"


def test_get_status_includes_null_when_unset(
    client, admin_token, config_state_snapshot
):
    """An empty / missing ``hosting_mode`` surfaces as JSON ``null`` (not ``""``).

    The frontend uses a strict ``=== null`` check to drive the first-launch
    Selector overlay, so the response must NOT be the empty string.

    Validates: Requirements 5.4, 8.6
    """
    _seed_hosting_mode("")

    resp = client.get(
        "/api/status",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "hosting_mode" in body, body
    assert body["hosting_mode"] is None, (
        f"GET /api/status must return JSON null (not the empty string) when "
        f"hosting_mode is unset; got {body['hosting_mode']!r} (R5.4, R8.6)."
    )


# ===========================================================================
# Audit log — old-and-new transition naming (regression for R7.6)
# ===========================================================================


def test_put_hosting_mode_audit_entry_names_old_and_new(
    client, admin_token, config_state_snapshot, audit_log_state_snapshot
):
    """The latest ``CONFIG_CHANGE`` entry after PUT names BOTH values.

    R7.6 requires the audit log to record both the old and new hosting mode
    so the operator can read history and tell exactly what changed without
    diffing two snapshots of ``config.json``.

    Validates: Requirements 7.6
    """
    # Pre-seed a stable old value, then transition to the other.
    _seed_hosting_mode("local_pc")

    resp = client.put(
        "/api/hosting-mode",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"hosting_mode": "cloud"},
    )

    assert resp.status_code == 200, resp.text

    logs = _read_audit_log()
    assert logs, "audit_log.json should contain at least one entry after PUT"

    # The newest entry is at index 0 (log_action prepends).
    latest = logs[0]
    assert latest.get("category") == "CONFIG_CHANGE", latest
    action_text = latest.get("action", "")
    assert "local_pc" in action_text, (
        f"Latest audit entry should name the OLD value 'local_pc'; "
        f"got action={action_text!r}"
    )
    assert "cloud" in action_text, (
        f"Latest audit entry should name the NEW value 'cloud'; "
        f"got action={action_text!r}"
    )


# ===========================================================================
# AEGIS_HOSTING_MODE lifespan bootstrap (web_server._bootstrap_hosting_mode_from_env)
# ===========================================================================
#
# These tests exercise the module-level bootstrap helper directly rather than
# routing through ``TestClient`` + the FastAPI lifespan. The helper is the
# unit of behavior described by Requirement 6 — invoking it directly avoids
# spinning up uvicorn, the bot service, or the auth middleware and lets each
# test focus on the env-var → config.json contract.
#
# The helper's algorithm (per design.md §"Modified lifespan startup"):
#   1. ``utils.load_config()``; if the persisted ``hosting_mode`` is already
#      ``"local_pc"`` or ``"cloud"`` → return immediately (R6.3).
#   2. Read ``os.environ.get("AEGIS_HOSTING_MODE", "").strip().lower()``.
#   3. Empty → return silently (no log, no write).
#   4. Non-empty but not in the valid pair → ``logger.warning(...)`` naming
#      the rejected value, then return (R6.2). config.json is unchanged.
#   5. Valid → re-read under ``utils.config_lock`` (race protection), and
#      only write when the persisted value is still empty / invalid (R6.3),
#      then ``logger.info(...)``.
# ===========================================================================


import logging  # noqa: E402  (imported here to keep the bootstrap-section
                 # imports co-located with the bootstrap-section tests; the
                 # top-of-file imports are intentionally minimal)


def test_bootstrap_writes_local_pc_when_unset_and_env_valid(
    monkeypatch, config_state_snapshot
):
    """Empty persisted value + valid env var → bootstrap persists ``local_pc``.

    Validates: Requirement 6.1
    """
    _seed_hosting_mode("")  # explicit empty string — the on-disk default
    monkeypatch.setenv("AEGIS_HOSTING_MODE", "local_pc")

    _bootstrap_hosting_mode_from_env()

    assert _read_config().get("hosting_mode") == "local_pc", (
        "Bootstrap must write the env-provided value when config.json has "
        "no persisted hosting_mode (R6.1)."
    )


def test_bootstrap_writes_cloud_when_unset_and_env_valid(
    monkeypatch, config_state_snapshot
):
    """Empty persisted value + valid env var → bootstrap persists ``cloud``.

    Validates: Requirement 6.1
    """
    _seed_hosting_mode("")
    monkeypatch.setenv("AEGIS_HOSTING_MODE", "cloud")

    _bootstrap_hosting_mode_from_env()

    assert _read_config().get("hosting_mode") == "cloud", (
        "Bootstrap must accept 'cloud' as a valid env-var value and write "
        "it to config.json when no value is persisted yet (R6.1)."
    )


def test_bootstrap_ignores_invalid_env_value(
    monkeypatch, caplog, config_state_snapshot
):
    """Unknown env value → WARNING log, config.json untouched.

    The helper must reject any value that is not exactly ``local_pc`` or
    ``cloud`` (after ``.strip().lower()``) and emit a maintainer-facing
    WARNING that names the rejected value so the operator can correct
    their deployment env (R6.2).

    Validates: Requirement 6.2
    """
    _seed_hosting_mode("")
    monkeypatch.setenv("AEGIS_HOSTING_MODE", "onprem")

    # ``web_server.logger`` is ``logging.getLogger("WebServer")`` which
    # propagates to root by default; setting the caplog level on the
    # module's logger explicitly captures even when the root logger is
    # configured higher than WARNING.
    with caplog.at_level(logging.WARNING, logger="WebServer"):
        _bootstrap_hosting_mode_from_env()

    # config.json must NOT have been written — the empty string seeded
    # above is preserved verbatim.
    persisted = _read_config().get("hosting_mode")
    assert persisted in ("", None), (
        f"Bootstrap must NOT persist an invalid env-var value; "
        f"hosting_mode is now {persisted!r} (R6.2)."
    )

    # A WARNING-level record naming the rejected value must have been
    # emitted. Searching across all captured records (rather than just
    # ``caplog.text``) lets the assertion pin down BOTH the level and
    # the substring in the same check.
    matching = [
        rec
        for rec in caplog.records
        if rec.levelno == logging.WARNING and "onprem" in rec.getMessage()
    ]
    assert matching, (
        f"Expected a WARNING log record naming the rejected value 'onprem'; "
        f"captured records: {[(r.levelname, r.getMessage()) for r in caplog.records]!r}"
    )


def test_bootstrap_does_not_overwrite_persisted_value(
    monkeypatch, config_state_snapshot
):
    """Persisted ``local_pc`` + env=``cloud`` → persisted value wins.

    R6.3 is the single most important guarantee in this section: a stale
    Render or other cloud env var must never silently stomp an explicit
    Maintainer choice. Without this rule, an admin who switched modes
    from the dashboard could see their preference reverted on every
    cloud restart.

    Validates: Requirement 6.3
    """
    _seed_hosting_mode("local_pc")  # the Maintainer's explicit choice
    monkeypatch.setenv("AEGIS_HOSTING_MODE", "cloud")

    _bootstrap_hosting_mode_from_env()

    assert _read_config().get("hosting_mode") == "local_pc", (
        "Bootstrap must NOT overwrite a pre-existing valid persisted "
        "hosting_mode regardless of the env-var value (R6.3)."
    )


def test_bootstrap_no_env_var_no_change(monkeypatch, config_state_snapshot):
    """No env var + empty persisted value → silent return, no write.

    The ``raising=False`` form of ``delenv`` means the test passes whether
    ``AEGIS_HOSTING_MODE`` was set in the developer's shell or not, which
    keeps the suite reproducible across machines.
    """
    _seed_hosting_mode("")
    monkeypatch.delenv("AEGIS_HOSTING_MODE", raising=False)

    _bootstrap_hosting_mode_from_env()

    persisted = _read_config().get("hosting_mode")
    assert persisted in ("", None), (
        f"Bootstrap must leave hosting_mode untouched when no env var is "
        f"set; got {persisted!r}"
    )


def test_bootstrap_case_insensitive(monkeypatch, config_state_snapshot):
    """``LOCAL_PC`` (or whitespace-padded ``Cloud``) → lowercased canonical write.

    The helper applies ``.strip().lower()`` to the env value before
    validating against the allowed pair, so common Windows / shell
    capitalization variants must all funnel to the canonical lowercase
    form on disk.
    """
    _seed_hosting_mode("")
    monkeypatch.setenv("AEGIS_HOSTING_MODE", "LOCAL_PC")

    _bootstrap_hosting_mode_from_env()

    assert _read_config().get("hosting_mode") == "local_pc", (
        "Bootstrap must lowercase the env-var value before persisting so "
        "config.json always carries the canonical 'local_pc' / 'cloud' "
        "string (per the design's .strip().lower() contract)."
    )


# ===========================================================================
# Managed-hosting invariants + content-drift regression tests
# ===========================================================================
#
# Task 8.3 — these tests pin down behaviors that the prior
# ``managed-hosting-migration`` spec deliberately removed (the Setup Wizard,
# the ``bot_token`` field on ``ConfigModel``, the bot start/stop endpoints,
# the secret-store layering of non-secret preferences) and the README ↔
# dashboard parity rule from Requirement 10.4 that prevents the two
# documented surfaces from drifting apart.
#
# Every assertion here is a *negative* / *parity* check against a static
# artifact (HTML, README, Python source). They do not need the FastAPI
# ``TestClient`` and intentionally avoid it — the tests should be cheap to
# run and stable across refactors of the request handlers.
# ===========================================================================


import re  # noqa: E402  (kept local to this section so the bootstrap-section
            # tests above are unaffected by import reordering)
import io  # noqa: E402
import tokenize  # noqa: E402

INDEX_HTML_PATH = REPO_ROOT / "static" / "index.html"
APP_JS_PATH = REPO_ROOT / "static" / "app.js"
README_PATH = REPO_ROOT / "README.md"
SECRET_STORE_PATH = REPO_ROOT / "aegis" / "core" / "secret_store.py"
ENV_PATH = REPO_ROOT / ".env"
ENV_ENC_PATH = REPO_ROOT / ".env.enc"


def _strip_python_comments_and_strings(source: str) -> str:
    """Return ``source`` with all comments and string literals stripped.

    The managed-hosting invariant for ``secret_store.py`` only forbids
    *code references* to the hosting mode; documentation (comments,
    docstrings) referencing the field is harmless. The tokenize-based
    approach handles ``#`` line comments, single-line strings, and
    triple-quoted docstrings uniformly without resorting to a brittle
    line-prefix check.
    """
    out: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenizeError:
        # Fall back to the raw source so a tokenizer failure does not silently
        # let a real reference slip past the assertion.
        return source
    return " ".join(out)


def test_no_setup_wizard_in_index_html():
    """``static/index.html`` must not reintroduce any deleted setup-wizard ids.

    The ``managed-hosting-migration`` spec removed the in-dashboard Setup
    Wizard and its component ids; this feature must not regress that
    decision (Requirement 11.1). A grep-style substring check is enough
    because the ids are unique tokens that only appeared on the wizard's
    DOM elements.

    Validates: Requirement 11.1
    """
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    forbidden = [
        'id="setup-wizard"',
        'id="wizard-token"',
        'id="wizard-client-id"',
        'id="btn-save-wizard"',
        'id="btn-bot-toggle"',
        'id="btn-reconfigure"',
    ]
    found = [needle for needle in forbidden if needle in html]
    assert not found, (
        f"static/index.html reintroduces deleted setup-wizard element(s): "
        f"{found!r}. The managed-hosting-migration spec removed these "
        f"surfaces; the hosting-mode-selector feature must not bring them "
        f"back (R11.1)."
    )


def test_config_model_has_no_bot_token():
    """``ConfigModel`` must not regain a ``bot_token`` field.

    Tokens live exclusively in the server-side ``.env`` (or DPAPI-decrypted
    ``.env.enc``) and are read via ``utils.get_bot_token``. Adding
    ``bot_token`` back to the Pydantic model would re-expose it through
    ``GET /api/config`` and ``POST /api/config`` (R11.2).

    Validates: Requirement 11.2
    """
    fields = ConfigModel.model_fields  # Pydantic v2 introspection
    assert "bot_token" not in fields, (
        f"ConfigModel.model_fields contains 'bot_token'; the "
        f"managed-hosting-migration spec removed this field and the "
        f"hosting-mode-selector feature must not reintroduce it. "
        f"Current fields: {sorted(fields.keys())!r} (R11.2)."
    )


def test_no_bot_start_stop_endpoints_registered():
    """No FastAPI route must be registered at ``/api/bot/start`` or ``/api/bot/stop``.

    Iterating ``app.routes`` is the correct introspection — the routing
    table is the single source of truth for what URLs the server will
    actually answer, regardless of whether a stale ``@app.post(...)``
    decorator is sitting elsewhere in the source (R11.3).

    Validates: Requirement 11.3
    """
    forbidden_paths = {"/api/bot/start", "/api/bot/stop"}
    registered = []
    from unittest.mock import MagicMock
    from aegis.core.paths import Paths
    from aegis.core.state import LifecycleStateMachine
    mock_core = MagicMock()
    mock_core.paths = Paths()
    mock_core.state = LifecycleStateMachine()
    mock_core.config = None
    app = build_app(mock_core)
    for route in app.routes:
        path = getattr(route, "path", None)
        if path in forbidden_paths:
            registered.append(path)
    assert not registered, (
        f"FastAPI app has reintroduced bot start/stop endpoint(s): "
        f"{registered!r}. The managed-hosting-migration spec deleted "
        f"these routes (the bot is started by the server-side lifespan, "
        f"not by an HTTP call); the hosting-mode-selector feature must "
        f"not bring them back (R11.3)."
    )


def test_hosting_mode_not_in_secret_store_or_env():
    """The hosting mode must not leak into the Secret Store or ``.env`` files.

    R5.6 / R9.2 require the hosting mode to live exclusively in
    ``config.json`` because it is a non-sensitive deployment preference
    rather than a credential. This test pins down that boundary across
    all three on-disk surfaces:

    * ``secret_store.py`` source (excluding comments and docstrings, which
      may legitimately mention the field as documentation),
    * the on-disk ``.env`` (plaintext key=value file),
    * the on-disk ``.env.enc`` (DPAPI-encrypted JSON wrapper).

    Validates: Requirements 5.6, 9.2
    """
    # 1. secret_store.py — code-level check (comments and docstrings are
    #    permitted to mention the field as cross-reference documentation).
    source = SECRET_STORE_PATH.read_text(encoding="utf-8")
    code_only = _strip_python_comments_and_strings(source)
    assert "hosting_mode" not in code_only, (
        "secret_store.py code references 'hosting_mode'. The hosting mode "
        "is a non-sensitive deployment preference and must not be routed "
        "through the DPAPI secret store (R5.6, R9.2)."
    )
    assert "HOSTING_MODE" not in code_only, (
        "secret_store.py code references 'HOSTING_MODE'. The env-var "
        "bootstrap lives in web_server.py (the FastAPI lifespan), not in "
        "the secret store (R5.6, R9.2)."
    )

    # 2. .env (plaintext) — the substring check covers both the canonical
    #    ``HOSTING_MODE=...`` shape and any accidental lowercase variant.
    if ENV_PATH.is_file():
        env_text = ENV_PATH.read_text(encoding="utf-8", errors="replace")
        assert "HOSTING_MODE=" not in env_text, (
            ".env contains 'HOSTING_MODE=' — the hosting mode must not be "
            "persisted to the .env file (R5.6, R9.2). Move the value to "
            "config.json instead."
        )
        assert "hosting_mode=" not in env_text, (
            ".env contains 'hosting_mode=' — the hosting mode must not be "
            "persisted to the .env file (R5.6, R9.2)."
        )

    # 3. .env.enc (DPAPI-encrypted JSON wrapper) — the wrapper itself is a
    #    JSON document with a ``ciphertext_b64`` field, so a literal
    #    ``HOSTING_MODE=`` substring would only appear if someone hand-edited
    #    the file. Check raw bytes to catch both the JSON envelope and any
    #    incidental plaintext tail.
    if ENV_ENC_PATH.is_file():
        enc_bytes = ENV_ENC_PATH.read_bytes()
        assert b"HOSTING_MODE=" not in enc_bytes, (
            ".env.enc contains the literal substring 'HOSTING_MODE=' — the "
            "hosting mode must not be persisted to the encrypted secret "
            "store (R5.6, R9.2)."
        )
        assert b"hosting_mode=" not in enc_bytes, (
            ".env.enc contains the literal substring 'hosting_mode=' — the "
            "hosting mode must not be persisted to the encrypted secret "
            "store (R5.6, R9.2)."
        )


def _normalize_feature_item(text: str) -> str:
    """Strip ``<code>`` tags, backticks, and whitespace from a feature item.

    The README uses Markdown backticks (`` `on_guild_remove` ``) while the
    HTML uses ``<code>`` tags around the same identifiers. The two surfaces
    must contain the same *feature names*, so the comparison normalizes
    both to plain text before set-equality checking.
    """
    # Drop both halves of the <code> tag.
    text = re.sub(r"</?code\b[^>]*>", "", text, flags=re.IGNORECASE)
    # Drop Markdown backticks.
    text = text.replace("`", "")
    # Collapse runs of whitespace and trim.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_html_warning_items(html: str, section_class: str) -> list[str]:
    """Return the normalized ``<li>`` text for a warning section in ``html``.

    ``section_class`` is one of ``"warning-section-impacted"`` or
    ``"warning-section-unaffected"`` (the per-list modifier on the parent
    ``<section class="warning-section ...">`` element). The regex anchors
    on the literal class string so an unrelated ``<section>`` elsewhere in
    the document cannot match.
    """
    pattern = re.compile(
        r'<section\b[^>]*class="[^"]*\b' + re.escape(section_class) + r'\b[^"]*"[^>]*>'
        r"(.*?)</section>",
        re.DOTALL,
    )
    match = pattern.search(html)
    assert match, (
        f"Could not locate <section class='warning-section {section_class}'> "
        f"in static/index.html. The Feature Availability Warning panel "
        f"layout has drifted — update the regression test or restore the "
        f"section."
    )
    block = match.group(1)
    items = re.findall(r"<li>(.*?)</li>", block, flags=re.DOTALL)
    return [_normalize_feature_item(it) for it in items]


def _extract_readme_bullet_list(readme: str, header_label: str) -> list[str]:
    """Return the normalized bullet items under a ``**header_label**`` in README.

    The README emits each list as ``**Header:**`` followed by a blank line
    and a run of ``- `` bullets. The regex captures everything from the
    bold header up to the first paragraph break that isn't another bullet,
    which lets the test handle additional whitespace or line endings
    between the header and the list without false negatives.
    """
    pattern = re.compile(
        r"\*\*"
        + re.escape(header_label)
        + r"\*\*\s*\n+((?:[ \t]*-[ \t]+.+(?:\r?\n|$))+)",
    )
    match = pattern.search(readme)
    assert match, (
        f"Could not locate the '**{header_label}**' bullet list in README.md. "
        f"The README structure has drifted — update the regression test or "
        f"restore the section."
    )
    bullets_block = match.group(1)
    items = re.findall(r"^[ \t]*-[ \t]+(.+?)\s*$", bullets_block, flags=re.MULTILINE)
    return [_normalize_feature_item(it) for it in items]


def test_readme_feature_list_matches_dashboard_panel():
    """The README and the dashboard panel must list the SAME features.

    R10.4 forbids drift between the in-product Feature Availability Warning
    and the README's Hosting Modes section: if a feature moves between
    "Impacted" and "Unaffected" in one place, it must move in the other.
    The check is set-equality (not list-equality) so a benign reordering of
    bullet points does not break the regression — only an actual mismatch
    of feature names does.

    Validates: Requirement 10.4
    """
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    readme = README_PATH.read_text(encoding="utf-8")

    html_impacted = set(_extract_html_warning_items(html, "warning-section-impacted"))
    html_unaffected = set(
        _extract_html_warning_items(html, "warning-section-unaffected")
    )
    readme_impacted = set(
        _extract_readme_bullet_list(readme, "Impacted by intermittent uptime:")
    )
    readme_unaffected = set(
        _extract_readme_bullet_list(readme, "Unaffected by intermittent uptime:")
    )

    # Sanity — the lists are non-empty (a regex regression that captured
    # nothing would otherwise let the equality below pass vacuously).
    assert html_impacted, "HTML 'Impacted' list is empty"
    assert html_unaffected, "HTML 'Unaffected' list is empty"
    assert readme_impacted, "README 'Impacted' list is empty"
    assert readme_unaffected, "README 'Unaffected' list is empty"

    # The actual drift checks. ``symmetric_difference`` makes any mismatch
    # immediately readable in the failure message.
    impacted_diff = html_impacted ^ readme_impacted
    assert not impacted_diff, (
        f"Drift detected between the dashboard 'Impacted' list and the "
        f"README 'Impacted' list (R10.4). Items present in one but not the "
        f"other: {sorted(impacted_diff)!r}.\n"
        f"  HTML  : {sorted(html_impacted)!r}\n"
        f"  README: {sorted(readme_impacted)!r}"
    )
    unaffected_diff = html_unaffected ^ readme_unaffected
    assert not unaffected_diff, (
        f"Drift detected between the dashboard 'Unaffected' list and the "
        f"README 'Unaffected' list (R10.4). Items present in one but not the "
        f"other: {sorted(unaffected_diff)!r}.\n"
        f"  HTML  : {sorted(html_unaffected)!r}\n"
        f"  README: {sorted(readme_unaffected)!r}"
    )


def test_readme_documents_aegis_hosting_mode_env_var():
    """README must document ``AEGIS_HOSTING_MODE`` and its precedence rules.

    R6.4 / R10.5 require the README to spell out (a) the literal env-var
    name, (b) the two accepted values, and (c) the rule that a persisted
    ``config.json`` value wins over the env var on subsequent boots. The
    third point is the most operationally important — without it, an
    operator could expect a stale cloud env var to override a dashboard
    switch and be surprised when it doesn't.

    Validates: Requirements 6.4, 10.5
    """
    readme = README_PATH.read_text(encoding="utf-8")

    assert "AEGIS_HOSTING_MODE" in readme, (
        "README.md must document the AEGIS_HOSTING_MODE environment "
        "variable by exact name (R6.4, R10.5)."
    )
    assert "local_pc" in readme, (
        "README.md must list 'local_pc' as an accepted AEGIS_HOSTING_MODE "
        "value (R6.4, R10.5)."
    )
    assert "cloud" in readme, (
        "README.md must list 'cloud' as an accepted AEGIS_HOSTING_MODE "
        "value (R6.4, R10.5)."
    )
    # The "ignored when persisted" rule is the load-bearing safety guarantee
    # of R6.3. Accept either of two natural phrasings so a future README
    # rewrite can pick the wording that reads best in context.
    has_precedence_doc = ("ignored" in readme.lower()) or ("not overwrite" in readme.lower())
    assert has_precedence_doc, (
        "README.md must explicitly state that AEGIS_HOSTING_MODE is "
        "ignored (or 'will not overwrite') when a value is already "
        "persisted in config.json. Without this line, operators may "
        "expect a stale cloud env var to override their dashboard "
        "choice on the next boot (R6.4, R10.5)."
    )


def test_readme_hosting_modes_section_is_present():
    """README must keep the Hosting Modes, Discord Bot Setup, and Secrets sections.

    R10.1 requires a ``## Hosting Modes`` (level-2) section. R10.7 / R10.8
    require the existing ``## 🤖 Discord Bot Setup`` and ``## 🔐 Secrets at
    Rest`` sections to remain intact. Use a regex that anchors on the
    start of a line plus exactly two ``#`` characters so we are not fooled
    by a stray reference to "Hosting Modes" inside a paragraph.

    Validates: Requirements 10.1, 10.7, 10.8
    """
    readme = README_PATH.read_text(encoding="utf-8")

    # Level-2 headers only — ``## ``, not ``### `` or ``#### ``.
    h2_pattern = re.compile(r"^## (.+)$", re.MULTILINE)
    h2_headers = h2_pattern.findall(readme)

    has_hosting_modes = any("Hosting Modes" in h for h in h2_headers)
    assert has_hosting_modes, (
        f"README.md is missing a level-2 '## ... Hosting Modes' header "
        f"(R10.1). Found H2 headers: {h2_headers!r}."
    )

    has_bot_setup = any("Discord Bot Setup" in h for h in h2_headers)
    assert has_bot_setup, (
        f"README.md is missing the level-2 '## 🤖 Discord Bot Setup' "
        f"header — the hosting-mode-selector feature must not remove the "
        f"managed-hosting Pairing Onboarding Flow documentation (R10.7). "
        f"Found H2 headers: {h2_headers!r}."
    )

    has_secrets = any("Secrets at Rest" in h for h in h2_headers)
    assert has_secrets, (
        f"README.md is missing the level-2 '## 🔐 Secrets at Rest' header "
        f"— the hosting-mode-selector feature must not remove the DPAPI "
        f"secret-store documentation (R10.8). Found H2 headers: "
        f"{h2_headers!r}."
    )
