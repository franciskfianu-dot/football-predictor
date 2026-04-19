"""
FBref.com scraper.
Collects: match results, xG, xGA, possession, shots, progressive passes, PPDA, set-piece goals.
Uses BeautifulSoup + requests with 3s delay between requests.
"""
import re
from typing import Optional
from bs4 import BeautifulSoup
from scrapers.base import ScraperBase
from app.core.logging import logger


# FBref league IDs mapped to our slugs
FBREF_LEAGUE_MAP = {
    "epl":        {"id": "9",  "name": "Premier-League"},
    "laliga":     {"id": "12", "name": "La-Liga"},
    "seriea":     {"id": "11", "name": "Serie-A"},
    "bundesliga": {"id": "20", "name": "Bundesliga"},
    "ligue1":     {"id": "13", "name": "Ligue-1"},
}


class FBrefScraper(ScraperBase):
    SOURCE_NAME = "fbref"
    BASE_URL = "https://fbref.com"

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """
        Scrape all matches for a league/season.
        season format: "2023-2024"
        Returns list of match dicts with full stats.
        """
        self.log_scrape_start()
        league_info = FBREF_LEAGUE_MAP.get(league_slug)
        if not league_info:
            logger.warning("Unknown league", slug=league_slug)
            return []

        matches = []
        try:
            url = (
                f"{self.BASE_URL}/en/comps/{league_info['id']}/{season}/schedule/"
                f"{season}-{league_info['name']}-Scores-and-Fixtures"
            )
            html = self.fetch(url)
            matches = self._parse_fixtures(html, league_slug, season)
            self._records_scraped = len(matches)
            self.log_scrape_end(status="success", target_url=url)
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("FBref scrape failed", league=league_slug, season=season, error=str(e))

        return matches

    def _parse_fixtures(self, html: str, league_slug: str, season: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", {"id": re.compile(r"sched_.*_1")})
        if not table:
            logger.warning("No schedule table found on FBref page")
            return []

        rows = table.find("tbody").find_all("tr", class_=lambda c: c != "spacer")
        matches = []

        for row in rows:
            try:
                match = self._parse_row(row, league_slug, season)
                if match:
                    matches.append(match)
            except Exception as e:
                logger.debug("Row parse error", error=str(e))
                continue

        return matches

    def _parse_row(self, row, league_slug: str, season: str) -> Optional[dict]:
        cells = {td.get("data-stat"): td for td in row.find_all(["td", "th"])}

        # Skip header rows or future matches without scores
        date_cell = cells.get("date")
        score_cell = cells.get("score")
        if not date_cell or not score_cell:
            return None

        date_str = date_cell.get_text(strip=True)
        score_text = score_cell.get_text(strip=True)

        if not date_str or not score_text or "–" not in score_text:
            return None

        # Parse score
        try:
            home_goals, away_goals = [int(x) for x in score_text.split("–")]
        except (ValueError, AttributeError):
            return None

        home_team = cells.get("home_team", cells.get("squad_a"))
        away_team = cells.get("away_team", cells.get("squad_b"))

        if not home_team or not away_team:
            return None

        match_dict = {
            "league_slug": league_slug,
            "season": season,
            "match_date": date_str,
            "home_team_name": home_team.get_text(strip=True),
            "away_team_name": away_team.get_text(strip=True),
            "home_goals": home_goals,
            "away_goals": away_goals,
            "fbref_match_id": self._extract_match_id(score_cell),
        }

        # Extended stats if available
        match_dict.update(self._safe_float(cells, "xg_a", "home_xg"))
        match_dict.update(self._safe_float(cells, "xg_b", "away_xg"))
        match_dict.update(self._safe_int(cells, "attendance", "attendance"))

        # Try to get referee
        ref_cell = cells.get("referee")
        if ref_cell:
            match_dict["referee_name"] = ref_cell.get_text(strip=True)

        # Get matchday/round
        round_cell = cells.get("round") or cells.get("gameweek")
        if round_cell:
            try:
                match_dict["matchday"] = int(round_cell.get_text(strip=True).replace("Matchweek ", ""))
            except (ValueError, AttributeError):
                pass

        return match_dict

    def scrape_match_detail(self, fbref_match_id: str) -> dict:
        """
        Scrape detailed stats for a single match (shots, possession, PPDA, set pieces).
        """
        url = f"{self.BASE_URL}/en/matches/{fbref_match_id}"
        try:
            html = self.fetch(url)
            return self._parse_match_detail(html)
        except Exception as e:
            logger.error("FBref match detail scrape failed", match_id=fbref_match_id, error=str(e))
            return {}

    def _parse_match_detail(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        stats = {}

        # Team stats table
        team_stats = soup.find("div", id="team_stats")
        if team_stats:
            rows = team_stats.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if len(cells) >= 3:
                    stat_name = cells[1].get_text(strip=True).lower().replace(" ", "_")
                    home_val = self._clean_stat(cells[0].get_text(strip=True))
                    away_val = self._clean_stat(cells[2].get_text(strip=True))
                    if home_val is not None:
                        stats[f"home_{stat_name}"] = home_val
                    if away_val is not None:
                        stats[f"away_{stat_name}"] = away_val

        # Extract possession
        poss_div = soup.find("div", id="possession")
        if poss_div:
            poss_values = re.findall(r"(\d+)%", poss_div.get_text())
            if len(poss_values) >= 2:
                stats["home_possession"] = float(poss_values[0])
                stats["away_possession"] = float(poss_values[1])

        # Half-time score
        ht_div = soup.find("div", class_="score_ht")
        if ht_div:
            ht_text = ht_div.get_text(strip=True)
            ht_match = re.search(r"(\d+)[–-](\d+)", ht_text)
            if ht_match:
                stats["home_goals_ht"] = int(ht_match.group(1))
                stats["away_goals_ht"] = int(ht_match.group(2))

        return stats

    def scrape_team_season_stats(self, league_slug: str, season: str) -> list[dict]:
        """Scrape season-level team stats for Dixon-Coles parameter initialisation."""
        league_info = FBREF_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        url = (
            f"{self.BASE_URL}/en/comps/{league_info['id']}/{season}/stats/"
            f"{season}-{league_info['name']}-Stats"
        )
        try:
            html = self.fetch(url)
            return self._parse_team_stats(html)
        except Exception as e:
            logger.error("FBref team stats scrape failed", error=str(e))
            return []

    def _parse_team_stats(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", id=re.compile(r"stats_squads_standard"))
        if not table:
            return []

        teams = []
        for row in table.find("tbody").find_all("tr"):
            cells = {td.get("data-stat"): td for td in row.find_all("td")}
            squad_cell = row.find("th", {"data-stat": "squad"})
            if not squad_cell:
                continue
            team = {
                "name": squad_cell.get_text(strip=True),
                "matches_played": self._cell_int(cells, "games"),
                "goals_for": self._cell_int(cells, "goals"),
                "goals_against": self._cell_int(cells, "goals_against"),
                "xg": self._cell_float(cells, "xg"),
                "xga": self._cell_float(cells, "xga"),
            }
            if team["name"]:
                teams.append(team)
        return teams

    # ── Helpers ──────────────────────────────────────────────────────

    def _extract_match_id(self, score_cell) -> Optional[str]:
        link = score_cell.find("a", href=True)
        if link:
            match = re.search(r"/matches/([a-f0-9]{8})", link["href"])
            if match:
                return match.group(1)
        return None

    def _safe_float(self, cells: dict, cell_key: str, field_name: str) -> dict:
        cell = cells.get(cell_key)
        if cell:
            try:
                return {field_name: float(cell.get_text(strip=True))}
            except (ValueError, TypeError):
                pass
        return {}

    def _safe_int(self, cells: dict, cell_key: str, field_name: str) -> dict:
        cell = cells.get(cell_key)
        if cell:
            try:
                return {field_name: int(cell.get_text(strip=True).replace(",", ""))}
            except (ValueError, TypeError):
                pass
        return {}

    def _cell_float(self, cells: dict, key: str) -> Optional[float]:
        cell = cells.get(key)
        if cell:
            try:
                return float(cell.get_text(strip=True))
            except (ValueError, TypeError):
                pass
        return None

    def _cell_int(self, cells: dict, key: str) -> Optional[int]:
        cell = cells.get(key)
        if cell:
            try:
                return int(cell.get_text(strip=True).replace(",", ""))
            except (ValueError, TypeError):
                pass
        return None

    def _clean_stat(self, text: str) -> Optional[float]:
        text = text.strip().replace("%", "").replace(",", "")
        try:
            return float(text)
        except (ValueError, TypeError):
            return None
