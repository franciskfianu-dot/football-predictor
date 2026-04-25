"""
football-data.org API client.
Free tier: 10 requests/minute, covers EPL, La Liga, Serie A, Bundesliga, Ligue 1.
No scraping - proper REST API, never gets blocked.
"""
import time
import requests
from app.core.config import settings
from app.core.logging import logger

BASE_URL = "https://api.football-data.org/v4"

LEAGUE_MAP = {
    "epl":        2021,
    "laliga":     2014,
    "seriea":     2019,
    "bundesliga": 2002,
    "ligue1":     2015,
}

def get_headers():
    return {"X-Auth-Token": settings.FOOTBALL_DATA_API_KEY}

def _get(endpoint: str) -> dict:
    url = f"{BASE_URL}{endpoint}"
    logger.info("API request", url=url)
    response = requests.get(url, headers=get_headers(), timeout=15)
    response.raise_for_status()
    time.sleep(6)
    return response.json()

def fetch_matches(league_slug: str, season: int) -> list[dict]:
    league_id = LEAGUE_MAP.get(league_slug)
    if not league_id:
        return []
    try:
        data = _get(f"/competitions/{league_id}/matches?season={season}")
        matches = data.get("matches", [])
        result = []
        for m in matches:
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            score = m.get("score", {})
            full = score.get("fullTime", {})
            half = score.get("halfTime", {})
            result.append({
                "league_slug": league_slug,
                "season": f"{season}-{season+1}",
                "matchday": m.get("matchday"),
                "match_date": m.get("utcDate", ""),
                "home_team_name": home.get("name", ""),
                "away_team_name": away.get("name", ""),
                "home_goals": full.get("home"),
                "away_goals": full.get("away"),
                "home_goals_ht": half.get("home"),
                "away_goals_ht": half.get("away"),
                "status": m.get("status", "").lower(),
                "football_data_id": str(m.get("id", "")),
            })
        logger.info("Fetched matches", league=league_slug, season=season, count=len(result))
        return result
    except Exception as e:
        logger.error("fetch_matches failed", league=league_slug, error=str(e))
        return []

def fetch_upcoming(league_slug: str) -> list[dict]:
    league_id = LEAGUE_MAP.get(league_slug)
    if not league_id:
        return []
    try:
        data = _get(f"/competitions/{league_id}/matches?status=SCHEDULED")
        matches = data.get("matches", [])
        result = []
        for m in matches:
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            result.append({
                "league_slug": league_slug,
                "matchday": m.get("matchday"),
                "match_date": m.get("utcDate", ""),
                "home_team_name": home.get("name", ""),
                "away_team_name": away.get("name", ""),
                "home_goals": None,
                "away_goals": None,
                "status": "scheduled",
                "football_data_id": str(m.get("id", "")),
            })
        return result
    except Exception as e:
        logger.error("fetch_upcoming failed", league=league_slug, error=str(e))
        return []
