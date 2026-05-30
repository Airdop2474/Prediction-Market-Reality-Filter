# app/api/router.py — v0.3.0
from fastapi import APIRouter
from app.api.routes import (
    markets, news, analysis, calibration,
    backtest, resolve, trades, signal_accuracy,
)

api_router = APIRouter()

api_router.include_router(markets.router,          prefix="/markets",          tags=["Markets"])
api_router.include_router(news.router,             prefix="/news",             tags=["News"])
api_router.include_router(analysis.router,         prefix="/analysis",         tags=["Analysis"])
api_router.include_router(calibration.router,      prefix="/calibration",      tags=["Calibration"])
api_router.include_router(backtest.router,         prefix="/backtest",         tags=["Backtest"])
api_router.include_router(resolve.router,          prefix="/resolve",          tags=["Resolve"])
api_router.include_router(trades.router,           prefix="/trades",           tags=["Trades"])
api_router.include_router(signal_accuracy.router,  prefix="/signals/accuracy", tags=["Signals"])
