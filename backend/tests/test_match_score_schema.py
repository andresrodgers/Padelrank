import pytest
from pydantic import ValidationError

from app.schemas.match import MatchScoreIn


def test_valid_two_set_score():
    score = MatchScoreIn(score_json={"sets": [{"t1": 6, "t2": 4}, {"t1": 7, "t2": 5}]})
    assert score.derived_winner() == 1


def test_invalid_two_set_split_raises():
    with pytest.raises(ValidationError):
        MatchScoreIn(score_json={"sets": [{"t1": 6, "t2": 4}, {"t1": 4, "t2": 6}]})


def test_valid_three_set_split():
    score = MatchScoreIn(score_json={"sets": [{"t1": 6, "t2": 4}, {"t1": 4, "t2": 6}, {"t1": 6, "t2": 3}]})
    assert score.derived_winner() == 1
