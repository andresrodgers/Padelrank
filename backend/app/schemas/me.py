from pydantic import BaseModel
from typing import List, Optional

class ProfileOut(BaseModel):
    alias: str
    gender: str
    is_public: bool

class MeOut(BaseModel):
    id: str
    phone_e164: str
    status: str
    profile: ProfileOut | None

class ProfileUpdateIn(BaseModel):
    alias: str | None = None
    gender: str | None = None
    is_public: bool | None = None
    primary_category_code: str | None = None

class LadderStateOut(BaseModel):
    ladder_code: str
    category_id: str
    category_code: str
    category_name: str
    rating: int
    verified_matches: int
    is_provisional: bool
    trust_score: int

class PlayEligibilityOut(BaseModel):
    can_play: bool
    can_create_match: bool
    can_be_invited: bool
    missing: List[str]
    message: Optional[str] = None
