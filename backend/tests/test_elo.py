from app.services.elo import compute_elo


def test_elo_is_zero_sum():
    r = compute_elo(team1_rating=1000, team2_rating=1000, winner_team_no=1, k=32, weight=1.0)
    assert r.delta_team1 == -r.delta_team2


def test_elo_underdog_wins_gets_positive_delta():
    r = compute_elo(team1_rating=900, team2_rating=1100, winner_team_no=1, k=32, weight=1.0)
    assert r.delta_team1 > 0
    assert r.delta_team2 < 0
