import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from aegis.db.models import Base, Server, ConfigKV, Template, SchemaMeta
from aegis.db.legacy_import import run_legacy_import
from aegis.core.single_instance import SingleInstanceGuard
from aegis.web.app import build_app
from aegis.core.app_core import AppCore
import auth

def test_legacy_importer_idempotency_and_preservation(paths_tmp):
    # Setup legacy files under paths_tmp.root
    config_data = {
        "bot_token": "some_token_here",
        "client_id": "99998888",
        "hosting_mode": "local_pc",
        "welcome_settings": {"enabled": True, "channel_name": "general"},
        "guild_configs": {
            "12345": {
                "welcome_settings": {"channel_name": "welcome"}
            }
        }
    }
    
    config_file = paths_tmp.config_file
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    leveling_data = {
        "12345": {
            "6789": {"xp": 1500, "level": 3, "messages": 100}
        }
    }
    leveling_file = paths_tmp.root / "leveling_data.json"
    with open(leveling_file, "w", encoding="utf-8") as f:
        json.dump(leveling_data, f)

    # Setup mock templates directory
    builtin_dir = paths_tmp.root / "templates" / "builtin"
    builtin_dir.mkdir(parents=True, exist_ok=True)
    for filename in ["gaming.json", "community.json", "creator.json"]:
        with open(builtin_dir / filename, "w", encoding="utf-8") as f:
            json.dump({"name": filename.replace(".json", ""), "roles": []}, f)

    # Setup database
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    
    with Session() as session:
        # Run legacy import first time
        run_legacy_import(session, paths_tmp)
        
        # Verify schema_meta updated
        done_row = session.query(SchemaMeta).filter(SchemaMeta.key == "legacy_import_done").first()
        assert done_row is not None
        assert done_row.value == "true"
        
        # Verify config_kv populated
        client_id_row = session.query(ConfigKV).filter(ConfigKV.key == "client_id").first()
        assert client_id_row is not None
        assert client_id_row.value == '99998888'
        
        # Secrets should be omitted from config_kv
        token_row = session.query(ConfigKV).filter(ConfigKV.key == "bot_token").first()
        assert token_row is None
        
        # Verify servers table populated
        srv = session.query(Server).filter(Server.guild_id == "12345").first()
        assert srv is not None
        assert srv.mode == "local_pc"
        
        # Verify leveling data imported
        lvl_row = session.query(ConfigKV).filter(ConfigKV.key == "leveling_data").first()
        assert lvl_row is not None
        assert json.loads(lvl_row.value) == leveling_data
        
        # Verify templates table populated
        tmpl_count = session.query(Template).filter(Template.source == "builtin").count()
        assert tmpl_count == 3
        
        # Run legacy import second time (idempotency check)
        run_legacy_import(session, paths_tmp)
        
        # Ensure count is still the same (no duplicates)
        assert session.query(Template).filter(Template.source == "builtin").count() == 3
        assert session.query(Server).filter(Server.guild_id == "12345").count() == 1
        
    # Legacy files must not be deleted or modified
    assert config_file.exists()
    assert leveling_file.exists()

def test_single_instance_guard(paths_tmp):
    guard1 = SingleInstanceGuard(paths_tmp.root, name="TestAegisMutex")
    guard2 = SingleInstanceGuard(paths_tmp.root, name="TestAegisMutex")
    
    # First acquisition succeeds
    assert guard1.acquire() is True
    
    # Second acquisition fails
    assert guard2.acquire() is False
    
    # Write and read dashboard URL
    test_url = "http://127.0.0.1:8003"
    guard1.write_dashboard_url(test_url)
    assert guard2.read_dashboard_url() == test_url
    
    # Release first
    guard1.release()
    
    # Second acquisition now succeeds
    assert guard2.acquire() is True
    guard2.release()

def test_jwt_fail_closed_security(paths_tmp, monkeypatch):
    # Setup AppCore with paths
    core = AppCore(paths=paths_tmp)
    
    # Simulate setup completed but JWT_SECRET missing
    monkeypatch.delenv("JWT_SECRET", raising=False)
    
    app = build_app(core)
    client = TestClient(app)
    
    # Setup a password hash so middleware checks password completion
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")
    
    # Request secure endpoint without authorization header - fails 401
    r = client.get("/api/config")
    assert r.status_code == 401
    
    # Attempting validation with a token signed when secret is missing should fail
    token = auth.create_session(role="admin")
    if token:
        r2 = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code in (401, 403)
