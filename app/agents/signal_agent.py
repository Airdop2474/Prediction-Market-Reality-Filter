"""
signal_agent.py
===============
纯规则引擎。不调用 LLM。

使用 Fractional Kelly Criterion 计算仓位大小：
  f* = (b*p - q) / b
  b = 市场赔率（押注1元的回报）
  p = 我们估算的真实概率
  q = 1 - p

  使用 1/4 Kelly（Quarter Kelly）控制风险。
  最大仓位上限：5% 总资金。
"""

from typing import Any


DEFAULT_SIGNAL_RESULT: dict[str, Any] = {
    "signal": "NO_TRADE",
    "edge": 0.0,
    "position_size": 0.0,
    "kelly_fraction": 0.0,
    "signal_strength": "LOW",
    "signal_direction": "NEUTRAL",
    "reason": "default",
}

# 触发信号的最小偏差（%）
MIN_DIVERGENCE_THRESHOLD = 8.0

# 触发强信号的最小置信度
MIN_CONFIDENCE_FOR_TRADE = 0.45

# Kelly 缩放因子（Quarter Kelly）
KELLY_FRACTION = 0.25

# 最大仓位（占总资金的比例）
MAX_POSITION = 0.05


class SignalAgent:
    name = "signal_agent"

    async def generate(
        self,
        market_probability: float,
        probability_result: dict[str, Any],
        risk_result: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            true_prob = self._f(probability_result.get("true_probability"), 50.0)
            mkt_prob = self._f(market_probability, 50.0)
            confidence = self._f01(probability_result.get("confidence_score"))
            risk_level = str(risk_result.get("risk_level", "LOW")).upper()

            divergence = true_prob - mkt_prob
            abs_div = abs(divergence)
            edge = abs_div / 100.0

            result = {
                "signal": "NO_TRADE",
                "edge": round(edge, 4),
                "position_size": 0.0,
                "kelly_fraction": 0.0,
                "signal_strength": self._strength(abs_div),
                "signal_direction": self._direction(divergence),
                "reason": "",
            }

            # ── 风控过滤 ──────────────────────────────────────────────────
            if risk_level == "HIGH":
                result["reason"] = "blocked_high_risk"
                return result

            if confidence < MIN_CONFIDENCE_FOR_TRADE:
                result["reason"] = f"low_confidence({confidence:.2f})"
                return result

            if abs_div < MIN_DIVERGENCE_THRESHOLD:
                result["reason"] = f"divergence_too_small({abs_div:.1f}%)"
                return result

            # ── 信号方向 ─────────────────────────────────────────────────
            if divergence > 0:
                # 真实概率 > 市场概率 → YES 被低估 → LONG (买 YES)
                result["signal"] = "LONG"
                p = true_prob / 100.0
                b = (1.0 - mkt_prob / 100.0) / (mkt_prob / 100.0)  # 回报倍率
            else:
                # 真实概率 < 市场概率 → NO 被低估 → SHORT (买 NO)
                result["signal"] = "SHORT"
                p = 1.0 - true_prob / 100.0   # NO 的真实概率
                b = (mkt_prob / 100.0) / (1.0 - mkt_prob / 100.0)  # NO 赔率

            # ── Kelly Criterion ──────────────────────────────────────────
            kelly = self._kelly(p=p, b=b)
            # 按置信度缩放：confidence 低时再降仓位
            kelly_adj = kelly * confidence
            # MEDIUM 风险再减半
            if risk_level == "MEDIUM":
                kelly_adj *= 0.5
            # Quarter Kelly + 上限
            final_position = min(kelly_adj * KELLY_FRACTION, MAX_POSITION)
            final_position = max(0.0, final_position)

            result["kelly_fraction"] = round(kelly, 4)
            result["position_size"] = round(final_position, 4)
            result["reason"] = "signal_generated"

            return result

        except Exception as exc:
            result = DEFAULT_SIGNAL_RESULT.copy()
            result["reason"] = f"error:{exc}"
            return result

    # ── Kelly formula ────────────────────────────────────────────────────

    def _kelly(self, p: float, b: float) -> float:
        """
        Full Kelly: f* = (b*p - q) / b
        p = 赢的概率, b = 赔率（赢1元需要下注多少的倒数）
        """
        if b <= 0:
            return 0.0
        q = 1.0 - p
        k = (b * p - q) / b
        return max(0.0, k)  # Kelly 为负 = 不该下注

    # ── Helpers ──────────────────────────────────────────────────────────

    def _strength(self, abs_div: float) -> str:
        if abs_div >= 25:
            return "EXTREME"
        if abs_div >= 15:
            return "HIGH"
        if abs_div >= 8:
            return "MEDIUM"
        return "LOW"

    def _direction(self, divergence: float) -> str:
        if divergence > 0:
            return "BULLISH"
        if divergence < 0:
            return "BEARISH"
        return "NEUTRAL"

    def _f(self, value: Any, fallback: float) -> float:
        try:
            return max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            return fallback

    def _f01(self, value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0
