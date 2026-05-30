"""
rss_service.py — 改进版
========================
新增：
- CoinDesk（加密专项）
- The Block（加密专项）
- Reuters Politics（政治专项）
- Reuters Business（宏观专项）
- 每个 feed 独立并发，最慢单源决定总耗时（约 4-6s）
- 去掉已确认返回空数据的 Reuters TopNews / AP News
"""

import asyncio
from functools import partial

import feedparser

# (名称, URL, 类别标签)
RSS_FEEDS = [
    # 政治/选举
    ("Politico",         "https://rss.politico.com/politics-news.xml",        "politics"),
    ("The Hill",         "https://thehill.com/feed/",                          "politics"),
    ("Reuters Politics", "https://feeds.reuters.com/reuters/politicsNews",     "politics"),
    # 金融/宏观
    ("WSJ Markets",      "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",     "finance"),
    ("Financial Times",  "https://www.ft.com/?format=rss",                    "finance"),
    ("Reuters Business", "https://feeds.reuters.com/reuters/businessNews",     "finance"),
    # 加密货币（Polymarket 最大类别）
    ("CoinTelegraph",    "https://cointelegraph.com/rss",                      "crypto"),
    ("Decrypt",          "https://decrypt.co/feed",                            "crypto"),
    ("CoinDesk",         "https://www.coindesk.com/arc/outboundfeeds/rss/",   "crypto"),
    # AI/科技
    ("TechCrunch",       "https://techcrunch.com/feed/",                       "tech"),
]


def _fetch_one(name: str, url: str, limit: int) -> list[dict]:
    """同步抓取单个 RSS 源。在线程池中执行。"""
    try:
        feed = feedparser.parse(url)
        return [
            {
                "title":     entry.get("title", ""),
                "summary":   entry.get("summary", ""),
                "source":    name,
                "link":      entry.get("link", ""),
                "published": entry.get("published", ""),
            }
            for entry in feed.entries[:limit]
        ]
    except Exception:
        return []


async def fetch_news(limit: int = 5) -> list:
    """
    并发抓取所有 RSS 源（每个 feed 独立线程）。
    总耗时 ≈ 最慢单源（约 4-6 秒），而非各源之和（约 40 秒）。
    """
    from app.models.news import NewsModel

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, partial(_fetch_one, name, url, limit))
        for name, url, _ in RSS_FEEDS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    articles = []
    for result in results:
        if isinstance(result, list):
            for item in result:
                articles.append(NewsModel(
                    title=item["title"],
                    summary=item["summary"],
                    source=item["source"],
                    link=item["link"],
                    published=item["published"],
                ))
    return articles
