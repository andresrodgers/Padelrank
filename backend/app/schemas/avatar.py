from typing import Literal

from pydantic import BaseModel, Field


AvatarMode = Literal["preset", "upload"]


class AvatarPresetOut(BaseModel):
    key: str
    display_name: str
    image_url: str
    sort_order: int


class AvatarOut(BaseModel):
    mode: AvatarMode
    preset_key: str | None = None
    avatar_url: str | None = None
    resolved_image_url: str | None = None


class AvatarSetPresetIn(BaseModel):
    preset_key: str = Field(..., min_length=2, max_length=120)


class AvatarSetUploadIn(BaseModel):
    avatar_url: str = Field(..., min_length=12, max_length=2048)


class AvatarUploadPolicyOut(BaseModel):
    enabled: bool
    max_size_mb: int
    allowed_extensions: list[str] = Field(default_factory=list)
    allowed_hosts: list[str] = Field(default_factory=list)
    requires_signed_urls: bool = True
