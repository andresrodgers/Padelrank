from dataclasses import dataclass

@dataclass
class ScoreFeatures:
    sets_played: int
    games_t1: int
    games_t2: int
    games_margin: int
    total_games: int
    tiebreak_sets: int

def extract_score_features(score_json: dict) -> ScoreFeatures:
    sets = score_json.get("sets", [])
    games_t1 = sum(int(s["t1"]) for s in sets)
    games_t2 = sum(int(s["t2"]) for s in sets)
    tiebreak_sets = sum(1 for s in sets if sorted([int(s["t1"]), int(s["t2"])]) == [6, 7])
    return ScoreFeatures(
        sets_played=len(sets),
        games_t1=games_t1,
        games_t2=games_t2,
        games_margin=abs(games_t1 - games_t2),
        total_games=games_t1 + games_t2,
        tiebreak_sets=tiebreak_sets,
    )

def clamp(lo: float, hi: float, x: float) -> float:
    return max(lo, min(hi, x))

def mov_weight_from_features(f: ScoreFeatures) -> float:
    mov_raw = 1.0 + 0.06 * min(f.games_margin, 12) - 0.08 * (f.sets_played - 2)
    return clamp(0.85, 1.25, mov_raw)
