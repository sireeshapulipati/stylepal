"""LangGraph memory store (06_Agent_Memory pattern): semantic, episodic, procedural."""
import json
import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore

from services import memory as memory_service

# Namespaces (user_id, category)
PROFILE_NS = ("stylist", "profile")
EPISODES_NS = ("stylist", "episodes")
EPISODES_AVOID_NS = ("stylist", "episodes_avoid")
INSTRUCTIONS_NS = ("stylist", "instructions")

# Procedural base instructions
BASE_INSTRUCTIONS = """You are Stylepal, a trusted style companion for intentional professionals.

Guidelines:
- Reuse is the default. Prioritize combinations from the user's existing wardrobe.
- Apply professional styling principles: fit, color coordination, proportion, occasion appropriateness.
- Respect any constraints the user specifies.
- Consider weather and location when relevant.
- Keep recommendations practical and actionable.
- Single event: suggest 2 outfit options. Multi-day trip: one primary outfit per day/occasion, plus 1-3 optional items to pack.
- When a request is vague (trip, conference, multi-day), ask clarifying questions first: location, dates, event types (formal dinner vs casual pub vs sightseeing vs business, day vs evening). Do not suggest outfits until you have enough detail."""

_stylist_store: InMemoryStore | None = None


def create_stylist_store() -> InMemoryStore:
    """Create InMemoryStore with Gemini embeddings for semantic search."""
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GEMINI_API_KEY"),
    )
    return InMemoryStore(
        index={
            "embed": embeddings,
            "dims": 768,
        }
    )


def get_stylist_store() -> InMemoryStore:
    """Get or create the stylist memory store."""
    global _stylist_store
    if _stylist_store is None:
        _stylist_store = create_stylist_store()
        _initialize_store(_stylist_store)
    return _stylist_store


def _initialize_store(store: InMemoryStore) -> None:
    """Load profile, episodic memories, and procedural instructions into store."""
    # 1. Semantic memory: user profile as searchable facts
    profile = memory_service.get_profile()
    _sync_profile_to_store(store, profile)

    # 2. Episodic memory: high-rated outfits as few-shot examples
    _sync_episodes_to_store(store)

    # 3. Procedural memory: base instructions
    try:
        store.get(INSTRUCTIONS_NS, "stylist")
    except Exception:
        store.put(
            INSTRUCTIONS_NS,
            "stylist",
            {"instructions": BASE_INSTRUCTIONS, "version": 1},
        )


def _sync_profile_to_store(store: InMemoryStore, profile: dict) -> None:
    """Sync profile to store as semantic facts (searchable by meaning)."""
    facts = []
    if profile.get("name"):
        facts.append(("name", f"User's name is {profile['name']}"))
    if profile.get("location"):
        facts.append(("location", f"User is in {profile['location']}"))
    if profile.get("body_type"):
        facts.append(("body_type", f"User has {profile['body_type']} body type"))
    if profile.get("silhouette_preferences"):
        prefs = ", ".join(profile["silhouette_preferences"])
        facts.append(("silhouette", f"User prefers silhouettes: {prefs}"))
    if profile.get("comfort_thresholds"):
        ct = profile["comfort_thresholds"]
        parts = []
        if ct.get("prefer_breathable_fabrics"):
            parts.append("prefers breathable fabrics")
        if ct.get("avoid_high_heels"):
            parts.append("avoids high heels")
        if parts:
            facts.append(("comfort", "User comfort: " + "; ".join(parts)))
    if profile.get("rotation_patterns"):
        rp = profile["rotation_patterns"]
        if rp.get("prefer_underworn_items"):
            facts.append(("rotation", "User prefers to wear underutilized items"))
        if rp.get("min_days_between_same_item"):
            facts.append(
                (
                    "rotation",
                    f"User likes at least {rp['min_days_between_same_item']} days between wearing same item",
                )
            )
    for key, value in facts:
        store.put(PROFILE_NS, key, {"text": value, "value": value})


def _sync_episodes_to_store(store: InMemoryStore) -> None:
    """Sync positive and negative episodes to episodic memory."""
    ep_idx = 0
    # 1. Outfit picks (legacy positive)
    history = memory_service.get_outfit_history()
    for record in history:
        occasion = record.get("occasion", "outfit")
        items = record.get("items", [])
        notes = record.get("notes", "")
        situation = f"User requested outfit for {occasion}"
        text = f"{situation}. Items: {items}. Feedback: {notes or 'User selected this outfit'}."
        store.put(
            EPISODES_NS,
            f"episode_{ep_idx}",
            {
                "text": text,
                "situation": situation,
                "occasion": occasion,
                "items": items,
                "feedback": notes or "User selected this outfit",
                "type": "outfit_pick",
            },
        )
        ep_idx += 1
    # 2. Generalized positive episodes
    for ep in memory_service.get_episodes():
        if ep.get("avoid_patterns") is not None:
            continue  # negative, handled below
        user_query = ep.get("user_query", "")[:200]
        answer_summary = ep.get("answer_summary", "")[:300]
        patterns = ep.get("patterns_used", [])
        patterns_str = ", ".join(patterns) if patterns else "occasion, wardrobe"
        text = f"User asked: {user_query}. Good answer: {answer_summary}. Patterns that worked: {patterns_str}. User was satisfied."
        store.put(
            EPISODES_NS,
            f"episode_{ep_idx}",
            {
                "text": text,
                "user_query": user_query,
                "answer_summary": answer_summary,
                "patterns_used": patterns,
                "type": "positive",
            },
        )
        ep_idx += 1
    # 3. Negative episodes (avoid)
    avoid_idx = 0
    for ep in memory_service.get_episodes():
        avoid = ep.get("avoid_patterns")
        if avoid is None:
            continue
        user_query = ep.get("user_query", "")[:200]
        answer_summary = ep.get("answer_summary", "")[:200]
        avoid_str = avoid if isinstance(avoid, str) else ", ".join(avoid) if isinstance(avoid, list) else str(avoid)
        text = f"User asked: {user_query}. We answered: {answer_summary}. User rejected. Avoid: {avoid_str}."
        store.put(
            EPISODES_AVOID_NS,
            f"avoid_{avoid_idx}",
            {
                "text": text,
                "user_query": user_query,
                "answer_summary": answer_summary,
                "avoid_patterns": avoid_str,
                "type": "negative",
            },
        )
        avoid_idx += 1


def sync_store_from_memory() -> None:
    """Re-sync store from JSON memory (call after profile/outfit updates)."""
    store = get_stylist_store()
    _sync_profile_to_store(store, memory_service.get_profile())
    _sync_episodes_to_store(store)


def get_profile_context(store: BaseStore) -> str:
    """Retrieve profile facts from store for prompt injection."""
    try:
        items = list(store.search(PROFILE_NS, query="user profile preferences", limit=10))
    except Exception:
        profile = memory_service.get_profile()
        return json.dumps(profile, indent=2)
    if not items:
        profile = memory_service.get_profile()
        return json.dumps(profile, indent=2)
    return "\n".join(item.value.get("text", str(item.value)) for item in items)


def get_episodic_examples(
    store: BaseStore, query: str, limit: int = 10, limit_avoid: int = 5
) -> str:
    """Retrieve similar past successes and avoid-patterns. Cap at ~15 total (limit positive + limit_avoid)."""
    parts = []
    try:
        # Positive: match tone, depth, reuse patterns that worked
        pos_results = store.search(EPISODES_NS, query=query, limit=limit)
        if pos_results:
            examples = []
            for r in pos_results:
                v = r.value
                if v.get("type") == "outfit_pick":
                    ex = f"- Past success for '{v.get('occasion', 'occasion')}': items={v.get('items', [])}, feedback: {v.get('feedback', '')}"
                else:
                    ex = f"- User asked: {v.get('user_query', '')[:80]}... Good answer: {v.get('answer_summary', '')[:100]}... Patterns: {v.get('patterns_used', [])}"
                examples.append(ex)
            parts.append("Match tone and depth from past successes. Reuse patterns that worked:\n" + "\n".join(examples))
        # Negative: avoid patterns that led to rejection
        avoid_results = store.search(EPISODES_AVOID_NS, query=query, limit=limit_avoid)
        if avoid_results:
            avoids = []
            for r in avoid_results:
                v = r.value
                avoids.append(f"- Avoid: {v.get('avoid_patterns', '')} (user rejected when we did this)")
            parts.append("Avoid patterns that led to clarification or rejection:\n" + "\n".join(avoids))
    except Exception:
        return ""
    return "\n\n".join(parts) if parts else ""


def get_instructions(store: BaseStore) -> tuple[str, int]:
    """Retrieve procedural instructions from store."""
    try:
        item = store.get(INSTRUCTIONS_NS, "stylist")
        return item.value["instructions"], item.value.get("version", 1)
    except Exception:
        return BASE_INSTRUCTIONS, 0


def update_instructions_from_feedback(store: BaseStore, feedback: str, llm) -> None:
    """Update procedural memory based on user feedback (self-improvement)."""
    from langchain_core.messages import HumanMessage

    instructions, version = get_instructions(store)
    prompt = f"""Improve these stylist instructions based on user feedback.

Current instructions:
{instructions}

User feedback:
{feedback}

Output only the improved instructions, nothing else."""
    response = llm.invoke([HumanMessage(content=prompt)])
    store.put(
        INSTRUCTIONS_NS,
        "stylist",
        {"instructions": response.content, "version": version + 1},
    )
