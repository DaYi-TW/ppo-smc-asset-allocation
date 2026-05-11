"""LiveFrameBuilder — T018 真實 FrameBuilder（取代 sentinel）。

對應 spec 010 FR-007 (daily pipeline) + Constitution Principle III (reward function 沿用)。

實作策略：複用既有 OOS evaluator 邏輯。

    1. 用 ``PortfolioEnvConfig(end_date=today)`` 建 env — 內部 data_loader 會自然
       clip 到 ``data/raw`` 實際有的最後交易日；若資料只到 2026-04-29 而 today 是
       2026-05-11，env 仍合法（episode 跑到 04-29 終止）。
    2. PPO policy.predict 走完整段 episode（與 005 handler 相同 warmup pattern）。
    3. 蒐集 ``TrajectoryRecord`` list（與 evaluate.py 相同 schema）。
    4. **僅保留** ``date >= start_anchor`` 的 frames（Live 起始 = OOS 結束 +1）。
       若 start_anchor 落在 env 最後一根之後 → 強制保留最後一根作為 anchor frame
       （SC-001：首次 refresh 至少 1 frame）。
    5. 寫 trajectory.parquet + eval_summary.json 到 ``tmp`` 目錄。
    6. 呼叫 ``scripts.build_episode_artifact.build_episode_artifact(...)`` 組
       ``EpisodeDetail`` — SMC overlay 用 008 ``smc_features`` pipeline 全段重算。
    7. 改寫 ``summary.id`` / ``summary.policyId`` 為 ``<policy_run_id>_live``。

不變式：
    * Reward function ≡ ``portfolio_env.reward.compute_reward_components``
      （env.step 內部呼叫，Constitution III 強制 parity）。
    * Append-only：pipeline `_verify_append_only` 已在 caller 端 check；本 builder
      只負責產 envelope，不需要再驗。
    * SMC overlay 透過 build_episode_artifact 內部 _build_smc_overlay → 重用
      008 batch_compute_events 鏈（FR-004）。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from inference_service.episode_schemas import EpisodeDetail
from live_tracking.pipeline import DataFetchError, InferenceError

logger = logging.getLogger(__name__)

_ENV_FORCE_FETCH_ERROR = "LIVE_TRACKER_FORCE_FETCH_ERROR"


class LiveFrameBuilder:
    """``FrameBuilder`` Protocol 的真實實作。

    Args:
        policy_path: PPO ``final_policy.zip`` 路徑（與 005 handler 同一支）。
        data_root: ``data/raw`` 目錄（六檔 parquet 所在）。
        policy_run_id: Live tracking id 後綴前的 base（``<id>_live``）。
        include_smc: 與訓練時一致；預設 True。
        seed: env reset seed（評估慣用 42）。
    """

    def __init__(
        self,
        *,
        policy_path: Path,
        data_root: Path,
        policy_run_id: str,
        include_smc: bool = True,
        seed: int = 42,
    ) -> None:
        self.policy_path = policy_path
        self.data_root = data_root
        self.policy_run_id = policy_run_id
        self.include_smc = include_smc
        self.seed = seed

    def __call__(
        self,
        *,
        current_envelope: EpisodeDetail | None,
        missing_days: list[date],
        initial_nav: float,
        start_anchor: date,
    ) -> EpisodeDetail:
        # Test hook — let integration tests force DATA_FETCH classification
        # without provisioning a broken yfinance mock (referenced by T057/quickstart §8).
        if os.environ.get(_ENV_FORCE_FETCH_ERROR):
            raise DataFetchError(
                "forced via LIVE_TRACKER_FORCE_FETCH_ERROR (test hook)"
            )

        target_date = missing_days[-1] if missing_days else start_anchor

        try:
            records, summary_payload = self._run_env_to_target(target_date)
        except DataFetchError:
            raise
        except FileNotFoundError as exc:
            # 6 檔 parquet 任一缺 → DATA_FETCH（FR-007 三段式 prefix）
            raise DataFetchError(str(exc)) from exc
        except Exception as exc:
            raise InferenceError(f"env rollout failed: {exc}") from exc

        # Filter to start_anchor onwards; protect SC-001 minimum 1 frame.
        kept = [r for r in records if date.fromisoformat(r.date[:10]) >= start_anchor]
        if not kept:
            kept = [records[-1]]

        # FR-007：env 在 start_anchor 當天 terminate（資料只到 OOS 終點時的常見情況），
        # 整段 live window 只剩 reset frame、沒有任何 transition → EpisodeSummary.nSteps≥1
        # 無法滿足。歸為 DATA_FETCH 失敗（沒有可推進的新交易日資料）。
        if len(kept) < 2:
            last_data_date = records[-1].date[:10] if records else "unknown"
            raise DataFetchError(
                "no new trading-day data beyond start_anchor "
                f"({start_anchor.isoformat()}); env terminated at {last_data_date}"
            )

        # Renumber step within Live window starting at 0.
        # (OOS evaluator numbers from 0 = reset frame；Live 我們也讓視窗第一根是 0。)
        for i, rec in enumerate(kept):
            rec.step = i

        # Patch summary_payload to reflect the Live window only.
        summary_payload = self._patch_summary_for_live(summary_payload, kept)

        envelope = self._build_envelope_via_artifact_builder(
            kept, summary_payload, start_anchor
        )

        # Tag id / policyId as `<policy_run_id>_live` (FR-021 + spec FR-001).
        live_id = f"{self.policy_run_id}_live"
        envelope.summary.id = live_id
        envelope.summary.policyId = live_id

        return envelope

    # ---------- env rollout ----------

    def _run_env_to_target(
        self, target_date: date
    ) -> tuple[list[Any], dict[str, Any]]:
        """Run PortfolioEnv from reset → terminal, return (records, summary).

        ``records`` 與 OOS evaluator 同型（TrajectoryRecord），由 build_episode_artifact
        間接消費（透過 parquet）。
        """
        # 延遲 import：torch / stable_baselines3 啟動慢，且只有 refresh 路徑會用到。
        from stable_baselines3 import PPO  # noqa: PLC0415

        from portfolio_env import PortfolioEnv, PortfolioEnvConfig  # noqa: PLC0415
        from ppo_training.evaluate import (  # noqa: PLC0415
            _make_softmax_wrapper,
            _max_drawdown,
            _sharpe,
            _sortino,
        )
        from ppo_training.trajectory_writer import (  # noqa: PLC0415
            TrajectoryRecord,
            policy_action_log_prob_entropy,
        )

        cfg = PortfolioEnvConfig(
            data_root=self.data_root,
            include_smc=self.include_smc,
            start_date=None,
            end_date=target_date,
        )
        base_env = PortfolioEnv(cfg)
        env = _make_softmax_wrapper()(base_env)

        if not self.policy_path.exists():
            raise FileNotFoundError(f"policy not found: {self.policy_path}")

        model = PPO.load(str(self.policy_path), env=env, device="auto")

        obs, info = env.reset(seed=self.seed)

        env_data = base_env._env_data  # noqa: SLF001
        env_dates = [str(d)[:10] for d in env_data.trading_days.astype("datetime64[D]")]
        env_date_to_index = {d: i for i, d in enumerate(env_dates)}
        smc_feat_nvda = (
            env_data.smc_features.get("NVDA")
            if env_data.smc_features is not None
            else None
        )

        def _smc_for(d: str) -> tuple[int, int, float | None, bool, float | None]:
            if smc_feat_nvda is None:
                return 0, 0, None, False, None
            idx = env_date_to_index.get(d[:10])
            if idx is None:
                return 0, 0, None, False, None
            row = smc_feat_nvda[idx]
            bos = int(row[0])
            choch = int(row[1])
            fvg = float(row[2])
            ob_touch = bool(row[3] >= 0.5)
            ob_dist = float(row[4])
            fvg_v: float | None = (
                None if (np.isnan(fvg) or fvg == 0.0) else fvg
            )
            ob_dist_v: float | None = (
                None if (np.isnan(ob_dist) or ob_dist == 0.0) else ob_dist
            )
            return bos, choch, fvg_v, ob_touch, ob_dist_v

        def _closes_for(d: str) -> list[float]:
            idx = env_date_to_index.get(d[:10])
            if idx is None:
                return [float("nan")] * env_data.closes.shape[1]
            return [float(v) for v in env_data.closes[idx]]

        initial_date = info["date"]
        initial_weights = [float(w) for w in info["weights"]]
        initial_smc = _smc_for(initial_date)
        records: list[Any] = [
            TrajectoryRecord(
                date=initial_date,
                step=0,
                nav=float(info["nav"]),
                log_return=0.0,
                weights=initial_weights,
                reward_total=0.0,
                reward_return=0.0,
                reward_drawdown_penalty=0.0,
                reward_cost_penalty=0.0,
                action_raw=initial_weights,
                action_normalized=initial_weights,
                action_log_prob=0.0,
                action_entropy=0.0,
                smc_bos=initial_smc[0],
                smc_choch=initial_smc[1],
                smc_fvg_distance_pct=initial_smc[2],
                smc_ob_touching=initial_smc[3],
                smc_ob_distance_ratio=initial_smc[4],
                closes=_closes_for(initial_date),
            )
        ]
        nav_traj: list[float] = [float(info["nav"])]
        log_returns: list[float] = []

        step_count = 0
        while True:
            action, _ = model.predict(obs, deterministic=True)
            try:
                log_prob, entropy = policy_action_log_prob_entropy(model, obs, action)
            except Exception:  # noqa: BLE001
                log_prob, entropy = 0.0, 0.0
            action_raw = np.asarray(action, dtype=np.float32).tolist()

            obs, reward_scalar, terminated, truncated, info = env.step(action)
            step_count += 1
            nav_traj.append(float(info["nav"]))
            rc = info["reward_components"]
            log_returns.append(float(rc["log_return"]))
            smc = _smc_for(info["date"])
            records.append(
                TrajectoryRecord(
                    date=info["date"],
                    step=step_count,
                    nav=float(info["nav"]),
                    log_return=float(rc["log_return"]),
                    weights=[float(w) for w in info["weights"]],
                    reward_total=float(reward_scalar),
                    reward_return=float(rc["log_return"]),
                    reward_drawdown_penalty=float(rc["drawdown_penalty"]),
                    reward_cost_penalty=float(rc["turnover_penalty"]),
                    action_raw=action_raw,
                    action_normalized=[float(w) for w in info["action_processed"]],
                    action_log_prob=log_prob,
                    action_entropy=entropy,
                    smc_bos=smc[0],
                    smc_choch=smc[1],
                    smc_fvg_distance_pct=smc[2],
                    smc_ob_touching=smc[3],
                    smc_ob_distance_ratio=smc[4],
                    closes=_closes_for(info["date"]),
                )
            )
            if terminated or truncated:
                break

        nav_arr = np.asarray(nav_traj, dtype=np.float64)
        log_ret_arr = np.asarray(log_returns, dtype=np.float64)
        final_nav = float(nav_arr[-1])
        initial_nav_val = float(nav_arr[0])
        cumulative_return = (final_nav / initial_nav_val) - 1.0
        n_steps = log_ret_arr.size
        annualized_return = (
            (final_nav / initial_nav_val) ** (252.0 / n_steps) - 1.0
            if n_steps > 0
            else 0.0
        )
        summary_payload = {
            "policy_path": str(self.policy_path),
            "data_root": str(self.data_root),
            "include_smc": self.include_smc,
            "deterministic": True,
            "seed": self.seed,
            "n_steps": int(n_steps),
            "initial_nav": initial_nav_val,
            "final_nav": final_nav,
            "cumulative_return_pct": float(cumulative_return * 100),
            "annualized_return_pct": float(annualized_return * 100),
            "max_drawdown_pct": float(_max_drawdown(nav_arr) * 100),
            "sharpe_ratio": float(_sharpe(log_ret_arr)),
            "sortino_ratio": float(_sortino(log_ret_arr)),
            "evaluator_version": "live_tracker/0.1",
        }
        return records, summary_payload

    # ---------- patch summary for live window ----------

    @staticmethod
    def _patch_summary_for_live(
        summary: dict[str, Any], live_records: list[Any]
    ) -> dict[str, Any]:
        from ppo_training.evaluate import _max_drawdown, _sharpe, _sortino  # noqa: PLC0415

        nav_arr = np.asarray([r.nav for r in live_records], dtype=np.float64)
        log_returns = np.asarray(
            [r.log_return for r in live_records[1:]], dtype=np.float64
        )
        initial_nav = float(nav_arr[0])
        final_nav = float(nav_arr[-1])
        n_steps = int(log_returns.size)
        cum_return = (final_nav / initial_nav) - 1.0 if initial_nav > 0 else 0.0
        annualized = (
            (final_nav / initial_nav) ** (252.0 / n_steps) - 1.0
            if n_steps > 0 and initial_nav > 0
            else 0.0
        )
        patched = dict(summary)
        patched["n_steps"] = n_steps
        patched["initial_nav"] = initial_nav
        patched["final_nav"] = final_nav
        patched["cumulative_return_pct"] = float(cum_return * 100)
        patched["annualized_return_pct"] = float(annualized * 100)
        patched["max_drawdown_pct"] = float(_max_drawdown(nav_arr) * 100)
        patched["sharpe_ratio"] = float(_sharpe(log_returns))
        patched["sortino_ratio"] = float(_sortino(log_returns))
        return patched

    # ---------- build envelope via existing artifact builder ----------

    @staticmethod
    def _resolve_scripts_root() -> Path:
        env_override = os.environ.get("LIVE_TRACKER_SCRIPTS_ROOT")
        if env_override:
            return Path(env_override)
        cwd_candidate = Path.cwd() / "scripts"
        if (cwd_candidate / "build_episode_artifact.py").exists():
            return cwd_candidate
        # Source-tree fallback：repo 內跑 pytest 時 __file__ 還在 src/ 下。
        return Path(__file__).resolve().parents[2] / "scripts"

    def _build_envelope_via_artifact_builder(
        self,
        records: list[Any],
        summary_payload: dict[str, Any],
        start_anchor: date,
    ) -> EpisodeDetail:
        from ppo_training.trajectory_writer import (  # noqa: PLC0415
            write_trajectory_parquet,
        )

        # scripts/ 不在 default sys.path（service container 走 src layout）— 動態加。
        # __file__ 在 docker image 內會解析到 site-packages/（pip install copy 過去），
        # 與 repo 的 src/ 樹脫鉤。優先：env var LIVE_TRACKER_SCRIPTS_ROOT > cwd/scripts >
        # source-tree relative。container 的 WORKDIR=/app + `COPY scripts/ /app/scripts/`
        # 保證 cwd/scripts 一定存在。
        scripts_root = self._resolve_scripts_root()
        if str(scripts_root) not in sys.path:
            sys.path.insert(0, str(scripts_root))
        from build_episode_artifact import build_episode_artifact  # noqa: PLC0415

        with tempfile.TemporaryDirectory(prefix="live_builder_") as tmpdir:
            tmp_path = Path(tmpdir)
            run_dir = tmp_path / "eval_live"
            run_dir.mkdir(parents=True, exist_ok=True)

            write_trajectory_parquet(records, run_dir / "trajectory.parquet")
            (run_dir / "eval_summary.json").write_text(
                json.dumps(summary_payload, indent=2),
                encoding="utf-8",
            )

            output_path = tmp_path / "live_tracking.json"
            build_episode_artifact(
                run_dir=run_dir,
                data_root=self.data_root,
                output_path=output_path,
                policy_id=self.policy_run_id,
            )

            envelope_json = json.loads(output_path.read_text(encoding="utf-8"))
            # envelope_json 是 {"data": EpisodeDetail, "meta": ...} 包裝
            detail = EpisodeDetail.model_validate(envelope_json["data"])

        _ = start_anchor  # 目前 anchor 由 caller filter；保留 hook 給未來 incremental
        return detail


__all__ = ["LiveFrameBuilder"]
