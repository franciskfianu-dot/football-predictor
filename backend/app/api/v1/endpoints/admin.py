"""Admin endpoints — protected by secret token."""
from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

router = APIRouter()


def verify_admin(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != settings.ADMIN_SECRET_TOKEN:
        raise HTTPException(403, "Invalid admin token")


@router.get("/status")
async def get_status(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    return {"status": "ok", "message": "Admin working"}


@router.post("/seed")
async def trigger_seed(
    background_tasks: BackgroundTasks,
    x_admin_token: Optional[str] = Header(None),
):
    verify_admin(x_admin_token)
    background_tasks.add_task(run_seed)
    return {"status": "queued", "task": "seed_leagues"}


@router.post("/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    leagues: Optional[str] = None,
    x_admin_token: Optional[str] = Header(None),
):
    verify_admin(x_admin_token)
    league_list = leagues.split(",") if leagues else settings.SUPPORTED_LEAGUES
    background_tasks.add_task(run_scrape, league_list)
    return {"status": "queued", "leagues": league_list}


@router.post("/retrain")
async def trigger_retrain(
    background_tasks: BackgroundTasks,
    leagues: Optional[str] = None,
    x_admin_token: Optional[str] = Header(None),
):
    verify_admin(x_admin_token)
    league_list = leagues.split(",") if leagues else settings.SUPPORTED_LEAGUES
    background_tasks.add_task(run_retrain, league_list)
    return {"status": "queued", "leagues": league_list}


def run_seed():
    try:
        from pipeline.seed_leagues import seed
        seed()
        logger.info("Seed completed")
    except Exception as e:
        logger.error("Seed failed", error=str(e))


def run_scrape(leagues: list):
    try:
        from scrapers.manager import ScraperManager
        manager = ScraperManager()
        manager.scrape_daily_update(leagues)
        logger.info("Scrape completed")
    except Exception as e:
        logger.error("Scrape failed", error=str(e))


def run_retrain(leagues: list):
    try:
        from app.celery_app import _retrain_league
        for league in leagues:
            _retrain_league(league)
        logger.info("Retrain completed")
    except Exception as e:
        logger.error("Retrain failed", error=str(e))