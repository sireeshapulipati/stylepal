import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent
_project_root = _backend_dir.parent

# Load .env FIRST (before any app imports that need env vars)
from dotenv import load_dotenv
load_dotenv(_project_root / ".env", override=True)
load_dotenv(_backend_dir / ".env", override=True)

# Ensure backend is on path (for `uvicorn backend.main:app` from project root)
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import core.database  # noqa: F401 - triggers DB table creation
from routers import wardrobe, profile, stylist

app = FastAPI(
    title="Stylepal API",
    description="Wardrobe intelligence system for intentional professionals",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    import os
    from models.database import SessionLocal
    from services.wardrobe_service import list_items

    try:
        db = SessionLocal()
        count = len(list_items(db))
        db.close()
    except Exception:
        count = None
    return {
        "status": "ok",
        "env_loaded": bool(os.getenv("OPENAI_API_KEY")),
        "wardrobe_count": count,
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes"),
    }


app.include_router(wardrobe.router, prefix="/wardrobe", tags=["wardrobe"])
app.include_router(profile.router, prefix="", tags=["profile"])
app.include_router(stylist.router, prefix="/stylist", tags=["stylist"])
