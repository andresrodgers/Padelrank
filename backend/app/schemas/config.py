from pydantic import BaseModel

class ClubOut(BaseModel):
    id: str
    name: str
    city: str
    is_active: bool

class LadderOut(BaseModel):
    code: str
    name: str
    is_active: bool

class CategoryOut(BaseModel):
    id: str
    ladder_code: str
    code: str
    name: str
    sort_order: int
