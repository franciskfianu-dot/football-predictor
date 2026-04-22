"""
/predictions endpoints
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import json
import os

from app.db.session import get_db
from app.db.models import Match, Team, League, Prediction
from app.core.logging import logger
from app.core.config import settings
import pandas as pd

router = APIRouter()

# Simple in-memory prediction cache
_pred_cache: dict = {}


class PredictRequest(BaseModel):
    home_team: str
    away_team: str
    league: str
    match_date: str
    override_features: Optional[dict] = None


@router.post("/predict")
async def predict_match(
    request: PredictRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Generate a full prediction for a match."""
    cache_key = f"{request.league}:{request.home_team}:{request.away_team}:{request.match_date[:10]}"

    if cache_key in _pred_cache and not request.override_features:
        return _pred_cache[cache_key]

    league = db.query(League).filter(League.slug == request.league).first()
    if not league:
        raise HTTPException(404, f"League '{request.league}' not found")

    home_team = db.query(Team).filter(
        Team.league_id == league.id,
        Team.name.ilike(f"%{request.home_team}%")
    ).first()
    away_team = db.query(Team).filter(
        Team.league_id == league.id,
        Team.name.ilike(f"%{request.away_team}%")
    ).first()

    if not home_team:
        raise HTTPException(404, f"Home team '{request.home_team}' not found")
    if not away_team:
        raise HTTPException(404, f"Away team '{request.away_team}' not found")

    # Load match history
    matches_df = _load_match_history(db, league.id)

    # Get weather
    weather = _get_weather(home_team)

    # Engineer features
    from features.engineer import FeatureEngineer
    engineer = FeatureEngineer()
    features = engineer.build_features_for_match(
        match_date=request.match_date,
        home_team_id=home_team.id,
        away_team_id=away_team.id,
        league_id=league.id,
        match_history_df=matches_df,
        weather=weather,
    )

    if request.override_features:
        features.update(request.override_features)

    # Run prediction
    from models.prediction_engine import PredictionEngine
    engine = PredictionEngine(league.id)
    engine.load_champion()
    prediction = engine.predict(features)

    response = {
        "home_team": home_team.name,
        "away_team": away_team.name,
        "league": league.name,
        "match_date": request.match_date,
        "prediction": prediction,
        "data_coverage": _assess_coverage(features),
        "disclaimer": "Statistical model outputs only. Not financial or gambling advice. Gamble responsibly.",
    }

    _pred_cache[cache_key] = response
    return response


@router.post("/batch")
async def batch_predict(
    matches: list[PredictRequest],
    db: Session = Depends(get_db),
):
    results = []
    for match in matches:
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
    league = db.query(League).filter(League.slug == league_slug).first()
    if not league:
        raise HTTPException(404, "League not found")

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


def _load_match_history(db, league_id: str) -> pd.DataFrame:
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
        "home_xg": m.home_xg,
        "away_xg": m.away_xg,
    } for m in matches])


def _get_weather(team) -> dict:
    if not (team.stadium_lat and team.stadium_lon):
        return {}
    try:
        from scrapers.weather import WeatherScraper
        return WeatherScraper().get_match_weather(team.stadium_lat, team.stadium_lon)
    except Exception:
        return {}


def _assess_coverage(features: dict) -> str:
    if not features or features.get("data_insufficient"):
        return "limited"
    return "full"