"""Long-term memory stored in JSON files."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import DATA_DIR

PROFILE_FILE = DATA_DIR / "profile.json"
OUTFIT_HISTORY_FILE = DATA_DIR / "outfit_history.json"
EPISODES_FILE = DATA_DIR / "episodes.json"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    tmp.rename(path)


DEFAULT_PROFILE = {
    "name": "Maya",
    "gender": "female",
    "age": 34,
    "body_type": "hourglass",
    "location": "San Francisco",
    "silhouette_preferences": ["tailored", "fitted", "belted"],
    "comfort_thresholds": {
        "prefer_breathable_fabrics": True,
        "avoid_high_heels": False,
        "max_formality": 5,
    },
    "rotation_patterns": {
        "min_days_between_same_item": 3,
        "prefer_underworn_items": True,
    },
}


def get_profile() -> dict:
    """Get user profile with demographics, preferences, and styling data."""
    return _read_json(PROFILE_FILE, DEFAULT_PROFILE.copy())


def update_profile(updates: dict) -> dict:
    """Update profile with partial updates."""
    profile = get_profile()
    profile.update(updates)
    _write_json(PROFILE_FILE, profile)
    return profile


def get_outfit_history() -> list:
    """Get outfit history: outfit_id, items, occasion, created_at."""
    return _read_json(OUTFIT_HISTORY_FILE, [])


def add_outfit(outfit: dict) -> dict:
    """Add outfit to history. Generates outfit_id if not provided."""
    history = get_outfit_history()
    outfit_id = outfit.get("outfit_id") or len(history) + 1
    record = {
        "outfit_id": outfit_id,
        "items": outfit.get("items", []),
        "occasion": outfit.get("occasion", ""),
        "created_at": outfit.get("created_at"),
    }
    history.append(record)
    _write_json(OUTFIT_HISTORY_FILE, history)
    return record


def get_episodes() -> list:
    """Get generalized episodes (positive and negative) for episodic memory."""
    return _read_json(EPISODES_FILE, [])


# Episodic memory caps and gates
MAX_POSITIVE_EPISODES = 65
MAX_NEGATIVE_EPISODES = 20
MIN_ANSWER_LENGTH = 50
SIMILAR_QUERY_PREFIX_LEN = 60


def _is_negative(ep: dict) -> bool:
    return ep.get("avoid_patterns") is not None


def _is_similar_episode(existing: dict, new_ep: dict) -> bool:
    """True if new episode is too similar to existing (same query type)."""
    eq = (existing.get("user_query") or "")[:SIMILAR_QUERY_PREFIX_LEN].strip().lower()
    nq = (new_ep.get("user_query") or "")[:SIMILAR_QUERY_PREFIX_LEN].strip().lower()
    if not eq or not nq:
        return False
    # Same start of query suggests duplicate
    return eq == nq or eq in nq or nq in eq


def add_episode(episode: dict) -> dict | None:
    """Add an episode (positive or negative) for episodic memory.
    Applies gates (substantive, dedup) and pruning (caps).
    Returns the episode if added, None if skipped."""
    is_neg = _is_negative(episode)
    answer_summary = (episode.get("answer_summary") or "").strip()

    # Gate: positive episodes must have substantive answer
    if not is_neg and len(answer_summary) < MIN_ANSWER_LENGTH:
        return None

    # Gate: deduplication - skip if very similar episode exists
    episodes = get_episodes()
    for ex in episodes:
        if _is_similar_episode(ex, episode) and _is_negative(ex) == is_neg:
            return None

    episode["created_at"] = episode.get("created_at") or datetime.now(timezone.utc).isoformat()
    episodes.append(episode)

    # Pruning: enforce caps (remove oldest first)
    positives = [e for e in episodes if not _is_negative(e)]
    negatives = [e for e in episodes if _is_negative(e)]
    to_drop: set[str] = set()
    if len(negatives) > MAX_NEGATIVE_EPISODES:
        neg_sorted = sorted(negatives, key=lambda e: e.get("created_at", ""))
        for e in neg_sorted[: len(negatives) - MAX_NEGATIVE_EPISODES]:
            to_drop.add(e.get("created_at", ""))
    if len(positives) > MAX_POSITIVE_EPISODES:
        pos_sorted = sorted(positives, key=lambda e: e.get("created_at", ""))
        for e in pos_sorted[: len(positives) - MAX_POSITIVE_EPISODES]:
            to_drop.add(e.get("created_at", ""))

    episodes = [e for e in episodes if e.get("created_at", "") not in to_drop]
    _write_json(EPISODES_FILE, episodes)
    return episode
