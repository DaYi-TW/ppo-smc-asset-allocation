"""parquet_to_ohlc_fixture — 把 data/raw/*_daily_*.parquet 的 6 檔 OHLC
   依 trajectory.csv 的日期 join 成 ohlcvByAsset 區塊，
   並對 NVDA（K 線預設顯示資產）計算 SMC 訊號，
   一併注入 episode-detail.json。

用法：
   python apps/warroom/scripts/parquet_to_ohlc_fixture.py \
       --raw-dir data/raw \
       --detail apps/warroom/src/mocks/fixtures/episode-detail.json \
       --output apps/warroom/src/mocks/fixtures/episode-detail.json

設計：直接讀現有 episode-detail.json（已由 csv-to-fixture.cjs 產出），
逐 frame 用 timestamp 反查 6 檔 parquet，補上 frame.ohlcvByAsset。
SMC：用 smc_features.batch_compute 對 NVDA OHLCV 整段算一次，
按 timestamp 對齊回填 frame.smcSignals。
找不到對應日期的資產，該日 frame 該欄位略過（前端 fallback）。
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from pathlib import Path

import pandas as pd

from smc_features import SMCFeatureParams, batch_compute

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("parquet_to_ohlc_fixture")

ASSETS = ["NVDA", "AMD", "TSM", "MU", "GLD", "TLT"]
# K 線 default 顯示 NVDA — SMC 訊號算這檔即可。
SMC_ASSET = "NVDA"


def load_parquet(raw_dir: Path, asset: str) -> pd.DataFrame:
    """讀對應 ticker 的最新 parquet — 命名: {lower}_daily_*.parquet。"""
    candidates = sorted(raw_dir.glob(f"{asset.lower()}_daily_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No parquet found for {asset} in {raw_dir}")
    path = candidates[-1]
    df = pd.read_parquet(path)
    # parquet schema 是 [open, high, low, close, volume] 加 date index
    if "date" in df.columns:
        df = df.set_index("date")
    df.index = pd.to_datetime(df.index).normalize()
    log.info("loaded %s: %s rows from %s", asset, len(df), path.name)
    return df


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--raw-dir",
        type=Path,
        required=True,
        help="data/raw directory containing *_daily_*.parquet",
    )
    parser.add_argument(
        "--detail",
        type=Path,
        required=True,
        help="existing episode-detail.json to augment in-place",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="output JSON (can be same as --detail to overwrite)",
    )
    args = parser.parse_args()

    if not args.detail.exists():
        log.error("detail not found: %s", args.detail)
        return 1

    detail = json.loads(args.detail.read_text(encoding="utf-8"))
    frames = detail.get("trajectoryInline") or []
    if not frames:
        log.error("trajectoryInline empty — run csv-to-fixture.cjs first")
        return 1

    # 載入 6 檔 parquet
    by_asset: dict[str, pd.DataFrame] = {}
    for asset in ASSETS:
        by_asset[asset] = load_parquet(args.raw_dir, asset)

    # 對 SMC_ASSET 整段跑 batch_compute（一次算完，按 timestamp 查表）。
    smc_df = compute_smc_signals(by_asset[SMC_ASSET])
    log.info("SMC computed for %s: %d rows", SMC_ASSET, len(smc_df))

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

        if ts in smc_df.index:
            frame["smcSignals"] = smc_row_to_signals(smc_df.loc[ts])
            smc_matched += 1

    detail["trajectoryInline"] = frames
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
    bos = int((smc_df["bos_signal"].fillna(0) != 0).sum())
    choch = int((smc_df["choch_signal"].fillna(0) != 0).sum())
    ob = int(smc_df["ob_touched"].fillna(False).sum())
    log.info("SMC totals over full history: BOS=%d CHoCh=%d OB-touch=%d", bos, choch, ob)
    log.info("wrote %s", args.output)
    return 0


def compute_smc_signals(df: pd.DataFrame) -> pd.DataFrame:
    """對單檔 OHLCV 跑 batch_compute；回傳含 SMC 欄位的 DataFrame。"""
    work = df[["open", "high", "low", "close", "volume"]].copy()
    work.index = pd.to_datetime(work.index).normalize()
    result = batch_compute(work, SMCFeatureParams())
    return result.output


def smc_row_to_signals(row: pd.Series) -> dict[str, float | int | bool]:
    """把 batch_compute output 一列轉成 fixture 用 smcSignals dict。

    JSON 不支援 NaN/None — 缺值填 neutral（0/false）以對齊 DTO schema（number / bool）。
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


if __name__ == "__main__":
    raise SystemExit(main())
