#!/usr/bin/env python3
"""
Load wardrobe_seed.csv into SQLite.
Run from project root: python -m backend.scripts.seed_wardrobe
Or from backend/: PYTHONPATH=. python scripts/seed_wardrobe.py
"""
import csv
import json
import os
import sys
from pathlib import Path

# Add backend to path when run from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from models.database import Base, SessionLocal, engine
from models.wardrobe import WardrobeItem

CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "wardrobe_seed.csv"


def parse_tags(s: str) -> list[str] | None:
    """Parse pipe-separated tags into list. Empty string returns None."""
    if not s or not s.strip():
        return None
    return [t.strip() for t in s.split("|") if t.strip()]


def load_csv() -> None:
    """Load CSV into wardrobe_items table. Clears existing items first to avoid duplicates."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Clear existing items (and wear_history) so re-running doesn't duplicate
        db.execute(text("DELETE FROM wear_history"))
        db.execute(text("DELETE FROM wardrobe_items"))
        db.commit()
        if not CSV_PATH.exists():
            print(f"Error: {CSV_PATH} not found")
            sys.exit(1)
        count = 0
        def parse_date(s: str):
            """Parse YYYY-MM or YYYY-MM-DD to date. Returns None if empty."""
            from datetime import date

            s = (s or "").strip()
            if not s:
                return None
            try:
                parts = s.split("-")
                if len(parts) >= 2:
                    y, m = int(parts[0]), int(parts[1])
                    return date(y, m, 1)
            except (ValueError, IndexError):
                pass
            return None

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                occ_tags = parse_tags(row.get("occasion_tags", ""))
                sea_tags = parse_tags(row.get("season_tags", ""))
                purchased = parse_date(row.get("purchased_at", ""))
                item = WardrobeItem(
                    name=row["name"].strip(),
                    category=row["category"].strip(),
                    subcategory=row["subcategory"].strip() or None,
                    color=row["color"].strip() or None,
                    pattern=row["pattern"].strip() or None,
                    material=row["material"].strip() or None,
                    occasion_tags=json.dumps(occ_tags) if occ_tags else None,
                    season_tags=json.dumps(sea_tags) if sea_tags else None,
                    brand=row.get("brand", "").strip() or None,
                    purchased_at=purchased,
                )
                db.add(item)
                count += 1
        db.commit()
        print(f"Loaded {count} items from {CSV_PATH}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    load_csv()
