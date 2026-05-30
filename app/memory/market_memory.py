"""
market_memory.py
================
轻量级市场记忆层。

功能：
- 缓存扫描结果，避免同一问题短时间内重复调用 LLM
- 追踪市场历史分析记录
- 提供简单的 TTL (Time-To-Live) 缓存
"""

import os
import time
from typing import Any

from app.core.config import settings
from app.utils.file_store import locked_file, read_json, write_json_atomic


_MARKET_CACHE_FILE = os.path.join(
    os.path.dirname(settings.MEMORY_FILE),
    "market_cache.json",
)

# 缓存有效期（秒）
_DEFAULT_TTL = 3600  # 1 hour


def _load_cache() -> dict[str, Any]:
    data = read_json(_MARKET_CACHE_FILE, {})
    return data if isinstance(data, dict) else {}


def _save_cache(cache: dict[str, Any]) -> None:
    write_json_atomic(_MARKET_CACHE_FILE, cache, indent=2)


def _cache_key(market_question: str) -> str:
    return market_question.strip().lower()[:200]


def get_cached_analysis(
    market_question: str,
    ttl: int = _DEFAULT_TTL,
) -> dict[str, Any] | None:
    """
    返回缓存的分析结果，若已过期或不存在则返回 None。
    """
    cache = _load_cache()
    key = _cache_key(market_question)
    entry = cache.get(key)
    if entry is None:
        return None
    if time.time() - entry.get("cached_at", 0) > ttl:
        return None
    return entry.get("result")


def set_cached_analysis(
    market_question: str,
    result: dict[str, Any],
) -> None:
    """将分析结果写入缓存。"""
    with locked_file(_MARKET_CACHE_FILE):
        cache = _load_cache()
        key = _cache_key(market_question)
        cache[key] = {
            "cached_at": time.time(),
            "market_question": market_question,
            "result": result,
        }
        _purge_expired(cache)
        _save_cache(cache)


def _purge_expired(
    cache: dict[str, Any],
    ttl: int = _DEFAULT_TTL,
) -> None:
    now = time.time()
    expired = [
        k for k, v in cache.items()
        if now - v.get("cached_at", 0) > ttl
    ]
    for k in expired:
        del cache[k]


def list_recent_markets(limit: int = 20) -> list[dict[str, Any]]:
    """返回最近缓存的市场分析（按时间降序）。"""
    cache = _load_cache()
    entries = sorted(
        cache.values(),
        key=lambda e: e.get("cached_at", 0),
        reverse=True,
    )
    return [
        {
            "market_question": e["market_question"],
            "cached_at": e["cached_at"],
            "signal": e["result"].get("signal", "NO_TRADE"),
            "divergence": e["result"].get("divergence", 0.0),
        }
        for e in entries[:limit]
    ]
