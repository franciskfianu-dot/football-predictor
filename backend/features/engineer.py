"""
Feature engineering pipeline.
Computes all 50+ features needed for the ML models from raw match data.
"""
import numpy as np
import pandas as pd
from typing import Optional
from app.core.logging import logger


# ─── Constants ────────────────────────────────────────────────────────

ROLLING_WINDOWS = [3, 5, 10, 38]
EWMA_SPANS = [3, 5, 10]
ELO_K = 32          # K-factor for Elo updates
ELO_INIT = 1500.0
HOME_ADVANTAGE = 100  # Elo home advantage in points


class FeatureEngineer:
    """
    Transforms raw match data into a feature matrix for ML models.
    """

    def build_features_for_match(
        self,
        match_date: str,
        home_team_id: str,
        away_team_id: str,
        league_id: str,
        match_history_df: pd.DataFrame,
        player_availability: dict = None,
        weather: dict = None,
        referee_stats: dict = None,
        odds_data: dict = None,
    ) -> dict:
        """
        Build the full feature vector for a single upcoming match.
        Returns a flat dict of all features.
        """
        features = {}

        # Filter history up to (not including) match date
        hist = match_history_df[match_history_df["match_date"] < match_date].copy()

        if hist.empty:
            logger.warning("No historical data", home=home_team_id, away=away_team_id)
            return self._empty_features()

        # ── Team form features ─────────────────────────────────────────
        home_form = self._get_team_form(hist, home_team_id, home_or_away="home")
        away_form = self._get_team_form(hist, away_team_id, home_or_away="away")

        features.update({f"home_{k}": v for k, v in home_form.items()})
        features.update({f"away_{k}": v for k, v in away_form.items()})

        # ── Overall (home + away combined) form ───────────────────────
        home_all = self._get_team_form(hist, home_team_id, home_or_away="all")
        away_all = self._get_team_form(hist, away_team_id, home_or_away="all")

        features.update({f"home_all_{k}": v for k, v in home_all.items()})
        features.update({f"away_all_{k}": v for k, v in away_all.items()})

        # ── Elo ratings ────────────────────────────────────────────────
        home_elo, away_elo = self._get_elo_ratings(hist, home_team_id, away_team_id)
        features["home_elo"] = home_elo
        features["away_elo"] = away_elo
        features["elo_diff"] = home_elo - away_elo
        features["elo_diff_with_home_adv"] = (home_elo + HOME_ADVANTAGE) - away_elo

        # ── Dixon-Coles strength parameters ───────────────────────────
        dc = self._get_dixon_coles_params(hist, home_team_id, away_team_id, league_id)
        features.update(dc)

        # ── H2H features ───────────────────────────────────────────────
        h2h = self._get_h2h_features(hist, home_team_id, away_team_id)
        features.update(h2h)

        # ── Fixture congestion ─────────────────────────────────────────
        features["home_days_since_last_match"] = self._days_since_last(hist, home_team_id, match_date)
        features["away_days_since_last_match"] = self._days_since_last(hist, away_team_id, match_date)
        features["home_matches_last_14d"] = self._matches_in_last_n_days(hist, home_team_id, match_date, 14)
        features["away_matches_last_14d"] = self._matches_in_last_n_days(hist, away_team_id, match_date, 14)

        # ── Player availability ────────────────────────────────────────
        if player_availability:
            features.update(self._player_features(player_availability, home_team_id, away_team_id))

        # ── Weather ────────────────────────────────────────────────────
        if weather:
            features["weather_temp_c"] = weather.get("temp_c", 12.0)
            features["weather_humidity"] = weather.get("humidity_pct", 70.0)
            features["weather_precipitation_mm"] = weather.get("precipitation_mm", 0.0)
            features["weather_wind_kmh"] = weather.get("wind_speed_kmh", 15.0)
            features["weather_is_rainy"] = float(weather.get("is_rainy", False))
        else:
            features.update(self._default_weather())

        # ── Referee stats ──────────────────────────────────────────────
        if referee_stats:
            features["ref_avg_yellow_cards"] = referee_stats.get("avg_yellow_cards", 3.5)
            features["ref_avg_red_cards"] = referee_stats.get("avg_red_cards", 0.15)
            features["ref_penalty_rate"] = referee_stats.get("avg_penalties_awarded", 0.3)
            features["ref_home_win_rate"] = referee_stats.get("home_win_rate", 0.46)
        else:
            features.update(self._default_referee())

        # ── Market signals (implied probabilities) ─────────────────────
        if odds_data:
            features.update(self._odds_features(odds_data))

        # ── Interaction terms ──────────────────────────────────────────
        features["home_attack_x_away_defence"] = (
            features.get("home_all_avg_goals_scored_5", 1.5) *
            (1 / max(features.get("away_all_avg_goals_conceded_5", 1.2), 0.1))
        )
        features["away_attack_x_home_defence"] = (
            features.get("away_all_avg_goals_scored_5", 1.2) *
            (1 / max(features.get("home_all_avg_goals_conceded_5", 1.0), 0.1))
        )
        features["elo_diff_x_home_form"] = (
            features.get("elo_diff", 0) * features.get("home_all_form_points_5", 1.5)
        )

        # ── Poisson-derived meta-features ─────────────────────────────
        poisson_meta = self._poisson_meta_features(features)
        features.update(poisson_meta)

        # ── Season phase ───────────────────────────────────────────────
        features.update(self._season_phase(match_date, league_id, hist))

        # ── Missingness flags ──────────────────────────────────────────
        features.update(self._missingness_flags(features))

        return features

    def build_feature_matrix(self, matches_df: pd.DataFrame) -> pd.DataFrame:
        """Build features for all historical matches (for training)."""
        feature_rows = []
        for _, row in matches_df.iterrows():
            hist_before = matches_df[matches_df["match_date"] < row["match_date"]]
            feats = self.build_features_for_match(
                match_date=row["match_date"],
                home_team_id=row["home_team_id"],
                away_team_id=row["away_team_id"],
                league_id=row["league_id"],
                match_history_df=hist_before,
            )
            feats["target_home_goals"] = row.get("home_goals")
            feats["target_away_goals"] = row.get("away_goals")
            feats["match_id"] = row.get("id")
            feature_rows.append(feats)

        return pd.DataFrame(feature_rows)

    # ─── Form Features ────────────────────────────────────────────────

    def _get_team_form(self, hist: pd.DataFrame, team_id: str, home_or_away: str = "all") -> dict:
        """Compute rolling form stats for a team."""
        if home_or_away == "home":
            team_matches = hist[hist["home_team_id"] == team_id].copy()
            goals_scored_col = "home_goals"
            goals_conceded_col = "away_goals"
        elif home_or_away == "away":
            team_matches = hist[hist["away_team_id"] == team_id].copy()
            goals_scored_col = "away_goals"
            goals_conceded_col = "home_goals"
        else:
            home_m = hist[hist["home_team_id"] == team_id].copy()
            away_m = hist[hist["away_team_id"] == team_id].copy()
            home_m["gs"] = home_m["home_goals"]
            home_m["gc"] = home_m["away_goals"]
            home_m["xgs"] = home_m.get("home_xg", np.nan)
            home_m["xgc"] = home_m.get("away_xg", np.nan)
            home_m["sot"] = home_m.get("home_shots_on_target", np.nan)
            away_m["gs"] = away_m["away_goals"]
            away_m["gc"] = away_m["home_goals"]
            away_m["xgs"] = away_m.get("away_xg", np.nan)
            away_m["xgc"] = away_m.get("home_xg", np.nan)
            away_m["sot"] = away_m.get("away_shots_on_target", np.nan)
            team_matches = pd.concat([home_m, away_m]).sort_values("match_date")
            goals_scored_col = "gs"
            goals_conceded_col = "gc"

        team_matches = team_matches.sort_values("match_date").tail(38)
        if team_matches.empty:
            return self._empty_form()

        # Compute result points
        if home_or_away in ("home", "away"):
            if home_or_away == "home":
                team_matches["points"] = np.where(
                    team_matches["home_goals"] > team_matches["away_goals"], 3,
                    np.where(team_matches["home_goals"] == team_matches["away_goals"], 1, 0)
                )
                team_matches["clean_sheet"] = (team_matches["away_goals"] == 0).astype(float)
            else:
                team_matches["points"] = np.where(
                    team_matches["away_goals"] > team_matches["home_goals"], 3,
                    np.where(team_matches["away_goals"] == team_matches["home_goals"], 1, 0)
                )
                team_matches["clean_sheet"] = (team_matches["home_goals"] == 0).astype(float)
        else:
            team_matches["points"] = team_matches.apply(
                lambda r: 3 if r.get("gs", 0) > r.get("gc", 0)
                          else (1 if r.get("gs", 0) == r.get("gc", 0) else 0),
                axis=1
            )
            team_matches["clean_sheet"] = (team_matches.get("gc", pd.Series()) == 0).astype(float)

        team_matches["goals_scored"] = team_matches[goals_scored_col]
        team_matches["goals_conceded"] = team_matches[goals_conceded_col]

        feats = {}
        for w in ROLLING_WINDOWS:
            tail = team_matches.tail(w)
            n = len(tail)
            if n == 0:
                continue
            suffix = f"_{w}"
            feats[f"avg_goals_scored{suffix}"] = tail["goals_scored"].mean()
            feats[f"avg_goals_conceded{suffix}"] = tail["goals_conceded"].mean()
            feats[f"form_points{suffix}"] = tail["points"].mean()
            feats[f"clean_sheet_rate{suffix}"] = tail["clean_sheet"].mean()
            feats[f"win_rate{suffix}"] = (tail["points"] == 3).mean()
            feats[f"loss_rate{suffix}"] = (tail["points"] == 0).mean()

            if "xgs" in tail.columns:
                feats[f"avg_xg{suffix}"] = tail["xgs"].mean()
                feats[f"avg_xga{suffix}"] = tail["xgc"].mean() if "xgc" in tail.columns else np.nan

        # EWMA form
        for span in EWMA_SPANS:
            feats[f"ewma_goals_scored_{span}"] = (
                team_matches["goals_scored"].ewm(span=span).mean().iloc[-1]
            )
            feats[f"ewma_goals_conceded_{span}"] = (
                team_matches["goals_conceded"].ewm(span=span).mean().iloc[-1]
            )

        # Win/draw/loss streak
        if len(team_matches) > 0:
            last_results = team_matches["points"].tail(5).tolist()
            feats["current_win_streak"] = self._count_streak(last_results, 3)
            feats["current_unbeaten_streak"] = self._count_streak(last_results, [1, 3])
            feats["last_result_pts"] = last_results[-1] if last_results else 1.0

        return feats

    # ─── Elo Rating ───────────────────────────────────────────────────

    def _get_elo_ratings(
        self, hist: pd.DataFrame, home_team_id: str, away_team_id: str
    ) -> tuple[float, float]:
        """Compute current Elo ratings from match history."""
        elo = {}

        for _, row in hist.sort_values("match_date").iterrows():
            hid = row["home_team_id"]
            aid = row["away_team_id"]
            h_elo = elo.get(hid, ELO_INIT) + HOME_ADVANTAGE
            a_elo = elo.get(aid, ELO_INIT)

            exp_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400))
            exp_a = 1 - exp_h

            hg = row.get("home_goals", 0) or 0
            ag = row.get("away_goals", 0) or 0

            if hg > ag:
                s_h, s_a = 1.0, 0.0
            elif hg == ag:
                s_h, s_a = 0.5, 0.5
            else:
                s_h, s_a = 0.0, 1.0

            elo[hid] = elo.get(hid, ELO_INIT) + ELO_K * (s_h - exp_h)
            elo[aid] = elo.get(aid, ELO_INIT) + ELO_K * (s_a - exp_a)

        return (
            elo.get(home_team_id, ELO_INIT),
            elo.get(away_team_id, ELO_INIT),
        )

    # ─── Dixon-Coles Params ───────────────────────────────────────────

    def _get_dixon_coles_params(
        self, hist: pd.DataFrame, home_team_id: str, away_team_id: str, league_id: str
    ) -> dict:
        """Compute simplified Dixon-Coles attack/defence parameters."""
        from features.dixon_coles import DixonColesModel
        dc = DixonColesModel()
        params = dc.fit(hist, league_id)

        return {
            "dc_home_attack": params.get(home_team_id, {}).get("attack", 1.0),
            "dc_home_defence": params.get(home_team_id, {}).get("defence", 1.0),
            "dc_away_attack": params.get(away_team_id, {}).get("attack", 1.0),
            "dc_away_defence": params.get(away_team_id, {}).get("defence", 1.0),
            "dc_home_advantage": params.get("home_advantage", 0.25),
            "dc_rho": params.get("rho", -0.13),
        }

    # ─── H2H Features ─────────────────────────────────────────────────

    def _get_h2h_features(
        self, hist: pd.DataFrame, home_team_id: str, away_team_id: str
    ) -> dict:
        """Head-to-head statistics from last 6 meetings."""
        h2h = hist[
            ((hist["home_team_id"] == home_team_id) & (hist["away_team_id"] == away_team_id)) |
            ((hist["home_team_id"] == away_team_id) & (hist["away_team_id"] == home_team_id))
        ].tail(6)

        if h2h.empty:
            return {
                "h2h_home_win_rate": 0.45, "h2h_draw_rate": 0.25, "h2h_away_win_rate": 0.30,
                "h2h_avg_total_goals": 2.5, "h2h_avg_home_goals": 1.3, "h2h_avg_away_goals": 1.2,
                "h2h_matches": 0,
            }

        home_wins = ((h2h["home_team_id"] == home_team_id) & (h2h["home_goals"] > h2h["away_goals"])).sum()
        home_wins += ((h2h["away_team_id"] == home_team_id) & (h2h["away_goals"] > h2h["home_goals"])).sum()
        draws = (h2h["home_goals"] == h2h["away_goals"]).sum()
        n = len(h2h)

        return {
            "h2h_home_win_rate": home_wins / n if n else 0.45,
            "h2h_draw_rate": draws / n if n else 0.25,
            "h2h_away_win_rate": (n - home_wins - draws) / n if n else 0.30,
            "h2h_avg_total_goals": (h2h["home_goals"] + h2h["away_goals"]).mean(),
            "h2h_avg_home_goals": h2h["home_goals"].mean(),
            "h2h_avg_away_goals": h2h["away_goals"].mean(),
            "h2h_matches": n,
        }

    # ─── Poisson Meta-Features ────────────────────────────────────────

    def _poisson_meta_features(self, features: dict) -> dict:
        """Compute Poisson-derived score probabilities as meta-features."""
        from scipy.stats import poisson

        lambda_home = features.get("dc_home_attack", 1.5) * features.get("dc_away_defence", 1.0) * \
                      np.exp(features.get("dc_home_advantage", 0.25))
        lambda_away = features.get("dc_away_attack", 1.2) * features.get("dc_home_defence", 1.0)

        lambda_home = max(0.1, lambda_home)
        lambda_away = max(0.1, lambda_away)

        # Score probabilities up to 5-5
        prob_home_win = 0.0
        prob_draw = 0.0
        prob_away_win = 0.0
        prob_btts = 0.0
        total_goals_probs = np.zeros(9)

        for i in range(6):
            for j in range(6):
                p = poisson.pmf(i, lambda_home) * poisson.pmf(j, lambda_away)
                if i > j:
                    prob_home_win += p
                elif i == j:
                    prob_draw += p
                else:
                    prob_away_win += p
                if i > 0 and j > 0:
                    prob_btts += p
                total = min(i + j, 8)
                total_goals_probs[total] += p

        return {
            "poisson_prob_home_win": round(prob_home_win, 4),
            "poisson_prob_draw": round(prob_draw, 4),
            "poisson_prob_away_win": round(prob_away_win, 4),
            "poisson_prob_btts": round(prob_btts, 4),
            "poisson_prob_over25": round(sum(total_goals_probs[3:]), 4),
            "poisson_lambda_home": round(lambda_home, 4),
            "poisson_lambda_away": round(lambda_away, 4),
        }

    # ─── Helpers ──────────────────────────────────────────────────────

    def _days_since_last(self, hist: pd.DataFrame, team_id: str, match_date: str) -> float:
        team_matches = hist[
            (hist["home_team_id"] == team_id) | (hist["away_team_id"] == team_id)
        ].sort_values("match_date")

        if team_matches.empty:
            return 7.0

        try:
            last = pd.to_datetime(team_matches["match_date"].iloc[-1])
            current = pd.to_datetime(match_date)
            return max(0, (current - last).days)
        except Exception:
            return 7.0

    def _matches_in_last_n_days(self, hist: pd.DataFrame, team_id: str, match_date: str, n: int) -> int:
        try:
            current = pd.to_datetime(match_date)
            cutoff = current - pd.Timedelta(days=n)
            team_matches = hist[
                ((hist["home_team_id"] == team_id) | (hist["away_team_id"] == team_id)) &
                (hist["match_date"] >= cutoff.isoformat())
            ]
            return len(team_matches)
        except Exception:
            return 0

    def _count_streak(self, results: list, target) -> int:
        streak = 0
        for r in reversed(results):
            if isinstance(target, list):
                if r in target:
                    streak += 1
                else:
                    break
            else:
                if r == target:
                    streak += 1
                else:
                    break
        return streak

    def _player_features(self, availability: dict, home_id: str, away_id: str) -> dict:
        home_avail = availability.get(home_id, {})
        away_avail = availability.get(away_id, {})
        return {
            "home_key_players_available": home_avail.get("available_ratio", 1.0),
            "away_key_players_available": away_avail.get("available_ratio", 1.0),
            "home_injuries_count": home_avail.get("injuries", 0),
            "away_injuries_count": away_avail.get("injuries", 0),
            "home_suspensions_count": home_avail.get("suspensions", 0),
            "away_suspensions_count": away_avail.get("suspensions", 0),
        }

    def _odds_features(self, odds: dict) -> dict:
        home_odds = odds.get("odds_home", 0)
        draw_odds = odds.get("odds_draw", 0)
        away_odds = odds.get("odds_away", 0)
        margin = (1/home_odds + 1/draw_odds + 1/away_odds) if all([home_odds, draw_odds, away_odds]) else 1.1
        return {
            "mkt_implied_home": round((1/home_odds) / margin, 4) if home_odds else 0.45,
            "mkt_implied_draw": round((1/draw_odds) / margin, 4) if draw_odds else 0.25,
            "mkt_implied_away": round((1/away_odds) / margin, 4) if away_odds else 0.30,
            "mkt_margin": round(margin, 4),
        }

    def _season_phase(self, match_date: str, league_id: str, hist: pd.DataFrame) -> dict:
        try:
            month = pd.to_datetime(match_date).month
            if month in (8, 9, 10):
                phase = 0  # early
            elif month in (11, 12, 1, 2):
                phase = 1  # mid
            else:
                phase = 2  # late
            return {
                "season_phase": phase,
                "season_phase_early": float(phase == 0),
                "season_phase_mid": float(phase == 1),
                "season_phase_late": float(phase == 2),
            }
        except Exception:
            return {"season_phase": 1, "season_phase_early": 0.0, "season_phase_mid": 1.0, "season_phase_late": 0.0}

    def _missingness_flags(self, features: dict) -> dict:
        key_features = [
            "home_all_avg_xg_5", "away_all_avg_xg_5",
            "home_key_players_available", "away_key_players_available",
            "mkt_implied_home", "weather_temp_c",
        ]
        return {
            f"missing_{k}": float(features.get(k) is None or (
                isinstance(features.get(k), float) and np.isnan(features.get(k))
            ))
            for k in key_features
        }

    def _empty_form(self) -> dict:
        return {
            f"avg_goals_scored_{w}": 1.5 for w in ROLLING_WINDOWS
        } | {
            f"avg_goals_conceded_{w}": 1.2 for w in ROLLING_WINDOWS
        } | {
            f"form_points_{w}": 1.5 for w in ROLLING_WINDOWS
        }

    def _empty_features(self) -> dict:
        return {"data_insufficient": True}

    def _default_weather(self) -> dict:
        return {
            "weather_temp_c": 12.0,
            "weather_humidity": 70.0,
            "weather_precipitation_mm": 0.0,
            "weather_wind_kmh": 15.0,
            "weather_is_rainy": 0.0,
        }

    def _default_referee(self) -> dict:
        return {
            "ref_avg_yellow_cards": 3.5,
            "ref_avg_red_cards": 0.15,
            "ref_penalty_rate": 0.3,
            "ref_home_win_rate": 0.46,
        }
