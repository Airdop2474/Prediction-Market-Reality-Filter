"""
base_rate_service.py  — 改进版
================================
改进：
1. 新增 governor / state 选举类别
2. 更精确的 Senate 席位数量市场
3. 更广的加密价格匹配
4. 新增股票/公司类别
5. 支持短语优先匹配（先长后短，避免误匹配）
"""

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class BaseRate:
    category: str
    low: float
    high: float
    prior: float
    note: str


# ── 规则列表（越具体的放越前面）──────────────────────────────────────
_RULES: list[tuple[list[str], BaseRate]] = [

    # ── 美国联邦选举 ──────────────────────────────────────────────────
    (["win the presidency", "become president", "presidential election",
      "win the general election", "win the white house"],
     BaseRate("us_presidential", 30, 70, 50,
              "总统大选：两党制，历史上胜率接近50/50")),

    (["win the primary", "win primary", "secure the nomination",
      "win the democratic", "win the republican"],
     BaseRate("primary_election", 15, 85, 40,
              "初选：领先者通常胜出，但黑马概率被高估")),

    (["win senate seat", "win the senate race", "win senate election",
      "hold exactly", "senate seats after", "control the senate",
      "win senate", "win house seat", "win the house race"],
     BaseRate("congressional", 20, 80, 48,
              "国会选举：中期执政党往往失利，约-5%优势")),

    # ── 州长/州级选举 ─────────────────────────────────────────────────
    (["win the governor", "win governor", "gubernatorial",
      "governor election", "governor race", "win the governorship"],
     BaseRate("governor_election", 25, 75, 48,
              "州长选举：现任优势约+5%，竞争激烈")),

    (["win the state", "state senate", "state house", "state legislature",
      "state election", "state representative"],
     BaseRate("state_election", 20, 80, 48,
              "州级选举：高度依赖州内党派格局")),

    # ── 美联储/宏观 ───────────────────────────────────────────────────
    (["fed raise", "rate hike", "raise rates", "fed hike",
      "increase interest", "basis points"],
     BaseRate("fed_hike", 5, 95, 50,
              "美联储决定：市场定价极为准确，边际优势极小")),

    (["fed cut", "rate cut", "lower rates", "cut rates",
      "reduce interest", "fed lower", "pivot"],
     BaseRate("fed_cut", 5, 95, 50,
              "美联储决定：市场定价极为准确")),

    (["recession", "gdp negative", "gdp contraction", "economic contraction"],
     BaseRate("recession", 10, 35, 22,
              "年度衰退概率：历史约15-25%，恐慌期市场高估")),

    (["cpi", "inflation", "pce", "core inflation"],
     BaseRate("inflation_data", 30, 70, 50,
              "通胀数据：经济学家预测接近市场定价")),

    # ── 加密货币 ─────────────────────────────────────────────────────
    (["bitcoin ath", "btc ath", "bitcoin all-time high", "btc all time high",
      "new all time high"],
     BaseRate("crypto_ath", 10, 55, 28,
              "ATH 需要牛市条件，年度概率约20-40%")),

    (["bitcoin above", "bitcoin reach", "bitcoin price", "bitcoin hit",
      "btc above", "btc reach", "btc price", "btc hit",
      "will bitcoin"],
     BaseRate("crypto_price_btc", 20, 80, 50,
              "BTC 价格：接近随机游走，市场定价相对有效")),

    (["ethereum above", "ethereum reach", "ethereum price", "eth above",
      "eth reach", "eth price", "eth hit", "will ethereum",
      "ether price"],
     BaseRate("crypto_price_eth", 20, 80, 48,
              "ETH 价格：波动大，但整体跟随 BTC")),

    (["solana above", "solana reach", "solana price", "sol above",
      "sol reach", "sol price", "solana hit", "will solana",
      "solana dip"],
     BaseRate("altcoin_price", 15, 85, 45,
              "山寨币价格：波动更大，市场效率更低")),

    (["crypto etf", "bitcoin etf", "btc etf", "ethereum etf", "eth etf",
      "etf approval", "spot etf"],
     BaseRate("crypto_etf", 20, 80, 50,
              "ETF 审批：监管决定，信息不对称较大")),

    (["crypto", "defi", "nft", "blockchain", "web3", "token",
      "altcoin", "memecoin"],
     BaseRate("crypto_general", 15, 85, 45,
              "加密货币市场：高波动，市场效率较低")),

    # ── AI / 科技 ─────────────────────────────────────────────────────
    (["gpt", "openai", "anthropic", "gemini", "llm", "ai model",
      "claude", "grok", "llama", "mistral"],
     BaseRate("ai_release", 20, 80, 55,
              "AI 发布：公司公告有提前泄露，市场反应常过度")),

    (["ipo", "go public", "stock market listing", "direct listing",
      "spac", "public offering"],
     BaseRate("ipo", 15, 75, 40,
              "IPO：市场条件依赖性强，推迟概率被低估")),

    # ── 地缘政治 ─────────────────────────────────────────────────────
    (["ceasefire", "peace deal", "peace agreement", "peace talks",
      "end the war", "end the conflict"],
     BaseRate("ceasefire", 5, 35, 15,
              "停火/和平：历史上极难短期达成，市场高估")),

    (["conflict escalation", "military operation", "troops",
      "invasion", "attack on", "strike on"],
     BaseRate("conflict_escalation", 10, 55, 30,
              "冲突升级：取决于当前紧张程度")),

    (["sanctions", "tariff", "trade war", "trade deal",
      "trade agreement", "import tax"],
     BaseRate("trade_policy", 20, 70, 45,
              "贸易政策：政治博弈，不确定性大")),

    # ── 司法/监管 ─────────────────────────────────────────────────────
    (["supreme court", "court ruling", "court decision",
      "lawsuit", "trial", "verdict", "overturned"],
     BaseRate("legal", 20, 80, 50,
              "司法结果：法律案件具有高度不确定性")),

    (["sec", "cftc", "regulatory", "regulation", "ban crypto",
      "crypto ban", "approved by sec"],
     BaseRate("regulatory", 15, 75, 42,
              "监管决定：内部信息不对称最大的领域")),

    # ── 体育 ─────────────────────────────────────────────────────────
    (["win the championship", "win the title", "win the super bowl",
      "win the nba", "win the world series", "win the world cup",
      "win the playoffs", "win the finals"],
     BaseRate("sports_championship", 3, 50, 18,
              "体育冠军：赛前赔率通常有效，关注受伤信息")),

    (["win the game", "win the match", "beat the", "defeat the"],
     BaseRate("sports_game", 30, 70, 50,
              "单场比赛：赔率市场非常有效")),

    # ── 人事/企业 ─────────────────────────────────────────────────────
    (["resign", "step down", "leave the company", "fired",
      "removed as ceo", "replaced as"],
     BaseRate("executive_change", 5, 35, 15,
              "高管离职：基准较低，市场通常低估稳定性")),

    (["acquire", "acquisition", "merger", "takeover", "buy out",
      "taken private"],
     BaseRate("ma", 10, 60, 32,
              "M&A：谣言传播快，历史完成率约40-60%")),

    (["bankrupt", "bankruptcy", "default on", "collapse", "insolvency"],
     BaseRate("bankruptcy", 3, 25, 10,
              "破产：基准很低，恐慌期市场高估")),

    (["stock price", "share price", "market cap", "stock above",
      "stock hit", "s&p 500", "nasdaq", "dow jones"],
     BaseRate("stock_price", 30, 70, 50,
              "股票价格：接近随机游走，赌注无明显边际")),

    # ── 自然/科学 ─────────────────────────────────────────────────────
    (["hurricane", "earthquake", "flood", "tornado", "typhoon",
      "natural disaster", "wildfire"],
     BaseRate("natural_disaster", 15, 65, 35,
              "自然灾害：气象模型比新闻可靠得多")),

    (["discovery", "scientific", "experiment", "launch rocket",
      "mars mission", "moon landing"],
     BaseRate("science_event", 20, 75, 45,
              "科学事件：计划表经常推迟")),
]

_DEFAULT = BaseRate("unknown", 20, 80, 50, "无法分类，使用最大熵先验")


def classify_market(question: str) -> BaseRate:
    """
    匹配优先级：长短语 > 短关键词。
    对同等长度的规则，靠前的优先。
    """
    text = question.lower()
    # Sort rules by max keyword length descending for specificity
    sorted_rules = sorted(_RULES, key=lambda r: max(len(k) for k in r[0]), reverse=True)
    for keywords, base_rate in sorted_rules:
        if any(kw in text for kw in keywords):
            return base_rate
    return _DEFAULT


def anchor_probability(
    llm_probability: float,
    base_rate: BaseRate,
    confidence: float,
) -> float:
    """
    将 LLM 概率向基准利率锚定。
    confidence 高 → 更信任 LLM；confidence 低 → 回归基准。
    """
    confidence = max(0.0, min(1.0, confidence))
    alpha = confidence ** 1.5  # 低置信时快速衰减
    prior = base_rate.prior
    anchored = llm_probability * alpha + prior * (1.0 - alpha)
    # 软限制到历史合理范围
    anchored = max(base_rate.low - 5.0, min(base_rate.high + 5.0, anchored))
    return round(anchored, 2)


def get_base_rate_context(question: str) -> dict:
    """返回基准利率上下文，供 ProbabilityAgent prompt 使用。"""
    br = classify_market(question)
    return {
        "category": br.category,
        "historical_range": f"{br.low}% – {br.high}%",
        "prior": br.prior,
        "note": br.note,
    }
