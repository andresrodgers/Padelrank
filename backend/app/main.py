from fastapi import FastAPI
from app.api.router import router

app = FastAPI(
    title="Padel Ranking MVP (Neiva)",
    version="0.1.0",
)

app.include_router(router)

@app.get("/health")
def health():
    return {"ok": True}
