"""
Football Predictor API
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import setup_logging, logger
from app.api.v1 import router as api_v1_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("Starting Football Predictor API", version=settings.VERSION, env=settings.ENVIRONMENT)
    try:
        from app.db.session import create_tables
        create_tables()
        logger.info("Database tables ready")
    except Exception as e:
        logger.error("Database setup error", error=str(e))
    yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Football score prediction engine",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    status = {"status": "ok", "version": settings.VERSION}

    # DB check
    try:
        from app.db.session import SessionLocal
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        status["database"] = "ok"
    except Exception as e:
        status["database"] = f"error: {str(e)}"
        status["status"] = "degraded"

    # Redis check via Upstash HTTP
    try:
        from upstash_redis import Redis
        r = Redis(
            url=os.environ.get("UPSTASH_REDIS_REST_URL", ""),
            token=os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
        )
        r.ping()
        status["redis"] = "ok"
    except Exception as e:
        status["redis"] = f"error: {str(e)}"
        status["status"] = "degraded"

    return status