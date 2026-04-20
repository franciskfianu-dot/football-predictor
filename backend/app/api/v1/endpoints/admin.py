from fastapi import APIRouter, Header, HTTPException, BackgroundTasks
from typing import Optional
from app.core.config import settings
from app.core.logging import logger

router = APIRouter()

def verify_admin(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != settings.ADMIN_SECRET_TOKEN:
        raise HTTPException(403, "Invalid admin token")

@router.get("/status")
async def status(x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    return {"status": "ok"}

@router.post("/seed")
async def seed(background_tasks: BackgroundTasks, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    background_tasks.add_task(do_seed)
    return {"status": "queued"}

@router.post("/scrape")
async def scrape(background_tasks: BackgroundTasks, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    background_tasks.add_task(do_scrape)
    return {"status": "queued"}

@router.post("/retrain")
async def retrain(background_tasks: BackgroundTasks, x_admin_token: Optional[str] = Header(None)):
    verify_admin(x_admin_token)
    background_tasks.add_task(do_retrain)
    return {"status": "queued"}

def do_seed():
    try:
        from pipeline.seed_leagues import seed
        seed()
        logger.info("Seed completed")
    except Exception as e:
        logger.error("Seed failed", error=str(e))

def do_scrape():
    try:
        from scrapers.manager import ScraperManager
        ScraperManager().scrape_daily_update()
        logger.info("Scrape completed")
    except Exception as e:
        logger.error("Scrape failed", error=str(e))

def do_retrain():
    try:
        from app.celery_app import _retrain_league
        from app.core.config import settings
        for league in settings.SUPPORTED_LEAGUES:
            _retrain_league(league)
        logger.info("Retrain completed")
    except Exception as e:
        logger.error("Retrain failed", error=str(e))
