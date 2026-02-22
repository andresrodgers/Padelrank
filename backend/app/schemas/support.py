from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


SupportCategory = Literal["general", "billing", "premium", "bug", "abuse"]
SupportStatus = Literal["open", "in_progress", "closed", "spam"]


class SupportContactOut(BaseModel):
    to_email: str
    subject_template: str
    body_template: str
    mailto_url: str


class SupportTicketCreateIn(BaseModel):
    category: SupportCategory = "general"
    subject: str = Field(..., min_length=5, max_length=160)
    message: str = Field(..., min_length=10, max_length=5000)


class SupportTicketOut(BaseModel):
    id: str
    category: SupportCategory
    subject: str
    message: str
    status: SupportStatus
    created_at: datetime
    updated_at: datetime


class SupportTicketListOut(BaseModel):
    rows: list[SupportTicketOut] = Field(default_factory=list)
    limit: int
    offset: int
    next_offset: int | None = None
