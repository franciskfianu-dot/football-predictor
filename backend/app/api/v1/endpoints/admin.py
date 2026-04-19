"""Admin endpoints — protected by secret token."""
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from typing import Optional
from app.core.config import settings
from app.core.logging import logger
from app.celery_app import retrain_task, daily_scrape_task

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
    """Trigger model retraining (called by GitHub Actions cron at 02:00 UTC)."""
    verify_admin(x_admin_token)
    league_list = leagues.split(",") if leagues else settings.SUPPORTED_LEAGUES
    logger.info("Retrain triggered", leagues=league_list)
    retrain_task.delay(league_list)
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
    daily_scrape_task.delay(league_list)
    return {"status": "queued", "leagues": league_list}


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
            {"source": s.source, "status": s.status, "records": s.records_scraped,
             "started": s.started_at.isoformat() if s.started_at else None}
            for s in recent_scrapes
        ],
        "champion_models": [
            {"league": m.league_id, "model": m.model_name, "rps": m.rps_score,
             "trained": m.trained_at.isoformat() if m.trained_at else None}
            for m in champion_models
        ],
    }
