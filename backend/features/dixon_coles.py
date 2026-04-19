"""
Dixon-Coles (1997) bivariate Poisson model for football score prediction.
Implements attack/defence parameter estimation with low-score correction (rho).
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.stats import poisson
from typing import Optional
from app.core.logging import logger


def _tau(home_goals: int, away_goals: int, lambda_h: float, lambda_a: float, rho: float) -> float:
    """Dixon-Coles low-score correction factor."""
    if home_goals == 0 and away_goals == 0:
        return 1 - lambda_h * lambda_a * rho
    elif home_goals == 0 and away_goals == 1:
        return 1 + lambda_h * rho
    elif home_goals == 1 and away_goals == 0:
        return 1 + lambda_a * rho
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0


def _dc_log_likelihood(params: np.ndarray, matches: pd.DataFrame, teams: list[str]) -> float:
    """Negative log-likelihood for Dixon-Coles model."""
    n_teams = len(teams)
    team_idx = {t: i for i, t in enumerate(teams)}

    # Unpack params: [attack * n, defence * n, home_adv, rho]
    attack = np.exp(params[:n_teams])
    defence = np.exp(params[n_teams:2*n_teams])
    home_adv = np.exp(params[2*n_teams])
    rho = params[2*n_teams + 1]

    log_lik = 0.0
    for _, row in matches.iterrows():
        hi = team_idx.get(row["home_team_id"])
        ai = team_idx.get(row["away_team_id"])
        if hi is None or ai is None:
            continue

        hg = int(row.get("home_goals", 0) or 0)
        ag = int(row.get("away_goals", 0) or 0)

        lambda_h = attack[hi] * defence[ai] * home_adv
        lambda_a = attack[ai] * defence[hi]

        tau = _tau(hg, ag, lambda_h, lambda_a, rho)
        if tau <= 0:
            return 1e10

        log_lik += (
            np.log(tau)
            + poisson.logpmf(hg, lambda_h)
            + poisson.logpmf(ag, lambda_a)
        )

    return -log_lik


class DixonColesModel:
    """
    Fits Dixon-Coles attack/defence parameters per team.
    Used as:
    1. A baseline prediction model (score probabilities)
    2. A source of features for the ML models
    """

    def __init__(self):
        self.params: dict = {}
        self.teams: list[str] = []
        self.is_fitted: bool = False

    def fit(self, matches: pd.DataFrame, league_id: str) -> dict:
        """Fit the model on historical match data."""
        # Only use completed matches
        completed = matches[
            matches["home_goals"].notna() & matches["away_goals"].notna()
        ].copy()

        if len(completed) < 50:
            logger.warning("Insufficient data for Dixon-Coles", n=len(completed))
            return {}

        self.teams = sorted(list(set(
            completed["home_team_id"].tolist() + completed["away_team_id"].tolist()
        )))
        n = len(self.teams)

        if n < 2:
            return {}

        # Initial params: log(1) = 0 for all attack/defence, log(1.35)≈0.3 for home adv
        x0 = np.zeros(2 * n + 2)
        x0[2 * n] = np.log(1.35)  # home advantage
        x0[2 * n + 1] = -0.13    # rho

        # Bounds: rho in [-0.99, 0.99]
        bounds = (
            [(None, None)] * (2 * n + 1) +
            [(-0.99, 0.99)]
        )

        try:
            result = minimize(
                _dc_log_likelihood,
                x0,
                args=(completed, self.teams),
                method="L-BFGS-B",
                bounds=bounds,
                options={"maxiter": 200, "ftol": 1e-8},
            )

            params_opt = result.x
            team_idx = {t: i for i, t in enumerate(self.teams)}

            self.params = {
                t: {
                    "attack": float(np.exp(params_opt[team_idx[t]])),
                    "defence": float(np.exp(params_opt[n + team_idx[t]])),
                }
                for t in self.teams
            }
            self.params["home_advantage"] = float(np.exp(params_opt[2 * n]))
            self.params["rho"] = float(params_opt[2 * n + 1])
            self.is_fitted = True

            logger.info("Dixon-Coles fitted", n_teams=n, neg_ll=round(result.fun, 2))
            return self.params

        except Exception as e:
            logger.error("Dixon-Coles fit failed", error=str(e))
            return {}

    def predict_score_probabilities(
        self,
        home_team_id: str,
        away_team_id: str,
        max_goals: int = 8,
    ) -> np.ndarray:
        """
        Returns a (max_goals+1) x (max_goals+1) matrix of score probabilities.
        Row = home goals, column = away goals.
        """
        if not self.is_fitted:
            return np.ones((max_goals + 1, max_goals + 1)) / ((max_goals + 1) ** 2)

        home_params = self.params.get(home_team_id, {"attack": 1.0, "defence": 1.0})
        away_params = self.params.get(away_team_id, {"attack": 1.0, "defence": 1.0})

        lambda_h = home_params["attack"] * away_params["defence"] * self.params.get("home_advantage", 1.35)
        lambda_a = away_params["attack"] * home_params["defence"]
        rho = self.params.get("rho", -0.13)

        matrix = np.zeros((max_goals + 1, max_goals + 1))
        for i in range(max_goals + 1):
            for j in range(max_goals + 1):
                tau = _tau(i, j, lambda_h, lambda_a, rho)
                matrix[i][j] = max(0, tau * poisson.pmf(i, lambda_h) * poisson.pmf(j, lambda_a))

        # Normalise
        total = matrix.sum()
        if total > 0:
            matrix /= total

        return matrix

    def predict_all_markets(
        self, home_team_id: str, away_team_id: str
    ) -> dict:
        """Compute all market probabilities from the score matrix."""
        matrix = self.predict_score_probabilities(home_team_id, away_team_id)
        return _score_matrix_to_markets(matrix)


def _score_matrix_to_markets(matrix: np.ndarray) -> dict:
    """Convert a score probability matrix to all betting markets."""
    max_g = matrix.shape[0] - 1

    prob_home_win = float(np.sum(np.tril(matrix, -1)))
    prob_draw = float(np.trace(matrix))
    prob_away_win = float(np.sum(np.triu(matrix, 1)))

    # Over/under
    total_goals_prob = {}
    for total in range(2 * max_g + 1):
        p = 0.0
        for i in range(min(total + 1, max_g + 1)):
            j = total - i
            if 0 <= j <= max_g:
                p += matrix[i][j]
        total_goals_prob[total] = p

    def over(threshold):
        return sum(p for t, p in total_goals_prob.items() if t > threshold)

    # BTTS
    prob_btts = float(sum(
        matrix[i][j]
        for i in range(1, max_g + 1)
        for j in range(1, max_g + 1)
    ))

    # Top 10 most likely correct scores
    scores = []
    for i in range(max_g + 1):
        for j in range(max_g + 1):
            scores.append({"score": f"{i}-{j}", "home": i, "away": j, "prob": float(matrix[i][j])})
    scores.sort(key=lambda x: x["prob"], reverse=True)

    # HT/FT: approximate using split Poisson (lambda * 0.5 per half)
    # Simplified: use same matrix but scale lambdas
    htft = _compute_htft(matrix)

    # Asian handicap
    asian_handicap = _compute_asian_handicap(matrix)

    return {
        "prob_home_win": round(prob_home_win, 4),
        "prob_draw": round(prob_draw, 4),
        "prob_away_win": round(prob_away_win, 4),
        "prob_btts": round(prob_btts, 4),
        "prob_over_05": round(over(0.5), 4),
        "prob_over_15": round(over(1.5), 4),
        "prob_over_25": round(over(2.5), 4),
        "prob_over_35": round(over(3.5), 4),
        "prob_over_45": round(over(4.5), 4),
        "top_scores": scores[:10],
        "score_matrix": matrix.tolist(),
        "htft": htft,
        "asian_handicap": asian_handicap,
    }


def _compute_htft(matrix: np.ndarray) -> dict:
    """Approximate HT/FT probabilities. Uses home/draw/away marginals."""
    hw = float(np.sum(np.tril(matrix, -1)))
    d = float(np.trace(matrix))
    aw = float(np.sum(np.triu(matrix, 1)))

    # Simplified HT model using same win probs scaled to half-time
    ht_hw = hw * 0.6
    ht_d = d * 0.65
    ht_aw = aw * 0.6
    norm = ht_hw + ht_d + ht_aw

    ht_hw, ht_d, ht_aw = ht_hw/norm, ht_d/norm, ht_aw/norm

    return {
        "HH": round(ht_hw * hw, 4),
        "HD": round(ht_hw * d, 4),
        "HA": round(ht_hw * aw, 4),
        "DH": round(ht_d * hw, 4),
        "DD": round(ht_d * d, 4),
        "DA": round(ht_d * aw, 4),
        "AH": round(ht_aw * hw, 4),
        "AD": round(ht_aw * d, 4),
        "AA": round(ht_aw * aw, 4),
    }


def _compute_asian_handicap(matrix: np.ndarray) -> dict:
    """Compute Asian handicap probabilities from the score matrix."""
    handicaps = [-2.5, -2.0, -1.5, -1.0, -0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    max_g = matrix.shape[0] - 1
    result = {}

    for hcp in handicaps:
        home_cover = 0.0
        push = 0.0
        away_cover = 0.0

        for i in range(max_g + 1):
            for j in range(max_g + 1):
                adjusted = (i + hcp) - j
                p = matrix[i][j]
                if adjusted > 0:
                    home_cover += p
                elif adjusted == 0:
                    push += p
                else:
                    away_cover += p

        result[str(hcp)] = {
            "home": round(home_cover, 4),
            "push": round(push, 4),
            "away": round(away_cover, 4),
        }

    return result
