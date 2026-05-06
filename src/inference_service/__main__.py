"""``python -m inference_service`` 入口 — uvicorn boot。

對應 spec FR-014：scheduler 與 HTTP server 同 process / 同 container。
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    """啟動 inference service（uvicorn + FastAPI + APScheduler）。

    Phase 1 skeleton：先 stub 回 0；T026 由 Phase 3 實作 uvicorn.run。
    """
    # 後續由 T026 填入：
    #   from inference_service.app import create_app
    #   from inference_service.config import ServiceConfig
    #   import uvicorn
    #   cfg = ServiceConfig()
    #   uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port)
    print("[inference-service] skeleton — implement at T026", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
