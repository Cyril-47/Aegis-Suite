import asyncio
import ast
import builtins
import logging
import os
import re
from pathlib import Path
import pytest
import discord
from aegis.core.paths import Paths, UnwritableDataDirError
from aegis.core.logging_setup import setup_logging, register_secret, redact_string, RedactionFilter



@pytest.fixture(autouse=True)
def clean_logging():
    """Backup and restore logging configuration to avoid polluting other tests and keep files unlocked."""
    logger = logging.getLogger()
    orig_handlers = list(logger.handlers)
    orig_level = logger.level
    
    yield
    
    # Close and remove any handlers added during the test
    for h in list(logger.handlers):
        h.close()
        logger.removeHandler(h)
    
    # Restore original handlers
    for h in orig_handlers:
        logger.addHandler(h)
    logger.setLevel(orig_level)


def test_skeleton():
    """Verify package structure: subpackage __init__.py files exist and migration init does not."""
    expected_subpackages = [
        "core", "config", "db", "bot", "web", "web/routes", "templates_engine", "diagnostics"
    ]
    
    # Check that root __init__.py and __main__.py exist
    aegis_dir = Path("aegis")
    assert (aegis_dir / "__init__.py").exists()
    assert (aegis_dir / "__main__.py").exists()
    
    # Check subpackages
    for sub in expected_subpackages:
        init_file = aegis_dir / sub / "__init__.py"
        assert init_file.exists(), f"Missing subpackage __init__.py at {init_file}"
        
    # Check migrations folder does NOT have __init__.py
    migrations_init = aegis_dir / "db" / "migrations" / "__init__.py"
    assert not migrations_init.exists(), "migrations directory must NOT be a Python package"


def test_paths_attributes():
    """Verify that all path attributes resolve under the root and use pathlib.Path."""
    root_dir = Path("foo/bar")
    p = Paths(root=root_dir)
    
    assert p.root == root_dir
    assert isinstance(p.db_file, Path)
    assert p.db_file == root_dir / "aegis.db"
    assert p.config_file == root_dir / "config" / "config.json"
    assert p.backups_db == root_dir / "backups" / "db"
    assert p.backups_config == root_dir / "backups" / "config"
    assert p.templates_builtin == root_dir / "templates" / "builtin"
    assert p.templates_user == root_dir / "templates" / "user"
    assert p.diagnostics == root_dir / "diagnostics"
    assert p.log_file == root_dir / "logs" / "aegis.log"
    assert p.err_log_file == root_dir / "logs" / "aegis.err.log"


def test_paths_default_resolution_and_fallback():
    """Verify default root lazy resolution using APPDATA env var and fallback."""
    # Test case 1: APPDATA is set
    orig_appdata = os.environ.get("APPDATA")
    try:
        os.environ["APPDATA"] = "C:\\FakeAppData"
        p = Paths()
        assert p.root == Path("C:\\FakeAppData") / "Aegis"
        
        # Test case 2: APPDATA is unset
        del os.environ["APPDATA"]
        p2 = Paths()
        assert p2.root == Path.home() / "Aegis"
    finally:
        if orig_appdata is not None:
            os.environ["APPDATA"] = orig_appdata


def test_paths_ensure_and_idempotency(tmp_path):
    """Verify folder creation is correct and calling ensure() twice is idempotent."""
    root_dir = tmp_path / "my_aegis"
    p = Paths(root=root_dir)
    
    # First ensure call
    p.ensure()
    
    assert root_dir.exists()
    assert (root_dir / "config").exists()
    assert (root_dir / "backups" / "db").exists()
    assert (root_dir / "backups" / "config").exists()
    assert (root_dir / "templates" / "builtin").exists()
    assert (root_dir / "templates" / "user").exists()
    assert (root_dir / "diagnostics").exists()
    assert (root_dir / "logs").exists()
    
    # Second ensure call (idempotency check)
    p.ensure()


def test_paths_unwritable(tmp_path, monkeypatch):
    """Verify that Paths.ensure() raises UnwritableDataDirError when write probe fails."""
    root_dir = tmp_path / "unwritable_aegis"
    p = Paths(root=root_dir)
    
    # Monkeypatch the open built-in for the write probe to raise OSError
    orig_open = builtins.open
    
    def mock_open(file, *args, **kwargs):
        if ".write_probe" in str(file):
            raise OSError("Access denied")
        return orig_open(file, *args, **kwargs)
        
    monkeypatch.setattr(builtins, "open", mock_open)
    
    with pytest.raises(UnwritableDataDirError) as exc_info:
        p.ensure()
        
    assert "Data directory is unwritable" in str(exc_info.value)
    assert exc_info.value.path == root_dir


def test_paths_zero_imports():
    """Verify that aegis/core/paths.py has no imports of legacy modules (utils, secret_store, auth)."""
    module_path = Path("aegis/core/paths.py")
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    
    forbidden = {"utils", "secret_store", "auth"}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                assert name.name not in forbidden, f"Forbidden import found: {name.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in forbidden, f"Forbidden import found: {node.module}"


def test_fixtures_confirm(paths_tmp):
    """Confirm paths_tmp fixture works and real user profile is untouched."""
    assert paths_tmp.root.exists()
    assert "pytest" in str(paths_tmp.root)
    assert not (Path.home() / "AppData" / "Roaming" / "Aegis" / ".write_probe").exists()


def test_mock_discord_fixture(mock_discord):
    """Verify mock_discord fixture implements Real client shape and raises LoginFailure on bad token."""
    client = mock_discord()
    
    # Test valid token
    import asyncio
    async def run_success():
        await client.login("valid_token")
        assert len(client.guilds) == 2
        assert client.guilds[0].name == "Test Guild 1"
        await client.close()
        assert client.closed
        
    asyncio.run(run_success())

    # Test bad token raises LoginFailure
    async def run_failure():
        with pytest.raises(discord.errors.LoginFailure):
            await client.login("bad_token")
            
    asyncio.run(run_failure())


@pytest.mark.asyncio
async def test_async_pytest_mark_asyncio():
    """Verify that async test with mark runs successfully along with other tests."""
    await asyncio.sleep(0.01)
    assert True


def test_logging_setup_idempotency_and_handlers(paths_tmp):
    """Verify setup_logging is idempotent and attaches RedactionFilter to root handlers."""
    setup_logging(paths_tmp)
    
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) >= 3  # Console, aegis.log, aegis.err.log
    
    # Inspect handlers and confirm RedactionFilter is attached to each
    for h in root_logger.handlers:
        filters = [type(f) for f in h.filters]
        assert RedactionFilter in filters
        
    # Run setup_logging again (idempotency check)
    original_handler_count = len(root_logger.handlers)
    setup_logging(paths_tmp)
    assert len(root_logger.handlers) == original_handler_count


def test_logging_unwritable_fallback():
    """Verify logging setup falls back to console-only if directories/files are unwritable."""
    # Build a Paths instance with a totally invalid/unwritable path format
    # E.g. using invalid path characters on Windows
    bad_p = Paths(root=Path("NUL:\\InvalidPath"))
    
    # This should not raise an exception, but degrade to console-only
    setup_logging(bad_p)
    
    root_logger = logging.getLogger()
    from logging.handlers import RotatingFileHandler
    assert not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers)
    assert any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers)


def test_logging_redaction(paths_tmp):
    """Verify secret redaction across log files, logger args, exceptions, and third-party loggers."""
    setup_logging(paths_tmp)
    
    # 1. Register a secret
    live_secret = "SECRET_TOKEN_456"
    register_secret(live_secret)
    
    logger = logging.getLogger("aegis.core")
    third_party_logger = logging.getLogger("uvicorn.access")
    
    # Log direct secret
    logger.info("The secret token is SECRET_TOKEN_456.")
    
    # Log Discord-token-shaped heuristic string (not registered beforehand)
    heuristic_token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTA.abcdef.MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkw"
    logger.info("Token shape: %s", heuristic_token)
    
    # Log secret key pattern values
    logger.info("Config key: bot_token='secret_val_1'")
    logger.info("Config key: JWT_SECRET: \"secret_val_2\"")
    
    # Log via third-party logger
    third_party_logger.info("Third-party log carrying live_token: SECRET_TOKEN_456")
    
    # Log via logger.error with args
    logger.error("Token key in args: %s", live_secret)
    
    # Log a raised exception with secret
    try:
        raise ValueError(f"Crash due to secret value: {live_secret}")
    except ValueError as e:
        logger.exception("An exception occurred")

    # Flush loggers to ensure write completion
    for h in logging.getLogger().handlers:
        h.flush()
        
    # Read the log files
    log_content = paths_tmp.log_file.read_text(encoding="utf-8")
    err_content = paths_tmp.err_log_file.read_text(encoding="utf-8")
    
    # Verify no plaintext secrets are in the log files
    assert live_secret not in log_content
    assert heuristic_token not in log_content
    assert "secret_val_1" not in log_content
    assert "secret_val_2" not in log_content
    
    # Verify redacted content is present
    assert "***REDACTED***" in log_content
    assert "The secret token is ***REDACTED***" in log_content
    assert "Token shape: ***REDACTED***" in log_content
    assert "bot_token='***REDACTED***'" in log_content
    assert "JWT_SECRET: \"***REDACTED***\"" in log_content
    assert "Third-party log carrying live_token: ***REDACTED***" in log_content
    assert "Token key in args: ***REDACTED***" in log_content
    
    # Check error log file for exception redaction
    assert live_secret not in err_content
    assert "Crash due to secret value: ***REDACTED***" in err_content


def test_logging_utf8_emoji(paths_tmp):
    """Verify that file handlers use UTF-8 and log emojis without raising UnicodeEncodeError."""
    setup_logging(paths_tmp)
    
    logger = logging.getLogger("aegis.emoji")
    logger.info("Logging emojis: 🏆 and 📢")
    
    for h in logging.getLogger().handlers:
        h.flush()
        
    log_content = paths_tmp.log_file.read_text(encoding="utf-8")
    assert "Logging emojis: 🏆 and 📢" in log_content
