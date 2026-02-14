from pydantic import BaseModel

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

    # Categoría predefinida seleccionada en onboarding:
    # M -> HM: 1ra..7ma
    # F -> WM: A..D
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
