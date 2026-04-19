"""Unit tests for Dixon-Coles model."""
import pytest
import pandas as pd
import numpy as np
from features.dixon_coles import DixonColesModel, _score_matrix_to_markets, _tau


def test_tau_low_score_correction():
    # 0-0 should get rho correction
    tau_00 = _tau(0, 0, 1.5, 1.2, -0.13)
    tau_11 = _tau(1, 1, 1.5, 1.2, -0.13)
    tau_22 = _tau(2, 2, 1.5, 1.2, -0.13)
    assert tau_00 != 1.0
    assert tau_11 != 1.0
    assert tau_22 == 1.0  # Only 0-0, 0-1, 1-0, 1-1 adjusted


def test_score_matrix_probabilities_sum():
    """Score matrix probabilities should sum to ~1."""
    dc = DixonColesModel()
    matrix = dc.predict_score_probabilities.__func__(dc, None, None)
    assert abs(matrix.sum() - 1.0) < 0.01


def test_markets_from_matrix():
    """All market probabilities should be between 0 and 1."""
    matrix = np.zeros((6, 6))
    # Simple 1-0 dominant scenario
    matrix[1][0] = 0.15
    matrix[0][0] = 0.10
    matrix[1][1] = 0.12
    matrix[2][1] = 0.08
    # Fill rest
    remaining = 1.0 - matrix.sum()
    matrix[0][1] = remaining
    
    markets = _score_matrix_to_markets(matrix)
    assert 0 <= markets["prob_home_win"] <= 1
    assert 0 <= markets["prob_draw"] <= 1
    assert 0 <= markets["prob_away_win"] <= 1
    total = markets["prob_home_win"] + markets["prob_draw"] + markets["prob_away_win"]
    assert abs(total - 1.0) < 0.02


@pytest.fixture
def small_match_df():
    import uuid
    rows = []
    for i in range(60):
        rows.append({
            "home_team_id": "team_a" if i % 2 == 0 else "team_b",
            "away_team_id": "team_b" if i % 2 == 0 else "team_a",
            "home_goals": np.random.randint(0, 4),
            "away_goals": np.random.randint(0, 3),
            "match_date": f"2022-{(i//28)+9:02d}-{(i%28)+1:02d}",
        })
    return pd.DataFrame(rows)


def test_dixon_coles_fit(small_match_df):
    dc = DixonColesModel()
    params = dc.fit(small_match_df, "test")
    assert dc.is_fitted
    assert "team_a" in params
    assert "home_advantage" in params
    assert params["team_a"]["attack"] > 0
    assert params["team_a"]["defence"] > 0
