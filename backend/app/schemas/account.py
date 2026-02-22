from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AccountDeletionRequestIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AccountDeletionStatusOut(BaseModel):
    status: Literal["none", "scheduled", "cancelled", "executed"]
    reason: str | None = None
    requested_at: datetime | None = None
    scheduled_for: datetime | None = None
    cancelled_at: datetime | None = None
    executed_at: datetime | None = None
    grace_days: int


class AccountDeletionActionOut(BaseModel):
    ok: bool = True
    detail: str
    deletion: AccountDeletionStatusOut
