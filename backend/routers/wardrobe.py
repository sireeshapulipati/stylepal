from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from models.database import get_db
from schemas.wardrobe import (
    WardrobeItemCreate,
    WardrobeItemResponse,
    WardrobeItemUpdate,
    WearHistoryEntry,
)
from services import wardrobe_service as svc

router = APIRouter()


def _item_to_response(item, rotation: dict | None = None):
    """Convert WardrobeItem to response with parsed tags. rotation: {last_worn_at, wear_count, wear_count_90d}."""
    from services.wardrobe_service import _json_to_tags

    r = rotation or {}
    return WardrobeItemResponse(
        id=item.id,
        name=item.name,
        category=item.category,
        subcategory=item.subcategory,
        color=item.color,
        pattern=item.pattern,
        material=item.material,
        occasion_tags=_json_to_tags(item.occasion_tags),
        season_tags=_json_to_tags(item.season_tags),
        brand=item.brand,
        purchased_at=item.purchased_at,
        deprecated_at=getattr(item, "deprecated_at", None),
        created_at=item.created_at,
        last_worn_at=r.get("last_worn_at"),
        wear_count=r.get("wear_count", 0),
        wear_count_90d=r.get("wear_count_90d", 0),
    )


@router.get("/items", response_model=list[WardrobeItemResponse])
def list_items(
    category: Optional[str] = Query(None),
    occasion: Optional[str] = Query(None),
    season: Optional[str] = Query(None),
    include_deprecated: bool = Query(False, description="Include deprecated/removed items"),
    include_rotation: bool = Query(True, description="Include last_worn_at, wear_count, wear_count_90d"),
    db: Session = Depends(get_db),
):
    """List wardrobe items with optional filters. Deprecated items excluded by default."""
    items = svc.list_items(db, category=category, occasion=occasion, season=season, include_deprecated=include_deprecated)
    if include_rotation:
        stats = svc.get_rotation_stats(db, [i.id for i in items])
        return [_item_to_response(i, stats.get(i.id)) for i in items]
    return [_item_to_response(i) for i in items]


@router.post("/items", response_model=WardrobeItemResponse)
def create_item(data: WardrobeItemCreate, db: Session = Depends(get_db)):
    """Add a new wardrobe item."""
    item = svc.create_item(db, data)
    return _item_to_response(item)


@router.get("/items/{item_id}", response_model=WardrobeItemResponse)
def get_item(item_id: int, db: Session = Depends(get_db)):
    """Get item by ID with rotation stats."""
    item = svc.get_item(db, item_id)
    stats = svc.get_rotation_stats(db, [item_id])
    return _item_to_response(item, stats.get(item_id))


@router.get("/items/{item_id}/wear-history", response_model=list[WearHistoryEntry])
def get_item_wear_history(item_id: int, db: Session = Depends(get_db)):
    """Get wear history for an item."""
    item = svc.get_item(db, item_id)
    return [WearHistoryEntry.model_validate(h) for h in item.wear_history]


@router.patch("/items/{item_id}", response_model=WardrobeItemResponse)
def update_item(item_id: int, data: WardrobeItemUpdate, db: Session = Depends(get_db)):
    """Update a wardrobe item."""
    item = svc.update_item(db, item_id, data)
    return _item_to_response(item)


@router.post("/items/{item_id}/deprecate", response_model=WardrobeItemResponse)
def deprecate_item(item_id: int, db: Session = Depends(get_db)):
    """Soft delete: remove item from suggestions (can be restored)."""
    item = svc.deprecate_item(db, item_id)
    return _item_to_response(item)


@router.post("/items/{item_id}/undeprecate", response_model=WardrobeItemResponse)
def undeprecate_item(item_id: int, db: Session = Depends(get_db)):
    """Restore a deprecated item."""
    item = svc.undeprecate_item(db, item_id)
    return _item_to_response(item)


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    """Hard delete a wardrobe item (permanent)."""
    svc.delete_item(db, item_id)
    return {"ok": True}


@router.get("/wear-history")
def get_wear_history(db: Session = Depends(get_db)):
    """Get wear frequency analytics for all items."""
    return svc.get_wear_history(db)
