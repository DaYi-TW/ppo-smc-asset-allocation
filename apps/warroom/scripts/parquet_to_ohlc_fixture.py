"""parquet_to_ohlc_fixture — 把 data/raw/*_daily_*.parquet 的 6 檔 OHLC
   依 trajectory.csv 的日期 join 成 ohlcvByAsset 區塊，注入 episode-detail.json。

用法：
   python scripts/parquet_to_ohlc_fixture.py \
       --trajectory ../../runs/20260505_003950_ed76d69_seed42_no_smc/trajectory.csv \
       --raw-dir ../../data/raw \
       --output src/mocks/fixtures/episode-detail.json

設計：直接讀現有 episode-detail.json（已由 csv-to-fixture.cjs 產出），
逐 frame 用 timestamp 反查 6 檔 parquet，補上 frame.ohlcvByAsset = {NVDA:{o,h,l,c,v}, …}。
找不到對應日期的資產，該日 frame 該欄位略過（前端會 fallback 到單一 close）。
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("parquet_to_ohlc_fixture")

ASSETS = ["NVDA", "AMD", "TSM", "MU", "GLD", "TLT"]


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

    matched = 0
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

    detail["trajectoryInline"] = frames
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(detail, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    log.info(
        "matched %s/%s frames; missing per asset: %s",
        matched,
        len(frames),
        missing_per_asset,
    )
    log.info("wrote %s", args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
