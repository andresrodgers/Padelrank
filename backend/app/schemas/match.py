from datetime import datetime
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class ParticipantIn(BaseModel):
    user_id: str
    team_no: int = Field(..., ge=1, le=2)


class MatchScoreIn(BaseModel):
    score_json: Dict[str, Any]
    winner_team_no: Optional[int] = Field(None, ge=1, le=2)

    @field_validator("score_json")
    @classmethod
    def validate_score_json(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(v, dict):
            raise ValueError("score_json debe ser un objeto")

        sets = v.get("sets", [])
        if not (2 <= len(sets) <= 3):
            raise ValueError("score_json.sets debe tener 2 o 3 sets")

        t1_wins = 0
        t2_wins = 0
        for s in sets:
            if not isinstance(s, dict):
                raise ValueError("cada set debe ser un objeto")
            t1 = s.get("t1")
            t2 = s.get("t2")
            if not (isinstance(t1, int) and isinstance(t2, int)):
                raise ValueError("los puntajes de cada set deben ser enteros")
            if not (0 <= t1 <= 7 and 0 <= t2 <= 7):
                raise ValueError("los puntajes de cada set deben estar entre 0 y 7")
            if t1 == t2:
                raise ValueError("un set no puede terminar empatado")

            mx = max(t1, t2)
            mn = min(t1, t2)
            if mx not in (6, 7):
                raise ValueError("un set debe terminar en 6 o 7")
            if mx == 6 and mn > 4:
                raise ValueError("6-x debe ser 6-0..6-4")
            if mx == 7 and mn not in (5, 6):
                raise ValueError("7-x debe ser 7-5 o 7-6")

            if t1 > t2:
                t1_wins += 1
            else:
                t2_wins += 1

        if len(sets) == 2:
            if t1_wins == 1 and t2_wins == 1:
                raise ValueError("si hay 2 sets, el ganador debe ganar 2-0 (no 1-1)")
        else:
            if (t1_wins, t2_wins) not in ((2, 1), (1, 2)):
                raise ValueError("si hay 3 sets, debe terminar 2-1")
            first2 = sets[:2]
            a = sum(1 for s in first2 if s["t1"] > s["t2"])
            b = 2 - a
            if not (a == 1 and b == 1):
                raise ValueError("el tercer set solo se permite si los dos primeros quedan 1-1")

        return v

    def derived_winner(self) -> int:
        sets = self.score_json["sets"]
        t1_sets = sum(1 for s in sets if s["t1"] > s["t2"])
        t2_sets = len(sets) - t1_sets
        return 1 if t1_sets > t2_sets else 2


class MatchCreateIn(BaseModel):
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
    my_confirmation_status: str


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
