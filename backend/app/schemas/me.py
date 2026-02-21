from datetime import date
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, model_validator

class ProfileOut(BaseModel):
    alias: str
    gender: str
    is_public: bool
    country: str
    city: str | None = None
    handedness: str
    preferred_side: str
    birthdate: date | None = None
    first_name: str | None = None
    last_name: str | None = None

class MeOut(BaseModel):
    id: str
    phone_e164: str | None
    email: str | None
    status: str
    profile: ProfileOut | None

class ProfileUpdateIn(BaseModel):
    alias: str | None = None
    gender: str | None = None
    is_public: bool | None = None
    primary_category_code: str | None = None
    country: str | None = None
    city: str | None = None
    handedness: Literal["R", "L", "U"] | None = None
    preferred_side: Literal["drive", "reves", "both", "U"] | None = None
    birthdate: date | None = None
    first_name: str | None = None
    last_name: str | None = None

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


def _looks_like_email(value: str) -> bool:
    v = value.strip()
    return "@" in v and "." in v.split("@")[-1]


class ContactChangeRequestIn(BaseModel):
    phone_e164: str | None = None
    country_code: str | None = None
    phone_number: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def validate_contact_input(self):
        has_email = bool(self.email)
        has_e164 = bool(self.phone_e164)
        has_split = bool(self.country_code) and bool(self.phone_number)
        has_phone = has_e164 or has_split
        if has_email and has_phone:
            raise ValueError("Provee email o telefono, pero no ambos")
        if not has_email and not has_phone:
            raise ValueError("Debes proveer email o telefono")
        if has_email and not _looks_like_email(self.email or ""):
            raise ValueError("Email invalido")
        return self


class ContactChangeRequestOut(BaseModel):
    ok: bool = True
    contact_kind: Literal["phone", "email"]
    dev_code: str | None = None


class ContactChangeConfirmIn(BaseModel):
    contact_kind: Literal["phone", "email"]
    code: str = Field(..., min_length=6, max_length=6)


class ContactChangeConfirmOut(BaseModel):
    ok: bool = True
    contact_kind: Literal["phone", "email"]
    phone_e164: str | None
    email: str | None
