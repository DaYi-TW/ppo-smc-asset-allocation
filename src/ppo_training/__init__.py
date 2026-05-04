"""PPO 訓練主迴圈（spec 004-ppo-training-loop，最小可行版本）。

本模組為 003 ``PortfolioEnv`` 的訓練 wrapper：使用 stable-baselines3 PPO，
產出 ``runs/<timestamp>_<git_hash>_seed<N>/`` 目錄含：

* ``final_policy.zip`` — sb3 PPO checkpoint（005 推理服務輸入）。
* ``metrics.csv`` — 訓練曲線（step、reward 三項分量、loss、entropy …）。
* ``metadata.json`` — 訓練 metadata（git commit、Parquet hash、套件版本）。
* ``tensorboard/`` — TensorBoard event files。

CLI 入口：``python -m ppo_training.train --help``。

注意：此版本為 spec 004 之 MVP（僅含 US1 P1 + 部分 US3 ablation 支援），
不含 multi-seed aggregate / checkpoint resume / Welch t-test 比較
（後續版本補足）。
"""

from __future__ import annotations

__version__ = "0.1.0"
