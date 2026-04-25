"""
ScraperManager: uses football-data.org API for reliable data fetching.
No web scraping - proper REST API calls only.
"""
from typing import Optional
from datetime import datetime, date
from app.core.config import settings
from app.core.logging import logger

_active_scrapes: set = set()


class ScraperManager:
    def scrape_daily_update(self, leagues: Optional[list] = None) -> dict:
        leagues = leagues or settings.SUPPORTED_LEAGUES
        results = {}
        for league in leagues:
            lock_key = f"daily:{league}:{date.today()}"
            if lock_key in _active_scrapes:
                results[league] = {"skipped": True}
                continue
            _active_scrapes.add(lock_key)
            try:
                results[league] = self._update_league(league)
            except Exception as e:
                logger.error("League update failed", league=league, error=str(e))
                results[league] = {"error": str(e)}
            finally:
                _active_scrapes.discard(lock_key)
        return results

    def scrape_full_history(self, leagues: list, seasons: int = 3) -> dict:
        results = {}
        current_year = datetime.utcnow().year
        for league in leagues:
            results[league] = {"seasons": {}, "errors": []}
            for i in range(seasons):
                year = current_year - i - 1
                logger.info("Scraping season", league=league, year=year)
                try:
                    from scrapers.football_data_api import fetch_matches
                    matches = fetch_matches(league, year)
                    self._persist_matches(matches, league)
                    results[league]["seasons"][str(year)] = len(matches)
                except Exception as e:
                    results[league]["errors"].append(str(e))
                    logger.error("Season scrape failed", league=league, year=year, error=str(e))
        return results

    def _update_league(self, league: str) -> dict:
        result = {}
        current_year = datetime.utcnow().year
        try:
            from scrapers.football_data_api import fetch_matches, fetch_upcoming
            matches = fetch_matches(league, current_year - 1)
            self._persist_matches(matches, league)
            result["matches"] = len(matches)
            upcoming = fetch_upcoming(league)
            self._persist_fixtures(upcoming, league)
            result["upcoming"] = len(upcoming)
            logger.info("League updated", league=league, matches=len(matches), upcoming=len(upcoming))
        except Exception as e:
            result["error"] = str(e)
            logger.error("Update failed", league=league, error=str(e))
        return result

    def _persist_matches(self, matches: list, league: str) -> None:
        if not matches:
            return
        try:
            from app.db.session import SessionLocal
            from app.db.models import Match, Team, League as LeagueModel
            from datetime import datetime as dt
            db = SessionLocal()
            league_obj = db.query(LeagueModel).filter(LeagueModel.slug == league).first()
            if not league_obj:
                db.close()
                return
            saved = 0
            for m in matches:
                try:
                    home_name = m.get("home_team_name", "")
                    away_name = m.get("away_team_name", "")
                    home = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{home_name[:8]}%")
                    ).first()
                    away = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{away_name[:8]}%")
                    ).first()
                    if not home or not away:
                        continue
                    match_date_str = m.get("match_date", "")
                    if not match_date_str:
                        continue
                    try:
                        match_date = dt.fromisoformat(match_date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        continue
                    existing = db.query(Match).filter(
                        Match.home_team_id == home.id,
                        Match.away_team_id == away.id,
                        Match.match_date == match_date,
                    ).first()
                    if existing:
                        if m.get("home_goals") is not None:
                            existing.home_goals = m["home_goals"]
                            existing.away_goals = m["away_goals"]
                            existing.home_goals_ht = m.get("home_goals_ht")
                            existing.away_goals_ht = m.get("away_goals_ht")
                            existing.status = "finished"
                        continue
                    match = Match(
                        league_id=league_obj.id,
                        season=m.get("season", ""),
                        matchday=m.get("matchday"),
                        match_date=match_date,
                        home_team_id=home.id,
                        away_team_id=away.id,
                        home_goals=m.get("home_goals"),
                        away_goals=m.get("away_goals"),
                        home_goals_ht=m.get("home_goals_ht"),
                        away_goals_ht=m.get("away_goals_ht"),
                        status="finished" if m.get("home_goals") is not None else "scheduled",
                    )
                    db.add(match)
                    saved += 1
                except Exception as ex:
                    logger.debug("Match persist error", error=str(ex))
                    continue
            db.commit()
            db.close()
            logger.info("Matches saved", league=league, count=saved)
        except Exception as e:
            logger.error("Persist matches failed", error=str(e))

    def _persist_fixtures(self, fixtures: list, league: str) -> None:
        self._persist_matches(fixtures, league)
