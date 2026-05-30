"""
market_utils.py
===============
跨层共享的工具函数。
避免路由层 (api/routes) 被 services 或 scheduler 反向依赖。
"""
from typing import Any


def safe_float(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))
