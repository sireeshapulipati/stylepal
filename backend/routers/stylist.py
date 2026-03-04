import os

from fastapi import APIRouter, HTTPException

from schemas.stylist import StylistPlanRequest, StylistPlanResponse
from services import agent

router = APIRouter()


@router.get("/trace-status")
def trace_status():
    """Return LangSmith tracing configuration status."""
    tracing = os.getenv("LANGSMITH_TRACING", "").lower() in ("true", "1", "yes")
    return {
        "tracing_enabled": tracing,
        "api_key_set": bool(os.getenv("LANGSMITH_API_KEY")),
        "project": os.getenv("LANGSMITH_PROJECT", "default"),
    }


@router.post("/plan", response_model=StylistPlanResponse)
def plan_outfit(data: StylistPlanRequest):
    """Generate an outfit plan from a query using the Stylist Agent."""
    try:
        result = agent.plan_outfit(
            query=data.query,
            constraints=data.constraints,
            location=data.location,
            thread_id=data.thread_id or "default",
        )
        return StylistPlanResponse(**result)
    except Exception as e:
        err_msg = str(e)
        if "API key" in err_msg or "GEMINI" in err_msg.upper() or "OPENAI" in err_msg.upper():
            raise HTTPException(
                status_code=503,
                detail=f"Stylist service unavailable: {err_msg}",
            )
        raise HTTPException(status_code=500, detail=err_msg)
