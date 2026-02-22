from fastapi import APIRouter
from app.api.routes import analytics, auth, billing, config, entitlements, history, matches, me, rankings, support, users

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(me.router, prefix="/me", tags=["me"])
router.include_router(config.router, prefix="", tags=["config"])
router.include_router(matches.router, prefix="/matches", tags=["matches"])
router.include_router(rankings.router, prefix="/rankings", tags=["rankings"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(history.router, prefix="/history", tags=["history"])
router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
router.include_router(entitlements.router, prefix="/entitlements", tags=["entitlements"])
router.include_router(support.router, prefix="/support", tags=["support"])
router.include_router(billing.router, prefix="/billing", tags=["billing"])
