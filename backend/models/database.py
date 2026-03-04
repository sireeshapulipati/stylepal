from pathlib import Path
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Resolve to absolute path so seed script and backend always use the same DB regardless of CWD
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_DB = _PROJECT_ROOT / "stylepal.db"

_raw_url = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB}")
if "sqlite" in _raw_url and "///" in _raw_url:
    # sqlite:///./stylepal.db or sqlite:///path -> resolve to absolute
    db_path = _raw_url.replace("sqlite:///", "").replace("sqlite://", "")
    if db_path.startswith("./") or db_path.startswith(".\\"):
        db_path = (_PROJECT_ROOT / db_path[2:]).resolve()
    elif not Path(db_path).is_absolute():
        db_path = (_PROJECT_ROOT / db_path).resolve()
    else:
        db_path = Path(db_path).resolve()
    DATABASE_URL = f"sqlite:///{db_path}"
else:
    DATABASE_URL = _raw_url

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
