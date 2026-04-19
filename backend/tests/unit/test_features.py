"""Unit tests for feature engineering."""
import pytest
import pandas as pd
import numpy as np
from features.engineer import FeatureEngineer


@pytest.fixture
def sample_matches():
    """30 matches of fake history."""
    rows = []
    import uuid
    teams = ["team_a", "team_b", "team_c", "team_d"]
    from itertools import combinations
    pairs = list(combinations(teams, 2))
    for i in range(30):
        h, a = pairs[i % len(pairs)]
        rows.append({
            "id": str(uuid.uuid4()),
            "match_date": f"2023-{(i//30)+8:02d}-{(i%28)+1:02d}",
            "home_team_id": h,
            "away_team_id": a,
            "league_id": "test_league",
            "home_goals": np.random.randint(0, 4),
            "away_goals": np.random.randint(0, 3),
            "home_xg": round(np.random.uniform(0.5, 2.5), 2),
            "away_xg": round(np.random.uniform(0.3, 2.0), 2),
            "home_possession": round(np.random.uniform(40, 65), 1),
            "away_possession": None,
            "home_shots_on_target": np.random.randint(2, 8),
            "away_shots_on_target": np.random.randint(1, 6),
            "home_goals_ht": np.random.randint(0, 2),
            "away_goals_ht": np.random.randint(0, 2),
        })
    return pd.DataFrame(rows)


def test_feature_engineer_returns_dict(sample_matches):
    eng = FeatureEngineer()
    hist = sample_matches.iloc[:20]
    features = eng.build_features_for_match(
        match_date="2023-12-01",
        home_team_id="team_a",
        away_team_id="team_b",
        league_id="test_league",
        match_history_df=hist,
    )
    assert isinstance(features, dict)
    assert len(features) > 10


def test_elo_ratings_positive(sample_matches):
    eng = FeatureEngineer()
    h_elo, a_elo = eng._get_elo_ratings(sample_matches, "team_a", "team_b")
    assert h_elo > 0
    assert a_elo > 0


def test_h2h_features_no_history():
    eng = FeatureEngineer()
    empty = pd.DataFrame(columns=["home_team_id", "away_team_id", "home_goals", "away_goals", "match_date"])
    result = eng._get_h2h_features(empty, "team_x", "team_y")
    assert "h2h_home_win_rate" in result
    assert result["h2h_matches"] == 0


def test_poisson_meta_features_sum_to_one():
    eng = FeatureEngineer()
    fake_features = {
        "dc_home_attack": 1.4,
        "dc_away_defence": 1.0,
        "dc_away_attack": 1.1,
        "dc_home_defence": 1.0,
        "dc_home_advantage": 0.25,
    }
    result = eng._poisson_meta_features(fake_features)
    total = result["poisson_prob_home_win"] + result["poisson_prob_draw"] + result["poisson_prob_away_win"]
    assert abs(total - 1.0) < 0.05  # Allow for capping at 5-5
