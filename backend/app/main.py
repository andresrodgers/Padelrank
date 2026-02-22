from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import settings
from app.api.router import router

app = FastAPI(
    title="Padel Ranking MVP (Neiva)",
    version="0.1.6",
)

allowed_hosts = [h.strip() for h in settings.ALLOWED_HOSTS.split(",") if h.strip()]
if not allowed_hosts:
    allowed_hosts = ["*"]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response: Response = await call_next(request)
    if settings.SECURITY_HEADERS_ENABLED:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'none'; base-uri 'self'"
        if settings.ENV != "dev":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(router)

@app.get("/health")
def health():
    return {"ok": True}
