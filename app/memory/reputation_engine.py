"""
reputation_engine.py
====================
基于历史 audit 日志计算各 Agent 的准确率声誉评分。

数据来源：analysis_audit.jsonl（由 analysis_audit_service 写入）
解析逻辑：
  - 每条已解决记录 (resolved=True) 中，读取 ai_probability 作为预测
  - actual_outcome 作为实际结果
  - 用二元准确率（预测方向 vs 实际方向）打分
  - 同时计算 Brier Score（更严格的概率校准指标）
"""

import json
import os
from collections import defaultdict
from typing import Any

from app.core.config import settings


AUDIT_FILE = os.path.join(
    os.path.dirname(settings.MEMORY_FILE),
    "analysis_audit.jsonl",
)

# 初始声誉：新系统没有历史数据时的默认值
DEFAULT_REPUTATION = 0.5

# 最少需要多少条已解决数据才启用声誉评分
MIN_RESOLVED_FOR_SCORING = 5


class ReputationEngine:

    def calculate_scores(self) -> dict[str, dict[str, Any]]:
        """
        计算所有 Agent 的声誉评分。
        当前主流程（ai_analysis_service）是单体分析，没有子 Agent 名称。
        因此这里提供系统级整体声誉评分，
        并保留兼容接口供 JudgeAgent 查询 agent_name → score。
        """
        records = self._load_resolved_records()

        if len(records) < MIN_RESOLVED_FOR_SCORING:
            # 数据不足时返回默认值，避免误导
            return {"_system": self._default_stat()}

        total = len(records)
        correct = 0
        brier_sum = 0.0

        for record in records:
            predicted = float(record.get("ai_probability") or 50)
            actual = float(record.get("actual_outcome") or 50)

            predicted_yes = predicted >= 50
            actual_yes = actual >= 50
            if predicted_yes == actual_yes:
                correct += 1

            p = predicted / 100.0
            a = actual / 100.0
            brier_sum += (p - a) ** 2

        accuracy = correct / total
        brier = brier_sum / total
        # Brier Skill Score (vs random 0.25): 越高越好
        skill = round(1.0 - brier / 0.25, 3)

        system_stat = {
            "total": total,
            "correct": correct,
            "score": round(accuracy, 3),
            "brier_score": round(brier, 4),
            "skill_score": skill,
            "grade": self._grade(brier),
        }

        # 兼容旧接口：JudgeAgent 按 agent_name 查询时返回系统分
        return defaultdict(lambda: system_stat, {"_system": system_stat})

    def get_agent_score(self, agent_name: str) -> float:
        """返回指定 agent 的声誉分（0–1）。无历史数据时返回默认 0.5。"""
        scores = self.calculate_scores()
        return scores.get(agent_name, {}).get("score", DEFAULT_REPUTATION)

    def _load_resolved_records(self) -> list[dict[str, Any]]:
        if not os.path.exists(AUDIT_FILE):
            return []
        records = []
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("resolved") and record.get("actual_outcome") is not None:
                        records.append(record)
                except json.JSONDecodeError:
                    continue
        return records

    def _default_stat(self) -> dict[str, Any]:
        return {
            "total": 0,
            "correct": 0,
            "score": DEFAULT_REPUTATION,
            "brier_score": None,
            "skill_score": None,
            "grade": "no_data",
        }

    def _grade(self, brier: float) -> str:
        if brier <= 0.05:
            return "EXCELLENT"
        if brier <= 0.10:
            return "GOOD"
        if brier <= 0.15:
            return "ACCEPTABLE"
        if brier <= 0.20:
            return "POOR"
        return "RANDOM_LEVEL"
