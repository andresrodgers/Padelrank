from fastapi import APIRouter
from app.api.routes import auth, me, config, matches, rankings

router = APIRouter()
router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(me.router, prefix="/me", tags=["me"])
router.include_router(config.router, prefix="", tags=["config"])
router.include_router(matches.router, prefix="/matches", tags=["matches"])
router.include_router(rankings.router, prefix="/rankings", tags=["rankings"])
