"""Episode artefact builder — feature 009 (T020-T030)。

把 trajectory.parquet + eval_summary.json + data/raw/<asset>_daily_*.parquet
組裝成單一 ``episode_detail.json``（``EpisodeDetailEnvelope``），供 005
Inference Service image build 時 COPY 進去。

設計原則：
* Pure：除了 file I/O 與 stdout，沒有副作用。
* Determinism：``json.dumps(..., sort_keys=True, separators=(",",":"),
  ensure_ascii=False, allow_nan=False)`` + 全部 float 先過 ``round(x, 12)``。
* Strict schema：序列化前用 ``EpisodeDetailEnvelope`` Pydantic 模型驗一次。
* SMC overlay：透過 ``smc_features`` 子模組（``detect_swings``/
  ``detect_and_track_fvgs``/``compute_bos_choch``/``build_obs_from_breaks``/
  ``track_ob_lifecycle``）直接展全段事件，不靠 ``state.open_fvgs`` 過濾子集。

對應 spec FR-006~014、tasks T020~T030。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from inference_service.episode_schemas import (
    DetailMeta,
    EpisodeDetail,
    EpisodeDetailEnvelope,
    EpisodeSummary,
    OHLCV,
    RewardCumulativePoint,
    RewardSeries,
    RewardSnapshot,
    SMCOverlay,
    SMCSignals,
    TrajectoryFrame,
    WeightAllocation,
)
from ppo_training.trajectory_writer import ASSET_NAMES_DEFAULT
from smc_features.atr import compute_atr
from smc_features.fvg import detect_and_track_fvgs
from smc_features.ob import build_obs_from_breaks, track_ob_lifecycle
from smc_features.structure import compute_bos_choch
from smc_features.swing import detect_swings
from smc_features.types import SMCFeatureParams

# Risk-On / Risk-Off / Cash bucket（對齊 docs/proposed_design.md）
RISK_ON_ASSETS: tuple[str, ...] = ("NVDA", "AMD", "TSM", "MU")
RISK_OFF_ASSETS: tuple[str, ...] = ("GLD", "TLT")

# SMC warmup：往前多吃 60 個交易日，避免 swing/ATR 在 episode 起始日仍 NaN。
_SMC_WARMUP_BARS = 60


def _round12(value: float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and (np.isnan(value) or np.isinf(value)):
        return None
    return round(float(value), 12)


def _find_asset_parquet(data_root: Path, asset: str) -> Path:
    matches = sorted(
        p
        for p in data_root.glob(f"{asset.lower()}_daily_*.parquet")
        if not p.name.endswith(".meta.json")
    )
    if not matches:
        raise FileNotFoundError(
            f"找不到 {asset} 的 OHLCV parquet（pattern: {asset.lower()}_daily_*.parquet）"
        )
    if len(matches) > 1:
        raise ValueError(f"{asset} 多個 parquet 撞名：{[p.name for p in matches]}")
    return matches[0]


def _load_asset_ohlc(data_root: Path, asset: str) -> pd.DataFrame:
    path = _find_asset_parquet(data_root, asset)
    df = pd.read_parquet(path)
    # 確保 DatetimeIndex（loader 通常會保證；這裡 defensive）
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df.sort_index()


def _slice_for_smc(
    df: pd.DataFrame, episode_dates: Sequence[pd.Timestamp]
) -> pd.DataFrame:
    """切出 [warmup_start, episode_end] 區段，給 SMC pipeline 用。"""
    end = episode_dates[-1]
    # warmup_start: 往前找 _SMC_WARMUP_BARS 個交易日
    df_before = df.loc[: episode_dates[0]]
    if len(df_before) >= _SMC_WARMUP_BARS:
        warmup_start = df_before.index[-_SMC_WARMUP_BARS]
    else:
        warmup_start = df.index[0]
    return df.loc[warmup_start:end].copy()


def _build_smc_overlay(asset_df: pd.DataFrame, params: SMCFeatureParams) -> SMCOverlay:
    """跑 SMC pipeline，回傳 overlay (swings/zigzag/fvgs/obs/breaks)。"""
    if "quality_flag" in asset_df.columns:
        qf = asset_df["quality_flag"].astype("string")
        valid_mask = (qf == "ok").to_numpy(dtype=np.bool_, na_value=False)
    else:
        valid_mask = np.ones(len(asset_df), dtype=np.bool_)

    opens = asset_df["open"].to_numpy(dtype=np.float64, copy=False)
    highs = asset_df["high"].to_numpy(dtype=np.float64, copy=False)
    lows = asset_df["low"].to_numpy(dtype=np.float64, copy=False)
    closes = asset_df["close"].to_numpy(dtype=np.float64, copy=False)
    timestamps = asset_df.index.to_numpy()

    swing_high_marker, swing_low_marker = detect_swings(
        highs, lows, params.swing_length, valid_mask
    )
    atr = compute_atr(highs, lows, closes, params.atr_window, valid_mask)
    _bos, _choch, breaks = compute_bos_choch(
        closes,
        highs,
        lows,
        swing_high_marker,
        swing_low_marker,
        valid_mask,
        timestamps=timestamps.astype("datetime64[ns]"),
    )
    fvgs, _ = detect_and_track_fvgs(
        highs,
        lows,
        closes,
        timestamps,
        valid_mask,
        params.fvg_min_pct,
        atr=atr,
        fvg_min_atr_ratio=params.fvg_min_atr_ratio,
    )
    obs_pre = build_obs_from_breaks(
        breaks=breaks,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=timestamps,
        valid_mask=valid_mask,
        ob_lookback_bars=params.ob_lookback_bars,
    )
    obs, _, _ = track_ob_lifecycle(
        obs=obs_pre,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        timestamps=timestamps,
        valid_mask=valid_mask,
        atr=atr,
    )

    # swings → SwingPoint list（高 + 低 合併排序）
    swings: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        if swing_high_marker[i]:
            swings.append(
                {
                    "time": pd.Timestamp(ts).strftime("%Y-%m-%d"),
                    "price": _round12(float(highs[i])),
                    "kind": "high",
                    "barIndex": int(i),
                }
            )
        if swing_low_marker[i]:
            swings.append(
                {
                    "time": pd.Timestamp(ts).strftime("%Y-%m-%d"),
                    "price": _round12(float(lows[i])),
                    "kind": "low",
                    "barIndex": int(i),
                }
            )
    swings.sort(key=lambda s: (s["barIndex"], s["kind"]))
    # zigzag = swings 的順序版本（MVP 直接同一份；前端可後加去抖）
    zigzag = list(swings)

    fvg_list = [
        {
            "from": pd.Timestamp(f.formation_timestamp).strftime("%Y-%m-%d"),
            "to": (
                pd.Timestamp(f.fill_timestamp).strftime("%Y-%m-%d")
                if f.fill_timestamp is not None
                else pd.Timestamp(timestamps[-1]).strftime("%Y-%m-%d")
            ),
            "top": _round12(f.top),
            "bottom": _round12(f.bottom),
            "direction": f.direction,
            "filled": bool(f.is_filled),
        }
        for f in fvgs
    ]

    ob_list = [
        {
            "from": pd.Timestamp(o.formation_timestamp).strftime("%Y-%m-%d"),
            "to": (
                pd.Timestamp(o.invalidation_timestamp).strftime("%Y-%m-%d")
                if o.invalidation_timestamp is not None
                else pd.Timestamp(timestamps[min(o.expiry_bar_index, len(timestamps) - 1)]).strftime("%Y-%m-%d")
            ),
            "top": _round12(o.top),
            "bottom": _round12(o.bottom),
            "direction": o.direction,
            "invalidated": bool(o.invalidated),
        }
        for o in obs
    ]

    break_list = [
        {
            "time": pd.Timestamp(b.time).strftime("%Y-%m-%d"),
            "anchorTime": pd.Timestamp(b.anchor_swing_time).strftime("%Y-%m-%d"),
            "price": _round12(float(b.anchor_swing_price)),
            "breakClose": _round12(float(b.break_price)),
            "kind": b.kind,
        }
        for b in breaks
    ]

    return SMCOverlay.model_validate(
        {
            "swings": swings,
            "zigzag": zigzag,
            "fvgs": fvg_list,
            "obs": ob_list,
            "breaks": break_list,
        }
    )


def _row_to_weight_allocation(row: pd.Series, asset_names: tuple[str, ...]) -> WeightAllocation:
    asset_with_cash = (*asset_names, "CASH")
    per_asset = {a: _round12(float(row[f"weight_{a}"])) for a in asset_with_cash}
    risk_on = sum(per_asset[a] for a in RISK_ON_ASSETS if a in per_asset)
    risk_off = sum(per_asset[a] for a in RISK_OFF_ASSETS if a in per_asset)
    cash = per_asset.get("CASH", 0.0)
    return WeightAllocation(
        riskOn=_round12(risk_on),
        riskOff=_round12(risk_off),
        cash=_round12(cash),
        perAsset={k: v for k, v in per_asset.items() if v is not None},
    )


def _row_to_reward_snapshot(row: pd.Series) -> RewardSnapshot:
    return RewardSnapshot(
        total=_round12(float(row["reward_total"])),
        returnComponent=_round12(float(row["reward_return"])),
        drawdownPenalty=_round12(max(0.0, float(row["reward_drawdown_penalty"]))),
        costPenalty=_round12(max(0.0, float(row["reward_cost_penalty"]))),
    )


def _row_to_smc_signals(row: pd.Series) -> SMCSignals:
    fvg_pct = row.get("smc_fvg_distance_pct")
    ob_dist = row.get("smc_ob_distance_ratio")
    return SMCSignals(
        bos=int(row["smc_bos"]),
        choch=int(row["smc_choch"]),
        fvgDistancePct=(
            None
            if (fvg_pct is None or (isinstance(fvg_pct, float) and np.isnan(fvg_pct)))
            else _round12(float(fvg_pct))
        ),
        obTouching=bool(row["smc_ob_touching"]),
        obDistanceRatio=(
            None
            if (ob_dist is None or (isinstance(ob_dist, float) and np.isnan(ob_dist)))
            else _round12(float(ob_dist))
        ),
    )


def _build_ohlcv(asset_df: pd.DataFrame, date: pd.Timestamp) -> OHLCV | None:
    if date not in asset_df.index:
        return None
    bar = asset_df.loc[date]
    return OHLCV(
        open=_round12(float(bar["open"])),
        high=_round12(float(bar["high"])),
        low=_round12(float(bar["low"])),
        close=_round12(float(bar["close"])),
        volume=_round12(float(bar["volume"])),
    )


def _compute_max_drawdown_pct(navs: np.ndarray) -> float:
    if len(navs) == 0:
        return 0.0
    peak = np.maximum.accumulate(navs)
    dd = (peak - navs) / peak
    return float(np.max(dd) * 100)


def _drawdown_pct_at(navs: np.ndarray, idx: int) -> float:
    """從起始到 idx 的 NAV peak 推 drawdown_pct（≥ 0）。"""
    if idx == 0:
        return 0.0
    peak = float(np.max(navs[: idx + 1]))
    if peak <= 0:
        return 0.0
    return max(0.0, (peak - float(navs[idx])) / peak * 100)


def build_episode_artifact(
    *,
    run_dir: Path,
    data_root: Path,
    output_path: Path,
    asset_names: tuple[str, ...] = ASSET_NAMES_DEFAULT,
    smc_params: SMCFeatureParams | None = None,
    policy_id: str | None = None,
) -> Path:
    """組 episode artefact 並寫成 ``episode_detail.json``。

    Args:
        run_dir: 含 ``trajectory.parquet`` + ``eval_summary.json`` 的目錄
            （通常為 ``runs/<run_id>/eval_oos``）。
        data_root: 含 6 檔 ``<asset>_daily_*.parquet`` 的目錄。
        output_path: 輸出 JSON 的完整路徑。
        asset_names: 6 檔資產代碼（順序對應 trajectory 的 weight_/close_ 欄位）。
        smc_params: SMC 特徵參數；省略時用 ``SMCFeatureParams()`` 預設。
        policy_id: 對齊 005 policies endpoint 的 ID；省略時取 run_dir 上層名稱。

    Returns:
        實際寫出的路徑（== ``output_path``）。

    Raises:
        FileNotFoundError: trajectory.parquet / eval_summary.json / 任一資產
            parquet 找不到。
        pydantic.ValidationError: 組出來的 payload 不符合契約。
    """
    if smc_params is None:
        smc_params = SMCFeatureParams()

    traj_path = run_dir / "trajectory.parquet"
    summary_path = run_dir / "eval_summary.json"
    if not traj_path.exists():
        raise FileNotFoundError(f"trajectory.parquet 不存在：{traj_path}")
    if not summary_path.exists():
        raise FileNotFoundError(f"eval_summary.json 不存在：{summary_path}")

    df = pd.read_parquet(traj_path).reset_index(drop=True)
    summary_data = json.loads(summary_path.read_text(encoding="utf-8"))

    n_frames = len(df)
    if n_frames < 2:
        raise ValueError(f"trajectory 太短：{n_frames} frames（至少 2）")

    # episode 日期序列（含 step=0 起始 frame）
    episode_dates = pd.to_datetime(df["date"]).tolist()

    # 每資產載入 OHLCV，切 SMC 視窗，跑 pipeline
    asset_full: dict[str, pd.DataFrame] = {}
    smc_overlay_by_asset: dict[str, SMCOverlay] = {}
    for asset in asset_names:
        full_df = _load_asset_ohlc(data_root, asset)
        smc_window = _slice_for_smc(full_df, episode_dates)
        smc_overlay_by_asset[asset] = _build_smc_overlay(smc_window, smc_params)
        asset_full[asset] = full_df

    # NAV / drawdown
    navs = df["nav"].to_numpy(dtype=np.float64)

    # trajectory frames
    trajectory_frames: list[TrajectoryFrame] = []
    for i in range(n_frames):
        row = df.iloc[i]
        date_ts = pd.Timestamp(episode_dates[i])
        ohlc_per_asset: dict[str, OHLCV] = {}
        for asset in asset_names:
            ohlc = _build_ohlcv(asset_full[asset], date_ts)
            if ohlc is None:
                # 資料缺：前向填補（最近一根）
                back = asset_full[asset].loc[:date_ts]
                if len(back) == 0:
                    raise ValueError(
                        f"{asset} 在 {date_ts.date()} 之前沒有任何 OHLCV bar"
                    )
                last_date = back.index[-1]
                ohlc = _build_ohlcv(asset_full[asset], last_date)
                assert ohlc is not None
            ohlc_per_asset[asset] = ohlc

        # 第一根的 ohlcv 取 NVDA（與 viewmodel 約定相同；前端用 ohlcvByAsset）
        primary_ohlc = ohlc_per_asset[asset_names[0]]

        frame = TrajectoryFrame(
            timestamp=date_ts.strftime("%Y-%m-%d"),
            step=int(row["step"]),
            weights=_row_to_weight_allocation(row, asset_names),
            nav=_round12(float(row["nav"])),
            drawdownPct=_round12(_drawdown_pct_at(navs, i)),
            reward=_row_to_reward_snapshot(row),
            smcSignals=_row_to_smc_signals(row),
            ohlcv=primary_ohlc,
            ohlcvByAsset=ohlc_per_asset,
            action={
                "raw": [
                    _round12(float(row[f"action_raw_{j}"])) for j in range(7)
                ],
                "normalized": [
                    _round12(float(row[f"action_normalized_{j}"])) for j in range(7)
                ],
                "logProb": _round12(float(row["action_log_prob"])),
                "entropy": _round12(float(row["action_entropy"])),
            },
        )
        trajectory_frames.append(frame)

    # rewardBreakdown.byStep + cumulative
    by_step: list[RewardSnapshot] = [f.reward for f in trajectory_frames]
    cum_total = 0.0
    cum_return = 0.0
    cum_dd = 0.0
    cum_cost = 0.0
    cumulative: list[RewardCumulativePoint] = []
    for i, snap in enumerate(by_step):
        cum_total += snap.total
        cum_return += snap.returnComponent
        cum_dd += snap.drawdownPenalty
        cum_cost += snap.costPenalty
        cumulative.append(
            RewardCumulativePoint(
                step=max(1, i),  # contract: step ≥ 1；i=0 時也標 1
                cumulativeTotal=_round12(cum_total),
                cumulativeReturn=_round12(cum_return),
                cumulativeDrawdownPenalty=_round12(max(0.0, cum_dd)),
                cumulativeCostPenalty=_round12(max(0.0, cum_cost)),
            )
        )
    reward_series = RewardSeries(byStep=by_step, cumulative=cumulative)

    # summary
    run_id = policy_id or run_dir.parent.name
    summary = EpisodeSummary(
        id=run_id,
        policyId=run_id,
        startDate=episode_dates[0].strftime("%Y-%m-%d"),
        endDate=episode_dates[-1].strftime("%Y-%m-%d"),
        nSteps=int(summary_data.get("n_steps", n_frames - 1)),
        initialNav=_round12(float(summary_data.get("initial_nav", navs[0]))),
        finalNav=_round12(float(summary_data.get("final_nav", navs[-1]))),
        cumulativeReturnPct=_round12(
            float(summary_data.get("cumulative_return_pct", (navs[-1] - 1.0) * 100))
        ),
        annualizedReturnPct=_round12(
            float(summary_data.get("annualized_return_pct", 0.0))
        ),
        maxDrawdownPct=_round12(
            max(
                0.0,
                float(summary_data.get("max_drawdown_pct", _compute_max_drawdown_pct(navs))),
            )
        ),
        sharpeRatio=_round12(float(summary_data.get("sharpe_ratio", 0.0))),
        sortinoRatio=_round12(float(summary_data.get("sortino_ratio", 0.0))),
        includeSmc=bool(summary_data.get("include_smc", True)),
    )

    detail = EpisodeDetail(
        summary=summary,
        trajectoryInline=trajectory_frames,
        rewardBreakdown=reward_series,
        smcOverlayByAsset=smc_overlay_by_asset,
    )

    # meta — checksum 在 evaluate.py 端寫入；artefact 自身只記 generatedAt
    # 但 generatedAt 為 wall clock，會破壞 byte-identical。對策：當環境變數
    # ``EPISODE_ARTEFACT_FROZEN_TIME`` 存在時改用該值；否則用 trajectory.parquet
    # 的 mtime 對應的 UTC ISO（同檔同時間 → 同字串）。
    import os
    frozen = os.environ.get("EPISODE_ARTEFACT_FROZEN_TIME")
    if frozen:
        generated_at = frozen
    else:
        # 用 trajectory.parquet 的 SHA-256 前綴對應的 deterministic ISO 時間
        # —— 同檔內容 → 同 hash → 同字串。
        h = hashlib.sha256(traj_path.read_bytes()).hexdigest()[:8]
        # 把 hash 轉成 fake epoch 偏移（0 ~ 2^32 秒）以維持 ISO 格式。
        offset = int(h, 16) % (10**8)
        generated_at = datetime.fromtimestamp(offset, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    envelope = EpisodeDetailEnvelope(
        data=detail,
        meta=DetailMeta(
            generatedAt=generated_at,
            evaluatorVersion=summary_data.get("evaluator_version"),
            policyChecksum=summary_data.get("policy_checksum"),
            dataChecksum=summary_data.get("data_checksum"),
        ),
    )

    payload = envelope.model_dump(mode="json", by_alias=True)
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(text.encode("utf-8"))
    return output_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="把 PPO OOS evaluator 跑出來的 trajectory + 6 資產 OHLC 組成 episode_detail.json",
    )
    parser.add_argument("--run-dir", type=Path, required=True, help="含 trajectory.parquet 的目錄")
    parser.add_argument("--data-root", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--output", type=Path, required=True, help="episode_detail.json 寫出路徑"
    )
    parser.add_argument("--policy-id", type=str, default=None)
    args = parser.parse_args(argv)

    out = build_episode_artifact(
        run_dir=args.run_dir,
        data_root=args.data_root,
        output_path=args.output,
        policy_id=args.policy_id,
    )
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    size_kb = out.stat().st_size / 1024
    print(f"wrote {out}  sha256={sha}  size={size_kb:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
