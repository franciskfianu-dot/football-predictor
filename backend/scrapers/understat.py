"""
Understat.com scraper.
Collects shot-level xG data, rolling xG timelines, team xG per match.
JSON is embedded in page source — extracted with regex (no Selenium needed).
"""
import re
import json
from typing import Optional
from scrapers.base import ScraperBase
from app.core.logging import logger


UNDERSTAT_LEAGUE_MAP = {
    "epl":        "EPL",
    "laliga":     "La_liga",
    "seriea":     "Serie_A",
    "bundesliga": "Bundesliga",
    "ligue1":     "Ligue_1",
}


class UnderstatScraper(ScraperBase):
    SOURCE_NAME = "understat"
    BASE_URL = "https://understat.com"

    # Regex to extract JSON blobs embedded in Understat's JS
    JSON_PATTERN = re.compile(r"JSON\.parse\('(.+?)'\)", re.DOTALL)

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """
        Scrape all match xG data for a league/season.
        season format: "2023" (Understat uses single year = start of season)
        """
        self.log_scrape_start()
        understat_league = UNDERSTAT_LEAGUE_MAP.get(league_slug)
        if not understat_league:
            return []

        # Convert "2023-2024" to "2023"
        year = season.split("-")[0]
        url = f"{self.BASE_URL}/league/{understat_league}/{year}"

        matches = []
        try:
            html = self.fetch(url)
            raw_matches = self._extract_json_block(html, "datesData")
            if raw_matches:
                for m in raw_matches:
                    parsed = self._parse_match(m, league_slug, season)
                    if parsed:
                        matches.append(parsed)
            self._records_scraped = len(matches)
            self.log_scrape_end(status="success", target_url=url)
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("Understat scrape failed", league=league_slug, season=season, error=str(e))

        return matches

    def scrape_match_shots(self, understat_match_id: str) -> dict:
        """Get shot-level xG for a specific match."""
        url = f"{self.BASE_URL}/match/{understat_match_id}"
        try:
            html = self.fetch(url)
            home_shots = self._extract_json_block(html, "shotsData", key="h") or []
            away_shots = self._extract_json_block(html, "shotsData", key="a") or []
            return {
                "match_id": understat_match_id,
                "home_shots": home_shots,
                "away_shots": away_shots,
                "home_xg_total": sum(float(s.get("xG", 0)) for s in home_shots),
                "away_xg_total": sum(float(s.get("xG", 0)) for s in away_shots),
                "home_shots_ot": sum(1 for s in home_shots if s.get("shotType") in ("SavedShot", "Goal")),
                "away_shots_ot": sum(1 for s in away_shots if s.get("shotType") in ("SavedShot", "Goal")),
            }
        except Exception as e:
            logger.error("Understat match shots scrape failed", match_id=understat_match_id, error=str(e))
            return {}

    def scrape_team_stats(self, league_slug: str, season: str) -> list[dict]:
        """Scrape team-level xG stats for a season."""
        understat_league = UNDERSTAT_LEAGUE_MAP.get(league_slug)
        if not understat_league:
            return []

        year = season.split("-")[0]
        url = f"{self.BASE_URL}/league/{understat_league}/{year}"

        try:
            html = self.fetch(url)
            teams_data = self._extract_json_block(html, "teamsData")
            if not teams_data:
                return []

            teams = []
            for team_id, team_info in (teams_data.items() if isinstance(teams_data, dict) else []):
                history = team_info.get("history", [])
                teams.append({
                    "understat_id": team_id,
                    "name": team_info.get("title", ""),
                    "matches": history,
                    "season_xg": sum(float(m.get("xG", 0)) for m in history),
                    "season_xga": sum(float(m.get("xGA", 0)) for m in history),
                })
            return teams
        except Exception as e:
            logger.error("Understat team stats failed", error=str(e))
            return []

    def _extract_json_block(self, html: str, var_name: str, key: str = None):
        """Extract a JSON variable embedded in Understat's page source."""
        # Pattern 1: JSON.parse('...')
        pattern = re.compile(
            rf"var\s+{re.escape(var_name)}\s*=\s*JSON\.parse\('(.+?)'\)",
            re.DOTALL
        )
        match = pattern.search(html)
        if match:
            raw = match.group(1)
            # Understat escapes unicode: \x22 → "
            raw = raw.encode().decode("unicode_escape")
            try:
                data = json.loads(raw)
                return data.get(key) if key else data
            except json.JSONDecodeError:
                pass

        # Pattern 2: direct assignment var name = {...}
        pattern2 = re.compile(
            rf"var\s+{re.escape(var_name)}\s*=\s*(\[.+?\]|\{{.+?\}})\s*;",
            re.DOTALL
        )
        match2 = pattern2.search(html)
        if match2:
            try:
                data = json.loads(match2.group(1))
                return data.get(key) if key else data
            except json.JSONDecodeError:
                pass

        return None

    def _parse_match(self, raw: dict, league_slug: str, season: str) -> Optional[dict]:
        try:
            home = raw.get("h", {})
            away = raw.get("a", {})
            goals = raw.get("goals", {})

            if not home or not away:
                return None

            return {
                "understat_match_id": raw.get("id"),
                "league_slug": league_slug,
                "season": season,
                "match_date": raw.get("datetime"),
                "home_team_name": home.get("title"),
                "away_team_name": away.get("title"),
                "home_goals": int(goals.get("h", 0)),
                "away_goals": int(goals.get("a", 0)),
                "home_xg": float(raw.get("xG", {}).get("h", 0) or 0),
                "away_xg": float(raw.get("xG", {}).get("a", 0) or 0),
                "home_xpts": float(raw.get("xpts", {}).get("h", 0) or 0),
                "away_xpts": float(raw.get("xpts", {}).get("a", 0) or 0),
                "is_result": bool(raw.get("isResult")),
            }
        except (KeyError, TypeError, ValueError) as e:
            logger.debug("Understat row parse error", error=str(e))
            return None
