from fastapi import APIRouter
from app.api.routes import auth, me, config, matches, rankings, users, history, analytics

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(me.router, prefix="/me", tags=["me"])
router.include_router(config.router, prefix="", tags=["config"])
router.include_router(matches.router, prefix="/matches", tags=["matches"])
router.include_router(rankings.router, prefix="/rankings", tags=["rankings"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(history.router, prefix="/history", tags=["history"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
