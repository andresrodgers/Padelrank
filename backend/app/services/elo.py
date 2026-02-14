import math
from dataclasses import dataclass

@dataclass
class EloResult:
    delta_team1: int
    delta_team2: int
    expected_team1: float
    expected_team2: float

def expected_score(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))

def compute_elo(team1_rating: float, team2_rating: float, winner_team_no: int, k: int, weight: float = 1.0) -> EloResult:
    e1 = expected_score(team1_rating, team2_rating)
    e2 = 1.0 - e1
    s1 = 1.0 if winner_team_no == 1 else 0.0
    s2 = 1.0 - s1
    d1 = round(k * weight * (s1 - e1))
    d2 = -d1
    return EloResult(delta_team1=d1, delta_team2=d2, expected_team1=e1, expected_team2=e2)
