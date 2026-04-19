"""
/predictions endpoints — the core of the application.
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json

from app.db.session import get_db
from app.db.models import Match, Team, League, MatchFeatures, Prediction, MatchOdds
from models.prediction_engine import PredictionEngine
from features.engineer import FeatureEngineer
from scrapers.manager import ScraperManager
from app.core.logging import logger
import redis as redis_client
from app.core.config import settings
import pandas as pd

router = APIRouter()
redis_conn = redis_client.from_url(settings.REDIS_URL, decode_responses=True)

PREDICTION_CACHE_TTL = 3600 * 6  # 6 hours


class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    league: str
    match_date: str  # ISO format: "2024-12-15T15:00:00"
    override_features: Optional[dict] = None


class BatchPredictRequest(BaseModel):
    matches: list[PredictRequest]


@router.post("/predict")
async def predict_match(
    request: PredictRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Generate a full prediction for a single match.
    Returns all markets: 1X2, correct score, over/under, BTTS, Asian handicap, HT/FT.
    Includes EV betting value analysis.
    """
    cache_key = f"pred:{request.league}:{request.home_team}:{request.away_team}:{request.match_date[:10]}"
    cached = redis_conn.get(cache_key)
    if cached and not request.override_features:
        logger.info("Prediction cache hit", key=cache_key)
        return json.loads(cached)

    # Look up league
    league = db.query(League).filter(League.slug == request.league).first()
    if not league:
        raise HTTPException(404, f"League '{request.league}' not found")

    # Look up teams
    home_team = db.query(Team).filter(
        Team.league_id == league.id,
        Team.name.ilike(f"%{request.home_team}%")
    ).first()
    away_team = db.query(Team).filter(
        Team.league_id == league.id,
        Team.name.ilike(f"%{request.away_team}%")
    ).first()

    if not home_team:
        raise HTTPException(404, f"Home team '{request.home_team}' not found in {request.league}")
    if not away_team:
        raise HTTPException(404, f"Away team '{request.away_team}' not found in {request.league}")

    # Load historical match data for feature engineering
    matches_df = _load_match_history(db, league.id)

    if matches_df.empty:
        raise HTTPException(503, "Insufficient historical data. Please run initial data scrape first.")

    # Engineer features
    engineer = FeatureEngineer()

    # Get weather + referee + odds (on-demand, non-blocking)
    weather = _get_weather(home_team)
    referee_stats = _get_referee_stats(db, request.match_date)
    odds_data = _get_latest_odds(db, home_team.id, away_team.id)

    features = engineer.build_features_for_match(
        match_date=request.match_date,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        league_id=league.id,
        match_history_df=matches_df,
        weather=weather,
        referee_stats=referee_stats,
        odds_data=odds_data,
    )

    # Apply user overrides
    if request.override_features:
        features.update(request.override_features)

    # Load model and predict
    engine = PredictionEngine(league.id)
    engine.load_champion()
    prediction = engine.predict(features, odds_data=odds_data)

    # Build response
    response = {
        "home_team": home_team.name,
        "away_team": away_team.name,
        "league": league.name,
        "match_date": request.match_date,
        "prediction": prediction,
        "features_used": list(features.keys()),
        "data_coverage": _assess_data_coverage(features),
        "disclaimer": "Statistical model outputs only. Not financial or gambling advice. Gamble responsibly.",
    }

    # Cache result
    redis_conn.setex(cache_key, PREDICTION_CACHE_TTL, json.dumps(response, default=str))

    # Save prediction to DB in background
    background_tasks.add_task(_save_prediction, db, home_team.id, away_team.id, prediction)

    return response


@router.post("/batch")
async def batch_predict(
    request: BatchPredictRequest,
    db: Session = Depends(get_db),
):
    """Predict multiple matches at once (for Google Sheets sync)."""
    results = []
    for match in request.matches:
        try:
            result = await predict_match(match, BackgroundTasks(), db)
            results.append({"status": "ok", "result": result})
        except HTTPException as e:
            results.append({"status": "error", "detail": e.detail})
        except Exception as e:
            results.append({"status": "error", "detail": str(e)})
    return {"results": results}


@router.get("/upcoming/{league_slug}")
async def get_upcoming_predictions(
    league_slug: str,
    db: Session = Depends(get_db),
):
    """Get pre-generated predictions for upcoming fixtures."""
    league = db.query(League).filter(League.slug == league_slug).first()
    if not league:
        raise HTTPException(404, "League not found")

    # Upcoming matches with pre-computed predictions
    from app.db.models import Match
    from datetime import datetime, timedelta
    upcoming = (
        db.query(Match)
        .filter(
            Match.league_id == league.id,
            Match.match_date >= datetime.utcnow(),
            Match.match_date <= datetime.utcnow() + timedelta(days=7),
            Match.status == "scheduled",
        )
        .order_by(Match.match_date)
        .all()
    )

    return {
        "league": league_slug,
        "fixtures": [
            {
                "match_id": m.id,
                "home_team": m.home_team.name if m.home_team else "",
                "away_team": m.away_team.name if m.away_team else "",
                "match_date": m.match_date.isoformat() if m.match_date else "",
                "matchday": m.matchday,
            }
            for m in upcoming
        ],
    }


# ── Helpers ────────────────────────────────────────────────────────────

def _load_match_history(db: Session, league_id: str) -> pd.DataFrame:
    """Load all finished matches for a league into a DataFrame."""
    matches = (
        db.query(Match)
        .filter(Match.league_id == league_id, Match.status == "finished")
        .order_by(Match.match_date)
        .all()
    )
    if not matches:
        return pd.DataFrame()

    return pd.DataFrame([{
        "id": m.id,
        "match_date": m.match_date.isoformat() if m.match_date else "",
        "home_team_id": m.home_team_id,
        "away_team_id": m.away_team_id,
        "league_id": m.league_id,
        "home_goals": m.home_goals,
        "away_goals": m.away_goals,
        "home_goals_ht": m.home_goals_ht,
        "away_goals_ht": m.away_goals_ht,
        "home_xg": m.home_xg,
        "away_xg": m.away_xg,
        "home_possession": m.home_possession,
        "away_possession": m.away_possession,
        "home_shots_on_target": m.home_shots_on_target,
        "away_shots_on_target": m.away_shots_on_target,
    } for m in matches])


def _get_weather(team: Team) -> dict:
    if not (team.stadium_lat and team.stadium_lon):
        return {}
    try:
        from scrapers.weather import WeatherScraper
        scraper = WeatherScraper()
        return scraper.get_match_weather(team.stadium_lat, team.stadium_lon)
    except Exception:
        return {}


def _get_referee_stats(db: Session, match_date: str) -> dict:
    return {}  # Returns populated when referee data is available


def _get_latest_odds(db: Session, home_id: str, away_id: str) -> dict:
    from app.db.models import Match, MatchOdds
    try:
        match = (
            db.query(Match)
            .filter(Match.home_team_id == home_id, Match.away_team_id == away_id)
            .order_by(Match.match_date.desc())
            .first()
        )
        if not match:
            return {}
        odds = db.query(MatchOdds).filter(
            MatchOdds.match_id == match.id,
            MatchOdds.market == "1x2",
        ).all()
        if not odds:
            return {}
        best = {o.selection: o.closing_odds for o in odds}
        return {
            "odds_home": best.get("home"),
            "odds_draw": best.get("draw"),
            "odds_away": best.get("away"),
        }
    except Exception:
        return {}


def _assess_data_coverage(features: dict) -> str:
    missing_count = sum(1 for k, v in features.items() if k.startswith("missing_") and v == 1.0)
    if missing_count == 0:
        return "full"
    elif missing_count <= 2:
        return "partial"
    return "limited"


def _save_prediction(db: Session, home_id: str, away_id: str, prediction: dict):
    """Background task: persist prediction to DB."""
    try:
        match = (
            db.query(Match)
            .filter(Match.home_team_id == home_id, Match.away_team_id == away_id)
            .order_by(Match.match_date.desc())
            .first()
        )
        if not match:
            return
        pred = Prediction(
            match_id=match.id,
            confidence_band=prediction.get("confidence_band"),
            prob_home_win=prediction.get("prob_home_win"),
            prob_draw=prediction.get("prob_draw"),
            prob_away_win=prediction.get("prob_away_win"),
            prob_btts=prediction.get("prob_btts"),
            prob_over_25=prediction.get("prob_over_25"),
            top_scores_json=prediction.get("top_scores"),
            ev_flags_json=prediction.get("ev_flags"),
            shap_values_json=prediction.get("shap_drivers"),
        )
        db.add(pred)
        db.commit()
    except Exception as e:
        logger.error("Failed to save prediction", error=str(e))
