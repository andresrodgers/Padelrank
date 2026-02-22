from datetime import datetime
from pydantic import BaseModel, Field


class HistoryTimelineItemOut(BaseModel):
    match_id: str
    ladder_code: str
    category_id: str
    category_code: str
    club_id: str | None
    club_name: str | None
    club_city: str | None
    played_at: datetime
    created_at: datetime
    confirmation_deadline: datetime
    status: str
    status_reason: str
    visibility_reason: str
    ranking_impact: bool
    ranking_impact_reason: str
    confirmed_count: int
    has_dispute: bool
    focus_team_no: int
    rival_aliases: list[str] = Field(default_factory=list)
    winner_team_no: int | None = None
    did_focus_user_win: bool | None = None
    created_by: str
    created_by_alias: str | None = None


class HistoryTimelineOut(BaseModel):
    target_user_id: str
    rows: list[HistoryTimelineItemOut]
    limit: int
    offset: int
    next_offset: int | None
    next_cursor: str | None = None


class HistoryParticipantOut(BaseModel):
    user_id: str
    alias: str
    gender: str | None = None
    team_no: int
    confirmation_status: str
    decided_at: datetime | None


class HistoryScoreOut(BaseModel):
    score_json: dict | None = None
    winner_team_no: int | None = None


class HistoryMatchDetailOut(BaseModel):
    focus_user_id: str
    event: HistoryTimelineItemOut
    participants: list[HistoryParticipantOut]
    teammate_aliases: list[str] = Field(default_factory=list)
    rival_aliases: list[str] = Field(default_factory=list)
    score: HistoryScoreOut | None = None
