from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import ROOT

app = FastAPI()


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


dist = ROOT / "frontend" / "dist"
if dist.exists():
    app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
