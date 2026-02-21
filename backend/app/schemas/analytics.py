from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsStateOut(BaseModel):
    user_id: str
    ladder_code: str
    total_verified_matches: int
    wins: int
    losses: int
    win_rate: float
    current_streak_type: str | None = None
    current_streak_len: int
    best_win_streak: int
    best_loss_streak: int
    recent_form: list[str] = Field(default_factory=list)
    recent_10_matches: int
    recent_10_wins: int
    recent_10_win_rate: float
    current_rating: int | None = None
    peak_rating: int | None = None
    last_match_at: datetime | None = None
    updated_at: datetime


class AnalyticsPublicOut(BaseModel):
    user_id: str
    ladder_code: str
    total_verified_matches: int
    wins: int
    losses: int
    win_rate: float
    current_streak_type: str | None = None
    current_streak_len: int
    best_win_streak: int
    recent_10_matches: int
    recent_10_wins: int
    recent_10_win_rate: float
    current_rating: int | None = None
    last_match_at: datetime | None = None
