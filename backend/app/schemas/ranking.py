from pydantic import BaseModel

class RankingRow(BaseModel):
    user_id: str
    alias: str
    rating: int
    verified_matches: int
    is_provisional: bool

class RankingOut(BaseModel):
    ladder_code: str
    category_id: str
    rows: list[RankingRow]
