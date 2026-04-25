from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.models import League, Team

router = APIRouter()

@router.get("/")
async def get_leagues(db: Session = Depends(get_db)):
    leagues = db.query(League).filter(League.active == True).all()
    return [
        {
            "id": l.id,
            "slug": l.slug,
            "name": l.name,
            "country": l.country,
        }
        for l in leagues
    ]

@router.get("/{league_slug}/teams")
async def get_teams(league_slug: str, db: Session = Depends(get_db)):
    league = db.query(League).filter(League.slug == league_slug).first()
    if not league:
        return []
    teams = db.query(Team).filter(Team.league_id == league.id).order_by(Team.name).all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "short_name": t.short_name,
        }
        for t in teams
    ]
