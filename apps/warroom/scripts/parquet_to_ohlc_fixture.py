"""parquet_to_ohlc_fixture — 對 data/raw/*_daily_*.parquet 的 6 檔資產：
   1) 把 OHLC 依 trajectory.csv 日期 join 成 ohlcvByAsset
   2) 各跑 SMC batch_compute，輸出 NVDA 的 frame.smcSignals（K 線 default）
   3) 各 dump 結構化 SMC overlay (swings/fvgs/obs/breaks/zigzag) 到
      detail.smcOverlayByAsset[ticker]，供 TradingView-like 渲染

用法：
   python apps/warroom/scripts/parquet_to_ohlc_fixture.py \
       --raw-dir data/raw \
       --detail apps/warroom/src/mocks/fixtures/episode-detail.json \
       --output apps/warroom/src/mocks/fixtures/episode-detail.json
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from smc_features import SMCFeatureParams, batch_compute
from smc_features.fvg import detect_and_track_fvgs
from smc_features.ob import detect_and_track_obs
from smc_features.atr import compute_atr
from smc_features.structure import compute_bos_choch
from smc_features.swing import detect_swings

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("parquet_to_ohlc_fixture")

ASSETS = ["NVDA", "AMD", "TSM", "MU", "GLD", "TLT"]
# K 線 default 顯示 NVDA — frame.smcSignals 用這檔的訊號。
SMC_DEFAULT_ASSET = "NVDA"


def load_parquet(raw_dir: Path, asset: str) -> pd.DataFrame:
    """讀對應 ticker 的最新 parquet — 命名: {lower}_daily_*.parquet。"""
    candidates = sorted(raw_dir.glob(f"{asset.lower()}_daily_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No parquet found for {asset} in {raw_dir}")
    path = candidates[-1]
    df = pd.read_parquet(path)
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index).normalize()
    log.info("loaded %s: %s rows from %s", asset, len(df), path.name)
    return df


def compute_smc_full(df: pd.DataFrame) -> dict[str, Any]:
    """對單檔 OHLCV 算完整 SMC，回傳：
       - signals_df: 每 bar 的 bos/choch/fvg_dist/ob_touched/ob_dist
       - overlay: 結構化 overlay (swings/fvgs/obs/breaks/zigzag) 給前端渲染

    視覺化過濾策略（與 RL feature 計算分離 — 這只影響圖面密度）：
      * swing_length=15（vs default 5）— swing 變稀，整體標記減量。
      * BOS 去重：每個 anchor swing 只保留首次突破。
      * OB 過濾：只保留「有對應同方向 break 的 OB」（造成結構突破的反向 K 棒）。
    """
    # 視覺化用較大的 swing_length + 較大的 fvg_min_pct，產生 TradingView-style 較粗結構
    # （研究上 RL feature 仍用預設 swing_length=5 / fvg_min_pct=0.001，這份只影響圖面）
    params = SMCFeatureParams(swing_length=15, fvg_min_pct=0.01)
    work = df[["open", "high", "low", "close", "volume"]].copy()
    work.index = pd.to_datetime(work.index).normalize()

    # 用 batch_compute 拿 signal series（fvg_distance_pct / ob_distance / ob_touched）
    batch = batch_compute(work, params)
    signals_df = batch.output

    # 為了拿原始 fvgs / obs / swing markers，重跑底層子模組
    n = len(work)
    valid_mask = np.ones(n, dtype=np.bool_)
    opens = work["open"].to_numpy(np.float64)
    highs = work["high"].to_numpy(np.float64)
    lows = work["low"].to_numpy(np.float64)
    closes = work["close"].to_numpy(np.float64)
    timestamps = work.index.to_numpy()

    swing_high_marker, swing_low_marker = detect_swings(
        highs, lows, params.swing_length, valid_mask
    )
    atr = compute_atr(highs, lows, closes, params.atr_window, valid_mask)
    bos, choch = compute_bos_choch(
        closes, highs, lows, swing_high_marker, swing_low_marker, valid_mask
    )
    fvgs, _ = detect_and_track_fvgs(
        highs, lows, closes, timestamps, valid_mask, params.fvg_min_pct
    )
    obs, _, _ = detect_and_track_obs(
        opens,
        highs,
        lows,
        closes,
        timestamps,
        valid_mask,
        swing_high_marker,
        swing_low_marker,
        atr,
        params.ob_lookback_bars,
    )

    # ---- 結構化 overlay ----
    iso = lambda i: pd.Timestamp(timestamps[i]).strftime("%Y-%m-%d")  # noqa: E731

    swings: list[dict[str, Any]] = []
    zigzag: list[dict[str, Any]] = []  # 高低點交替的折線（按時間排序）
    for i in range(n):
        if swing_high_marker[i]:
            pt = {"time": iso(i), "price": float(highs[i]), "kind": "high", "barIndex": i}
            swings.append(pt)
            zigzag.append(pt)
        if swing_low_marker[i]:
            pt = {"time": iso(i), "price": float(lows[i]), "kind": "low", "barIndex": i}
            swings.append(pt)
            zigzag.append(pt)
    # zigzag 已經按 i 順序了；保險起見再排序
    zigzag.sort(key=lambda p: (p["barIndex"], 0 if p["kind"] == "low" else 1))

    fvg_list: list[dict[str, Any]] = []
    for f in fvgs:
        from_iso = pd.Timestamp(f.formation_timestamp).strftime("%Y-%m-%d")
        if f.fill_timestamp is not None:
            to_iso = pd.Timestamp(f.fill_timestamp).strftime("%Y-%m-%d")
        else:
            to_iso = iso(n - 1)  # 未填補 → 延伸到最後一根
        fvg_list.append(
            {
                "from": from_iso,
                "to": to_iso,
                "top": float(f.top),
                "bottom": float(f.bottom),
                "direction": f.direction,
                "filled": bool(f.is_filled),
            }
        )

    ob_list: list[dict[str, Any]] = []
    for ob in obs:
        from_iso = pd.Timestamp(ob.formation_timestamp).strftime("%Y-%m-%d")
        if ob.invalidation_timestamp is not None:
            to_iso = pd.Timestamp(ob.invalidation_timestamp).strftime("%Y-%m-%d")
        else:
            expiry_i = min(ob.expiry_bar_index, n - 1)
            to_iso = iso(max(expiry_i, 0))
        ob_list.append(
            {
                "from": from_iso,
                "to": to_iso,
                "top": float(ob.top),
                "bottom": float(ob.bottom),
                "direction": ob.direction,
                "invalidated": bool(ob.invalidated),
            }
        )

    # BOS / CHoCh breaks — 從 bos/choch != 0 的 bar 回推 anchor swing 價位。
    # 規則：bos/choch==+1 → anchor = 該時點之前最近的 swing high
    #       bos/choch==-1 → 之前最近的 swing low
    # 去重 (A 方案)：每個 anchor swing 只允許產出一次 break — 同一個高點被連續多日
    # 收盤穿越，只標第一次。CHoCh 是反轉訊號 priority 高，會分開 dedupe。
    raw_breaks: list[dict[str, Any]] = []
    last_high_i: int | None = None
    last_low_i: int | None = None
    used_anchors: set[tuple[str, int]] = set()  # (kind_prefix, anchor_i)
    for i in range(n):
        if bos[i] != 0 or choch[i] != 0:
            is_choch = choch[i] != 0
            sig = choch[i] if is_choch else bos[i]
            kind_prefix = "CHOCH" if is_choch else "BOS"
            kind = f"{kind_prefix}_{'BULL' if sig > 0 else 'BEAR'}"
            anchor_i = last_high_i if sig > 0 else last_low_i
            if anchor_i is not None:
                anchor_key = (kind_prefix, int(anchor_i))
                if anchor_key not in used_anchors:
                    used_anchors.add(anchor_key)
                    anchor_price = float(highs[anchor_i] if sig > 0 else lows[anchor_i])
                    raw_breaks.append(
                        {
                            "time": iso(i),
                            "anchorTime": iso(anchor_i),
                            "anchorBarIndex": int(anchor_i),
                            "barIndex": int(i),
                            "price": anchor_price,
                            "breakClose": float(closes[i]),
                            "kind": kind,
                            "direction": "bullish" if sig > 0 else "bearish",
                        }
                    )
        if swing_high_marker[i]:
            last_high_i = i
        if swing_low_marker[i]:
            last_low_i = i

    # OB 過濾：只保留「造成 break 的反向 K 棒」
    # 對每個 break，找形成於 break 之前 + 同方向 + 尚未綁定的最近 OB。
    ob_used: set[int] = set()
    for br in raw_breaks:
        br_i = br["barIndex"]
        br_dir = br["direction"]
        # 由近至遠掃 obs（已按 formation 時間升序）
        best: int | None = None
        for ob_idx, ob in enumerate(obs):
            if ob_idx in ob_used:
                continue
            if ob.direction != br_dir:
                continue
            if ob.formation_bar_index >= br_i:
                continue
            best = ob_idx  # 留最近的（迴圈會被後續同條件覆蓋）
        if best is not None:
            ob_used.add(best)

    filtered_ob_list: list[dict[str, Any]] = []
    for ob_idx, ob in enumerate(obs):
        if ob_idx not in ob_used:
            continue
        from_iso = pd.Timestamp(ob.formation_timestamp).strftime("%Y-%m-%d")
        if ob.invalidation_timestamp is not None:
            to_iso = pd.Timestamp(ob.invalidation_timestamp).strftime("%Y-%m-%d")
        else:
            expiry_i = min(ob.expiry_bar_index, n - 1)
            to_iso = iso(max(expiry_i, 0))
        filtered_ob_list.append(
            {
                "from": from_iso,
                "to": to_iso,
                "top": float(ob.top),
                "bottom": float(ob.bottom),
                "direction": ob.direction,
                "invalidated": bool(ob.invalidated),
            }
        )

    # breaks 只 dump 前端用的欄位（去掉 barIndex 等內部 hint）
    breaks: list[dict[str, Any]] = [
        {
            "time": br["time"],
            "anchorTime": br["anchorTime"],
            "price": br["price"],
            "breakClose": br["breakClose"],
            "kind": br["kind"],
        }
        for br in raw_breaks
    ]

    overlay = {
        "swings": swings,
        "zigzag": zigzag,
        "fvgs": fvg_list,
        "obs": filtered_ob_list,
        "breaks": breaks,
    }

    return {"signals_df": signals_df, "overlay": overlay}


def smc_row_to_signals(row: pd.Series) -> dict[str, float | int | bool]:
    """把 batch_compute output 一列轉成 fixture 用 smcSignals dict。

    JSON 不支援 NaN/None — 缺值填 neutral（0/false）以對齊 DTO schema。
    """

    def _int8(v: object) -> int:
        if v is None or (isinstance(v, float) and math.isnan(v)) or pd.isna(v):
            return 0
        iv = int(v)
        return -1 if iv < 0 else (1 if iv > 0 else 0)

    def _f(v: object) -> float:
        if v is None or pd.isna(v):
            return 0.0
        try:
            f = float(v)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0
        return 0.0 if math.isnan(f) else f

    def _b(v: object) -> bool:
        if v is None or pd.isna(v):
            return False
        return bool(v)

    return {
        "bos": _int8(row.get("bos_signal")),
        "choch": _int8(row.get("choch_signal")),
        "fvgDistancePct": _f(row.get("fvg_distance_pct")),
        "obTouching": _b(row.get("ob_touched")),
        "obDistanceRatio": _f(row.get("ob_distance_ratio")),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--detail", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if not args.detail.exists():
        log.error("detail not found: %s", args.detail)
        return 1

    detail = json.loads(args.detail.read_text(encoding="utf-8"))
    frames = detail.get("trajectoryInline") or []
    if not frames:
        log.error("trajectoryInline empty — run csv-to-fixture.cjs first")
        return 1

    by_asset: dict[str, pd.DataFrame] = {
        asset: load_parquet(args.raw_dir, asset) for asset in ASSETS
    }

    # 6 檔各跑 SMC
    smc_per_asset: dict[str, dict[str, Any]] = {}
    for asset in ASSETS:
        log.info("computing SMC for %s ...", asset)
        smc_per_asset[asset] = compute_smc_full(by_asset[asset])
        ov = smc_per_asset[asset]["overlay"]
        log.info(
            "  %s: %d swings | %d FVG | %d OB | %d breaks",
            asset,
            len(ov["swings"]),
            len(ov["fvgs"]),
            len(ov["obs"]),
            len(ov["breaks"]),
        )

    # 注入 ohlcvByAsset + smcSignals (default asset)
    default_signals_df = smc_per_asset[SMC_DEFAULT_ASSET]["signals_df"]
    matched = 0
    smc_matched = 0
    missing_per_asset: dict[str, int] = {a: 0 for a in ASSETS}
    for frame in frames:
        ts = pd.to_datetime(frame["timestamp"]).normalize()
        ohlcv_by_asset: dict[str, dict[str, float]] = {}
        for asset, df in by_asset.items():
            if ts in df.index:
                row = df.loc[ts]
                ohlcv_by_asset[asset] = {
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            else:
                missing_per_asset[asset] += 1
        if ohlcv_by_asset:
            frame["ohlcvByAsset"] = ohlcv_by_asset
            matched += 1

        if ts in default_signals_df.index:
            frame["smcSignals"] = smc_row_to_signals(default_signals_df.loc[ts])
            smc_matched += 1

    # 寫入 detail.smcOverlayByAsset
    detail["trajectoryInline"] = frames
    detail["smcOverlayByAsset"] = {a: smc_per_asset[a]["overlay"] for a in ASSETS}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info(
        "matched %s/%s frames; SMC matched %s; missing per asset: %s",
        matched,
        len(frames),
        smc_matched,
        missing_per_asset,
    )
    log.info("wrote %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
