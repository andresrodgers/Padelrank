from datetime import datetime
from pydantic import BaseModel, Field, field_validator
from typing import Any
from typing import Literal, Optional, Dict, Any

class ParticipantIn(BaseModel):
    user_id: str
    team_no: int = Field(..., ge=1, le=2)

class MatchScoreIn(BaseModel):
    score_json: dict
    winner_team_no: int | None = Field(None, ge=1, le=2)

    @field_validator("score_json")
    @classmethod
    def validate_score_json(cls, v: dict) -> dict:
        if not isinstance(v, dict) or "sets" not in v:
            raise ValueError("score_json must contain 'sets'")

        sets = v.get("sets")
        if not isinstance(sets, list) or len(sets) not in (2, 3):
            raise ValueError("Match must have 2 or 3 sets")

        def valid_set(a: int, b: int) -> bool:
            # basic bounds
            if not (0 <= a <= 7 and 0 <= b <= 7):
                return False
            if a == b:
                return False

            hi = max(a, b)
            lo = min(a, b)

            # Allowed set endings in padel
            # 6-x where x <= 4
            if hi == 6 and lo <= 4:
                return True
            # 7-5
            if hi == 7 and lo == 5:
                return True
            # 7-6 (tiebreak)
            if hi == 7 and lo == 6:
                return True

            return False

        t1_sets = 0
        t2_sets = 0

        for i, s in enumerate(sets, start=1):
            if not isinstance(s, dict) or "t1" not in s or "t2" not in s:
                raise ValueError(f"Set {i} must be an object with t1 and t2")

            t1 = s["t1"]
            t2 = s["t2"]
            if not (isinstance(t1, int) and isinstance(t2, int)):
                raise ValueError(f"Set {i} values must be integers")

            if not valid_set(t1, t2):
                raise ValueError(f"Invalid set score at set {i}: {t1}-{t2}")

            if t1 > t2:
                t1_sets += 1
            else:
                t2_sets += 1

        # Must be best-of-3: winner has exactly 2 sets
        if not ((t1_sets == 2 and t2_sets in (0, 1)) or (t2_sets == 2 and t1_sets in (0, 1))):
            raise ValueError("Match must end when one team wins 2 sets (best of 3)")

        # If 3 sets, first two must be split 1-1
        if len(sets) == 3:
            first_two = sets[:2]
            ft1 = sum(1 for s in first_two if s["t1"] > s["t2"])
            ft2 = 2 - ft1
            if not (ft1 == 1 and ft2 == 1):
                raise ValueError("If there are 3 sets, the first two sets must be split 1-1")

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

    # Si viene, significa "proponer corrección" (o confirmar ese score)
    score_json: Optional[Dict[str, Any]] = None
    
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
