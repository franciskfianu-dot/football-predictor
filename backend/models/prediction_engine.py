"""
Prediction engine - generates all market predictions from match features.
Uses Dixon-Coles Poisson model as the primary predictor.
"""
import numpy as np
from app.core.logging import logger
from features.dixon_coles import DixonColesModel, _score_matrix_to_markets


class PredictionEngine:
    def __init__(self, league_id: str):
        self.league_id = league_id
        self.dc_model = None

    def load_champion(self) -> bool:
        return True

    def predict(self, features: dict, odds_data: dict = None) -> dict:
        try:
            lambda_home = max(0.3, features.get("poisson_lambda_home",
                features.get("dc_home_attack", 1.4) *
                features.get("dc_away_defence", 1.0) *
                np.exp(features.get("dc_home_advantage", 0.25))
            ))
            lambda_away = max(0.3, features.get("poisson_lambda_away",
                features.get("dc_away_attack", 1.1) *
                features.get("dc_home_defence", 1.0)
            ))

            matrix = self._poisson_matrix(lambda_home, lambda_away)
            markets = _score_matrix_to_markets(matrix)
            confidence = self._confidence(lambda_home, lambda_away, features)
            ev_flags = self._compute_ev(markets, odds_data) if odds_data else []
            drivers = self._key_drivers(features)

            return {
                "confidence_band": confidence,
                "prob_home_win": markets["prob_home_win"],
                "prob_draw": markets["prob_draw"],
                "prob_away_win": markets["prob_away_win"],
                "prob_btts": markets["prob_btts"],
                "prob_over_05": markets["prob_over_05"],
                "prob_over_15": markets["prob_over_15"],
                "prob_over_25": markets["prob_over_25"],
                "prob_over_35": markets["prob_over_35"],
                "prob_over_45": markets["prob_over_45"],
                "top_scores": markets["top_scores"],
                "score_matrix": markets["score_matrix"],
                "htft": markets["htft"],
                "asian_handicap": markets["asian_handicap"],
                "winning_margin": self._margin(matrix),
                "double_chance": {
                    "1x": round(markets["prob_home_win"] + markets["prob_draw"], 4),
                    "x2": round(markets["prob_draw"] + markets["prob_away_win"], 4),
                    "12": round(markets["prob_home_win"] + markets["prob_away_win"], 4),
                },
                "draw_no_bet": {
                    "home": round(markets["prob_home_win"] / max(markets["prob_home_win"] + markets["prob_away_win"], 0.01), 4),
                    "away": round(markets["prob_away_win"] / max(markets["prob_home_win"] + markets["prob_away_win"], 0.01), 4),
                },
                "ev_flags": ev_flags,
                "shap_drivers": drivers,
                "model_name": "Dixon-Coles Poisson",
                "lambda_home": round(lambda_home, 3),
                "lambda_away": round(lambda_away, 3),
            }
        except Exception as e:
            logger.error("Prediction failed", error=str(e))
            return self._fallback(features)

    def _poisson_matrix(self, lh: float, la: float, max_g: int = 7) -> np.ndarray:
        from scipy.stats import poisson
        from features.dixon_coles import _tau
        matrix = np.zeros((max_g + 1, max_g + 1))
        for i in range(max_g + 1):
            for j in range(max_g + 1):
                tau = _tau(i, j, lh, la, -0.13)
                matrix[i][j] = max(0, tau * poisson.pmf(i, lh) * poisson.pmf(j, la))
        total = matrix.sum()
        if total > 0:
            matrix /= total
        return matrix

    def _confidence(self, lh: float, la: float, features: dict) -> str:
        h2h = features.get("h2h_matches", 0)
        data_ok = features.get("data_insufficient") is not True
        if data_ok and h2h >= 3:
            return "high"
        elif data_ok:
            return "medium"
        return "low"

    def _margin(self, matrix: np.ndarray) -> dict:
        max_g = matrix.shape[0] - 1
        margins = {}
        for margin in range(-max_g, max_g + 1):
            p = sum(
                matrix[i][i - margin]
                for i in range(max_g + 1)
                if 0 <= i - margin <= max_g
            )
            margins[str(margin)] = round(float(p), 4)
        return margins

    def _compute_ev(self, markets: dict, odds_data: dict) -> list:
        ev_flags = []
        checks = [
            ("1x2", "home", markets["prob_home_win"], odds_data.get("odds_home")),
            ("1x2", "draw", markets["prob_draw"], odds_data.get("odds_draw")),
            ("1x2", "away", markets["prob_away_win"], odds_data.get("odds_away")),
            ("over25", "over", markets["prob_over_25"], odds_data.get("odds_over_25")),
            ("btts", "yes", markets["prob_btts"], odds_data.get("odds_btts_yes")),
        ]
        for market, selection, prob, odds in checks:
            if not odds or odds <= 1.0 or not prob:
                continue
            ev = (prob * odds) - 1.0
            if ev >= 0.05:
                b = odds - 1.0
                kelly = max(0, min(((b * prob) - (1 - prob)) / b * 0.5, 0.25))
                ev_flags.append({
                    "market": market,
                    "selection": selection,
                    "model_prob": round(prob, 4),
                    "odds": round(odds, 2),
                    "ev_pct": round(ev * 100, 2),
                    "kelly_pct": round(kelly * 100, 2),
                    "bookmaker": odds_data.get("bookmaker", "market"),
                    "value_rating": "high" if ev > 0.10 else "medium",
                })
        return ev_flags

    def _key_drivers(self, features: dict) -> list:
        key_features = [
            ("elo_diff", "Elo rating difference"),
            ("home_all_avg_goals_scored_5", "Home goals scored (last 5)"),
            ("away_all_avg_goals_scored_5", "Away goals scored (last 5)"),
            ("home_all_form_points_5", "Home form points (last 5)"),
            ("away_all_form_points_5", "Away form points (last 5)"),
            ("h2h_home_win_rate", "H2H home win rate"),
            ("weather_precipitation_mm", "Rainfall (mm)"),
        ]
        drivers = []
        for key, label in key_features:
            val = features.get(key)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                drivers.append({
                    "feature": label,
                    "importance": round(abs(float(val)) / 10, 4),
                    "value": round(float(val), 3),
                })
        return drivers[:5]

    def _fallback(self, features: dict) -> dict:
        return {
            "confidence_band": "low",
            "prob_home_win": features.get("poisson_prob_home_win", 0.45),
            "prob_draw": features.get("poisson_prob_draw", 0.25),
            "prob_away_win": features.get("poisson_prob_away_win", 0.30),
            "prob_btts": 0.50,
            "prob_over_25": 0.52,
            "top_scores": [{"score": "1-1", "prob": 0.12, "home": 1, "away": 1}],
            "ev_flags": [],
            "shap_drivers": [],
            "model_name": "Fallback Poisson",
            "warning": "Insufficient data for full prediction",
        }
