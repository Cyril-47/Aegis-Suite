import json
from pathlib import Path
from typing import Union
from sqlalchemy.orm import Session
from aegis.core.paths import Paths
from aegis.db.models import Template
from aegis.templates_engine.model import validate

def import_json(raw: Union[str, dict], session: Session) -> Template:
    """Loads, validates, and stores a Template in the templates table with source='imported'."""
    if isinstance(raw, str):
        doc = json.loads(raw)
    else:
        doc = raw

    # Validate using the model
    model_instance = validate(doc)

    db_template = Template(
        name=model_instance.name,
        kind=doc.get("kind", "custom"),
        json=json.dumps(doc),
        source="imported"
    )
    session.add(db_template)
    session.commit()
    return db_template

def export_json(template_id: int, paths: Paths, session: Session) -> Path:
    """Reads a Template, validates it, serializes it, and writes it to templates/user."""
    db_template = session.query(Template).filter(Template.id == template_id).first()
    if not db_template:
        raise ValueError(f"Template with id {template_id} not found")

    doc = json.loads(db_template.json)
    # Validate just to be safe
    validate(doc)

    export_path = paths.templates_user / f"{db_template.name}.json"
    paths.templates_user.mkdir(parents=True, exist_ok=True)

    with open(export_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)

    return export_path
