from typing import Any, Optional

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    name: str = "Maya"
    gender: Optional[str] = None
    age: Optional[int] = None
    body_type: Optional[str] = None
    location: str = "San Francisco"
    silhouette_preferences: list = []
    comfort_thresholds: dict = {}
    rotation_patterns: dict = {}


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = Field(None, ge=1, le=120)
    body_type: Optional[str] = None
    location: Optional[str] = None
    silhouette_preferences: Optional[list] = None
    comfort_thresholds: Optional[dict] = None
    rotation_patterns: Optional[dict] = None


class OutfitCreate(BaseModel):
    items: list[int]  # item IDs
    occasion: Optional[str] = None
