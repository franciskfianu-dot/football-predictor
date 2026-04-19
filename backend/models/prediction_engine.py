"""
Prediction engine.
Loads the champion model, runs all market predictions, computes SHAP values,
and runs the EV betting engine.
"""
import numpy as np
import joblib
import shap
from pathlib import Path
from typing import Optional
from features.dixon_coles import _score_matrix_to_markets
from app.core.config import settings
from app.core.logging import logger

MODEL_STORAGE = Path(settings.MODEL_STORAGE_PATH)

# Kelly criterion cap (half-Kelly)
KELLY_CAP = 0.5
# Minimum EV threshold to flag as value bet
EV_THRESHOLD = 0.05


class PredictionEngine:
    """
    Loads the champion model for a league and generates predictions
    for all markets plus betting value analysis.
    """

    def __init__(self, league_id: str):
        self.league_id = league_id
        self.model = None
        self.label_encoder = None
        self.feature_names: list[str] = []
        self._loaded = False

    def load_champion(self) -> bool:
        """Load the champion model from storage."""
        try:
            from app.db.session import SessionLocal
            from app.db.models import ModelVersion

            db = SessionLocal()
            champion = (
                db.query(ModelVersion)
                .filter(
                    ModelVersion.league_id == self.league_id,
                    ModelVersion.is_champion == True,
                )
                .order_by(ModelVersion.trained_at.desc())
                .first()
            )
            db.close()

            if champion and champion.model_path:
                data = joblib.load(champion.model_path)
                self.model = data["model"]
                self.label_encoder = data["label_encoder"]
                self.feature_names = data["feature_names"]
                self._loaded = True
                return True
            else:
                # Fallback: try loading any saved model
                return self._load_latest_from_disk()
        except Exception as e:
            logger.error("Champion model load failed", league=self.league_id, error=str(e))
            return self._load_latest_from_disk()

    def _load_latest_from_disk(self) -> bool:
        """Fallback: load the latest model file from disk."""
        pattern = f"xgboost_{self.league_id}_*.pkl"
        files = sorted(MODEL_STORAGE.glob(pattern), reverse=True)
        if files:
            data = joblib.load(files[0])
            self.model = data["model"]
            self.label_encoder = data["label_encoder"]
            self.feature_names = data["feature_names"]
            self._loaded = True
            logger.info("Loaded model from disk fallback", file=files[0].name)
            return True
        return False

    def predict(self, features: dict, odds_data: dict = None) -> dict:
        """
        Generate full prediction for a match.
        Returns all markets + EV analysis + SHAP drivers.
        """
        if not self._loaded:
            logger.warning("Model not loaded, attempting load", league=self.league_id)
            if not self.load_champion():
                return self._fallback_prediction(features)

        try:
            # Build feature vector
            X = self._features_to_vector(features)

            # Get score probability distribution
            score_probs = self._predict_score_probs(X)

            # Convert to score matrix for all markets
            matrix = self._probs_to_matrix(score_probs)
            markets = _score_matrix_to_markets(matrix)

            # Confidence band
            confidence = self._compute_confidence(score_probs)

            # SHAP feature drivers
            shap_values = self._compute_shap(X)

            # EV analysis
            ev_flags = []
            if odds_data:
                ev_flags = self._compute_ev(markets, odds_data)

            # Winning margin distribution
            margin_dist = self._winning_margin(matrix)

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
                "winning_margin": margin_dist,
                "double_chance": {
                    "1x": round(markets["prob_home_win"] + markets["prob_draw"], 4),
                    "x2": round(markets["prob_draw"] + markets["prob_away_win"], 4),
                    "12": round(markets["prob_home_win"] + markets["prob_away_win"], 4),
                },
                "draw_no_bet": {
                    "home": round(markets["prob_home_win"] / (markets["prob_home_win"] + markets["prob_away_win"] + 1e-9), 4),
                    "away": round(markets["prob_away_win"] / (markets["prob_home_win"] + markets["prob_away_win"] + 1e-9), 4),
                },
                "ev_flags": ev_flags,
                "shap_drivers": shap_values,
                "model_name": getattr(self.model, "__class__", {__name__: "unknown"}).__name__,
            }

        except Exception as e:
            logger.error("Prediction failed", league=self.league_id, error=str(e))
            return self._fallback_prediction(features)

    def _features_to_vector(self, features: dict) -> np.ndarray:
        """Convert feature dict to numpy vector aligned with training feature order."""
        vector = np.array([
            float(features.get(f, -1) or -1)
            for f in self.feature_names
        ], dtype=np.float32)
        return vector.reshape(1, -1)

    def _predict_score_probs(self, X: np.ndarray) -> np.ndarray:
        """Get score class probabilities from model."""
        return self.model.predict_proba(X)[0]

    def _probs_to_matrix(self, probs: np.ndarray) -> np.ndarray:
        """Convert flat class probabilities to 6x6 score matrix."""
        matrix = np.zeros((6, 6))
        for i, cls in enumerate(self.label_encoder.classes_):
            h, a = map(int, cls.split("_"))
            if h <= 5 and a <= 5:
                matrix[h][a] += probs[i]
        # Normalize
        total = matrix.sum()
        if total > 0:
            matrix /= total
        return matrix

    def _compute_confidence(self, probs: np.ndarray) -> str:
        """Classify confidence as high/medium/low based on score entropy."""
        top_prob = float(np.max(probs))
        entropy = float(-np.sum(probs * np.log(probs + 1e-10)))
        max_entropy = float(np.log(len(probs)))
        normalized_entropy = entropy / max_entropy if max_entropy > 0 else 1.0

        if top_prob > 0.20 and normalized_entropy < 0.85:
            return "high"
        elif top_prob > 0.12 or normalized_entropy < 0.92:
            return "medium"
        return "low"

    def _compute_shap(self, X: np.ndarray) -> list[dict]:
        """Compute top-5 SHAP feature drivers."""
        try:
            # Try tree explainer for XGBoost/LightGBM
            base_model = getattr(self.model, "estimator", self.model)
            explainer = shap.TreeExplainer(base_model)
            shap_vals = explainer.shap_values(X)

            if isinstance(shap_vals, list):
                mean_abs_shap = np.mean([np.abs(sv) for sv in shap_vals], axis=0)[0]
            else:
                mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)[0] if shap_vals.ndim == 3 else np.abs(shap_vals)[0]

            top_indices = np.argsort(mean_abs_shap)[-5:][::-1]
            return [
                {
                    "feature": self.feature_names[i],
                    "importance": round(float(mean_abs_shap[i]), 4),
                    "value": round(float(X[0][i]), 4),
                }
                for i in top_indices
                if i < len(self.feature_names)
            ]
        except Exception:
            return []

    def _compute_ev(self, markets: dict, odds_data: dict) -> list[dict]:
        """
        Compute expected value for each available market selection.
        Returns bets with EV > EV_THRESHOLD and confidence = high.
        """
        ev_flags = []
        bookmaker_odds = odds_data if isinstance(odds_data, dict) else {}

        bets_to_check = [
            ("1x2", "home", markets["prob_home_win"], bookmaker_odds.get("odds_home")),
            ("1x2", "draw", markets["prob_draw"], bookmaker_odds.get("odds_draw")),
            ("1x2", "away", markets["prob_away_win"], bookmaker_odds.get("odds_away")),
            ("btts", "yes", markets["prob_btts"], bookmaker_odds.get("odds_btts_yes")),
            ("over25", "over", markets["prob_over_25"], bookmaker_odds.get("odds_over_25")),
            ("over25", "under", 1 - markets["prob_over_25"], bookmaker_odds.get("odds_under_25")),
        ]

        for market, selection, model_prob, odds in bets_to_check:
            if odds is None or odds <= 1.0 or model_prob is None:
                continue

            ev = (model_prob * odds) - 1.0
            if ev >= EV_THRESHOLD:
                b = odds - 1.0
                q = 1 - model_prob
                kelly = ((b * model_prob) - q) / b
                kelly = max(0, min(kelly * KELLY_CAP, 0.25))  # half-Kelly, capped at 25%

                ev_flags.append({
                    "market": market,
                    "selection": selection,
                    "model_prob": round(model_prob, 4),
                    "odds": round(odds, 2),
                    "ev_pct": round(ev * 100, 2),
                    "kelly_pct": round(kelly * 100, 2),
                    "bookmaker": bookmaker_odds.get("bookmaker", "best"),
                    "value_rating": "high" if ev > 0.10 else "medium",
                })

        return ev_flags

    def _winning_margin(self, matrix: np.ndarray) -> dict:
        """Compute winning margin distribution."""
        max_g = matrix.shape[0] - 1
        margins = {}
        for margin in range(-max_g, max_g + 1):
            p = 0.0
            for i in range(max_g + 1):
                j = i - margin
                if 0 <= j <= max_g:
                    p += matrix[i][j]
            margins[str(margin)] = round(p, 4)
        return margins

    def _fallback_prediction(self, features: dict) -> dict:
        """Return a minimal prediction when model is unavailable."""
        lambda_h = features.get("poisson_lambda_home", 1.4)
        lambda_a = features.get("poisson_lambda_away", 1.1)

        from features.dixon_coles import DixonColesModel
        dc = DixonColesModel()
        matrix = dc.predict_score_probabilities.__func__(dc, None, None)

        return {
            "confidence_band": "low",
            "prob_home_win": features.get("poisson_prob_home_win", 0.45),
            "prob_draw": features.get("poisson_prob_draw", 0.25),
            "prob_away_win": features.get("poisson_prob_away_win", 0.30),
            "prob_btts": features.get("poisson_prob_btts", 0.50),
            "prob_over_25": features.get("poisson_prob_over25", 0.52),
            "top_scores": [{"score": "1-1", "prob": 0.12}, {"score": "1-0", "prob": 0.11}],
            "ev_flags": [],
            "shap_drivers": [],
            "model_name": "fallback_poisson",
            "warning": "Model unavailable — using Poisson fallback",
        }
