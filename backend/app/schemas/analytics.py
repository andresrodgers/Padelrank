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
    rolling_5_win_rate: float
    rolling_20_win_rate: float
    rolling_50_win_rate: float
    matches_7d: int
    matches_30d: int
    matches_90d: int
    close_matches: int
    close_match_rate: float
    vs_stronger_matches: int
    vs_stronger_wins: int
    vs_stronger_win_rate: float
    vs_similar_matches: int
    vs_similar_wins: int
    vs_similar_win_rate: float
    vs_weaker_matches: int
    vs_weaker_wins: int
    vs_weaker_win_rate: float
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
    rolling_5_win_rate: float
    rolling_20_win_rate: float
    rolling_50_win_rate: float
    matches_7d: int
    matches_30d: int
    matches_90d: int
    close_matches: int
    close_match_rate: float
    vs_stronger_matches: int
    vs_stronger_wins: int
    vs_stronger_win_rate: float
    vs_similar_matches: int
    vs_similar_wins: int
    vs_similar_win_rate: float
    vs_weaker_matches: int
    vs_weaker_wins: int
    vs_weaker_win_rate: float
    current_rating: int | None = None
    last_match_at: datetime | None = None


class RatingTrendPointOut(BaseModel):
    at: datetime
    rating: int | None = None
    match_id: str | None = None


class RollingWinRatePointOut(BaseModel):
    at: datetime
    rolling_10_win_rate: float | None = None
    rolling_20_win_rate: float | None = None
    rolling_50_win_rate: float | None = None


class VolumePointOut(BaseModel):
    at: datetime
    matches: int


class StreakPointOut(BaseModel):
    at: datetime
    match_id: str
    streak_type: str
    streak_len: int


class PartnerStatOut(BaseModel):
    partner_user_id: str
    partner_alias: str | None = None
    matches: int
    wins: int
    losses: int
    win_rate: float
    last_played_at: datetime | None = None


class RivalStatOut(BaseModel):
    rival_user_id: str
    rival_alias: str | None = None
    matches: int
    wins: int
    losses: int
    win_rate: float
    last_played_at: datetime | None = None


class AnalyticsDashboardOut(BaseModel):
    state: AnalyticsStateOut
    rating_trend: list[RatingTrendPointOut] = Field(default_factory=list)
    rolling_win_rate_trend: list[RollingWinRatePointOut] = Field(default_factory=list)
    volume_weekly: list[VolumePointOut] = Field(default_factory=list)
    volume_monthly: list[VolumePointOut] = Field(default_factory=list)
    streak_timeline: list[StreakPointOut] = Field(default_factory=list)
    top_partners: list[PartnerStatOut] = Field(default_factory=list)
    top_rivals: list[RivalStatOut] = Field(default_factory=list)


class AnalyticsPublicDashboardOut(BaseModel):
    state: AnalyticsPublicOut
    rating_trend: list[RatingTrendPointOut] = Field(default_factory=list)
    rolling_win_rate_trend: list[RollingWinRatePointOut] = Field(default_factory=list)
    volume_weekly: list[VolumePointOut] = Field(default_factory=list)
    volume_monthly: list[VolumePointOut] = Field(default_factory=list)
    streak_timeline: list[StreakPointOut] = Field(default_factory=list)
    top_partners: list[PartnerStatOut] = Field(default_factory=list)
    top_rivals: list[RivalStatOut] = Field(default_factory=list)
