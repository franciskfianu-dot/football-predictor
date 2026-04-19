"""
SofaScore public JSON API scraper.
Collects: lineups, referee assignments, live events, attendance.
Uses SofaScore's undocumented but stable public endpoints.
"""
import re
from datetime import datetime, timedelta
from typing import Optional
from scrapers.base import ScraperBase
from app.core.logging import logger


SOFASCORE_LEAGUE_MAP = {
    "epl":        {"id": 17,   "season_map": {}},
    "laliga":     {"id": 8,    "season_map": {}},
    "seriea":     {"id": 23,   "season_map": {}},
    "bundesliga": {"id": 35,   "season_map": {}},
    "ligue1":     {"id": 34,   "season_map": {}},
}

SOFASCORE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
}


class SofaScoreScraper(ScraperBase):
    SOURCE_NAME = "sofascore"
    BASE_URL = "https://api.sofascore.com/api/v1"
    CACHE_TTL = 3600 * 2  # 2 hours for live data

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """Scrape all events for a league/season from SofaScore."""
        league_info = SOFASCORE_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        self.log_scrape_start()
        matches = []

        try:
            season_id = self._get_season_id(league_info["id"], season)
            if not season_id:
                return []

            # Paginate through all rounds
            for page in range(0, 50):  # Max 50 pages
                url = f"{self.BASE_URL}/unique-tournament/{league_info['id']}/season/{season_id}/events/last/{page}"
                try:
                    data = self.fetch_json(url, headers=SOFASCORE_HEADERS)
                    events = data.get("events", [])
                    if not events:
                        break
                    for event in events:
                        parsed = self._parse_event(event, league_slug, season)
                        if parsed:
                            matches.append(parsed)
                except Exception:
                    break

            self._records_scraped = len(matches)
            self.log_scrape_end(status="success")
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("SofaScore scrape failed", league=league_slug, error=str(e))

        return matches

    def scrape_upcoming_fixtures(self, league_slug: str, days_ahead: int = 7) -> list[dict]:
        """Scrape upcoming fixtures for a league (next N days)."""
        league_info = SOFASCORE_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        fixtures = []
        for i in range(days_ahead):
            date = (datetime.utcnow() + timedelta(days=i)).strftime("%Y-%m-%d")
            url = f"{self.BASE_URL}/sport/football/scheduled-events/{date}"
            try:
                data = self.fetch_json(url, headers=SOFASCORE_HEADERS)
                events = data.get("events", [])
                for event in events:
                    if event.get("tournament", {}).get("uniqueTournament", {}).get("id") == league_info["id"]:
                        parsed = self._parse_event(event, league_slug, "upcoming")
                        if parsed:
                            fixtures.append(parsed)
            except Exception as e:
                logger.debug("SofaScore fixtures error", date=date, error=str(e))
                continue

        return fixtures

    def scrape_match_lineups(self, sofascore_event_id: str) -> dict:
        """Get confirmed lineups for a match."""
        url = f"{self.BASE_URL}/event/{sofascore_event_id}/lineups"
        try:
            data = self.fetch_json(url, headers=SOFASCORE_HEADERS)
            return self._parse_lineups(data)
        except Exception as e:
            logger.error("SofaScore lineups failed", event_id=sofascore_event_id, error=str(e))
            return {}

    def scrape_match_statistics(self, sofascore_event_id: str) -> dict:
        """Get match statistics (possession, shots, etc.)."""
        url = f"{self.BASE_URL}/event/{sofascore_event_id}/statistics"
        try:
            data = self.fetch_json(url, headers=SOFASCORE_HEADERS)
            return self._parse_statistics(data)
        except Exception as e:
            logger.error("SofaScore stats failed", event_id=sofascore_event_id, error=str(e))
            return {}

    def _get_season_id(self, tournament_id: int, season: str) -> Optional[int]:
        """Resolve season year string to SofaScore season ID."""
        url = f"{self.BASE_URL}/unique-tournament/{tournament_id}/seasons"
        try:
            data = self.fetch_json(url, headers=SOFASCORE_HEADERS)
            seasons = data.get("seasons", [])
            year = season.split("-")[0]
            for s in seasons:
                if str(year) in s.get("year", ""):
                    return s["id"]
            # Fallback: return most recent
            return seasons[0]["id"] if seasons else None
        except Exception:
            return None

    def _parse_event(self, event: dict, league_slug: str, season: str) -> Optional[dict]:
        try:
            home = event.get("homeTeam", {})
            away = event.get("awayTeam", {})
            score = event.get("homeScore", {})
            status = event.get("status", {})

            timestamp = event.get("startTimestamp")
            match_date = datetime.utcfromtimestamp(timestamp).isoformat() if timestamp else None

            result = {
                "sofascore_event_id": str(event.get("id")),
                "league_slug": league_slug,
                "season": season,
                "match_date": match_date,
                "home_team_name": home.get("name"),
                "away_team_name": away.get("name"),
                "home_sofascore_id": str(home.get("id", "")),
                "away_sofascore_id": str(away.get("id", "")),
                "status": status.get("type", "notstarted"),
                "matchday": event.get("roundInfo", {}).get("round"),
                "attendance": event.get("attendance"),
            }

            # Score (if finished)
            if status.get("type") == "finished":
                result["home_goals"] = event.get("homeScore", {}).get("current")
                result["away_goals"] = event.get("awayScore", {}).get("current")
                result["home_goals_ht"] = event.get("homeScore", {}).get("period1")
                result["away_goals_ht"] = event.get("awayScore", {}).get("period1")

            # Referee
            referee = event.get("referee")
            if referee:
                result["referee_name"] = referee.get("name", "")
                result["referee_sofascore_id"] = str(referee.get("id", ""))

            return result
        except Exception as e:
            logger.debug("SofaScore event parse error", error=str(e))
            return None

    def _parse_lineups(self, data: dict) -> dict:
        """Parse lineup data into player availability dict."""
        result = {"home_starters": [], "away_starters": [], "home_bench": [], "away_bench": []}

        for side in ["home", "away"]:
            lineup = data.get(side, {})
            for player in lineup.get("players", []):
                p = player.get("player", {})
                info = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "position": player.get("position"),
                    "jersey": player.get("jerseyNumber"),
                }
                if player.get("substitute", False):
                    result[f"{side}_bench"].append(info)
                else:
                    result[f"{side}_starters"].append(info)

        return result

    def _parse_statistics(self, data: dict) -> dict:
        """Parse match statistics into flat dict."""
        stats = {}
        groups = data.get("statistics", [])
        for group in groups:
            for item in group.get("statisticsItems", []):
                name = item.get("name", "").lower().replace(" ", "_")
                home_val = item.get("homeValue")
                away_val = item.get("awayValue")
                if home_val is not None:
                    stats[f"home_{name}"] = self._clean_stat_value(home_val)
                if away_val is not None:
                    stats[f"away_{name}"] = self._clean_stat_value(away_val)
        return stats

    def _clean_stat_value(self, val):
        if isinstance(val, str):
            val = val.replace("%", "").strip()
            try:
                return float(val)
            except ValueError:
                return val
        return val
