from typing import Optional

from pydantic import BaseModel


class StylistPlanRequest(BaseModel):
    query: str
    constraints: Optional[list[str]] = None
    location: Optional[str] = None
    thread_id: Optional[str] = None  # For checkpointing (conversation memory)


class StylistPlanResponse(BaseModel):
    outfit_plan: dict
    reasoning: str
    is_informational: Optional[bool] = False  # True when answering style questions, not outfit suggestions
