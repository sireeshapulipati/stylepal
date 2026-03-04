"""Stylist Agent - LangGraph RAG + memory (06_Agent_Memory + 10_Evaluating_RAG patterns).

Uses tools for flexible access: RAG (retrieve_style_knowledge), wardrobe, and weather.
The LLM decides when to call each tool based on the user's request.
"""
import os
import re
from typing import Annotated, List, Literal, Optional, TypedDict

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.store.base import BaseStore
from sqlalchemy.orm import Session

from services import memory, rag, weather
from services.memory_store import (
    get_episodic_examples,
    get_instructions,
    get_profile_context,
    get_stylist_store,
    sync_store_from_memory,
)

# Feedback detection
THUMBS_UP_PATTERNS = ("thumbs up", "👍", "yes", "yeah", "yep", "sounds good", "going with it", "love it")
THUMBS_DOWN_PATTERNS = ("thumbs down", "👎", "no", "nope", "try again")

# RAG + memory prompt (outfit suggestions)
RAG_PROMPT_TEMPLATE = """{procedural_instructions}

### Your Wardrobe (ONLY suggest items from this list - every piece MUST use [id=X])
{wardrobe_context}

### User Profile & Preferences
{profile_context}
{weather_context}

### Style Knowledge (from RAG)
{context}

### Past Successful Outfits (learn from these)
{episodic_examples}

### Conversation
{chat_history}

### Current Request
{question}

DECISION: Choose one of these responses based on the request:

1. ASK CLARIFYING QUESTIONS - If the request is vague (trip, conference, multi-day), ask 1-3 short questions first. Do NOT suggest outfits yet. Clarify: location/destination, exact dates, event types (formal dinner vs casual pub vs sightseeing vs business meeting, day vs evening), dress codes. Examples: "Is it a formal dinner or casual gathering?", "Business or social events?", "Any evening events?" Output your questions directly (no OUTFIT format).

2. PROVIDE OUTFITS - If you have enough info to suggest:
   - Single-day/single event: Give OUTFIT 1 and OUTFIT 2 (two options to choose from).
   - Multi-day trip: One primary outfit per day/occasion (Day 1 travel, Day 2 business, Day 2 evening, etc.). Do NOT give 2 options per slot. Optionally add "Also consider packing: [1-3 items]" for flexibility. Cover the full trip.

When providing outfits, use this format. Every piece MUST include [id=X] from the wardrobe. List as [id=X] Item name only—no per-item tips. Same item used twice = same line, no varying descriptions.

OUTFIT 1:
- [id=X] Item name
- [id=X] Item name
OUTFIT 2:
- [id=X] Item name
- [id=X] Item name

REASONING:
[Summary. If weather was checked, include the actual forecast (e.g. "Tomorrow in NYC: 45°F, rain").]

Use plain text only—no Markdown (no ** or * for bold)."""

# Informational prompt (style questions, no outfit suggestions)
INFO_PROMPT_TEMPLATE = """{procedural_instructions}

### User Profile & Preferences
{profile_context}

### Style Knowledge (from RAG)
{context}

### Conversation
{chat_history}

### Current Request
{question}

The user is asking a question about styling principles, not requesting outfit suggestions. Answer directly and concisely using the style knowledge above. Do NOT suggest outfit options. Just provide the educational answer (e.g. which necklines/waistlines work, what colors pair well, how to dress for body type). Be specific and reference the style knowledge when relevant.

Use plain text only. Do not use Markdown (no asterisks for bold, no ** or *)."""

RAG_PROMPT = ChatPromptTemplate.from_template(RAG_PROMPT_TEMPLATE)
INFO_PROMPT = ChatPromptTemplate.from_template(INFO_PROMPT_TEMPLATE)

FEEDBACK_SUFFIX = """

---
**Which one?** Reply with "Pick Option 1" or "Pick Option 2"."""

INTENT_CLASSIFY_PROMPT = """Classify the user's intent. Reply with exactly one word: OUTFIT_REQUEST, INFORMATIONAL, or PROFILE_UPDATE.

OUTFIT_REQUEST: The user wants specific outfit suggestions from their wardrobe—what to wear, what to put together, outfit for an occasion, etc.
INFORMATIONAL: The user is asking about style principles, body types, colors, fit, or general how-to—not requesting a specific outfit.
PROFILE_UPDATE: The user is sharing personal info to store: name, body type, location, age, gender, or style preferences (e.g. "I prefer tailored fits", "I'm 35 and pear-shaped", "I moved to NYC").

User question: {question}"""

# Heuristic patterns that strongly suggest profile update intent (avoid LLM call for fast path)
PROFILE_UPDATE_PATTERNS = (
    "i prefer", "i'm ", "i am ", "my body type", "my name is", "i moved to",
    "i'm moving to", "i live in", "i'm from", "i'm in my", "years old", "pear-shaped",
    "hourglass", "apple-shaped", "rectangle", "inverted triangle", "tailored fits",
    "fitted", "loose fits", "relaxed fit", "silhouette", "my location", "my age",
)

# Heuristic patterns for outfit requests (what to wear, what to pack, etc.)
OUTFIT_REQUEST_PATTERNS = (
    "what should i wear", "what to wear", "what to pack", "outfit for",
    "suggest an outfit", "wear for", "pack for", "put together",
    "help me dress", "what can i wear", "pick an outfit",
)


# --- Tools (LLM decides when to use each) ---


def _get_wardrobe_context_impl(db: Optional[Session] = None) -> tuple[str, list]:
    """Build wardrobe context for the prompt. Returns (context_string, items_list)."""
    from models.database import SessionLocal
    from services.wardrobe_service import list_items

    session = db
    if session is None:
        session = SessionLocal()
        try:
            items = list_items(session)
        finally:
            session.close()
    else:
        items = list_items(session)
    if not items:
        return ("(Wardrobe is empty.)", [])
    lines = []
    for i in items[:80]:
        extra = []
        if getattr(i, "brand", None):
            extra.append(i.brand)
        if getattr(i, "purchased_at", None):
            extra.append(str(i.purchased_at)[:7])  # YYYY-MM
        suffix = f" [{', '.join(extra)}]" if extra else ""
        lines.append(f"- id={i.id}: {i.name}{suffix} ({i.category}, {i.color or 'any'})")
    return ("\n".join(lines), items)


OUTFIT_PRINCIPLES_PROMPT = """Given this style knowledge:

{context}

The user is planning an outfit for: {question}

Return ONLY brief styling principles for this occasion (e.g. tailored, neutral colors, professional, closed-toe shoes, weather-appropriate). 1-2 sentences. Do NOT suggest specific garments—the agent will match from the wardrobe."""


def _synthesize_style_answer(query: str, context: str, for_outfit: bool = False) -> str:
    """Use INFO_PROMPT (or OUTFIT_PRINCIPLES for outfit requests) to generate from RAG context."""
    if for_outfit:
        prompt = OUTFIT_PRINCIPLES_PROMPT.format(context=context, question=query)
    else:
        profile = memory.get_profile()
        profile_context = ""
        if profile:
            parts = []
            for k, v in profile.items():
                if v and k not in ("created_at", "updated_at"):
                    parts.append(f"{k}: {v}")
            profile_context = "\n".join(parts) if parts else "(No profile yet)"
        prompt = INFO_PROMPT_TEMPLATE.format(
            procedural_instructions="You are Stylepal. Answer style questions using the knowledge base. Be concise and specific.",
            profile_context=profile_context or "(None)",
            context=context,
            chat_history="(Current turn only)",
            question=query,
        )
    try:
        # Use gpt-4o-mini for synthesis—faster, especially for outfit principles
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
            timeout=30,
            max_retries=2,
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        out = (resp.content or "").strip()
        return out if out else context[:500]
    except Exception:
        return context[:500]  # fallback to truncated context on error


@tool
def retrieve_style_knowledge(query: str, for_outfit: bool = False) -> str:
    """Retrieve style knowledge from the knowledge base. Call once per question (don't repeat). For outfit requests, also call get_wardrobe—you need both results.
    Use for: (1) Style questions (body types, necklines, colors, fit)—answer directly. (2) Outfit requests—use WITH get_wardrobe. Pass for_outfit=True when the user wants outfit suggestions; this returns brief principles only. You MUST also call get_wardrobe to get actual items with [id=X]. For personalized queries, include body type in the query (e.g. "neckline hourglass")."""
    docs = rag.retrieve_as_documents(query, top_k=5)
    if not docs:
        return "(No style knowledge found. Use general styling principles.)"
    context = "\n\n".join(doc.page_content for doc in docs)
    return _synthesize_style_answer(query, context, for_outfit=for_outfit)


@tool
def get_wardrobe() -> str:
    """Fetch the user's wardrobe items. Use when the user wants outfit suggestions—you MUST have wardrobe data to suggest specific pieces with [id=X]. Do NOT suggest outfits without calling this first."""

    context, items = _get_wardrobe_context_impl()
    if not items:
        return (
            "The wardrobe is empty. Tell the user to add items first (via the Wardrobe page or seed script) before suggesting outfits."
        )
    return context


@tool
def update_last_worn(item_ids: list[int], occasion: str, last_worn_date: str) -> str:
    """Update last worn for wardrobe items. Call when the user confirms an outfit (pick option 1/2 or thumbs up).
    last_worn_date: Date when the outfit will be worn, YYYY-MM-DD. For trips, use the LAST day of the trip (e.g. vacation July 15-20 → use 2025-07-20). For single-day, use that day's date. For today/tomorrow, use the actual date."""
    from datetime import datetime, timezone
    from models.database import SessionLocal
    from services.wardrobe_service import record_outfit

    try:
        dt = datetime.strptime(last_worn_date.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return f"Invalid date format. Use YYYY-MM-DD (e.g. 2025-07-20). Got: {last_worn_date}"
    if not item_ids:
        return "No item IDs provided. Cannot update last worn."
    db = SessionLocal()
    try:
        record_outfit(db, item_ids, occasion=occasion or "outfit", worn_at=dt)
        return f"Updated last worn for {len(item_ids)} item(s) to {last_worn_date}."
    finally:
        db.close()


@tool
def update_profile(
    name: str | None = None,
    body_type: str | None = None,
    location: str | None = None,
    age: int | None = None,
    gender: str | None = None,
    silhouette_preferences: str | None = None,
) -> str:
    """Update user profile. Call when the user shares new info: name, body type, location, age, gender, or style preferences.
    silhouette_preferences: comma-separated (e.g. 'tailored, fitted, belted').
    Only pass fields the user explicitly mentioned."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if body_type is not None:
        updates["body_type"] = body_type
    if location is not None:
        updates["location"] = location
    if age is not None:
        updates["age"] = age
    if gender is not None:
        updates["gender"] = gender
    if silhouette_preferences is not None:
        updates["silhouette_preferences"] = [p.strip() for p in silhouette_preferences.split(",") if p.strip()]
    if not updates:
        return "No profile updates provided."
    memory.update_profile(updates)
    sync_store_from_memory()
    return f"Updated profile: {', '.join(updates.keys())}."


@tool
def add_wardrobe_item(
    name: str,
    category: str,
    subcategory: str | None = None,
    color: str | None = None,
    pattern: str | None = None,
    material: str | None = None,
    occasion_tags: str | None = None,
    season_tags: str | None = None,
    brand: str | None = None,
    purchased_at: str | None = None,
) -> str:
    """Add a new item to the user's wardrobe. When the user provides name + category (or inferrable category, e.g. blazer→outerwear, sneakers→shoes), add immediately with what they gave. Only ask follow-up questions when truly minimal (e.g. "I bought something" with no details). Do NOT ask when they clearly state the item (e.g. "I bought a navy blazer" has name, category, color—add it).
    category: one of top, bottom, outerwear, shoes, accessories.
    purchased_at: flexible format—pass the user's words as-is. Accepts: YYYY-MM, March 2024, last month, 3/2024, 2023, etc. We extract month and year.
    occasion_tags: comma-separated (e.g. 'casual, work').
    season_tags: comma-separated (e.g. 'spring, summer')."""
    from models.database import SessionLocal
    from schemas.wardrobe import WardrobeItemCreate
    from services.wardrobe_service import create_item

    cat = category.strip().lower()
    if cat not in ("top", "bottom", "outerwear", "shoes", "accessories"):
        return f"Invalid category. Use one of: top, bottom, outerwear, shoes, accessories. Got: {category}"
    from utils.date_parse import parse_purchased_at

    purchased_date = parse_purchased_at(purchased_at)
    data = WardrobeItemCreate(
        name=name.strip(),
        category=cat,
        subcategory=subcategory.strip() if subcategory else None,
        color=color.strip() if color else None,
        pattern=pattern.strip() if pattern else None,
        material=material.strip() if material else None,
        occasion_tags=[t.strip() for t in occasion_tags.split(",")] if occasion_tags else None,
        season_tags=[t.strip() for t in season_tags.split(",")] if season_tags else None,
        brand=brand.strip() if brand else None,
        purchased_at=purchased_date,
    )
    db = SessionLocal()
    try:
        item = create_item(db, data)
        return f"Added: {item.name} (id={item.id}, {item.category})."
    finally:
        db.close()


@tool
def deprecate_wardrobe_item(item_id: int) -> str:
    """Remove an item from suggestions (soft delete). Call ONLY when the user has confirmed a specific item id. When the user describes an item in words (e.g. "Ralph Lauren stripe dress"), do NOT guess the id. Instead: (1) call get_wardrobe to retrieve the list, (2) show matching items with their ids to the user, (3) ask them to confirm which one to remove (e.g. "I found: id=12 Ralph Lauren stripe dress. Is that the one?"), (4) only when they confirm the id, call this tool."""
    from fastapi import HTTPException
    from models.database import SessionLocal
    from services.wardrobe_service import deprecate_item

    db = SessionLocal()
    try:
        item = deprecate_item(db, item_id)
        return f"Removed '{item.name}' from your active wardrobe. It won't appear in suggestions anymore."
    except HTTPException as e:
        if e.status_code == 404:
            return f"Item {item_id} not found."
        raise
    finally:
        db.close()


@tool
def get_weather(question: str, location: str | None = None) -> str:
    """Get weather forecast for outfit planning. Use when the request mentions: tomorrow, today, this week, outdoor, rain, cold, hot, warm, etc.
    location: City or place the user mentioned (e.g. 'Paris', 'London'). Use the city from their message when they specify one; otherwise use profile location. If multiple cities match (e.g. London UK vs London Canada), the tool returns options—ask the user to clarify which one."""
    loc = (location or "").strip() or memory.get_profile().get("location", "San Francisco")
    ctx = weather.get_weather_context(loc, question)
    return ctx if ctx else "Weather not needed for this request."


STYLIST_TOOLS = [
    get_wardrobe,  # First—required for outfit suggestions
    retrieve_style_knowledge,
    get_weather,
    update_last_worn,
    update_profile,
    add_wardrobe_item,
    deprecate_wardrobe_item,
]

AGENT_SYSTEM_PROMPT = """You are Stylepal, a trusted style companion with access to a style knowledge base.

Your role is to:
1. Answer questions about style principles, body types, necklines, colors, fit, and occasion dressing
2. ALWAYS call retrieve_style_knowledge when the user asks style-related questions (call it once per question, then answer)
3. The retrieve_style_knowledge tool returns a synthesized answer—use it directly or add a brief intro. Do NOT call it again or re-paraphrase at length
4. For outfit requests (user wants suggestions from their wardrobe—what to wear, what to pack, outfit for an occasion, etc.): call get_wardrobe (required) and retrieve_style_knowledge (for principles). Use wardrobe items with [id=X]. For style/fashion questions (principles, body types, colors, how-to): use retrieve_style_knowledge—RAG responses are correct.
5. If the knowledge base returns nothing relevant, say so honestly

Remember: The retrieve_style_knowledge tool returns a ready-to-use synthesized answer. Use it directly.

WHEN TO STOP: For outfit requests: call get_wardrobe AND retrieve_style_knowledge (and get_weather if needed) in the same turn. Answer only after you have BOTH results. For style questions: call retrieve_style_knowledge once, then answer. You may call multiple different tools in one turn.

1. **retrieve_style_knowledge(query, for_outfit?)** - For style questions: use default. For outfit requests: pass for_outfit=True. Call once per question (don't repeat). For outfit requests, also call get_wardrobe—you need both.

2. **get_wardrobe()** - REQUIRED when the user wants outfit suggestions from their wardrobe. Call this—you cannot suggest specific pieces without it. Returns items with [id=X]. Every piece in OUTFIT 1/OUTFIT 2 MUST use [id=X] from this list. If wardrobe is empty, tell the user to add items.

3. **get_weather(question, location?)** - Use when the request mentions weather, tomorrow, today, outdoor, rain, cold, hot, etc. Pass the city/place the user mentioned. If they don't specify, omit location to use their profile. If you use the weather result, cite it in REASONING (e.g. "Tomorrow in NYC: 45°F, rain—chose sneakers for wet conditions").

4. **update_last_worn(item_ids, occasion, last_worn_date)** - Use when the user confirms an outfit (pick option 1/2, thumbs up). Record that those items will be worn. last_worn_date: YYYY-MM-DD. For trips, use the LAST day of the trip. You MUST call this when the user picks an option or thumbs up. After calling, respond with a brief confirmation only (e.g. "Great choice. Will update your wear history.")—no styling advice.

5. **update_profile(...)** - Use when the user shares profile info: name, body type, location, age, gender, or style preferences (e.g. "I prefer tailored fits", "I'm in NYC now").

6. **add_wardrobe_item(name, category, ...)** - Use when the user says they bought something. If they give name + category (or inferrable: blazer→outerwear, sneakers→shoes), add immediately. Only ask when truly minimal ("I bought something"). category: top, bottom, outerwear, shoes, accessories.

7. **deprecate_wardrobe_item(item_id)** - Use ONLY when the user has confirmed a specific item id. When they describe an item in words (e.g. "Ralph Lauren stripe dress"), call get_wardrobe first, show matching items with ids, ask them to confirm which one, then call this tool with the confirmed id.

CRITICAL:
- For style questions (principles, body types, colors, fit, how-to): Call retrieve_style_knowledge once. Use the RAG response directly—that is the correct answer.
- For outfit requests (user wants suggestions from their wardrobe): Call get_wardrobe AND retrieve_style_knowledge(query, for_outfit=True) (and get_weather if needed). Every suggested piece MUST have [id=X] from the wardrobe. If you did not call get_wardrobe or the wardrobe is empty, say so—do NOT suggest generic items like "a blazer" or "tailored suit".
- Once you have the tool results you need (e.g. get_wardrobe + retrieve_style_knowledge for outfits), respond—do not start another tool round.

DECISION RULES:
- For profile updates: Call ONLY update_profile.
- For style questions (principles, body types, colors, fit, occasion dressing how-to): retrieve_style_knowledge once → use the RAG response. Never call it twice.
- For outfit requests: Call get_wardrobe AND retrieve_style_knowledge(query, for_outfit=True) (and get_weather if tomorrow/today). Call all needed tools in one turn—you may call multiple tools. Response must use OUTFIT 1/OUTFIT 2 format with [id=X] for every piece.
- You may call multiple tools in one turn if needed.
- For clearly specified single-event requests (e.g. "job interview tomorrow", "casual Friday at the office", "dinner date Saturday"): Do NOT ask clarifying questions—proceed directly to outfit suggestions.
- For vague multi-day/trip requests: Ask clarifying questions BEFORE suggesting outfits. Do NOT suggest until you have enough detail. Ask about: location/destination, exact dates, types of events (formal dinner vs casual pub vs sightseeing vs business meeting vs conference, day vs evening), dress codes. Examples: "Is it a formal dinner or casual gathering?", "Business meetings or social events?", "Any evening events?", "Sightseeing, conferences, or mix?"
- When the user picks an option or thumbs up, call update_last_worn with the picked option's item_ids, occasion, and planned_end_date (or today's date if single-day).

OUTFIT FORMAT (when suggesting from the user's wardrobe):
- List items as [id=X] Item name only—no per-item descriptions or tips. Same item = same line (do not repeat with different text).
- SINGLE EVENT: Give OUTFIT 1 and OUTFIT 2 (two options to choose from).
- MULTI-DAY TRIP: One primary outfit per day/occasion. Do NOT give 2 options for each slot. Structure: Day 1 (travel), Day 2 (business), etc. Include PLANNED_END_DATE: YYYY-MM-DD. Optionally add "Also consider packing: [1-3 extra items]".
- REASONING: Summarize why these outfits work. If you called get_weather, include the actual forecast (e.g. "Tomorrow in NYC: 45°F, rain—sneakers for wet conditions").

Example (single event):
OUTFIT 1:
- [id=3] Navy blazer
- [id=7] White blouse
- [id=12] Black trousers
- [id=15] Black pumps
OUTFIT 2:
- [id=5] Grey suit jacket
- [id=8] Light blue shirt
- [id=13] Charcoal trousers
- [id=15] Black pumps
REASONING: [Summary—include weather forecast if get_weather was used]

Use plain text only—no Markdown."""


class StylistState(TypedDict):
    """State with messages for checkpointing (thread-based)."""
    messages: Annotated[list[BaseMessage], add_messages]
    context: List[Document]
    response: str
    last_outfit: Optional[dict]  # {options: [{description, item_ids}], occasion} or {description, item_ids, occasion}


def _classify_intent(question: str, llm) -> bool:
    """Use LLM to classify: True = outfit request, False = informational."""
    if not (question or "").strip():
        return False
    prompt = INTENT_CLASSIFY_PROMPT.format(question=question.strip())
    try:
        resp = llm.invoke([HumanMessage(content=prompt)])
        text = (resp.content or "").strip().upper()
        return "OUTFIT_REQUEST" in text
    except Exception:
        return False


MAX_TOOL_CALL_ROUNDS = 8  # Cap agent->tools cycles per turn; style questions need 1 RAG call then answer


def _ensure_tool_responses(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Fix orphaned AIMessage with tool_calls (e.g. from interrupted checkpoint).

    OpenAI requires every tool_call_id to have a matching ToolMessage.
    If any are missing, add placeholder ToolMessages so the API accepts the request.
    """
    result: list[BaseMessage] = []
    for i, msg in enumerate(messages):
        result.append(msg)
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            tc_ids = set()
            for tc in msg.tool_calls:
                tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tid:
                    tc_ids.add(tid)
            if not tc_ids:
                continue
            # Collect tool_call_ids that have responses in following messages
            responded = set()
            for j in range(i + 1, len(messages)):
                m = messages[j]
                if isinstance(m, ToolMessage) and getattr(m, "tool_call_id", None):
                    responded.add(m.tool_call_id)
                elif isinstance(m, AIMessage):
                    break  # Next AI turn; stop looking
            for tid in tc_ids:
                if tid not in responded:
                    result.append(
                        ToolMessage(
                            content="Error: tool execution was interrupted or timed out.",
                            tool_call_id=tid,
                        )
                    )
    return result


def _should_continue_agent(state: dict) -> Literal["tools", "__end__"]:
    """Route: if last AIMessage has tool_calls and under limit, go to tools; else end."""
    messages = state.get("messages", [])
    if not messages:
        return "__end__"
    last = messages[-1]
    if not (isinstance(last, AIMessage) and last.tool_calls):
        return "__end__"
    # Count tool rounds only since last HumanMessage (current turn); ignore prior turns
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HumanMessage):
            last_human_idx = i
            break
    tool_call_rounds = sum(
        1
        for m in messages[last_human_idx + 1 :]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
    )
    if tool_call_rounds >= MAX_TOOL_CALL_ROUNDS:
        return "__end__"  # Stop before executing more tools
    return "tools"


def agent(state: StylistState, *, store: BaseStore, config: RunnableConfig | None = None) -> dict:
    """Agent node: invoke LLM with tools. LLM decides when to call retrieve_style_knowledge, get_wardrobe, get_weather."""
    is_eval = (config or {}).get("metadata", {}).get("eval", False)
    llm_timeout = 60 if is_eval else 120
    llm_max_retries = 2 if is_eval else 3
    llm = ChatOpenAI(
        model="gpt-4o",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=llm_timeout,
        max_retries=llm_max_retries,
    )
    messages = state.get("messages", [])
    question = ""
    last_human_content = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            last_human_content = (m.content or "").strip().lower()
            if not question:
                question = m.content if hasattr(m, "content") else str(m)
            break
    last_outfit = state.get("last_outfit") or {}
    is_pick_or_thumbs = (
        any(p in last_human_content for p in PICK_OPTION_PATTERNS)
        or any(p in last_human_content for p in THUMBS_UP_PATTERNS)
    )
    looks_like_profile_update = (
        any(p in last_human_content for p in PROFILE_UPDATE_PATTERNS)
        and not is_pick_or_thumbs
    )
    # Check if update_profile was already called for this turn (avoid loop)
    update_profile_already_called = False
    if looks_like_profile_update and messages:
        last_human_idx = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], HumanMessage)), -1)
        for m in messages[last_human_idx + 1 :]:
            if isinstance(m, ToolMessage) and (m.content or "").lower().startswith("updated profile"):
                update_profile_already_called = True
                break
    # For profile updates: require tool only on FIRST call; after that allow text-only confirmation
    if looks_like_profile_update:
        if update_profile_already_called:
            llm_with_tools = llm.bind_tools([update_profile], tool_choice="none")  # Force text response
        else:
            llm_with_tools = llm.bind_tools([update_profile], tool_choice="required")
    else:
        q_lower = (question or "").strip().lower()
        is_outfit_request = any(p in q_lower for p in OUTFIT_REQUEST_PATTERNS)
        llm_with_tools = llm.bind_tools(
            STYLIST_TOOLS,
            tool_choice="required" if is_outfit_request else "any",
        )

    profile_context = get_profile_context(store)
    instructions, _ = get_instructions(store)
    episodic_examples = "" if is_eval else (get_episodic_examples(store, question, limit=10, limit_avoid=5) if question else "")

    profile_update_instructions = ""
    if looks_like_profile_update:
        if update_profile_already_called:
            profile_update_instructions = """

### Profile already updated
You have already called update_profile. Respond with ONLY a brief confirmation (e.g. "Got it, I've updated your profile."). Do NOT call any tools again."""
        else:
            profile_update_instructions = """

### ACTION REQUIRED: Profile update only
The user is ONLY sharing personal info to store—NOT asking for outfit suggestions or style advice.
- You MUST call update_profile with the extracted fields. Do NOT respond with text only.
- Do NOT call get_wardrobe, retrieve_style_knowledge, or get_weather. This is a profile update, not an outfit request.
- Extract values: "I'm moving to X" / "I moved to X" → location; "I prefer tailored fits" → silhouette_preferences="tailored"; "pear-shaped" / "I'm hourglass" → body_type; "I'm 35" / "35 years old" → age; "My name is Maya" → name; "I live in NYC" → location.
- Call update_profile ONCE, then you will get a confirmation—do not call it again."""

    outfit_request_instructions = ""
    q_lower = (question or "").strip().lower()
    if any(p in q_lower for p in OUTFIT_REQUEST_PATTERNS) and not looks_like_profile_update:
        outfit_request_instructions = """

### OUTFIT REQUEST: You MUST call get_wardrobe and retrieve_style_knowledge
- Call get_wardrobe FIRST. Then retrieve_style_knowledge(query, for_outfit=True). Call get_weather if they mention tomorrow/today.
- Do NOT respond with generic advice (e.g. "wear a tailored suit"). Your response MUST be OUTFIT 1 and OUTFIT 2 with [id=X] for every piece from the wardrobe.
- If wardrobe is empty, say so—do NOT suggest generic items.
- List items as [id=X] Item name only—no per-item descriptions. Same item = same line in both options.
- If you called get_weather, REASONING must cite the actual forecast (e.g. "Tomorrow in NYC: 45°F, rain")."""

    pick_instructions = ""
    if is_pick_or_thumbs and last_outfit:
        options = last_outfit.get("options")
        occasion = last_outfit.get("occasion", "")
        planned_end = last_outfit.get("planned_end_date")
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        occ_lower = (occasion or "").lower()
        # Infer date from occasion: "tomorrow" → tomorrow, "today" → today. For trips use planned_end. Else today.
        if "tomorrow" in occ_lower:
            planned_end_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in occ_lower:
            planned_end_date = now.strftime("%Y-%m-%d")
        elif planned_end:
            planned_end_date = planned_end  # multi-day trip: use parsed PLANNED_END_DATE
        else:
            planned_end_date = now.strftime("%Y-%m-%d")
        if options:
            ix = _get_picked_option_index(last_human_content)
            opt = options[min(ix, len(options) - 1)]
            item_ids = opt.get("items") or []
            if item_ids:
                pick_instructions = f"""

### ACTION REQUIRED: User just confirmed an outfit
Call update_last_worn with: item_ids={item_ids}, occasion="{occasion}", last_worn_date="{planned_end_date}"
Then respond with ONLY a brief confirmation. Example: "Great choice. Will update your wear history." Do NOT add styling advice or tips."""
        else:
            pick_instructions = "\n\n### User confirmed an outfit but no item IDs were linked. Respond with a brief thanks."

    system_content = f"""{AGENT_SYSTEM_PROMPT}

### User Profile & Preferences
{profile_context or "No profile stored."}

### Procedural Instructions
{instructions}

### Episodic Memory (match tone/depth, reuse patterns, avoid rejections)
{episodic_examples or "No past examples yet. Match tone and depth to the request. For outfit requests, consider weather, occasion, and rotation."}
{profile_update_instructions}
{outfit_request_instructions}
{pick_instructions}"""
    from langchain_core.messages import SystemMessage
    system_msg = SystemMessage(content=system_content)

    # Fix orphaned tool_calls (e.g. from interrupted request) so OpenAI accepts the request
    sanitized = _ensure_tool_responses(messages)
    model_messages = [system_msg] + list(sanitized)

    # Retry on transient errors (429 rate limit, 504 timeout, connection)
    max_retries = 2 if is_eval else 4
    retry_wait_max = 30 if is_eval else 45  # cap UI retries so user gets feedback sooner
    for attempt in range(max_retries):
        try:
            response = llm_with_tools.invoke(model_messages)
            break
        except Exception as e:
            err_str = str(e)
            if attempt >= max_retries - 1:
                raise
            # 429 RESOURCE_EXHAUSTED: wait for suggested retry delay
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                import re
                import time
                match = re.search(r"retry in (\d+(?:\.\d+)?)\s*s", err_str, re.I) or re.search(
                    r"retryDelay['\"]?\s*:\s*['\"]?(\d+)", err_str
                )
                wait = int(float(match.group(1))) if match else (30 if is_eval else 60)
                time.sleep(min(wait, retry_wait_max))
                continue
            # 504 DEADLINE_EXCEEDED / Stream cancelled - transient Gemini infra
            if "504" in err_str or "DEADLINE_EXCEEDED" in err_str or "Stream cancelled" in err_str:
                import time
                time.sleep(5 * (attempt + 1))  # 5s, 10s, 15s, 20s
                continue
            # Connection errors
            if (
                "RemoteProtocolError" in type(e).__name__
                or "Server disconnected" in err_str
                or "Connection" in type(e).__name__
            ):
                import time
                time.sleep(2 * (attempt + 1))
                continue
            raise

    raw = response.content if hasattr(response, "content") else str(response)
    if isinstance(raw, list):
        content = "".join(
            part.get("text", part) if isinstance(part, dict) else str(part) for part in raw
        )
    else:
        content = raw or ""
    if response.tool_calls:
        return {"messages": [response]}
    # If we just processed a pick/thumbs (agent already called update_last_worn), clear last_outfit
    if is_pick_or_thumbs and last_outfit:
        return {
            "messages": [AIMessage(content=content)],
            "response": content,
            "last_outfit": None,
        }
    # Final response: parse and set last_outfit
    outfit_plan, _, is_clarifying = _parse_response(content)
    options = outfit_plan.get("options")
    planned_end_date = outfit_plan.get("planned_end_date")
    if is_clarifying or not options:
        content_with_feedback = content
        last_outfit = None
    elif len(options) == 2:
        content_with_feedback = content + FEEDBACK_SUFFIX
        last_outfit = {"options": options, "occasion": (question or "")[:100]}
        if planned_end_date:
            last_outfit["planned_end_date"] = planned_end_date
    else:
        content_with_feedback = content
        last_outfit = {"options": options, "occasion": (question or "")[:100]}
        if planned_end_date:
            last_outfit["planned_end_date"] = planned_end_date
    return {
        "messages": [AIMessage(content=content_with_feedback)],
        "response": content_with_feedback,
        "last_outfit": last_outfit,
    }


def _extract_item_ids(text: str) -> list[int]:
    """Extract [id=X] references from outfit text."""
    ids = re.findall(r"\[id=(\d+)\]", text, re.IGNORECASE)
    return [int(x) for x in ids]


def _parse_planned_end_date(text: str) -> str | None:
    """Extract PLANNED_END_DATE: YYYY-MM-DD from text."""
    m = re.search(r"PLANNED_END_DATE:\s*(\d{4}-\d{2}-\d{2})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _parse_response(text: str) -> tuple[dict, str, bool]:
    """Parse LLM response into outfit_plan, reasoning, and is_clarifying (True if no outfits)."""
    reasoning = ""
    if "REASONING:" in text:
        _, reasoning = text.split("REASONING:", 1)
        reasoning = reasoning.strip()
    else:
        reasoning = "Styled for your request."

    planned_end_date = _parse_planned_end_date(text)

    options: list[dict] = []
    # Match OUTFIT 1, OUTFIT 2, OUTFIT 3, ... (supports multi-day trips)
    outfit_pattern = re.compile(
        r"OUTFIT\s+(\d+):\s*(.*?)(?=OUTFIT\s+\d+:|REASONING:|$)",
        re.DOTALL | re.IGNORECASE,
    )
    matches = list(outfit_pattern.finditer(text))
    if matches:
        for m in matches:
            options.append({"description": m.group(2).strip(), "items": _extract_item_ids(m.group(2))})
    elif "OUTFIT:" in text:
        outfit_section = text.split("OUTFIT:", 1)[1].split("REASONING:")[0].strip()
        options.append({"description": outfit_section, "items": _extract_item_ids(outfit_section)})

    from_outfit_format = bool(options)
    is_clarifying = not from_outfit_format
    if not options:
        options = [{"description": text.split("REASONING:")[0].strip() if "REASONING:" in text else text.strip(), "items": []}]
        reasoning = ""  # Plain text (clarifying questions or informational)

    # Only add "Option 1:" / "Option 2:" prefix when we parsed from OUTFIT format
    if from_outfit_format and len(options) > 1:
        description = "\n\n".join(
            f"Option {i + 1}:\n{opt['description']}" for i, opt in enumerate(options)
        )
    elif from_outfit_format:
        description = options[0]["description"]
    else:
        description = options[0]["description"]  # Plain message (clarifying or informational)

    outfit_plan: dict = {"description": description, "items": options[0]["items"]}
    if len(options) > 1:
        outfit_plan["options"] = options
    if planned_end_date:
        outfit_plan["planned_end_date"] = planned_end_date
    return outfit_plan, reasoning, is_clarifying


PICK_OPTION_PATTERNS = ("pick option 1", "pick option 2", "option 1", "option 2", "i pick 1", "i pick 2")


def _route(state: StylistState) -> Literal["agent", "clarify"]:
    """Route based on last user message: thumbs down → clarify; else → agent (handles pick/thumbs via update_last_worn tool)."""
    messages = state.get("messages", [])
    if not messages:
        return "agent"
    last = messages[-1]
    if not isinstance(last, HumanMessage):
        return "agent"
    content = (last.content or "").strip().lower()
    if any(p in content for p in THUMBS_DOWN_PATTERNS):
        return "clarify"
    return "agent"


def _get_picked_option_index(content: str) -> int:
    """Return 0 or 1 for 'pick option 1' / 'pick option 2', else 0."""
    c = (content or "").strip().lower()
    if "2" in c and ("option 2" in c or "pick 2" in c or "i pick 2" in c):
        return 1
    return 0


def clarify(state: StylistState) -> dict:
    """Ask for clarifications when user thumbs down."""
    msg = (
        "No problem! What would you like to change? "
        "For example: more casual, different colors, different pieces, or something else?"
    )
    return {
        "messages": [AIMessage(content=msg)],
        "response": msg,
    }


def create_stylist_graph():
    """Create the LangGraph agent graph with tools (RAG, wardrobe, weather, update_last_worn)."""
    store = get_stylist_store()
    checkpointer = MemorySaver()
    tool_node = ToolNode(STYLIST_TOOLS)

    builder = StateGraph(StylistState)
    builder.add_node("agent", agent)
    builder.add_node("tools", tool_node)
    builder.add_node("clarify", clarify)

    builder.add_conditional_edges(START, _route, {"agent": "agent", "clarify": "clarify"})
    builder.add_conditional_edges("agent", _should_continue_agent, {"tools": "tools", "__end__": END})
    builder.add_edge("tools", "agent")
    builder.add_edge("clarify", END)

    return builder.compile(
        checkpointer=checkpointer,
        store=store,
    )


_stylist_graph = None


def get_stylist_graph():
    """Get or create the compiled stylist graph."""
    global _stylist_graph
    if _stylist_graph is None:
        _stylist_graph = create_stylist_graph()
    return _stylist_graph


def _infer_patterns_from_response(text: str) -> list[str]:
    """Infer which patterns were used in the response (weather, occasion, rotation, etc.)."""
    text_lower = (text or "").lower()
    patterns = []
    if any(w in text_lower for w in ("weather", "forecast", "rain", "cold", "warm", "temperature")):
        patterns.append("weather")
    if any(w in text_lower for w in ("occasion", "dinner", "interview", "date", "trip", "conference")):
        patterns.append("occasion")
    if any(w in text_lower for w in ("rotation", "last worn", "underutilized", "wear count")):
        patterns.append("rotation")
    if "outfit" in text_lower or "id=" in text_lower:
        patterns.append("wardrobe")
    return patterns or ["occasion", "wardrobe"]


def _record_episodes_from_turn(result: dict, user_prompt: str) -> None:
    """Record positive or negative episode based on turn outcome.
    Pick = outfit suggestions only. Thumbs up/down = any answer type.
    Applies gates (substantive) and pruning (caps) via memory.add_episode."""
    messages = result.get("messages", [])
    last_outfit = result.get("last_outfit")
    response_text = result.get("response", "")

    # Extract: last Human (pick/thumbs), AI before it (our response), Human before that (the request)
    last_human = ""
    prev_ai_content = ""
    request_human = ""
    human_count = 0
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            c = (m.content or "").strip()
            human_count += 1
            if human_count == 1:
                last_human = c.lower()
            elif human_count == 2:
                request_human = c
                break
        elif isinstance(m, AIMessage) and human_count == 1 and not prev_ai_content:
            prev_ai_content = (m.content or "").strip()
    if not request_human:
        request_human = user_prompt

    is_pick = any(p in last_human for p in PICK_OPTION_PATTERNS)
    is_thumbs_up = any(p in last_human for p in THUMBS_UP_PATTERNS)
    is_thumbs_down = any(p in last_human for p in THUMBS_DOWN_PATTERNS)
    answer_text = (prev_ai_content or response_text).strip()

    added = False

    # Pick = outfit suggestions only (requires last_outfit)
    if is_pick and last_outfit:
        user_query = last_outfit.get("occasion", "") or request_human[:200] or user_prompt[:200]
        answer_summary = answer_text[:400]
        patterns = _infer_patterns_from_response(answer_text)
        if memory.add_episode({
            "user_query": user_query,
            "answer_summary": answer_summary,
            "patterns_used": patterns,
            "satisfaction_signal": "pick",
        }) is not None:
            added = True

    # Thumbs up = any answer type (outfit or informational), must be substantive
    elif is_thumbs_up and len(answer_text) >= 50:
        user_query = request_human[:200] or user_prompt[:200]
        answer_summary = answer_text[:400]
        patterns = _infer_patterns_from_response(answer_text) if last_outfit else []
        if memory.add_episode({
            "user_query": user_query,
            "answer_summary": answer_summary,
            "patterns_used": patterns,
            "satisfaction_signal": "thumbs_up",
        }) is not None:
            added = True

    # Thumbs down = any answer type, always record
    elif is_thumbs_down and prev_ai_content:
        user_query = request_human[:200] or user_prompt[:200]
        answer_summary = prev_ai_content[:300]
        avoid = "suggested outfits or approach that user rejected; consider clarifying or different tone/depth"
        if memory.add_episode({
            "user_query": user_query,
            "answer_summary": answer_summary,
            "avoid_patterns": avoid,
        }) is not None:
            added = True

    if added:
        sync_store_from_memory()


def _extract_tool_results_by_type(messages: list) -> tuple[str, str, str]:
    """Extract wardrobe, RAG (style principles), and weather from ToolMessages. Uses content heuristics."""
    wardrobe, rag, weather = "", "", ""
    for m in messages:
        if not isinstance(m, ToolMessage) or not getattr(m, "content", None):
            continue
        content = (m.content or "").strip()
        if len(content) < 10:
            continue
        # Wardrobe: list of items with id=X (e.g. "- id=197: white sneakers")
        if re.search(r"id=\d+", content) and ("-" in content or "(" in content):
            if len(content) > len(wardrobe):
                wardrobe = content
        # Weather: forecast-like (tomorrow, °F, rain, etc.)
        elif any(w in content.lower() for w in ("tomorrow", "°f", "°c", "rain", "cloudy", "sunny", "forecast", "weather")):
            weather = content
        # RAG/style: principles, no wardrobe format
        elif "tailored" in content.lower() or "neutral" in content.lower() or "professional" in content.lower() or "silhouette" in content.lower():
            if len(content) > len(rag):
                rag = content
        elif not wardrobe and not weather:  # fallback: last substantial content = likely RAG
            rag = content
    return wardrobe, rag, weather


def _fallback_from_tool_messages(messages: list, user_query: str = "") -> str:
    """When we hit tool-call limit with no final response, synthesize from tool results. Different prompts for outfit vs informational."""
    wardrobe, rag, weather = _extract_tool_results_by_type(messages)
    is_outfit_request = any(p in (user_query or "").lower() for p in OUTFIT_REQUEST_PATTERNS)

    if is_outfit_request and wardrobe:
        # Outfit request with wardrobe: use RAG_PROMPT-style synthesis to produce OUTFIT 1/OUTFIT 2
        try:
            from langchain_core.messages import HumanMessage
            llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=os.getenv("OPENAI_API_KEY"), timeout=45)
            prompt = f"""You are Stylepal. The user asked: {user_query}

### Wardrobe (use ONLY these items—every piece MUST have [id=X]):
{wardrobe[:4000]}

### Style Principles (from knowledge base):
{rag[:1500] if rag else "Professional, tailored, neutral colors. Closed-toe shoes."}

### Weather:
{weather[:500] if weather else "Not specified."}

Provide OUTFIT 1 and OUTFIT 2 with [id=X] for every piece. List items as [id=X] Item name only—no per-item descriptions. Same item in both options = same line. Format:

OUTFIT 1:
- [id=X] Item name
- [id=X] Item name
OUTFIT 2:
- [id=X] Item name
- [id=X] Item name
REASONING: [Summary. If weather is provided above, cite the actual forecast in your reasoning.]

Use plain text only."""
            resp = llm.invoke([HumanMessage(content=prompt)])
            out = (resp.content or "").strip()
            return out if out and "[id=" in out else f"Wardrobe available but synthesis failed. Your wardrobe:\n{wardrobe[:1000]}"
        except Exception:
            return f"Could not generate outfits. Your wardrobe has items—try asking again or simplifying:\n{wardrobe[:800]}"

    # Informational or no wardrobe: synthesize RAG into concise answer
    raw = rag or wardrobe or weather
    for m in reversed(messages):
        if isinstance(m, ToolMessage) and getattr(m, "content", None):
            c = (m.content or "").strip()
            if len(c) > 20:
                raw = raw or c
                break
    if not raw:
        return ""
    try:
        from langchain_core.messages import HumanMessage
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=os.getenv("OPENAI_API_KEY"), timeout=30)
        prompt = f"""You are a style advisor. The user asked: {user_query}

Context from the knowledge base:
{raw[:3000]}

Write a concise, conversational answer (2-4 sentences). Synthesize the information—do not list or copy raw text. Answer the user's question directly."""
        resp = llm.invoke([HumanMessage(content=prompt)])
        out = (resp.content or "").strip()
        return out if out else raw[:500]
    except Exception:
        return raw[:500]


def plan_outfit(
    query: str,
    constraints: list[str] | None = None,
    location: str | None = None,
    thread_id: str = "default",
) -> dict:
    """
    Generate an outfit plan or informational answer. Uses checkpointing when thread_id is provided.
    Agent uses its own DB session (same engine as API) for wardrobe and wear history.
    Returns dict with outfit_plan, reasoning, and is_informational.
    """
    user_prompt = query
    if constraints:
        user_prompt += f"\n\nConstraints: {', '.join(constraints)}"
    if location:
        user_prompt += f"\n\nLocation: {location}"

    graph = get_stylist_graph()
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": "StylepalAgent",
        "tags": ["stylepal", "stylist"],
        "metadata": {"thread_id": thread_id},
        "recursion_limit": 25,  # Allow agent→tools→agent cycles (each cycle = 2 steps)
    }
    result = graph.invoke(
        {"messages": [HumanMessage(content=user_prompt)]},
        config=config,
    )
    _record_episodes_from_turn(result, user_prompt)

    response_text = result.get("response", "")
    # Fallback: if we hit tool-call limit and never got a final response, synthesize from RAG chunks
    if not response_text:
        response_text = _fallback_from_tool_messages(result.get("messages", []), user_query=user_prompt)
    last_outfit = result.get("last_outfit")
    is_informational = last_outfit is None and "OUTFIT 1:" not in response_text and "OUTFIT:" not in response_text

    outfit_plan, reasoning, _ = _parse_response(response_text)
    return {"outfit_plan": outfit_plan, "reasoning": reasoning, "is_informational": is_informational}
