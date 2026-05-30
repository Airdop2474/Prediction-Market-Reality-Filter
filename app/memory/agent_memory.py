import os
from datetime import datetime, timezone

from app.core.config import settings
from app.utils.file_store import locked_file, read_json, write_json_atomic


def _memory_path() -> str:
    path = os.path.abspath(settings.MEMORY_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def load_memory() -> list[dict]:
    path = _memory_path()
    data = read_json(path, [])
    return data if isinstance(data, list) else []


def save_memory(data: list[dict]) -> None:
    path = _memory_path()
    write_json_atomic(path, data, indent=2)


def add_prediction(
    market_question: str,
    market_probability: float,
    final_probability: float,
    agent_results: list[dict],
) -> None:
    path = _memory_path()
    with locked_file(path):
        memory = load_memory()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_question": market_question,
            "market_probability": market_probability,
            "final_probability": final_probability,
            "divergence": round(final_probability - market_probability, 2),
            "resolved": False,
            "actual_outcome": None,
            "agents": agent_results,
        }
        memory.append(entry)
        save_memory(memory)


def resolve_prediction(
    market_question: str,
    actual_outcome: float,
) -> bool:
    """Mark the latest unresolved entry for this question as resolved."""
    path = _memory_path()
    with locked_file(path):
        memory = load_memory()
        for entry in reversed(memory):
            if (
                entry["market_question"] == market_question
                and not entry["resolved"]
            ):
                entry["resolved"] = True
                entry["actual_outcome"] = actual_outcome
                entry["resolved_at"] = datetime.now(timezone.utc).isoformat()
                save_memory(memory)
                return True
    return False
