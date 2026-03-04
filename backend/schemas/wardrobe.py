from datetime import date, datetime
from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator

from utils.date_parse import normalize_purchased_at


class WardrobeItemCreate(BaseModel):
    name: str
    category: str  # top, bottom, outerwear, shoes, accessories
    subcategory: Optional[str] = None
    color: Optional[str] = None
    pattern: Optional[str] = None
    material: Optional[str] = None
    occasion_tags: Optional[list[str]] = None
    season_tags: Optional[list[str]] = None
    brand: Optional[str] = None
    purchased_at: Optional[date] = None  # Always stored as YYYY-MM-01 (first of month)

    @field_validator("purchased_at", mode="before")
    @classmethod
    def parse_and_normalize_purchased_at(cls, v: Optional[Union[str, date]]) -> Optional[date]:
        return normalize_purchased_at(v)


class WardrobeItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    color: Optional[str] = None
    pattern: Optional[str] = None
    material: Optional[str] = None
    occasion_tags: Optional[list[str]] = None
    season_tags: Optional[list[str]] = None
    brand: Optional[str] = None
    purchased_at: Optional[date] = None

    @field_validator("purchased_at", mode="before")
    @classmethod
    def parse_and_normalize_purchased_at(cls, v: Optional[Union[str, date]]) -> Optional[date]:
        return normalize_purchased_at(v)


class WardrobeItemResponse(BaseModel):
    id: int
    name: str
    category: str
    subcategory: Optional[str] = None
    color: Optional[str] = None
    pattern: Optional[str] = None
    material: Optional[str] = None
    occasion_tags: Optional[list[str]] = None
    season_tags: Optional[list[str]] = None
    brand: Optional[str] = None
    purchased_at: Optional[date] = None
    deprecated_at: Optional[datetime] = None
    created_at: datetime
    last_worn_at: Optional[datetime] = None
    wear_count: int = 0
    wear_count_90d: int = 0

    class Config:
        from_attributes = True


class WearHistoryEntry(BaseModel):
    id: int
    item_id: int
    worn_at: datetime
    occasion: Optional[str] = None
    outfit_id: Optional[int] = None

    class Config:
        from_attributes = True
