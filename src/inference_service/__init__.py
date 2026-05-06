"""推理服務（005-inference-service）— C-lite 版。

把 ``src/ppo_training/predict.py`` 包裝成 FastAPI 微服務 + APScheduler 每日 cron
+ Redis pub/sub 廣播。對應 spec ``specs/005-inference-service/spec.md``（2026-05-06
重寫版本）。

模組結構：
    config.py     — ServiceConfig（env var 載入 + 啟動驗證）
    schemas.py    — PredictionPayload Pydantic model（對齊 predict.py JSON）
    handler.py    — run_inference() 共用 handler（asyncio.Lock 互斥）
    scheduler.py  — APScheduler cron + DST + 失敗不停 scheduler
    redis_io.py   — async Redis publisher + LatestCache
    app.py        — FastAPI app factory + 4 endpoints
    __main__.py   — uvicorn entry: ``python -m inference_service``
"""

from __future__ import annotations

__version__ = "0.1.0"
