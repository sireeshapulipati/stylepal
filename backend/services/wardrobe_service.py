import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.wardrobe import WardrobeItem, WearHistory
from schemas.wardrobe import WardrobeItemCreate, WardrobeItemUpdate


def _tags_to_json(tags: Optional[list[str]]) -> Optional[str]:
    if tags is None:
        return None
    return json.dumps(tags)


def _json_to_tags(s: Optional[str]) -> Optional[list[str]]:
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        return None


def list_items(
    db: Session,
    category: Optional[str] = None,
    occasion: Optional[str] = None,
    season: Optional[str] = None,
    include_deprecated: bool = False,
):
    """List wardrobe items with optional filters. Excludes deprecated by default."""
    q = db.query(WardrobeItem)
    if not include_deprecated:
        q = q.filter(WardrobeItem.deprecated_at.is_(None))
    if category:
        q = q.filter(WardrobeItem.category == category)
    if occasion:
        q = q.filter(WardrobeItem.occasion_tags.contains(occasion))
    if season:
        q = q.filter(WardrobeItem.season_tags.contains(season))
    return q.order_by(WardrobeItem.created_at.desc()).all()


def create_item(db: Session, data: WardrobeItemCreate) -> WardrobeItem:
    """Create a new wardrobe item. purchased_at is normalized to first of month by schema."""
    item = WardrobeItem(
        name=data.name,
        category=data.category,
        subcategory=data.subcategory,
        color=data.color,
        pattern=data.pattern,
        material=data.material,
        occasion_tags=_tags_to_json(data.occasion_tags),
        season_tags=_tags_to_json(data.season_tags),
        brand=data.brand,
        purchased_at=data.purchased_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def get_item(db: Session, item_id: int) -> WardrobeItem:
    """Get item by ID with wear history."""
    item = db.query(WardrobeItem).filter(WardrobeItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def update_item(db: Session, item_id: int, data: WardrobeItemUpdate) -> WardrobeItem:
    """Update a wardrobe item."""
    item = get_item(db, item_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        if k in ("occasion_tags", "season_tags"):
            setattr(item, k, _tags_to_json(v))
        else:
            setattr(item, k, v)
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item_id: int) -> None:
    """Hard delete a wardrobe item."""
    item = get_item(db, item_id)
    db.delete(item)
    db.commit()


def deprecate_item(db: Session, item_id: int) -> WardrobeItem:
    """Soft delete: set deprecated_at so item is excluded from suggestions."""
    item = get_item(db, item_id)
    item.deprecated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(item)
    return item


def undeprecate_item(db: Session, item_id: int) -> WardrobeItem:
    """Restore a deprecated item."""
    item = get_item(db, item_id)
    item.deprecated_at = None
    db.commit()
    db.refresh(item)
    return item


def get_rotation_stats(db: Session, item_ids: Optional[list[int]] = None) -> dict[int, dict]:
    """Compute last_worn_at, wear_count, wear_count_90d per item from WearHistory."""
    ninety_days_ago = datetime.now(timezone.utc) - timedelta(days=90)
    q = db.query(WearHistory.item_id, WearHistory.worn_at)
    if item_ids is not None:
        q = q.filter(WearHistory.item_id.in_(item_ids))
    rows = q.all()

    stats: dict[int, dict] = {}
    for item_id, worn_at in rows:
        if item_id not in stats:
            stats[item_id] = {"last_worn_at": None, "wear_count": 0, "wear_count_90d": 0}
        stats[item_id]["wear_count"] += 1
        if worn_at:
            if stats[item_id]["last_worn_at"] is None or worn_at > stats[item_id]["last_worn_at"]:
                stats[item_id]["last_worn_at"] = worn_at
            if worn_at >= ninety_days_ago:
                stats[item_id]["wear_count_90d"] += 1
    return stats


def record_outfit(
    db: Session,
    item_ids: list[int],
    occasion: str | None = None,
    worn_at: datetime | None = None,
) -> dict:
    """Record an outfit: create WearHistory entries and add to memory.
    worn_at: When the outfit was/will be worn. Defaults to now. Use for planned trips (e.g. last day of vacation)."""
    from services import memory
    from services.memory_store import sync_store_from_memory

    history = memory.get_outfit_history()
    outfit_id = len(history) + 1
    for item_id in item_ids:
        item = get_item(db, item_id)
        wear_kwargs = {"item_id": item_id, "occasion": occasion or "", "outfit_id": outfit_id}
        if worn_at is not None:
            wear_kwargs["worn_at"] = worn_at
        wear = WearHistory(**wear_kwargs)
        db.add(wear)
    db.commit()
    # Outfit history JSON write removed; WearHistory in DB is the source of truth
    record = {"outfit_id": outfit_id, "items": item_ids, "occasion": occasion}
    sync_store_from_memory()  # Sync episodic memory (episodes only)
    return record


def get_wear_history(db: Session) -> list:
    """Get wear frequency analytics with rotation stats."""
    items = db.query(WardrobeItem.id, WardrobeItem.name).all()
    stats = get_rotation_stats(db, [i.id for i in items])
    return [
        {
            "item_id": i.id,
            "name": i.name,
            "wear_count": stats.get(i.id, {}).get("wear_count", 0),
            "wear_count_90d": stats.get(i.id, {}).get("wear_count_90d", 0),
            "last_worn_at": stats.get(i.id, {}).get("last_worn_at"),
        }
        for i in items
    ]
