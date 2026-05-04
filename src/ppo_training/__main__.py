"""``python -m ppo_training`` 入口 — 轉發至 ``train.main()``。"""

from __future__ import annotations

from ppo_training.train import main

if __name__ == "__main__":
    raise SystemExit(main())
