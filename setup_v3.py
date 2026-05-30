"""
setup_v3.py
===========
一键完成 v0.3.0 所有文件部署和验证。
放到 backend 目录运行：python setup_v3.py
"""

import pathlib, shutil, sys, subprocess

BASE = pathlib.Path(__file__).parent
PASS, FAIL = [], []


def check(name, condition, detail=""):
    if condition:
        PASS.append(name)
        print(f"  OK   {name}")
    else:
        FAIL.append(name)
        print(f"  FAIL {name} {detail}")


print("=" * 55)
print("PMRF v0.3.0 Setup & Verification")
print("=" * 55)

# ── File existence checks ─────────────────────────────────
print("\n[1/3] File checks")
files = {
    "app/services/base_rate_service.py": "base_rate",
    "app/services/rss_service.py": "rss",
    "app/services/signal_tracker.py": "signal_tracker",
    "app/api/routes/signal_accuracy.py": "signal_accuracy",
    "app/api/routes/trades.py": "trades",
    "app/services/trade_journal_service.py": "trade_journal",
    "app/api/router.py": "router",
    "app/main.py": "main",
    "static/index.html": "dashboard",
}
for path, name in files.items():
    fp = BASE / path
    check(name, fp.exists() and fp.stat().st_size > 100, f"({fp})")

# ── Import checks ─────────────────────────────────────────
print("\n[2/3] Import checks")
sys.path.insert(0, str(BASE))
try:
    from app.main import app

    check("app.main", True)
except Exception as e:
    check("app.main", False, str(e))

try:
    from app.services.base_rate_service import classify_market

    r = classify_market("Will Xavier Becerra win the California Governor Race 2026?")
    check("base_rate governor", r.category == "governor_election", f"got {r.category}")
except Exception as e:
    check("base_rate governor", False, str(e))

try:
    from app.services.base_rate_service import classify_market

    r = classify_market("Will Bitcoin reach $150,000 by end of 2026?")
    check(
        "base_rate btc",
        "btc" in r.category or "crypto" in r.category,
        f"got {r.category}",
    )
except Exception as e:
    check("base_rate btc", False, str(e))

try:
    from app.services.signal_tracker import get_signal_accuracy

    check("signal_tracker import", True)
except Exception as e:
    check("signal_tracker import", False, str(e))

try:
    from app.services.trade_journal_service import get_summary, list_trades

    s = get_summary()
    check("trade_journal", True)
except Exception as e:
    check("trade_journal", False, str(e))

try:
    from app.api.routes import signal_accuracy, trades

    check("routes", True)
except Exception as e:
    check("routes", False, str(e))

# ── Dashboard check ───────────────────────────────────────
print("\n[3/3] Dashboard checks")
dash = BASE / "static/index.html"
if dash.exists():
    content = dash.read_text(encoding="utf-8", errors="replace")
    check("dashboard size > 30KB", dash.stat().st_size > 30000)
    check("has 交易日志 tab", "交易日志" in content)
    check("has Polymarket links", "polymarket.com/search" in content)
    check("has signal accuracy", "sa-acc" in content or "rAccuracy" in content)
    check("has prob bar", 'class="pbar"' in content)
else:
    check("dashboard exists", False)

# ── Summary ───────────────────────────────────────────────
print("\n" + "=" * 55)
print(f"Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print(f"FAILED: {', '.join(FAIL)}")
    print("\nRun: python dashboard_patch.py  (if sa-acc missing)")
else:
    print("All checks passed! System ready.")
    print("\nNext: uvicorn app.main:app --reload")
    print("      http://localhost:8000/dashboard")
