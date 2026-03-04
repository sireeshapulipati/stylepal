from sqlalchemy import Column, Date, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from models.database import Base


class WardrobeItem(Base):
    __tablename__ = "wardrobe_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)  # top, bottom, outerwear, shoes, accessories
    subcategory = Column(String(100), nullable=True)
    color = Column(String(100), nullable=True)
    pattern = Column(String(100), nullable=True)
    material = Column(String(100), nullable=True)
    occasion_tags = Column(Text, nullable=True)  # JSON array as string
    season_tags = Column(Text, nullable=True)  # JSON array as string
    brand = Column(String(100), nullable=True)
    purchased_at = Column(Date, nullable=True)  # YYYY-MM-01 for month/year
    deprecated_at = Column(DateTime(timezone=True), nullable=True)  # Soft delete: set when user no longer wears
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    wear_history = relationship("WearHistory", back_populates="item")


class WearHistory(Base):
    __tablename__ = "wear_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("wardrobe_items.id"), nullable=False)
    worn_at = Column(DateTime(timezone=True), server_default=func.now())
    occasion = Column(String(100), nullable=True)
    outfit_id = Column(Integer, nullable=True)

    item = relationship("WardrobeItem", back_populates="wear_history")
