import os
import json
import logging
from pathlib import Path
from sqlalchemy.orm import Session
from aegis.db.models import SchemaMeta, ConfigKV, Template, Server
from aegis.core.utils import get_resource_path

logger = logging.getLogger("aegis.db.legacy_import")

def run_legacy_import(session: Session, paths) -> None:
    """Idempotently transitions config.json and leveling_data.json into the SQLite DB."""
    # 1. Check if legacy import is already done
    done_row = session.query(SchemaMeta).filter(SchemaMeta.key == "legacy_import_done").first()
    if done_row and done_row.value == "true":
        logger.info("Legacy import already completed. Skipping.")
        return

    # 2. Resolve paths for legacy files
    config_path = paths.config_file
    root_config = paths.root.parent / "config.json" if paths.root.name == "aegis" else paths.root / "config.json"
    
    src_config = None
    if config_path.exists():
        src_config = config_path
    elif root_config.exists():
        src_config = root_config
    else:
        # Check parent folder config.json (workspace root check for dev)
        workspace_config = Path("config.json")
        if workspace_config.exists():
            src_config = workspace_config

    leveling_path = paths.root / "leveling_data.json"
    if not leveling_path.exists():
        workspace_leveling = Path("leveling_data.json")
        if workspace_leveling.exists():
            leveling_path = workspace_leveling
        else:
            leveling_path = paths.root.parent / "leveling_data.json"

    # Import config.json
    if src_config and os.path.exists(src_config):
        try:
            with open(src_config, "r", encoding="utf-8") as f:
                config_data = json.load(f)
            
            secrets_to_omit = {"bot_token", "admin_password_hash"}
            for k, v in config_data.items():
                if k in secrets_to_omit:
                    continue
                val_str = json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                
                kv_row = session.query(ConfigKV).filter(ConfigKV.key == k).first()
                if not kv_row:
                    session.add(ConfigKV(key=k, value=val_str))
            
            # Import servers from guild_configs
            guild_configs = config_data.get("guild_configs", {})
            for guild_id, g_conf in guild_configs.items():
                srv = session.query(Server).filter(Server.guild_id == str(guild_id)).first()
                if not srv:
                    session.add(Server(
                        guild_id=str(guild_id),
                        name=g_conf.get("welcome_settings", {}).get("channel_name", f"Server {guild_id}"),
                        mode=config_data.get("hosting_mode", "cloud")
                    ))
            logger.info(f"Successfully imported config from {src_config} into config_kv and servers.")
        except Exception as e:
            logger.error(f"Error importing config.json: {e}")
            raise e

    # Import leveling_data.json
    if leveling_path.exists():
        try:
            with open(leveling_path, "r", encoding="utf-8") as f:
                leveling_data = json.load(f)
            
            kv_row = session.query(ConfigKV).filter(ConfigKV.key == "leveling_data").first()
            if not kv_row:
                session.add(ConfigKV(key="leveling_data", value=json.dumps(leveling_data)))
            logger.info(f"Successfully imported leveling data from {leveling_path} into config_kv.")
        except Exception as e:
            logger.error(f"Error importing leveling_data.json: {e}")
            raise e

    # Import built-in templates
    try:
        builtin_templates_dir = Path(get_resource_path("templates/builtin"))
        if builtin_templates_dir.exists():
            for filename in ["gaming.json", "community.json", "creator.json"]:
                filepath = builtin_templates_dir / filename
                if filepath.exists():
                    with open(filepath, "r", encoding="utf-8") as f:
                        template_content = json.load(f)
                    
                    name = filename.replace(".json", "")
                    tmpl = session.query(Template).filter(Template.name == name, Template.source == "builtin").first()
                    if not tmpl:
                        session.add(Template(
                            name=name,
                            kind=name,
                            json=json.dumps(template_content),
                            source="builtin"
                        ))
            logger.info("Successfully registered built-in templates into database.")
    except Exception as e:
        logger.error(f"Error importing builtin templates: {e}")

    # Mark legacy import as done in schema_meta
    if not done_row:
        session.add(SchemaMeta(key="legacy_import_done", value="true"))
    else:
        done_row.value = "true"
    
    session.commit()
    logger.info("Legacy import process complete.")
