import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.routes import scanner
from app.core.logging import setup_logging
from app.core.scheduler import start_scheduler, stop_scheduler

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Prediction Market Reality Filter",
    version="0.3.0",
    description="AI-powered prediction market analysis. Filters narrative distortion, anchors to base rates, generates calibrated signals.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC = Path(__file__).parent.parent / "static"
_STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

app.include_router(scanner.router, prefix="/scan",  tags=["Scanner"])
app.include_router(api_router)


@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    f = _STATIC / "index.html"
    if f.exists():
        return FileResponse(str(f))
    return {"error": "Dashboard not found"}


@app.on_event("startup")
async def on_startup():
    logger.info("PMRF v0.3.0 starting — dashboard: http://localhost:8000/dashboard")
    start_scheduler()


@app.on_event("shutdown")
async def on_shutdown():
    stop_scheduler()


@app.get("/")
async def root():
    return {
        "system": "Prediction Market Reality Filter",
        "version": "0.3.0",
        "dashboard": "http://localhost:8000/dashboard",
        "docs": "http://localhost:8000/docs",
        "endpoints": {
            # Scanner
            "signal_summary":      "GET  /scan/summary",
            "debug_market":        "GET  /scan/debug",
            "full_scan":           "GET  /scan/",
            "deep_scan":           "GET  /scan/deep",
            "cached_results":      "GET  /scan/cache",
            # Analysis
            "manual_analysis":     "POST /analysis/",
            # Calibration
            "calibration":         "GET  /calibration/",
            "history":             "GET  /calibration/history",
            "audit_summary":       "GET  /calibration/summary",
            # Backtest
            "backtest_baseline":   "GET  /backtest/baseline",
            "backtest_base_rate":  "GET  /backtest/base-rate",
            # Resolve
            "auto_resolve":        "POST /resolve/auto",
            "manual_resolve":      "POST /resolve/manual",
            "pending":             "GET  /resolve/pending",
            # Trades
            "open_trade":          "POST /trades/open",
            "close_trade":         "POST /trades/close/{id}",
            "trade_summary":       "GET  /trades/summary",
            "trade_list":          "GET  /trades/",
            # Data
            "markets":             "GET  /markets/",
            "news":                "GET  /news/",
        },
    }
