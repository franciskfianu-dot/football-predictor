"""
Transfermarkt.com scraper.
Collects: squad market values, injury lists, suspension history, player ages.
Uses Selenium headless for JS-rendered tables.
"""
import time
import re
from typing import Optional
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from scrapers.base import ScraperBase
from app.core.logging import logger


TRANSFERMARKT_LEAGUE_MAP = {
    "epl":        {"id": "GB1", "name": "premier-league"},
    "laliga":     {"id": "ES1", "name": "laliga"},
    "seriea":     {"id": "IT1", "name": "serie-a"},
    "bundesliga": {"id": "L1",  "name": "bundesliga"},
    "ligue1":     {"id": "FR1", "name": "ligue-1"},
}


def _get_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


class TransfermarktScraper(ScraperBase):
    SOURCE_NAME = "transfermarkt"
    BASE_URL = "https://www.transfermarkt.com"
    CACHE_TTL = 3600 * 12  # 12 hours - injuries don't change that fast

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """Scrape league-level squad values."""
        league_info = TRANSFERMARKT_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        year = season.split("-")[0]
        url = (
            f"{self.BASE_URL}/{league_info['name']}/startseite/wettbewerb/"
            f"{league_info['id']}/plus/?saison_id={year}"
        )

        self.log_scrape_start()
        try:
            html = self._fetch_with_selenium(url)
            teams = self._parse_squad_values(html, league_slug)
            self._records_scraped = len(teams)
            self.log_scrape_end(status="success", target_url=url)
            return teams
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("Transfermarkt squad values failed", error=str(e))
            return []

    def scrape_injuries(self, league_slug: str) -> list[dict]:
        """Scrape current injury list for a league."""
        league_info = TRANSFERMARKT_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        url = (
            f"{self.BASE_URL}/{league_info['name']}/verletzte/wettbewerb/{league_info['id']}"
        )

        self.log_scrape_start()
        try:
            html = self._fetch_with_selenium(url)
            injuries = self._parse_injuries(html)
            self._records_scraped = len(injuries)
            self.log_scrape_end(status="success", target_url=url)
            return injuries
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("Transfermarkt injuries failed", error=str(e))
            return []

    def scrape_suspensions(self, league_slug: str) -> list[dict]:
        """Scrape current suspension list for a league."""
        league_info = TRANSFERMARKT_LEAGUE_MAP.get(league_slug)
        if not league_info:
            return []

        url = (
            f"{self.BASE_URL}/{league_info['name']}/gesperrt/wettbewerb/{league_info['id']}"
        )

        try:
            html = self._fetch_with_selenium(url)
            return self._parse_suspensions(html)
        except Exception as e:
            logger.error("Transfermarkt suspensions failed", error=str(e))
            return []

    def _fetch_with_selenium(self, url: str) -> str:
        """Fetch page using headless Selenium (JS-rendered tables)."""
        # Check cache first
        cache_key = self._cache_key(url)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        driver = None
        try:
            driver = _get_driver()
            driver.get(url)
            time.sleep(3 + self.delay)  # Wait for JS to render
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "table"))
            )
            html = driver.page_source
            self._set_cached(cache_key, html)
            return html
        finally:
            if driver:
                driver.quit()

    def _parse_squad_values(self, html: str, league_slug: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_=re.compile(r"items"))
        if not table:
            return []

        teams = []
        for row in table.find_all("tr", class_=["odd", "even"]):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            try:
                team_link = row.find("a", class_="vereinprofil_tooltip")
                squad_value_cell = cells[-1] if cells else None

                teams.append({
                    "team_name": team_link.get_text(strip=True) if team_link else "",
                    "transfermarkt_id": self._extract_team_id(team_link),
                    "squad_value_eur": self._parse_value(
                        squad_value_cell.get_text(strip=True) if squad_value_cell else ""
                    ),
                    "league_slug": league_slug,
                })
            except Exception:
                continue

        return [t for t in teams if t["team_name"]]

    def _parse_injuries(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_=re.compile(r"items"))
        if not table:
            return []

        injuries = []
        for row in table.find_all("tr", class_=["odd", "even"]):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue
            try:
                player_cell = cells[0]
                team_cell = cells[2] if len(cells) > 2 else None
                injury_cell = cells[3] if len(cells) > 3 else None
                return_cell = cells[4] if len(cells) > 4 else None

                player_link = player_cell.find("a")
                injuries.append({
                    "player_name": player_link.get_text(strip=True) if player_link else "",
                    "transfermarkt_player_id": self._extract_player_id(player_link),
                    "team_name": team_cell.get_text(strip=True) if team_cell else "",
                    "injury_type": injury_cell.get_text(strip=True) if injury_cell else "",
                    "expected_return": return_cell.get_text(strip=True) if return_cell else "",
                    "status": "injured",
                })
            except Exception:
                continue

        return [i for i in injuries if i["player_name"]]

    def _parse_suspensions(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "lxml")
        table = soup.find("table", class_=re.compile(r"items"))
        if not table:
            return []

        suspensions = []
        for row in table.find_all("tr", class_=["odd", "even"]):
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            try:
                player_link = row.find("a", href=re.compile(r"/spieler/"))
                team_name = cells[2].get_text(strip=True) if len(cells) > 2 else ""
                suspensions.append({
                    "player_name": player_link.get_text(strip=True) if player_link else "",
                    "team_name": team_name,
                    "status": "suspended",
                    "games_remaining": self._extract_games_remaining(cells),
                })
            except Exception:
                continue

        return [s for s in suspensions if s["player_name"]]

    def _extract_team_id(self, tag) -> Optional[str]:
        if tag and tag.get("href"):
            m = re.search(r"/verein/(\d+)", tag["href"])
            if m:
                return m.group(1)
        return None

    def _extract_player_id(self, tag) -> Optional[str]:
        if tag and tag.get("href"):
            m = re.search(r"/spieler/(\d+)", tag["href"])
            if m:
                return m.group(1)
        return None

    def _extract_games_remaining(self, cells) -> Optional[int]:
        for cell in cells:
            text = cell.get_text(strip=True)
            m = re.search(r"(\d+)\s*(?:game|match|Spiel)", text, re.IGNORECASE)
            if m:
                return int(m.group(1))
        return None

    def _parse_value(self, text: str) -> Optional[float]:
        """Parse '€45.00m' or '€500k' to float in millions EUR."""
        text = text.replace("€", "").strip()
        try:
            if "bn" in text.lower():
                return float(re.sub(r"[^\d.]", "", text)) * 1000
            elif "m" in text.lower():
                return float(re.sub(r"[^\d.]", "", text))
            elif "k" in text.lower():
                return float(re.sub(r"[^\d.]", "", text)) / 1000
            return float(re.sub(r"[^\d.]", "", text))
        except (ValueError, TypeError):
            return None
