#!/usr/bin/env python3
"""
Add brand and purchased_at columns to wardrobe_items.
Run from project root: python -m backend.scripts.migrate_add_brand_purchased
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from models.database import SessionLocal, engine


def migrate():
    db = SessionLocal()
    try:
        # Check if columns exist (SQLite)
        r = db.execute(text("PRAGMA table_info(wardrobe_items)"))
        cols = {row[1] for row in r.fetchall()}
        if "brand" not in cols:
            db.execute(text("ALTER TABLE wardrobe_items ADD COLUMN brand VARCHAR(100)"))
            print("Added column: brand")
        if "purchased_at" not in cols:
            db.execute(text("ALTER TABLE wardrobe_items ADD COLUMN purchased_at DATE"))
            print("Added column: purchased_at")
        db.commit()
        print("Migration complete.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate()
