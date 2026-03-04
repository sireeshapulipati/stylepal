from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.database import get_db
from schemas.profile import OutfitCreate, ProfileResponse, ProfileUpdate
from services import memory
from services.memory_store import sync_store_from_memory
from services.wardrobe_service import record_outfit

router = APIRouter()


@router.get("/profile", response_model=ProfileResponse)
def get_profile():
    """Get user profile and preferences."""
    p = memory.get_profile()
    return ProfileResponse(**p)


@router.patch("/profile", response_model=ProfileResponse)
def update_profile(data: ProfileUpdate):
    """Update user preferences."""
    updates = data.model_dump(exclude_unset=True)
    p = memory.update_profile(updates)
    sync_store_from_memory()  # Sync semantic memory (profile)
    return ProfileResponse(**p)


@router.post("/outfits")
def create_outfit(data: OutfitCreate, db: Session = Depends(get_db)):
    """Record an outfit selection and link to wear history."""
    return record_outfit(db, data.items, data.occasion)
