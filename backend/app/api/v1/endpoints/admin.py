"""Admin endpoints — protected by secret token."""
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

router = APIRouter()


def verify_admin(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != settings.ADMIN_SECRET_TOKEN:
        raise HTTPException(403, "Invalid admin token")


@router.post("/retrain")
async def trigger_retrain(
    background_tasks: BackgroundTasks,
    leagues: Optional[str] = None,
    x_admin_token: Optional[str] = Header(None),
):
    """Trigger model retraining."""
    verify_admin(x_admin_token)
    league_list = leagues.split(",") if leagues else settings.SUPPORTED_LEAGUES
    logger.info("Retrain triggered", leagues=league_list)
    background_tasks.add_task(run_retrain, league_list)
    return {"status": "queued", "leagues": league_list}


@router.post("/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    leagues: Optional[str] = None,
    x_admin_token: Optional[str] = Header(None),
):
    """Trigger a full daily scrape."""
    verify_admin(x_admin_token)
    league_list = leagues.split(",") if leagues else settings.SUPPORTED_LEAGUES
    logger.info("Scrape triggered", leagues=league_list)
    background_tasks.add_task(run_scrape, league_list)
    return {"status": "queued", "leagues": league_list}


@router.post("/seed")
async def trigger_seed(
    background_tasks: BackgroundTasks,
    x_admin_token: Optional[str] = Header(None),
):
    """Seed leagues and teams into the database."""
    verify_admin(x_admin_token)
    background_tasks.add_task(run_seed)
    return {"status": "queued", "task": "seed_leagues"}


@router.get("/status")
async def get_status(x_admin_token: Optional[str] = Header(None)):
    """Get system status."""
    verify_admin(x_admin_token)
    from app.db.session import SessionLocal
    from app.db.models import ScrapeLog, ModelVersion
    db = SessionLocal()
    recent_scrapes = (
        db.query(ScrapeLog)
        .order_by(ScrapeLog.started_at.desc())
        .limit(10)
        .all()
    )
    champion_models = (
        db.query(ModelVersion)
        .filter(ModelVersion.is_champion == True)
        .all()
    )
    db.close()
    return {
        "recent_scrapes": [
            {"source": s.source, "status": s.status,
             "records": s.records_scraped,
             "started": s.started_at.isoformat() if s.started_at else None}
            for s in recent_scrapes
        ],
        "champion_models": [
            {"league": m.league_id, "model": m.model_name,
             "rps": m.rps_score,
             "trained": m.trained_at.isoformat() if m.trained_at else None}
            for m in champion_models
        ],
    }


def run_seed():
    """Run database seeding in background."""
    try:
        from pipeline.seed_leagues import seed
        seed()
        logger.info("Seed completed successfully")
    except Exception as e:
        logger.error("Seed failed", error=str(e))


def run_scrape(leagues: list):
    """Run scrape in background without Celery."""
    try:
        from scrapers.manager import ScraperManager
        manager = ScraperManager()
        result = manager.scrape_daily_update(leagues)
        logger.info("Scrape completed", result=result)
    except Exception as e:
        logger.error("Scrape failed", error=str(e))


def run_retrain(leagues: list):
    """Run retraining in background without Celery."""
    try:
        from app.celery_app import _retrain_league
        for league in leagues:
            _retrain_league(league)
        logger.info("Retrain completed")
    except Exception as e:
        logger.error("Retrain failed", error=str(e))