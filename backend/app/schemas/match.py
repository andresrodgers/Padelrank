from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any
from typing import Literal, Optional, Dict, Any

class ParticipantIn(BaseModel):
    user_id: str
    team_no: int = Field(..., ge=1, le=2)

class MatchScoreIn(BaseModel):
    score_json: Dict[str, Any]
    winner_team_no: Optional[int] = Field(None, ge=1, le=2)

    @field_validator("score_json")
    @classmethod
    def validate_score_json(cls, v):
        if not isinstance(v, dict):
            raise ValueError("score_json must be an object")
        sets = v.get("sets", [])
        if not (2 <= len(sets) <= 3):
            raise ValueError("score_json.sets must have 2 or 3 sets")

        t1_wins = 0
        t2_wins = 0

        for s in sets:
            if not isinstance(s, dict):
                raise ValueError("each set must be an object")
            t1 = s.get("t1")
            t2 = s.get("t2")
            if not (isinstance(t1, int) and isinstance(t2, int)):
                raise ValueError("set scores must be ints")
            if not (0 <= t1 <= 7 and 0 <= t2 <= 7):
                raise ValueError("set scores must be between 0 and 7")
            if t1 == t2:
                raise ValueError("set cannot be tied")

            mx = max(t1, t2)
            mn = min(t1, t2)
            if mx not in (6, 7):
                raise ValueError("set must end at 6 or 7")
            if mx == 6 and mn > 4:
                raise ValueError("6-x must be 6-0..6-4")
            if mx == 7 and mn not in (5, 6):
                raise ValueError("7-x must be 7-5 or 7-6")

            if t1 > t2:
                t1_wins += 1
            else:
                t2_wins += 1

        # coherencia best-of-3
        if len(sets) == 2:
            if t1_wins == 1 and t2_wins == 1:
                raise ValueError("if 2 sets, winner must win 2-0 (no 1-1)")
        else:  # 3 sets
            if not ((t1_wins, t2_wins) in [(2, 1), (1, 2)]):
                raise ValueError("if 3 sets, must end 2-1")
            first2 = sets[:2]
            a = sum(1 for s in first2 if s["t1"] > s["t2"])
            b = 2 - a
            if not (a == 1 and b == 1):
                raise ValueError("third set only allowed when first two sets are split 1-1")

        return v

    def derived_winner(self) -> int:
        sets = self.score_json["sets"]
        t1_sets = sum(1 for s in sets if s["t1"] > s["t2"])
        t2_sets = len(sets) - t1_sets
        return 1 if t1_sets > t2_sets else 2

@field_validator("score_json")
@classmethod
def validate_score_json(cls, v):
    if not isinstance(v, dict):
        raise ValueError("score_json must be an object")
    sets = v.get("sets", [])
    if not (2 <= len(sets) <= 3):
        raise ValueError("score_json.sets must have 2 or 3 sets")

    t1_wins = 0
    t2_wins = 0

    for s in sets:
        if not isinstance(s, dict):
            raise ValueError("each set must be an object")
        t1 = s.get("t1")
        t2 = s.get("t2")
        if not (isinstance(t1, int) and isinstance(t2, int)):
            raise ValueError("set scores must be ints")
        if not (0 <= t1 <= 7 and 0 <= t2 <= 7):
            raise ValueError("set scores must be between 0 and 7")
        if t1 == t2:
            raise ValueError("set cannot be tied")

        mx = max(t1, t2)
        mn = min(t1, t2)
        if mx not in (6, 7):
            raise ValueError("set must end at 6 or 7")
        if mx == 6 and mn > 4:
            raise ValueError("6-x must be 6-0..6-4")
        if mx == 7 and mn not in (5, 6):
            raise ValueError("7-x must be 7-5 or 7-6")

        if t1 > t2:
            t1_wins += 1
        else:
            t2_wins += 1

    # coherencia best-of-3
    if len(sets) == 2:
        if t1_wins == 1 and t2_wins == 1:
            raise ValueError("if 2 sets, winner must win 2-0 (no 1-1)")
    else:  # 3 sets
        # debe ser 2-1
        if not ((t1_wins, t2_wins) in [(2, 1), (1, 2)]):
            raise ValueError("if 3 sets, must end 2-1")
        # y el 3er set solo existe si iban 1-1 en los dos primeros
        first2 = sets[:2]
        a = sum(1 for s in first2 if s["t1"] > s["t2"])
        b = 2 - a
        if not (a == 1 and b == 1):
            raise ValueError("third set only allowed when first two sets are split 1-1")

    return v


    def derived_winner(self) -> int:
        sets = self.score_json["sets"]
        t1_sets = sum(1 for s in sets if s["t1"] > s["t2"])
        t2_sets = len(sets) - t1_sets
        return 1 if t1_sets > t2_sets else 2

class MatchCreateIn(BaseModel):
    # ladder_code y category_id los calcula el backend
    club_id: str | None = None
    played_at: datetime
    participants: list[ParticipantIn] = Field(..., min_length=4, max_length=4)
    score: MatchScoreIn

class MatchOut(BaseModel):
    id: str
    ladder_code: str
    category_id: str
    club_id: str | None
    played_at: datetime
    created_by: str
    status: str
    confirmation_deadline: datetime
    confirmed_count: int
    has_dispute: bool

class ConfirmIn(BaseModel):
    status: Literal["confirmed"]
    note: Optional[str] = None
    source: Optional[str] = None

    score_json: Optional[Dict[str, Any]] = None
    
class ConfirmOut(BaseModel):
    ok: bool = True
    confirmed_count: int = 0
    teams_confirmed: int = 0
    
class MyMatchRowOut(BaseModel):
    id: str
    ladder_code: str
    category_code: str
    club_id: str | None
    club_name: str | None
    played_at: datetime
    status: str
    confirmation_deadline: datetime
    confirmed_count: int
    has_dispute: bool
    my_team_no: int
    my_confirmation_status: str  # pending|confirmed|disputed

class MyMatchesOut(BaseModel):
    rows: list[MyMatchRowOut]
    limit: int
    offset: int
    next_offset: int | None

class MatchParticipantOut(BaseModel):
    user_id: str
    alias: str
    team_no: int = Field(..., ge=1, le=2)

class MatchScoreOut(BaseModel):
    score_json: dict
    winner_team_no: int

class MatchConfirmationRowOut(BaseModel):
    user_id: str
    alias: str
    team_no: int
    status: str
    decided_at: datetime | None

class MatchConfirmationsOut(BaseModel):
    match_id: str
    status: str
    confirmation_deadline: datetime
    confirmed_count: int
    has_dispute: bool
    rows: list[MatchConfirmationRowOut]

class MatchDetailOut(BaseModel):
    id: str
    ladder_code: str
    category_id: str
    category_code: str
    club_id: str | None
    club_name: str | None
    played_at: datetime
    created_by: str
    status: str
    confirmation_deadline: datetime
    confirmed_count: int
    has_dispute: bool
    participants: list[MatchParticipantOut]
    score: MatchScoreOut
