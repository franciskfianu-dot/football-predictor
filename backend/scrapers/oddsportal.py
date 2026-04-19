"""
Oddsportal scraper for historical and upcoming odds.
Uses Playwright stealth mode to bypass JS rendering.
Collects: 1X2, over/under, BTTS, correct score, HT/FT odds across bookmakers.
"""
import re
import json
import asyncio
from typing import Optional
from scrapers.base import ScraperBase
from app.core.logging import logger


ODDSPORTAL_LEAGUE_MAP = {
    "epl":        "soccer/england/premier-league",
    "laliga":     "soccer/spain/laliga",
    "seriea":     "soccer/italy/serie-a",
    "bundesliga": "soccer/germany/bundesliga",
    "ligue1":     "soccer/france/ligue-1",
}

MARKET_CODES = {
    "1x2":  "1",
    "o25":  "5",
    "btts":  "8",
    "ah":   "3",
    "cs":   "6",
    "htft": "11",
}


class OddsportalScraper(ScraperBase):
    SOURCE_NAME = "oddsportal"
    BASE_URL = "https://www.oddsportal.com"
    CACHE_TTL = 3600 * 4  # 4 hours

    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """Scrape historical odds for a full league season."""
        league_path = ODDSPORTAL_LEAGUE_MAP.get(league_slug)
        if not league_path:
            return []

        year_start = season.split("-")[0]
        year_end = season.split("-")[-1] if "-" in season else str(int(year_start) + 1)
        url = f"{self.BASE_URL}/{league_path}-{year_start}-{year_end}/results/"

        self.log_scrape_start()
        try:
            html = asyncio.run(self._fetch_playwright(url))
            matches = self._parse_results_page(html, league_slug)
            self._records_scraped = len(matches)
            self.log_scrape_end(status="success", target_url=url)
            return matches
        except Exception as e:
            self.log_scrape_end(status="failed", error=str(e))
            logger.error("Oddsportal scrape failed", league=league_slug, error=str(e))
            return []

    def scrape_upcoming_odds(self, league_slug: str) -> list[dict]:
        """Scrape upcoming match odds for EV calculation."""
        league_path = ODDSPORTAL_LEAGUE_MAP.get(league_slug)
        if not league_path:
            return []

        url = f"{self.BASE_URL}/{league_path}/"
        try:
            html = asyncio.run(self._fetch_playwright(url))
            return self._parse_upcoming_page(html, league_slug)
        except Exception as e:
            logger.error("Oddsportal upcoming odds failed", league=league_slug, error=str(e))
            return []

    async def _fetch_playwright(self, url: str) -> str:
        """Fetch with Playwright stealth mode."""
        cache_key = self._cache_key(url)
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                )

                # Block images/fonts to speed up
                await context.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2}",
                    lambda route: route.abort()
                )

                page = await context.new_page()
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(2000)

                html = await page.content()
                await browser.close()

                self._set_cached(cache_key, html)
                return html
        except ImportError:
            logger.warning("Playwright not available, falling back to requests")
            return self.fetch(url)

    def _parse_results_page(self, html: str, league_slug: str) -> list[dict]:
        """Parse odds from results page."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        matches = []

        # Try to extract from embedded JSON first (faster)
        json_data = self._extract_json_data(html)
        if json_data:
            return self._parse_json_odds(json_data, league_slug)

        # Fallback: parse HTML table
        table = soup.find("table", id=re.compile(r"tournamentTable|table-matches"))
        if not table:
            return []

        for row in table.find_all("tr", class_=re.compile(r"deactivate|table-dummyrow")):
            match = self._parse_odds_row(row, league_slug)
            if match:
                matches.append(match)

        return matches

    def _parse_upcoming_page(self, html: str, league_slug: str) -> list[dict]:
        """Parse upcoming fixture odds."""
        json_data = self._extract_json_data(html)
        if json_data:
            return self._parse_json_odds(json_data, league_slug, upcoming=True)

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        matches = []

        table = soup.find("table", id=re.compile(r"tournamentTable"))
        if not table:
            return []

        for row in table.find_all("tr"):
            match = self._parse_odds_row(row, league_slug)
            if match:
                matches.append(match)

        return matches

    def _extract_json_data(self, html: str) -> Optional[dict]:
        """Try to extract JSON data embedded in page."""
        patterns = [
            r"window\.__INITIAL_STATE__\s*=\s*({.+?});",
            r"window\.bookmakersData\s*=\s*({.+?});",
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    continue
        return None

    def _parse_json_odds(self, data: dict, league_slug: str, upcoming: bool = False) -> list[dict]:
        """Parse odds from embedded JSON state."""
        matches = []
        # Navigate into the typical Oddsportal JSON structure
        events = (
            data.get("page", {}).get("tournament", {}).get("events", {}) or
            data.get("tournamentData", {}).get("matches", {}) or
            {}
        )

        for event_id, event in (events.items() if isinstance(events, dict) else []):
            try:
                home_odds, draw_odds, away_odds = self._extract_1x2(event)
                if not all([home_odds, draw_odds, away_odds]):
                    continue

                matches.append({
                    "league_slug": league_slug,
                    "oddsportal_id": event_id,
                    "home_team": event.get("home-name") or event.get("homeName", ""),
                    "away_team": event.get("away-name") or event.get("awayName", ""),
                    "match_date": event.get("date-start-timestamp"),
                    "market": "1x2",
                    "odds_home": home_odds,
                    "odds_draw": draw_odds,
                    "odds_away": away_odds,
                    "implied_home": round(1 / home_odds, 4) if home_odds else None,
                    "implied_draw": round(1 / draw_odds, 4) if draw_odds else None,
                    "implied_away": round(1 / away_odds, 4) if away_odds else None,
                    "bookmaker": "best",
                    "is_upcoming": upcoming,
                })
            except Exception:
                continue

        return matches

    def _parse_odds_row(self, row, league_slug: str) -> Optional[dict]:
        """Parse a single row from the HTML table fallback."""
        cells = row.find_all("td")
        if len(cells) < 5:
            return None
        try:
            odds_cells = [c for c in cells if "odds" in (c.get("class") or [])]
            if len(odds_cells) < 3:
                return None

            home_odds = self._parse_odd(odds_cells[0].get_text(strip=True))
            draw_odds = self._parse_odd(odds_cells[1].get_text(strip=True))
            away_odds = self._parse_odd(odds_cells[2].get_text(strip=True))

            return {
                "league_slug": league_slug,
                "market": "1x2",
                "odds_home": home_odds,
                "odds_draw": draw_odds,
                "odds_away": away_odds,
                "bookmaker": "avg",
            }
        except Exception:
            return None

    def _extract_1x2(self, event: dict):
        """Extract best 1X2 odds from event dict."""
        odds = event.get("odds", {}) or event.get("1", {}) or {}
        try:
            home = float(list(odds.get("1", {0: 0}).values())[0])
            draw = float(list(odds.get("2", {0: 0}).values())[0])
            away = float(list(odds.get("3", {0: 0}).values())[0])
            return (
                home if home > 1 else None,
                draw if draw > 1 else None,
                away if away > 1 else None,
            )
        except Exception:
            return None, None, None

    def _parse_odd(self, text: str) -> Optional[float]:
        try:
            return float(text.strip())
        except (ValueError, TypeError):
            return None
