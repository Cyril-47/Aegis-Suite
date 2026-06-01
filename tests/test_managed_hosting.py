"""Regression tests for the managed-hosting migration.

This module asserts that the self-hosted bot-token surface has been removed
from the frontend assets and that the one-shot cleanup of residual
``localStorage`` keys is in place.

Tests T1-T6 (this file, task 8.1) cover frontend assets only:
- T1, T2, T3: forbidden DOM ids/names absent from ``static/index.html``
- T4:        offline notice contains the maintenance phrase and no interactive controls
- T5:        forbidden symbols and endpoint URLs absent from ``static/app.js``
- T6:        residual ``localStorage`` keys are cleared on first load

Additional tests (T7-T15) for the server, config, workflow, and README live
under tasks 8.2 and 8.3 and are appended to this same file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Resolve repository paths relative to this file so the tests are independent
# of the current working directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_INDEX_HTML = REPO_ROOT / "static" / "index.html"
STATIC_APP_JS = REPO_ROOT / "static" / "app.js"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def index_html() -> str:
    """Return the contents of ``static/index.html``."""
    assert STATIC_INDEX_HTML.is_file(), (
        f"Expected {STATIC_INDEX_HTML} to exist; the migration cannot be "
        "verified without the dashboard HTML."
    )
    return STATIC_INDEX_HTML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_js() -> str:
    """Return the contents of ``static/app.js``."""
    assert STATIC_APP_JS.is_file(), (
        f"Expected {STATIC_APP_JS} to exist; the migration cannot be "
        "verified without the dashboard JavaScript."
    )
    return STATIC_APP_JS.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_offline_overlay(html: str) -> str:
    """Return the substring of ``html`` covering the ``#offline-notice-overlay``
    element (opening tag through its matching ``</div>``).

    The function walks the source counting ``<div`` opens and ``</div>``
    closes so nested wrappers inside the overlay are included while sibling
    blocks (like ``#main-app``) are not.
    """
    start_match = re.search(r'<div\s[^>]*id="offline-notice-overlay"', html)
    assert start_match, (
        "Could not locate the opening tag for #offline-notice-overlay in "
        "static/index.html."
    )
    start = start_match.start()
    depth = 0
    token_re = re.compile(r"<div\b|</div\s*>", re.IGNORECASE)
    for match in token_re.finditer(html, start):
        token = match.group(0).lower()
        if token.startswith("</"):
            depth -= 1
            if depth == 0:
                return html[start : match.end()]
        else:
            depth += 1
    raise AssertionError(
        "Could not find a balanced closing </div> for #offline-notice-overlay."
    )


# ---------------------------------------------------------------------------
# T1: Setup wizard element is removed from index.html
# ---------------------------------------------------------------------------


def test_t1_setup_wizard_id_absent(index_html: str) -> None:
    """The ``#setup-wizard`` element must not appear in the dashboard HTML.

    Validates: Requirements 1.1
    """
    assert 'id="setup-wizard"' not in index_html, (
        "static/index.html still contains an element with id=\"setup-wizard\"; "
        "the Setup Wizard block must be deleted entirely (R1.1)."
    )


# ---------------------------------------------------------------------------
# T2: Reconfigure and bot-toggle buttons are removed
# ---------------------------------------------------------------------------


def test_t2_reconfigure_and_bot_toggle_ids_absent(index_html: str) -> None:
    """Neither ``#btn-reconfigure`` nor ``#btn-bot-toggle`` should exist.

    Validates: Requirements 1.3, 1.4
    """
    assert 'id="btn-reconfigure"' not in index_html, (
        "static/index.html still contains id=\"btn-reconfigure\"; the "
        "\"Setup Configuration / Change Credentials\" info row must be "
        "removed (R1.3)."
    )
    assert 'id="btn-bot-toggle"' not in index_html, (
        "static/index.html still contains id=\"btn-bot-toggle\"; the bot "
        "start/stop button must be removed from the sidebar bot badge "
        "(R1.4)."
    )


# ---------------------------------------------------------------------------
# T3: Wizard inputs and bot-token form field are removed
# ---------------------------------------------------------------------------


def test_t3_wizard_inputs_and_bot_token_field_absent(index_html: str) -> None:
    """The wizard token/client_id inputs and the legacy ``bot-token`` form
    field must not appear anywhere in the dashboard HTML.

    Validates: Requirements 1.2, 4.3
    """
    assert 'id="wizard-token"' not in index_html, (
        "static/index.html still contains id=\"wizard-token\"; the wizard "
        "token input must be deleted (R1.2, R4.3)."
    )
    assert 'id="wizard-client-id"' not in index_html, (
        "static/index.html still contains id=\"wizard-client-id\"; the "
        "wizard client-id input must be deleted (R1.2, R4.3)."
    )
    assert 'name="bot-token"' not in index_html, (
        "static/index.html still contains name=\"bot-token\"; no form field "
        "named \"bot-token\" may exist (R4.3)."
    )


# ---------------------------------------------------------------------------
# T4: Offline overlay contains the maintenance phrase and no interactive controls
# ---------------------------------------------------------------------------


def test_t4_offline_overlay_is_maintenance_only(index_html: str) -> None:
    """The ``#offline-notice-overlay`` block must contain the maintenance
    phrase and must not embed any link, button, input, or form control.

    Validates: Requirements 3.2, 3.3, 3.4
    """
    overlay = _extract_offline_overlay(index_html)

    assert "temporarily unavailable" in overlay.lower(), (
        "#offline-notice-overlay does not contain the required "
        "maintenance phrase \"temporarily unavailable\" (R3.2)."
    )

    forbidden_tags = ("<a ", "<button ", "<input ", "<form ")
    for tag in forbidden_tags:
        assert tag not in overlay.lower(), (
            f"#offline-notice-overlay contains a forbidden interactive tag "
            f"{tag!r}. The offline notice must be a static maintenance "
            "message with no controls (R3.3, R3.4)."
        )


# ---------------------------------------------------------------------------
# T5: Frontend JS no longer references the removed credential surface
# ---------------------------------------------------------------------------


def test_t5_app_js_credential_surface_removed(app_js: str) -> None:
    """``static/app.js`` must not define ``saveWizardCredentials`` /
    ``startBot`` / ``stopBot``, must not call the deleted ``/api/bot/start``
    or ``/api/bot/stop`` endpoints, and must not look up the removed
    button ids.

    Validates: Requirements 1.5, 1.6, 2.1, 2.2
    """
    forbidden_substrings = (
        "saveWizardCredentials",
        "function startBot",
        "function stopBot",
        "'/api/bot/start'",
        "'/api/bot/stop'",
        "getElementById('btn-save-wizard')",
        "getElementById('btn-bot-toggle')",
        "getElementById('btn-reconfigure')",
    )
    for needle in forbidden_substrings:
        assert needle not in app_js, (
            f"static/app.js still contains the forbidden substring "
            f"{needle!r}; the credential-entry surface must be removed "
            "from the frontend (R1.5, R1.6, R2.1, R2.2)."
        )


# ---------------------------------------------------------------------------
# T6: One-shot cleanup of residual credential keys is in place
# ---------------------------------------------------------------------------


def test_t6_app_js_clears_residual_local_storage_keys(app_js: str) -> None:
    """``static/app.js`` must remove any pre-existing ``bot_token`` and
    ``client_id`` ``localStorage`` keys on first load.

    Validates: Requirements 4.2
    """
    assert "localStorage.removeItem('bot_token')" in app_js, (
        "static/app.js does not call "
        "localStorage.removeItem('bot_token'); residual credential keys "
        "from prior versions will not be cleared on first load (R4.2)."
    )
    assert "localStorage.removeItem('client_id')" in app_js, (
        "static/app.js does not call "
        "localStorage.removeItem('client_id'); residual credential keys "
        "from prior versions will not be cleared on first load (R4.2)."
    )


# ===========================================================================
# Wave 2 (task 8.2) — server-side route tests using fastapi.testclient
# ===========================================================================
#
# These tests bring the FastAPI app online via ``TestClient(app)`` with the
# Discord bot service stubbed out, then exercise the admin login flow to
# verify that:
#
#   T7  : the ``bot_token`` field has been removed from ``class ConfigModel``
#   T8  : ``POST /api/bot/start`` and ``POST /api/bot/stop`` return HTTP 404
#   T9  : ``GET /api/config`` no longer includes a ``bot_token`` key
#   T10 : ``POST /api/config`` with a stray ``bot_token`` field is silently
#         ignored and never writes to ``os.environ``, ``.env``, or
#         ``config.json``
#
# T7 is a pure source-file inspection. T8-T10 require the FastAPI app, an
# authenticated admin session, and a config-state snapshot/restore fixture.

import copy
import json
import os
import sys

# Ensure the repo root is on ``sys.path`` so ``import web_server`` resolves to
# the project module rather than any unrelated package on the global path.
_REPO_ROOT_STR = str(REPO_ROOT)
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)

WEB_SERVER_PY = REPO_ROOT / "web_server.py"
ENV_FILE = REPO_ROOT / ".env"
CONFIG_JSON = REPO_ROOT / "config.json"


# ---------------------------------------------------------------------------
# Fixtures for T8-T10
# ---------------------------------------------------------------------------


@pytest.fixture
def stubbed_app(monkeypatch):
    """Return the FastAPI app with the Discord bot service stubbed out.

    The lifespan startup in ``web_server.py`` calls
    ``bot_manager.start_bot_service(token)`` whenever
    ``DISCORD_BOT_TOKEN`` is present in the environment. Tests must not
    actually open a websocket to Discord, so ``start_bot_service`` and
    ``stop_bot_service`` are replaced with async no-ops before the
    ``TestClient`` enters its context manager (which triggers the
    lifespan).
    """
    import bot_manager
    import web_server

    async def _noop_start(_token):  # pragma: no cover - trivial stub
        return None

    async def _noop_stop():  # pragma: no cover - trivial stub
        return None

    monkeypatch.setattr(bot_manager, "start_bot_service", _noop_start)
    monkeypatch.setattr(bot_manager, "stop_bot_service", _noop_stop)
    # Make sure ``bot_manager.get_bot()`` keeps returning ``None`` so the
    # shutdown branch in the lifespan does not try to stop a non-existent
    # bot via the (already-stubbed) service.
    monkeypatch.setattr(bot_manager, "bot_instance", None, raising=False)

    return web_server.app


@pytest.fixture
def client(stubbed_app):
    """Return a ``TestClient`` whose lifespan has been entered."""
    from fastapi.testclient import TestClient

    with TestClient(stubbed_app) as test_client:
        yield test_client


@pytest.fixture
def admin_token(client, monkeypatch):
    """Authenticate as admin via ``POST /api/auth/login`` and return the JWT.

    The fixture installs a known password hash in ``ADMIN_PASSWORD_HASH``
    for the duration of the test (``monkeypatch.setenv`` restores the
    original value afterwards) and exchanges the matching plaintext for
    a signed admin session token.
    """
    import auth

    test_password = "test-admin-password-T8-T10"
    test_hash = auth.hash_password(test_password)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", test_hash)

    resp = client.post("/api/auth/login", json={"password": test_password})
    assert resp.status_code == 200, (
        f"Admin login failed: status={resp.status_code} body={resp.text!r}"
    )
    body = resp.json()
    assert body.get("role") == "admin", (
        f"Expected admin role from /api/auth/login, got {body!r}"
    )
    token = body.get("token")
    assert token, f"Login response did not include a token: {body!r}"
    return token


@pytest.fixture
def config_state_snapshot():
    """Snapshot ``config.json`` on disk and restore it after the test.

    The T10 test exercises ``POST /api/config`` which calls
    ``utils.save_config``. Even though the route MUST NOT mutate the
    ``bot_token`` field, the merge logic in the admin branch does
    rewrite the file. This fixture captures the original byte contents
    and writes them back unconditionally on teardown so the repo
    state is preserved.
    """
    original = CONFIG_JSON.read_bytes() if CONFIG_JSON.is_file() else None
    yield
    if original is not None:
        CONFIG_JSON.write_bytes(original)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_config_model_body(source: str) -> str:
    """Return the indented body of ``class ConfigModel`` in ``web_server.py``.

    The body is everything after the ``class ConfigModel`` opening line up
    to the next top-level statement (a non-blank line that starts at column
    0). Pydantic field declarations inside the class are uniformly indented
    by 4 spaces.
    """
    marker = "class ConfigModel"
    start_idx = source.find(marker)
    assert start_idx != -1, (
        "Could not find 'class ConfigModel' in web_server.py. The "
        "managed-hosting migration cannot be verified."
    )
    # Step over the class header line.
    header_end = source.find("\n", start_idx)
    assert header_end != -1, "ConfigModel class header has no terminating newline."

    body_lines: list[str] = []
    for line in source[header_end + 1 :].splitlines():
        # End of class body: a non-empty line that starts in column 0.
        if line and not line[0].isspace():
            break
        body_lines.append(line)
    return "\n".join(body_lines)


# ---------------------------------------------------------------------------
# T7: ConfigModel no longer carries a bot_token field
# ---------------------------------------------------------------------------


def test_t7_config_model_has_no_bot_token_field() -> None:
    """``class ConfigModel`` in ``web_server.py`` must not declare ``bot_token``.

    Validates: Requirements 2.4
    """
    source = WEB_SERVER_PY.read_text(encoding="utf-8")
    body = _extract_config_model_body(source)

    # Look for a Pydantic field declaration at the start of a stripped line.
    # ``bot_token: str`` was the original field — any reappearance with a
    # type annotation should fail the test.
    for raw_line in body.splitlines():
        stripped = raw_line.strip()
        assert not stripped.startswith("bot_token:"), (
            "class ConfigModel still declares a 'bot_token:' field; the "
            "managed-hosting migration requires that field to be removed "
            f"(R2.4). Offending line: {raw_line!r}"
        )


# ---------------------------------------------------------------------------
# T8: /api/bot/start and /api/bot/stop are deleted (HTTP 404)
# ---------------------------------------------------------------------------


def test_t8_bot_start_and_stop_routes_return_404(client, admin_token) -> None:
    """``POST /api/bot/start`` and ``POST /api/bot/stop`` must return 404.

    The middleware admits the request once a valid admin token is presented;
    FastAPI's router then has no matching route and replies with 404.

    Validates: Requirements 2.1, 2.2, 2.3
    """
    headers = {"Authorization": f"Bearer {admin_token}"}

    start_resp = client.post("/api/bot/start", headers=headers)
    assert start_resp.status_code == 404, (
        "POST /api/bot/start should return 404 because the route is "
        f"deleted, but got {start_resp.status_code}: {start_resp.text!r} "
        "(R2.1, R2.3)."
    )

    stop_resp = client.post("/api/bot/stop", headers=headers)
    assert stop_resp.status_code == 404, (
        "POST /api/bot/stop should return 404 because the route is "
        f"deleted, but got {stop_resp.status_code}: {stop_resp.text!r} "
        "(R2.2, R2.3)."
    )


# ---------------------------------------------------------------------------
# T9: GET /api/config does not expose a bot_token key
# ---------------------------------------------------------------------------


def test_t9_get_config_does_not_expose_bot_token(client, admin_token) -> None:
    """``GET /api/config`` must not include a top-level ``bot_token`` key.

    Validates: Requirements 2.5
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.get("/api/config", headers=headers)
    assert resp.status_code == 200, (
        f"GET /api/config failed: {resp.status_code} {resp.text!r}"
    )
    body = resp.json()
    assert isinstance(body, dict), (
        f"GET /api/config should return a JSON object, got {type(body).__name__}."
    )
    assert "bot_token" not in body, (
        "GET /api/config still includes a 'bot_token' key in the response. "
        "The managed-hosting migration requires that key to be removed "
        f"entirely (R2.5). Top-level keys present: {sorted(body.keys())!r}"
    )


# ---------------------------------------------------------------------------
# T10: POST /api/config with stray bot_token does not mutate any storage
# ---------------------------------------------------------------------------


def test_t10_post_config_ignores_stray_bot_token(
    client, admin_token, config_state_snapshot
) -> None:
    """``POST /api/config`` with a ``"bot_token": "FAKE.TOKEN.VALUE"`` field
    must succeed (HTTP 200) AND must not write the value to ``os.environ``,
    the on-disk ``.env`` file, or ``config.json``.

    Validates: Requirements 2.6
    """
    fake_token = "FAKE.TOKEN.VALUE"

    # --- Snapshot pre-state ---
    env_token_before = os.environ.get("DISCORD_BOT_TOKEN")
    env_file_before = ENV_FILE.read_bytes() if ENV_FILE.is_file() else b""

    # Build a valid ConfigModel payload from the current config.json so
    # the server's merge logic round-trips cleanly. Then attach the
    # stray ``bot_token`` field that the server must ignore.
    import utils  # noqa: WPS433 (test-time import is intentional)

    current = utils.load_config()
    payload = {
        "client_id": current.get("client_id", ""),
        "welcome_settings": copy.deepcopy(current.get("welcome_settings", {})),
        "automod_settings": copy.deepcopy(current.get("automod_settings", {})),
        "ticket_settings": copy.deepcopy(current.get("ticket_settings")),
        "custom_commands": copy.deepcopy(current.get("custom_commands", {})),
        # Stray field that MUST be ignored:
        "bot_token": fake_token,
    }

    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post("/api/config", headers=headers, json=payload)

    assert resp.status_code == 200, (
        f"POST /api/config returned {resp.status_code}: {resp.text!r}. "
        "A stray 'bot_token' field must be silently ignored, not rejected "
        "(R2.6)."
    )

    # --- os.environ unchanged ---
    env_token_after = os.environ.get("DISCORD_BOT_TOKEN")
    assert env_token_after == env_token_before, (
        "os.environ['DISCORD_BOT_TOKEN'] was mutated by POST /api/config. "
        f"Before: {env_token_before!r}, after: {env_token_after!r}. "
        "The dashboard must never write the bot token (R2.6)."
    )
    if env_token_after is not None:
        assert fake_token not in env_token_after, (
            "os.environ['DISCORD_BOT_TOKEN'] now contains the fake token "
            f"value {fake_token!r}; POST /api/config must not write the "
            "stray field (R2.6)."
        )

    # --- .env on disk unchanged (and definitely does not contain the fake) ---
    if ENV_FILE.is_file():
        env_file_after = ENV_FILE.read_bytes()
        assert fake_token.encode("utf-8") not in env_file_after, (
            f"The on-disk .env file at {ENV_FILE} now contains the fake "
            f"token value {fake_token!r}. POST /api/config must not write "
            "the stray field to .env (R2.6)."
        )
        assert env_file_after == env_file_before, (
            f"The on-disk .env file at {ENV_FILE} was modified by "
            "POST /api/config. The dashboard must never rewrite .env when "
            "configuration is saved (R2.6)."
        )

    # --- config.json["bot_token"] is empty after the round-trip ---
    config_after = utils.load_config()
    bot_token_in_config = config_after.get("bot_token", "")
    assert bot_token_in_config == "", (
        f"config.json['bot_token'] is {bot_token_in_config!r} after "
        "POST /api/config; the field must remain empty since tokens live "
        "exclusively in the server's .env (R2.6)."
    )

    # And as a belt-and-suspenders check, the raw bytes of config.json
    # must not contain the fake value either.
    raw_config = json.dumps(config_after)
    assert fake_token not in raw_config, (
        "config.json now contains the fake token value somewhere in its "
        "JSON body, even though config.json['bot_token'] is empty. The "
        "stray field must be dropped before persistence (R2.6)."
    )


# ===========================================================================
# Wave 3 (task 8.3) — config, workflow, README, and run.py tests
# ===========================================================================
#
# These tests validate the migration's non-server deliverables: the pinned
# ``requirements.txt`` (T11), the GitHub Actions deploy workflow (T12), the
# rewritten README "Discord Bot Setup" section (T13), and the headless-cloud
# environment guard in ``run.py`` (T14, T15).

import importlib

REQUIREMENTS_TXT = REPO_ROOT / "requirements.txt"
DEPLOY_YML = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
VERIFY_YML = REPO_ROOT / ".github" / "workflows" / "verify.yml"
README_MD = REPO_ROOT / "README.md"


# ---------------------------------------------------------------------------
# T11: requirements.txt pins every required runtime dependency
# ---------------------------------------------------------------------------


def test_t11_requirements_txt_pins_required_runtime_deps() -> None:
    """``requirements.txt`` must list each required runtime dependency and
    pin it via ``==`` or ``~=``.

    The check is per-line so blank lines, comments, and additional pinned
    dependencies (e.g. ``Pillow``) are ignored. For each required package,
    the test searches for a line that begins with the canonical name
    (case-insensitive), optionally followed by an extras specifier like
    ``[standard]``, then exactly ``==`` or ``~=``, then a digit.

    Validates: Requirements 8.1, 8.2, 8.3
    """
    assert REQUIREMENTS_TXT.is_file(), (
        f"Expected {REQUIREMENTS_TXT} to exist; cloud installers will "
        "fail without it (R8.1)."
    )
    contents = REQUIREMENTS_TXT.read_text(encoding="utf-8")

    required_packages = (
        "discord.py",
        "fastapi",
        "uvicorn",
        "websockets",
        "yt-dlp",
        "PyNaCl",
        "pydantic",
    )

    # The regex from the task spec, applied per-line. We escape ``.`` inside
    # the package name when building the per-package pattern so ``discord.py``
    # is matched literally.
    pin_re_template = r"^{name}(\[[a-z]+\])?(==|~=)\d"

    # Drop comment lines and empty lines for clearer error messages.
    declared_lines = [
        line.strip()
        for line in contents.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    for pkg in required_packages:
        pattern = pin_re_template.format(name=re.escape(pkg))
        compiled = re.compile(pattern, re.IGNORECASE)
        matches = [line for line in declared_lines if compiled.match(line)]
        assert matches, (
            f"requirements.txt does not pin a required runtime dependency: "
            f"expected a line matching pattern {pattern!r} (i.e. "
            f"`{pkg}[extras]==X` or `{pkg}~=X`). Declared lines were: "
            f"{declared_lines!r} (R8.2, R8.3)."
        )


# ---------------------------------------------------------------------------
# T12: deploy.yml structure and verify.yml preservation
# ---------------------------------------------------------------------------


def test_t12_deploy_workflow_structure_and_verify_preserved() -> None:
    """Parse ``.github/workflows/deploy.yml`` and assert its trigger,
    job structure, ``needs`` wiring, and ``RAILWAY_TOKEN`` reference. Also
    assert that ``.github/workflows/verify.yml`` still exists on disk.

    Validates: Requirements 9.1, 9.2, 9.4, 9.5, 9.7
    """
    yaml = pytest.importorskip(
        "yaml",
        reason="PyYAML is required to parse the deploy workflow. Install with "
        "`pip install pyyaml` (the deploy workflow's CI step already does).",
    )

    assert DEPLOY_YML.is_file(), (
        f"Expected {DEPLOY_YML} to exist; the managed-hosting migration "
        "ships a Railway deploy workflow (R9.1)."
    )

    with DEPLOY_YML.open("r", encoding="utf-8") as handle:
        workflow = yaml.safe_load(handle)

    assert isinstance(workflow, dict), (
        f"deploy.yml did not parse to a mapping; got {type(workflow).__name__}."
    )

    # NOTE: PyYAML interprets the unquoted YAML key ``on`` as the Python
    # boolean ``True``. Fall back to that key when the literal string is
    # missing so the test works against either representation.
    on_block = workflow.get("on", workflow.get(True))
    assert isinstance(on_block, dict), (
        f"deploy.yml's `on:` block must be a mapping with a `push` trigger; "
        f"got {on_block!r} (R9.2)."
    )
    push = on_block.get("push")
    assert isinstance(push, dict), (
        f"deploy.yml's `on.push:` must be a mapping; got {push!r} (R9.2)."
    )
    assert push.get("branches") == ["main"], (
        f"deploy.yml must trigger on push to `main` only; got "
        f"on.push.branches={push.get('branches')!r} (R9.2)."
    )

    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), (
        f"deploy.yml must declare a top-level `jobs:` mapping; got {jobs!r}."
    )
    assert "test" in jobs, (
        f"deploy.yml must define a `test` job; jobs present: "
        f"{sorted(jobs.keys())!r} (R9.4)."
    )
    assert "deploy" in jobs, (
        f"deploy.yml must define a `deploy` job; jobs present: "
        f"{sorted(jobs.keys())!r} (R9.4)."
    )

    deploy_job = jobs["deploy"]
    assert isinstance(deploy_job, dict), (
        f"`jobs.deploy` must be a mapping; got {deploy_job!r}."
    )
    assert deploy_job.get("needs") == "test", (
        "`jobs.deploy.needs` must equal the string 'test' so the deploy "
        "job is gated on a successful test job; got "
        f"{deploy_job.get('needs')!r} (R9.4)."
    )

    # The deploy job must reference the RAILWAY_TOKEN secret somewhere in
    # its YAML body. Re-serialize the job to YAML so the search is robust
    # against differing structures (env block, run script, with: keys).
    deploy_yaml = yaml.safe_dump(deploy_job)
    assert "secrets.RAILWAY_TOKEN" in deploy_yaml, (
        "The deploy job must reference `secrets.RAILWAY_TOKEN` so the "
        "Railway CLI can authenticate non-interactively. Job body did "
        f"not contain the substring. Job YAML:\n{deploy_yaml}\n(R9.5)."
    )

    # The pre-existing verify workflow must still be on disk untouched.
    assert VERIFY_YML.is_file(), (
        f"Expected {VERIFY_YML} to still exist; the managed-hosting "
        "migration must not delete or replace the security regression "
        "workflow (R9.7)."
    )


# ---------------------------------------------------------------------------
# T13: README's Discord Bot Setup section is rewritten
# ---------------------------------------------------------------------------


def test_t13_readme_discord_bot_setup_section_rewritten() -> None:
    """The rewritten "Discord Bot Setup" section in ``README.md`` must
    describe the pairing flow and must not retain any of the legacy
    Discord Developer Portal vocabulary. The "Known Technical Debt &
    Limits" section must remain on disk.

    Validates: Requirements 10.1, 10.2, 10.3, 10.4, 10.5
    """
    assert README_MD.is_file(), f"Expected {README_MD} to exist."
    readme = README_MD.read_text(encoding="utf-8")

    # Locate the rewritten section. The header may carry an emoji prefix
    # (the current copy uses "## 🤖 Discord Bot Setup"), so search for the
    # phrase rather than an exact prefix.
    header_match = re.search(
        r"^##[^\n]*Discord Bot Setup[^\n]*$",
        readme,
        flags=re.MULTILINE,
    )
    assert header_match, (
        "Could not find a level-2 header containing 'Discord Bot Setup' "
        "in README.md. The migration rewrote that section (R10.1)."
    )

    # Slice from the start of the matched header to the next ``## `` header
    # so the section body is well-defined.
    section_start = header_match.start()
    next_header = re.search(
        r"^## ",
        readme[section_start + len(header_match.group(0)) :],
        flags=re.MULTILINE,
    )
    if next_header is None:
        section_text = readme[section_start:]
    else:
        section_end = (
            section_start + len(header_match.group(0)) + next_header.start()
        )
        section_text = readme[section_start:section_end]

    # Required content (R10.2, R10.4).
    assert "/linkdashboard" in section_text, (
        "The rewritten Discord Bot Setup section must instruct users to "
        "run `/linkdashboard` in their server. Section body was:\n"
        f"{section_text!r}\n(R10.2)."
    )
    assert "[your domain]" in section_text, (
        "The rewritten Discord Bot Setup section must include the literal "
        "`[your domain]` placeholder for the maintainer's hosted "
        f"dashboard URL. Section body was:\n{section_text!r}\n(R10.4)."
    )

    # Forbidden legacy vocabulary (R10.3), case-insensitive.
    forbidden_phrases = (
        "Discord Developer Portal",
        "Privileged Gateway Intents",
        "Reset Token",
    )
    section_lower = section_text.lower()
    for phrase in forbidden_phrases:
        assert phrase.lower() not in section_lower, (
            f"The rewritten Discord Bot Setup section still mentions the "
            f"legacy phrase {phrase!r}; the managed-hosting migration "
            "removed all references to the Discord Developer Portal flow "
            f"(R10.3). Section body was:\n{section_text!r}"
        )

    # The Known Technical Debt section must still be present (R10.5).
    debt_match = re.search(
        r"^##[^\n]*Known Technical Debt[^\n]*$",
        readme,
        flags=re.MULTILINE,
    )
    assert debt_match, (
        "README.md no longer contains a level-2 header for 'Known "
        "Technical Debt & Limits'. That section must be retained verbatim "
        "(R10.5)."
    )
    debt_start = debt_match.start()
    debt_next = re.search(
        r"^## ",
        readme[debt_start + len(debt_match.group(0)) :],
        flags=re.MULTILINE,
    )
    if debt_next is None:
        debt_text = readme[debt_start:]
    else:
        debt_text = readme[
            debt_start : debt_start + len(debt_match.group(0)) + debt_next.start()
        ]
    assert "JSON" in debt_text, (
        "The 'Known Technical Debt & Limits' section must still mention "
        f"JSON file contention (R10.5). Section body:\n{debt_text!r}"
    )
    assert "SQLite" in debt_text, (
        "The 'Known Technical Debt & Limits' section must still mention "
        "the SQLite migration roadmap (R10.5). Section body:\n"
        f"{debt_text!r}"
    )


# ---------------------------------------------------------------------------
# T14: is_headless_cloud() returns False when neither var is set
# ---------------------------------------------------------------------------


def test_t14_is_headless_cloud_false_without_env_vars(monkeypatch) -> None:
    """``run.is_headless_cloud()`` must return ``False`` when neither
    ``RAILWAY_ENVIRONMENT`` nor ``RENDER`` is present in the environment.

    Validates: Requirements 7.1
    """
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.delenv("RENDER", raising=False)

    # ``run.py`` is guarded by ``if __name__ == "__main__":`` so importing
    # it does not start uvicorn. Use ``importlib`` so a previously cached
    # module still gets its function exercised against the patched env.
    import run  # noqa: WPS433 (test-time import is intentional)

    importlib.reload(run)

    assert run.is_headless_cloud() is False, (
        "is_headless_cloud() must return False when neither "
        "RAILWAY_ENVIRONMENT nor RENDER is set; the local launcher "
        "should still open a browser tab (R7.1)."
    )


# ---------------------------------------------------------------------------
# T15: is_headless_cloud() returns True when either var is set
# ---------------------------------------------------------------------------


def test_t15_is_headless_cloud_true_when_railway_or_render_set(
    monkeypatch,
) -> None:
    """``run.is_headless_cloud()`` must return ``True`` when either
    ``RAILWAY_ENVIRONMENT`` or ``RENDER`` is set to a non-empty value.

    Validates: Requirements 7.2
    """
    import run  # noqa: WPS433 (test-time import is intentional)

    # --- Case A: RAILWAY_ENVIRONMENT set, RENDER unset ---
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("RENDER", raising=False)
    importlib.reload(run)
    assert run.is_headless_cloud() is True, (
        "is_headless_cloud() must return True when "
        "RAILWAY_ENVIRONMENT is set to a non-empty value; the launcher "
        "must skip webbrowser.open on Railway (R7.2)."
    )

    # --- Case B: RAILWAY_ENVIRONMENT unset, RENDER set ---
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.setenv("RENDER", "true")
    importlib.reload(run)
    assert run.is_headless_cloud() is True, (
        "is_headless_cloud() must return True when "
        "RENDER is set to a non-empty value; the launcher must skip "
        "webbrowser.open on Render (R7.2)."
    )
