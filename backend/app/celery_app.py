"""
Celery application — background tasks for scraping, training, and daily pipeline.
"""
from celery import Celery
from celery.schedules import crontab
from app.core.config import settings

celery_app = Celery(
    "football_predictor",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.celery_app"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Daily scrape + retrain at 02:00 UTC
        "daily-pipeline": {
            "task": "app.celery_app.daily_pipeline_task",
            "schedule": crontab(hour=2, minute=0),
            "args": [],
        },
        # Keep Supabase awake (ping every 5 days)
        "keep-db-alive": {
            "task": "app.celery_app.ping_db_task",
            "schedule": crontab(hour=12, minute=0, day_of_week="*/5"),
        },
    },
)


@celery_app.task(name="app.celery_app.daily_pipeline_task", bind=True, max_retries=2)
def daily_pipeline_task(self):
    """Full daily pipeline: scrape → update features → retrain → elect champion."""
    from app.core.logging import logger
    logger.info("Daily pipeline starting")
    try:
        # Step 1: Scrape
        from scrapers.manager import ScraperManager
        manager = ScraperManager()
        scrape_results = manager.scrape_daily_update()
        logger.info("Daily scrape complete", results=scrape_results)

        # Step 2: Retrain all leagues
        for league in settings.SUPPORTED_LEAGUES:
            try:
                _retrain_league(league)
            except Exception as e:
                logger.error("Retrain failed", league=league, error=str(e))

        logger.info("Daily pipeline complete")
        return {"status": "complete"}
    except Exception as exc:
        logger.error("Daily pipeline failed", error=str(exc))
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(name="app.celery_app.retrain_task", bind=True, max_retries=1)
def retrain_task(self, leagues: list[str] = None):
    """On-demand model retraining (triggered by admin endpoint or GitHub Actions)."""
    from app.core.logging import logger
    leagues = leagues or settings.SUPPORTED_LEAGUES
    logger.info("Retrain task started", leagues=leagues)
    results = {}
    for league in leagues:
        try:
            result = _retrain_league(league)
            results[league] = result
        except Exception as e:
            logger.error("Retrain failed", league=league, error=str(e))
            results[league] = {"error": str(e)}
    return results


@celery_app.task(name="app.celery_app.daily_scrape_task")
def daily_scrape_task(leagues: list[str] = None):
    """On-demand scrape task."""
    from scrapers.manager import ScraperManager
    manager = ScraperManager()
    return manager.scrape_daily_update(leagues)


@celery_app.task(name="app.celery_app.ping_db_task")
def ping_db_task():
    """Keep Supabase from pausing on free tier."""
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return {"status": "pinged"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _retrain_league(league: str) -> dict:
    """Retrain all models for a single league and elect new champion."""
    from app.core.logging import logger
    from app.db.session import SessionLocal
    from app.db.models import Match, ModelVersion
    from features.engineer import FeatureEngineer
    from models.training.trainer import ModelTrainingPipeline
    import pandas as pd

    db = SessionLocal()

    # Load match history
    matches = (
        db.query(Match)
        .filter(Match.league_id == league, Match.status == "finished")
        .order_by(Match.match_date)
        .all()
    )

    if len(matches) < 200:
        logger.warning("Not enough matches to retrain", league=league, count=len(matches))
        db.close()
        return {"skipped": True, "reason": "insufficient_data"}

    # Build feature matrix
    matches_df = _matches_to_df(matches)
    engineer = FeatureEngineer()
    features_df = engineer.build_feature_matrix(matches_df)
    features_df = features_df.dropna(subset=["target_home_goals", "target_away_goals"])

    # Train all models
    pipeline = ModelTrainingPipeline(league)
    result = pipeline.run(features_df)

    if result and "champion" in result:
        # Update champion in DB
        db.query(ModelVersion).filter(
            ModelVersion.league_id == league,
            ModelVersion.is_champion == True,
        ).update({"is_champion": False})

        new_champ = ModelVersion(
            model_name=result["champion"],
            league_id=league,
            version=result["version"],
            is_champion=True,
            model_path=f"{settings.MODEL_STORAGE_PATH}/{result['champion']}_{league}_{result['version']}.pkl",
            rps_score=result.get("results", {}).get(result["champion"], {}).get("rps"),
            trained_at=pd.Timestamp.utcnow(),
        )
        db.add(new_champ)
        db.commit()
        logger.info("New champion saved", league=league, model=result["champion"])

    db.close()
    return result or {}


def _matches_to_df(matches) -> "pd.DataFrame":
    import pandas as pd
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
    } for m in matches])
