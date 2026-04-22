"""
ScraperManager: orchestrates all scrapers and persists data to the database.
Uses in-memory locking instead of Redis to avoid connection issues.
"""
from typing import Optional
from datetime import datetime, date

from scrapers.fbref import FBrefScraper
from scrapers.understat import UnderstatScraper
from scrapers.sofascore import SofaScoreScraper
from app.core.config import settings
from app.core.logging import logger

# In-memory lock to prevent duplicate scrape runs
_active_scrapes: set = set()


class ScraperManager:
    def __init__(self):
        self.fbref = FBrefScraper()
        self.understat = UnderstatScraper()
        self.sofascore = SofaScoreScraper()

    def scrape_daily_update(self, leagues: Optional[list] = None) -> dict:
        """Daily update: fetch recent results and upcoming fixtures."""
        leagues = leagues or settings.SUPPORTED_LEAGUES
        results = {}

        for league in leagues:
            lock_key = f"daily:{league}:{date.today()}"
            if lock_key in _active_scrapes:
                logger.info("Scrape already running", league=league)
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
        """Scrape full historical data for initial setup."""
        results = {}
        current_year = datetime.utcnow().year

        for league in leagues:
            results[league] = {"seasons": {}, "errors": []}
            for i in range(seasons):
                year = current_year - i - 1
                season = f"{year}-{year + 1}"
                logger.info("Scraping season", league=league, season=season)
                try:
                    result = self._scrape_season(league, season)
                    results[league]["seasons"][season] = result
                except Exception as e:
                    results[league]["errors"].append(str(e))
                    logger.error("Season scrape failed", league=league,
                               season=season, error=str(e))

        return results

    def _update_league(self, league: str) -> dict:
        result = {}
        current_year = datetime.utcnow().year
        season = f"{current_year - 1}-{current_year}"

        # Scrape recent FBref results
        try:
            matches = self.fbref.scrape_league_season(league, season)
            self._persist_matches(matches, league)
            result["fbref_matches"] = len(matches)
            logger.info("FBref scrape done", league=league, matches=len(matches))
        except Exception as e:
            result["fbref_error"] = str(e)
            logger.error("FBref scrape failed", league=league, error=str(e))

        # Scrape upcoming fixtures from SofaScore
        try:
            fixtures = self.sofascore.scrape_upcoming_fixtures(league, days_ahead=7)
            self._persist_fixtures(fixtures, league)
            result["upcoming_fixtures"] = len(fixtures)
        except Exception as e:
            result["sofascore_error"] = str(e)

        return result

    def _scrape_season(self, league: str, season: str) -> dict:
        result = {}

        try:
            matches = self.fbref.scrape_league_season(league, season)
            self._persist_matches(matches, league)
            result["fbref_matches"] = len(matches)
        except Exception as e:
            result["fbref_error"] = str(e)

        try:
            understat = self.understat.scrape_league_season(league, season)
            result["understat_matches"] = len(understat)
        except Exception as e:
            result["understat_error"] = str(e)

        return result

    def _persist_matches(self, matches: list, league: str) -> None:
        """Persist scraped matches to database."""
        if not matches:
            return
        try:
            from app.db.session import SessionLocal
            from app.db.models import Match, Team, League as LeagueModel
            db = SessionLocal()

            league_obj = db.query(LeagueModel).filter(
                LeagueModel.slug == league
            ).first()

            if not league_obj:
                db.close()
                return

            saved = 0
            for m in matches:
                try:
                    home = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{m.get('home_team_name', '')}%")
                    ).first()

                    away = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{m.get('away_team_name', '')}%")
                    ).first()

                    if not home or not away:
                        continue

                    # Check if match already exists
                    match_date_str = m.get("match_date", "")
                    if not match_date_str:
                        continue

                    from datetime import datetime as dt
                    try:
                        match_date = dt.fromisoformat(match_date_str)
                    except Exception:
                        from dateutil import parser as dparser
                        match_date = dparser.parse(match_date_str)

                    existing = db.query(Match).filter(
                        Match.home_team_id == home.id,
                        Match.away_team_id == away.id,
                        Match.match_date == match_date,
                    ).first()

                    if existing:
                        # Update score if available
                        if m.get("home_goals") is not None:
                            existing.home_goals = m["home_goals"]
                            existing.away_goals = m["away_goals"]
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
                        home_xg=m.get("home_xg"),
                        away_xg=m.get("away_xg"),
                        status="finished" if m.get("home_goals") is not None else "scheduled",
                        fbref_id=m.get("fbref_match_id"),
                    )
                    db.add(match)
                    saved += 1
                except Exception as e:
                    logger.debug("Match persist error", error=str(e))
                    continue

            db.commit()
            db.close()
            logger.info("Matches saved", league=league, count=saved)
        except Exception as e:
            logger.error("Persist matches failed", error=str(e))

    def _persist_fixtures(self, fixtures: list, league: str) -> None:
        """Persist upcoming fixtures to database."""
        if not fixtures:
            return
        try:
            from app.db.session import SessionLocal
            from app.db.models import Match, Team, League as LeagueModel
            from datetime import datetime as dt
            db = SessionLocal()

            league_obj = db.query(LeagueModel).filter(
                LeagueModel.slug == league
            ).first()

            if not league_obj:
                db.close()
                return

            for f in fixtures:
                try:
                    home = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{f.get('home_team_name', '')}%")
                    ).first()

                    away = db.query(Team).filter(
                        Team.league_id == league_obj.id,
                        Team.name.ilike(f"%{f.get('away_team_name', '')}%")
                    ).first()

                    if not home or not away:
                        continue

                    match_date_str = f.get("match_date", "")
                    if not match_date_str:
                        continue

                    try:
                        match_date = dt.fromisoformat(match_date_str)
                    except Exception:
                        from dateutil import parser as dparser
                        match_date = dparser.parse(match_date_str)

                    existing = db.query(Match).filter(
                        Match.home_team_id == home.id,
                        Match.away_team_id == away.id,
                        Match.match_date == match_date,
                    ).first()

                    if not existing:
                        match = Match(
                            league_id=league_obj.id,
                            season=f.get("season", ""),
                            matchday=f.get("matchday"),
                            match_date=match_date,
                            home_team_id=home.id,
                            away_team_id=away.id,
                            status="scheduled",
                            sofascore_id=f.get("sofascore_event_id"),
                        )
                        db.add(match)
                except Exception:
                    continue

            db.commit()
            db.close()
        except Exception as e:
            logger.error("Persist fixtures failed", error=str(e))