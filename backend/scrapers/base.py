"""
Base scraper with Redis caching, rate limiting, retry logic, and health logging.
All scrapers inherit from this class.
"""
import time
import hashlib
import json
import random
from datetime import datetime
from typing import Optional, Any
from abc import ABC, abstractmethod

import httpx
# redis imported below
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.logging import logger


ua = UserAgent()
try:
    import redis as redis_client
    redis_conn = redis_client.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    redis_conn.ping()
except Exception:
    redis_conn = None


class ScraperBase(ABC):
    """
    Base class for all scrapers.

    Features:
    - Redis response caching (6h TTL by default)
    - Configurable delay between requests
    - Exponential backoff retry (3 attempts)
    - Health logging to DB via log_scrape()
    - Random user-agent rotation
    """

    SOURCE_NAME: str = "base"
    BASE_URL: str = ""
    CACHE_TTL: int = settings.SCRAPE_CACHE_TTL_SECONDS

    def __init__(self):
        self.delay = settings.SCRAPE_DELAY_SECONDS
        self.session = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": ua.random},
        )
        self._start_time: Optional[float] = None
        self._records_scraped: int = 0

    def _cache_key(self, url: str, params: dict = None) -> str:
        raw = url + json.dumps(params or {}, sort_keys=True)
        return f"scrape:{self.SOURCE_NAME}:{hashlib.md5(raw.encode()).hexdigest()}"

    def _get_cached(self, cache_key: str) -> Optional[str]:
        try:
            return redis_conn.get(cache_key)
        except Exception:
            return None

    def _set_cached(self, cache_key: str, content: str) -> None:
        try:
            redis_conn.setex(cache_key, self.CACHE_TTL, content)
        except Exception:
            pass

    @retry(
        stop=stop_after_attempt(settings.SCRAPE_RETRY_COUNT),
        wait=wait_exponential(multiplier=1, min=4, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    )
    def fetch(self, url: str, params: dict = None, use_cache: bool = True) -> str:
        """Fetch a URL with caching, rate limiting, and retry."""
        cache_key = self._cache_key(url, params)

        if use_cache:
            cached = self._get_cached(cache_key)
            if cached:
                logger.debug("Cache hit", source=self.SOURCE_NAME, url=url)
                return cached

        # Polite delay + small jitter
        time.sleep(self.delay + random.uniform(0, 1.0))

        # Rotate user agent per request
        self.session.headers.update({"User-Agent": ua.random})

        logger.info("Fetching URL", source=self.SOURCE_NAME, url=url)
        response = self.session.get(url, params=params)
        response.raise_for_status()

        content = response.text
        if use_cache:
            self._set_cached(cache_key, content)

        return content

    def fetch_json(self, url: str, params: dict = None, headers: dict = None) -> Any:
        """Fetch a JSON endpoint."""
        cache_key = self._cache_key(url, params)
        cached = self._get_cached(cache_key)
        if cached:
            return json.loads(cached)

        time.sleep(self.delay + random.uniform(0, 0.5))
        self.session.headers.update({"User-Agent": ua.random})
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

        log_data = {
            "source": self.SOURCE_NAME,
            "status": status,
            "records_scraped": self._records_scraped,
            "duration_seconds": round(duration, 2),
        }
        if error:
            log_data["error"] = error
        if target_url:
            log_data["url"] = target_url

        if status == "success":
            logger.info("Scrape complete", **log_data)
        else:
            logger.error("Scrape failed", **log_data)

        # Write to DB scrape log table
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
        except Exception as e:
            logger.warning("Failed to write scrape log", error=str(e))

    def __del__(self):
        try:
            self.session.close()
        except Exception:
            pass

    @abstractmethod
    def scrape_league_season(self, league_slug: str, season: str) -> list[dict]:
        """Each scraper must implement this."""
        pass
