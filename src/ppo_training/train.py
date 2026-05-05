"""PPO 訓練主迴圈（spec 004 MVP）— 最小可行訓練 + artefact 寫出。

對應 spec 004 之：

* US1 P1（FR-001、FR-006、FR-007）：CLI entrypoint、yaml-style flags、run 目錄。
* US3 P2（FR-006 env.include_smc）：``--no-smc`` flag 切換 ablation。
* FR-008 metadata：寫入 git commit、套件版本、Parquet hash、seed、總 step。
* FR-010 metrics.csv：每 N step 一列，含 reward 三項分量 + loss/entropy/explained_variance。
* FR-013 NaN/Inf 偵測：sb3 內建 logger 出現 NaN 即由 callback 中止。
* FR-017 PRNG 同步：env seed + sb3 PPO seed + torch seed + numpy/random global。

不含：multi-seed aggregate（FR-014 / US2）、resume（FR-003 / US4）、
package version pinning gate（FR-018）、t-test compare（FR-015）—
本檔為 MVP，這些功能於 spec 004 完整實作時補足。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import random
import socket
import subprocess
import sys
from collections import deque
from datetime import date, datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any

import numpy as np

from portfolio_env import PortfolioEnv, PortfolioEnvConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SHORT_HASH_LEN = 7
_METRICS_HEADER = [
    "step",
    "elapsed_seconds",
    "fps",
    "mean_episode_return",
    "mean_episode_length",
    "mean_log_return",
    "mean_drawdown_penalty",
    "mean_turnover_penalty",
    "policy_loss",
    "value_loss",
    "entropy_loss",
    "approx_kl",
    "explained_variance",
    "learning_rate",
]


def _git_short_hash(repo_root: Path) -> str:
    """取得目前 HEAD 的 short commit hash；失敗則回傳 ``"nogit"``。"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()[:_SHORT_HASH_LEN] or "nogit"
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return "nogit"


def _git_dirty(repo_root: Path) -> bool:
    """檢查工作樹是否有未 commit 的修改；無 git 視為 dirty=False。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        return False


def _package_versions() -> dict[str, str]:
    """擷取訓練相關套件版本（FR-008 metadata 指紋）。"""
    pkgs = [
        "numpy",
        "pandas",
        "pyarrow",
        "gymnasium",
        "stable-baselines3",
        "torch",
    ]
    versions: dict[str, str] = {}
    for pkg in pkgs:
        try:
            versions[pkg] = importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            versions[pkg] = "not-installed"
    return versions


def _resolve_device(device: str) -> str:
    """處理 --device 旗標。``cuda`` 不可用時 ``auto`` → cpu，``cuda`` 顯式指定則 raise。"""
    if device == "auto":
        try:
            import torch  # 延遲 import：避免 module top-level 觸發 torch 載入

            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    if device == "cuda":
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "--device cuda 要求 torch 可用，但 torch import 失敗。"
                "請先 `pip install -e .[train]` 或在 Colab cell 執行 `pip install torch`。"
            ) from exc
        if not torch.cuda.is_available():
            raise RuntimeError(
                "--device cuda 但 torch.cuda.is_available()=False；"
                "若無 CUDA 環境請改用 --device cpu 或 --device auto（spec 004 FR-004）。"
            )
        return "cuda"
    if device == "cpu":
        return "cpu"
    raise ValueError(f"未知的 device: {device!r}（合法值：cpu / cuda / auto）")


def _seed_everything(seed: int) -> None:
    """同步 Python random、numpy、torch CPU/CUDA 全域 seed（FR-017 a/b/c/d）。

    003 env 自身的 4 層 seed 由 ``env.reset(seed=seed)`` 處理；本函式專責
    sb3 PPO + torch + numpy global / Python random 之同步。
    """
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        # deterministic 模式：訓練速度會慢，但跨次可重現（FR-009）。
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Custom callback
# ---------------------------------------------------------------------------


def _build_callback(
    metrics_path: Path,
    metrics_freq: int,
    info_buffer_size: int = 100,
) -> Any:
    """建構 sb3 BaseCallback：每 metrics_freq step 寫一列 CSV。

    sb3 內部已有 logger 系統（``self.logger.record(...)``），但 logger 之 dump
    時機由 sb3 控制（每 rollout 結束）；為了 FR-010「每 N step 一列」精確
    語意，這裡用獨立 callback 記 info-level metric。Logger 內 metric 由
    ``self.logger.name_to_value`` 讀取（sb3 內建 API）。
    """
    from stable_baselines3.common.callbacks import BaseCallback

    class _MetricsCSVCallback(BaseCallback):  # type: ignore[misc]
        """每 ``freq`` step 寫一列 CSV；同時偵測 NaN/Inf loss（FR-013）。"""

        def __init__(self, csv_path: Path, freq: int) -> None:
            super().__init__()
            self.csv_path = csv_path
            self.freq = freq
            self._writer: csv.writer | None = None
            self._fh: Any = None
            self._last_dump_step = 0
            # info-level 緩衝（reward 三項分量）— 由每 step env info 累積。
            self._log_return_buf: deque[float] = deque(maxlen=info_buffer_size)
            self._dd_buf: deque[float] = deque(maxlen=info_buffer_size)
            self._turnover_buf: deque[float] = deque(maxlen=info_buffer_size)
            self._start_time = 0.0

        def _on_training_start(self) -> None:
            import time

            self._start_time = time.time()
            self.csv_path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = self.csv_path.open("w", newline="", encoding="utf-8")
            self._writer = csv.writer(self._fh)
            self._writer.writerow(_METRICS_HEADER)
            self._fh.flush()

        def _on_step(self) -> bool:
            # 累積 reward 三項分量（從 VecEnv 各 sub-env 的最新 info）。
            infos = self.locals.get("infos", [])
            for info in infos:
                rc = info.get("reward_components")
                if rc is None:
                    continue
                self._log_return_buf.append(float(rc["log_return"]))
                self._dd_buf.append(float(rc["drawdown_penalty"]))
                self._turnover_buf.append(float(rc["turnover_penalty"]))

            if self.num_timesteps - self._last_dump_step < self.freq:
                return True
            self._last_dump_step = self.num_timesteps
            self._write_row()
            return True

        def _write_row(self) -> None:
            import time

            assert self._writer is not None
            logger = self.model.logger  # sb3 logger 物件
            name_to_value = getattr(logger, "name_to_value", {}) or {}

            # ep_info_buffer 由 sb3 monitor wrapper 維護；裡面是 deque[dict]。
            ep_buffer = getattr(self.model, "ep_info_buffer", None)
            if ep_buffer and len(ep_buffer) > 0:
                mean_return = float(np.mean([ep["r"] for ep in ep_buffer]))
                mean_length = float(np.mean([ep["l"] for ep in ep_buffer]))
            else:
                mean_return = float("nan")
                mean_length = float("nan")

            elapsed = time.time() - self._start_time
            fps = self.num_timesteps / elapsed if elapsed > 0 else 0.0

            def _safe(key: str) -> float:
                v = name_to_value.get(key)
                return float(v) if v is not None else float("nan")

            row = [
                self.num_timesteps,
                round(elapsed, 3),
                round(fps, 2),
                mean_return,
                mean_length,
                float(np.mean(self._log_return_buf)) if self._log_return_buf else float("nan"),
                float(np.mean(self._dd_buf)) if self._dd_buf else float("nan"),
                float(np.mean(self._turnover_buf)) if self._turnover_buf else float("nan"),
                _safe("train/policy_gradient_loss"),
                _safe("train/value_loss"),
                _safe("train/entropy_loss"),
                _safe("train/approx_kl"),
                _safe("train/explained_variance"),
                _safe("train/learning_rate"),
            ]
            # FR-013：NaN/Inf 偵測 — 對 loss 三欄；發現即中止訓練。
            for col_name, idx in (
                ("policy_loss", 8),
                ("value_loss", 9),
                ("entropy_loss", 10),
            ):
                v = row[idx]
                if isinstance(v, float) and (np.isnan(v) is False) and (np.isinf(v)):
                    print(
                        f"[train] FATAL: {col_name}={v} 為 Inf 於 step {self.num_timesteps}，中止訓練。",
                        file=sys.stderr,
                    )
                    self._write_and_flush(row)
                    return  # type: ignore[return-value]

            self._write_and_flush(row)

        def _write_and_flush(self, row: list[Any]) -> None:
            assert self._writer is not None
            self._writer.writerow(row)
            if self._fh is not None:
                self._fh.flush()

        def _on_training_end(self) -> None:
            # 補寫最後一筆（若上次寫入後又跑了部分 step）。
            if self.num_timesteps > self._last_dump_step:
                self._write_row()
            if self._fh is not None:
                self._fh.close()

    return _MetricsCSVCallback(metrics_path, metrics_freq)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ppo_training.train",
        description="PPO 訓練主迴圈（spec 004 MVP）— 訓練 003 PortfolioEnv。",
    )
    p.add_argument(
        "--data-root",
        type=Path,
        default=Path("data/raw"),
        help="002 Parquet 快照目錄（預設 data/raw/）。",
    )
    p.add_argument(
        "--total-timesteps",
        type=int,
        default=100_000,
        help="總訓練 step 數（預設 100k）。",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=42,
        help="訓練 seed（同步 env / sb3 / torch / numpy / random）。",
    )
    p.add_argument(
        "--device",
        choices=("cpu", "cuda", "auto"),
        default="auto",
        help="訓練 device。auto = 有 CUDA 用 CUDA、否則 CPU。",
    )
    p.add_argument(
        "--no-smc",
        action="store_true",
        help="ablation：關閉 SMC 特徵（observation 從 63 維降為 33 維）。",
    )
    p.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=None,
        help="訓練資料起始日（含），ISO 8601 例：2018-01-01。預設 None = 全部資料。",
    )
    p.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=None,
        help="訓練資料結束日（含），ISO 8601 例：2024-12-31。預設 None = 全部資料。",
    )
    p.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="run 目錄（預設 runs/<UTC_timestamp>_<git_hash>_seed<N>/）。",
    )
    p.add_argument(
        "--metrics-freq",
        type=int,
        default=1000,
        help="metrics.csv 寫入頻率（每 N step 一列；預設 1000）。",
    )
    p.add_argument(
        "--learning-rate",
        type=float,
        default=3e-4,
        help="PPO 學習率（sb3 預設 3e-4）。",
    )
    p.add_argument(
        "--n-steps",
        type=int,
        default=2048,
        help="PPO rollout buffer 長度（sb3 預設 2048）。",
    )
    p.add_argument(
        "--batch-size",
        type=int,
        default=64,
        help="PPO mini-batch size（sb3 預設 64）。",
    )
    p.add_argument(
        "--n-epochs",
        type=int,
        default=10,
        help="PPO update epochs per rollout（sb3 預設 10）。",
    )
    p.add_argument(
        "--gamma",
        type=float,
        default=0.99,
        help="discount factor（sb3 預設 0.99）。",
    )
    p.add_argument(
        "--gae-lambda",
        type=float,
        default=0.95,
        help="GAE λ（sb3 預設 0.95）。",
    )
    p.add_argument(
        "--clip-range",
        type=float,
        default=0.2,
        help="PPO clip range（sb3 預設 0.2）。",
    )
    p.add_argument(
        "--ent-coef",
        type=float,
        default=0.0,
        help="entropy 係數（sb3 預設 0.0）。",
    )
    p.add_argument(
        "--vf-coef",
        type=float,
        default=0.5,
        help="value loss 係數（sb3 預設 0.5）。",
    )
    return p


def _resolve_run_dir(repo_root: Path, args: argparse.Namespace) -> Path:
    if args.run_dir is not None:
        return args.run_dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short_hash = _git_short_hash(repo_root)
    name = f"{timestamp}_{short_hash}_seed{args.seed}"
    return repo_root / "runs" / name


def _make_wrappers() -> tuple[type, type]:
    """延遲 import gymnasium 並回傳兩個 wrapper class（避免 module top-level 載入）。"""
    import gymnasium

    class _DataHashesPlainDictWrapper(gymnasium.Wrapper):  # type: ignore[misc]
        """把 ``info['data_hashes']`` 從 ``MappingProxyType`` 換成 plain dict。

        spec 003 的核心 env 為防 mutate 將 ``data_hashes`` 包成 MappingProxyType；
        但 sb3 的 ``DummyVecEnv`` 會對 step return 的 info dict 做 ``copy.deepcopy``，
        而 Python 3.11 內建 deepcopy **不支援** mappingproxy。本 wrapper 在 train
        端轉型，不動核心 env 也不破壞 spec 003 的 immutability 不變式
        （unwrapped env 行為不變）。
        """

        def reset(self, **kwargs: Any) -> Any:
            obs, info = self.env.reset(**kwargs)
            if "data_hashes" in info:
                info["data_hashes"] = dict(info["data_hashes"])
            return obs, info

        def step(self, action: Any) -> Any:
            obs, reward, terminated, truncated, info = self.env.step(action)
            if "data_hashes" in info:
                info["data_hashes"] = dict(info["data_hashes"])
            return obs, reward, terminated, truncated, info

    class _SoftmaxActionWrapper(gymnasium.ActionWrapper):  # type: ignore[misc]
        """把任意實數向量 → softmax → simplex action，並改寫 action_space 為 ℝ^7。

        spec 003 的 ``PortfolioEnv.process_action`` 要求 action 為非負且 sum ≥ 1e-6；
        但 sb3 的 PPO ``MlpPolicy`` 預設用 Gaussian distribution，輸出值不受限
        （可為負、可全 0），直接餵會頻繁觸發 ``ValueError("Action sum near zero")``。
        標準解法：訓練側用 logits ∈ ℝ^7、softmax 後送 env。如此 PPO Gaussian 自由探索，
        env 收到的永遠是合法 simplex。
        """

        def __init__(self, env: Any) -> None:
            super().__init__(env)
            # logits 空間：無界連續、shape 與原 action 相同。
            self.action_space = gymnasium.spaces.Box(
                low=-10.0,
                high=10.0,
                shape=env.action_space.shape,
                dtype=np.float32,
            )

        def action(self, action: np.ndarray) -> np.ndarray:
            # 數值穩定的 softmax：減 max 後 exp + 歸一。
            a = np.asarray(action, dtype=np.float64)
            a = a - a.max()
            ex = np.exp(a)
            simplex = ex / ex.sum()
            return simplex.astype(np.float32)

    return _DataHashesPlainDictWrapper, _SoftmaxActionWrapper


def _build_env(
    data_root: Path,
    include_smc: bool,
    seed: int,
    start_date: date | None = None,
    end_date: date | None = None,
) -> Any:
    """建構單環境並包 softmax wrapper、data-hashes wrapper、Monitor。"""
    from stable_baselines3.common.monitor import Monitor

    DataHashesWrapper, SoftmaxWrapper = _make_wrappers()
    cfg = PortfolioEnvConfig(
        data_root=data_root,
        include_smc=include_smc,
        start_date=start_date,
        end_date=end_date,
    )
    env = PortfolioEnv(cfg)
    env.reset(seed=seed)
    wrapped = DataHashesWrapper(SoftmaxWrapper(env))
    return Monitor(wrapped)


def _write_metadata(
    run_dir: Path,
    args: argparse.Namespace,
    repo_root: Path,
    env: PortfolioEnv,
    device: str,
    utc_start: str,
    utc_end: str,
    final_mean_return: float,
    abort_reason: str | None,
) -> None:
    duration = (
        datetime.fromisoformat(utc_end.replace("Z", "+00:00"))
        - datetime.fromisoformat(utc_start.replace("Z", "+00:00"))
    ).total_seconds()
    metadata = {
        "spec": "004-ppo-training-loop",
        "git_commit_hash": _git_short_hash(repo_root),
        "git_dirty": _git_dirty(repo_root),
        "utc_start": utc_start,
        "utc_end": utc_end,
        "duration_seconds": round(duration, 2),
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "device": device,
        "package_versions": _package_versions(),
        "data_hashes": dict(env._cached_data_hashes),  # MappingProxy → dict
        "seed": args.seed,
        "total_timesteps": args.total_timesteps,
        "include_smc": not args.no_smc,
        "start_date": args.start_date.isoformat() if args.start_date else None,
        "end_date": args.end_date.isoformat() if args.end_date else None,
        "ppo_hyperparams": {
            "learning_rate": args.learning_rate,
            "n_steps": args.n_steps,
            "batch_size": args.batch_size,
            "n_epochs": args.n_epochs,
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "clip_range": args.clip_range,
            "ent_coef": args.ent_coef,
            "vf_coef": args.vf_coef,
        },
        "final_mean_episode_return": final_mean_return,
        "abort_reason": abort_reason,
        "warnings": [],
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # repo_root：從 CWD 往上找 pyproject.toml；找不到則用 CWD。
    repo_root = Path.cwd()
    while repo_root != repo_root.parent and not (repo_root / "pyproject.toml").exists():
        repo_root = repo_root.parent

    device = _resolve_device(args.device)
    _seed_everything(args.seed)

    run_dir = _resolve_run_dir(repo_root, args)
    run_dir.mkdir(parents=True, exist_ok=True)
    print(f"[train] run_dir = {run_dir}")
    print(f"[train] device  = {device}")
    print(f"[train] seed    = {args.seed}")
    print(f"[train] include_smc = {not args.no_smc}")

    # 建環境
    env = _build_env(
        args.data_root,
        include_smc=not args.no_smc,
        seed=args.seed,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    # Monitor → DataHashesPlainDictWrapper → PortfolioEnv；用 .unwrapped 直取最底層。
    portfolio_env: PortfolioEnv = env.unwrapped  # type: ignore[assignment]

    # 建 PPO
    from stable_baselines3 import PPO

    tb_dir = run_dir / "tensorboard"
    model = PPO(
        policy="MlpPolicy",
        env=env,
        learning_rate=args.learning_rate,
        n_steps=args.n_steps,
        batch_size=args.batch_size,
        n_epochs=args.n_epochs,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
        clip_range=args.clip_range,
        ent_coef=args.ent_coef,
        vf_coef=args.vf_coef,
        verbose=1,
        seed=args.seed,
        device=device,
        tensorboard_log=str(tb_dir),
    )

    # Callback
    metrics_path = run_dir / "metrics.csv"
    callback = _build_callback(metrics_path, args.metrics_freq)

    # 訓練
    utc_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    abort_reason: str | None = None
    try:
        model.learn(
            total_timesteps=args.total_timesteps,
            callback=callback,
            tb_log_name="ppo",
            progress_bar=False,
        )
    except KeyboardInterrupt:
        abort_reason = "keyboard_interrupt"
        print("[train] 收到 SIGINT，存檔後結束。", file=sys.stderr)
    except Exception as exc:
        abort_reason = f"exception: {type(exc).__name__}: {exc}"
        print(f"[train] FATAL: {abort_reason}", file=sys.stderr)
        # 仍然嘗試存 partial checkpoint。
    utc_end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 存 final policy
    final_policy_path = run_dir / "final_policy.zip"
    model.save(str(final_policy_path))
    print(f"[train] 已寫出 {final_policy_path}")

    # 取 final mean episode return（sb3 ep_info_buffer 維護）。
    ep_buffer = getattr(model, "ep_info_buffer", None)
    if ep_buffer and len(ep_buffer) > 0:
        final_mean_return = float(np.mean([ep["r"] for ep in ep_buffer]))
    else:
        final_mean_return = float("nan")

    _write_metadata(
        run_dir=run_dir,
        args=args,
        repo_root=repo_root,
        env=portfolio_env,
        device=device,
        utc_start=utc_start,
        utc_end=utc_end,
        final_mean_return=final_mean_return,
        abort_reason=abort_reason,
    )
    print(f"[train] 已寫出 {run_dir / 'metadata.json'}")
    print(f"[train] final_mean_episode_return = {final_mean_return:.6f}")
    print(f"[train] tensorboard --logdir {tb_dir}")

    env.close()
    return 0 if abort_reason is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
