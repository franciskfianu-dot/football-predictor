"""
Base scraper with in-memory caching, rate limiting, and retry logic.
Uses in-memory cache instead of Redis to avoid connection issues on free tier.
"""
import time
import hashlib
import json
import random
from datetime import datetime
from typing import Optional, Any
from abc import ABC, abstractmethod

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.logging import logger

# Simple in-memory cache - avoids all Redis TCP connection issues
_cache: dict = {}
_cache_expiry: dict = {}


def cache_get(key: str) -> Optional[str]:
    if key in _cache:
        if time.time() < _cache_expiry.get(key, 0):
            return _cache[key]
        else:
            del _cache[key]
            _cache_expiry.pop(key, None)
    return None


def cache_set(key: str, value: str, ttl: int = 21600) -> None:
    _cache[key] = value
    _cache_expiry[key] = time.time() + ttl


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


class ScraperBase(ABC):
    SOURCE_NAME: str = "base"
    BASE_URL: str = ""
    CACHE_TTL: int = settings.SCRAPE_CACHE_TTL_SECONDS

    def __init__(self):
        self.delay = settings.SCRAPE_DELAY_SECONDS
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers=HEADERS,
        )
        self._start_time: Optional[float] = None
        self._records_scraped: int = 0

    def _cache_key(self, url: str, params: dict = None) -> str:
        raw = url + json.dumps(params or {}, sort_keys=True)
        return f"scrape:{self.SOURCE_NAME}:{hashlib.md5(raw.encode()).hexdigest()}"

    def _get_cached(self, cache_key: str) -> Optional[str]:
        return cache_get(cache_key)

    def _set_cached(self, cache_key: str, content: str) -> None:
        cache_set(cache_key, content, self.CACHE_TTL)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    def fetch(self, url: str, params: dict = None, use_cache: bool = True) -> str:
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached:
                logger.debug("Cache hit", source=self.SOURCE_NAME, url=url)
                return cached

        time.sleep(self.delay + random.uniform(0, 1.0))

        logger.info("Fetching URL", source=self.SOURCE_NAME, url=url)
        response = self.session.get(url, params=params)
        response.raise_for_status()

        content = response.text
        if use_cache:
            self._set_cached(cache_key, content)

        return content

    def fetch_json(self, url: str, params: dict = None, headers: dict = None) -> Any:
        cache_key = self._cache_key(url, params)
        cached = self._get_cached(cache_key)
        if cached:
            return json.loads(cached)

        time.sleep(self.delay + random.uniform(0, 0.5))
        if headers:
            self.session.headers.update(headers)

        response = self.session.get(url, params=params)
        response.raise_for_status()

        data = response.json()
        self._set_cached(cache_key, json.dumps(data))
        return data

    def log_scrape_start(self) -> None:
        self._start_time = time.time()
        self._records_scraped = 0

    def log_scrape_end(self, status: str = "success", error: str = None,
                       target_url: str = None) -> None:
        duration = time.time() - self._start_time if self._start_time else 0
        if status == "success":
            logger.info("Scrape complete", source=self.SOURCE_NAME,
                       records=self._records_scraped, duration=round(duration, 2))
        else:
            logger.error("Scrape failed", source=self.SOURCE_NAME, error=error)

        try:
            from app.db.session import SessionLocal
            from app.db.models import ScrapeLog
            db = SessionLocal()
            log = ScrapeLog(
                source=self.SOURCE_NAME,
                target_url=target_url,
                status=status,
                records_scraped=self._records_scraped,
                error_message=error,
                duration_seconds=duration,
                completed_at=datetime.utcnow(),
            )
            db.add(log)
            db.commit()
            db.close()
        except Exception:
            pass

    def __del__(self):
        try:
            self.session.close()
        except Exception:
            pass

    @abstractmethod
    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        pass