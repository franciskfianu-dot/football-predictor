from fastapi import APIRouter
from app.api.v1.endpoints import predictions, matches, leagues, models, admin, sheets

router = APIRouter()
router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])
router.include_router(matches.router,     prefix="/matches",     tags=["matches"])
router.include_router(leagues.router,     prefix="/leagues",     tags=["leagues"])
router.include_router(models.router,      prefix="/models",      tags=["models"])
router.include_router(admin.router,       prefix="/admin",       tags=["admin"])
router.include_router(sheets.router,      prefix="/sheets",      tags=["sheets"])
