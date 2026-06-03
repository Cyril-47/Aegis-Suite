from typing import List, Optional
from pydantic import BaseModel, Field, ValidationError

class TemplateInvalid(Exception):
    """Exception raised when a template fails schema validation."""
    pass

class OverwriteModel(BaseModel):
    target_type: str
    target_name: str
    allow: int
    deny: int

class ChannelModel(BaseModel):
    name: str
    type: str  # text, voice
    position: int
    overwrites: List[OverwriteModel] = Field(default_factory=list)

class CategoryModel(BaseModel):
    name: str
    position: int
    overwrites: List[OverwriteModel] = Field(default_factory=list)
    channels: List[ChannelModel] = Field(default_factory=list)

class RoleModel(BaseModel):
    name: str
    color: int
    hoist: bool
    permissions: int
    position: int

class TemplateModel(BaseModel):
    name: str
    verification_level: Optional[str] = None
    explicit_content_filter: Optional[str] = None
    roles: List[RoleModel] = Field(default_factory=list)
    categories: List[CategoryModel] = Field(default_factory=list)
    uncategorized_channels: List[ChannelModel] = Field(default_factory=list)

def validate(doc: dict) -> TemplateModel:
    try:
        return TemplateModel.model_validate(doc)
    except ValidationError as e:
        raise TemplateInvalid(str(e)) from e
