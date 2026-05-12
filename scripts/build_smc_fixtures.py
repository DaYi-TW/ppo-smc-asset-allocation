"""從 data/raw/ NVDA 快照子集抽出 001 SMC Feature Engine 的測試 fixture。

產出兩份 parquet 至 ``tests/fixtures/``：

* ``nvda_2024H1.parquet`` — NVDA 2024-01-02 至 2024-06-30，~125 列日線（單元測試）。
* ``nvda_2023_2024.parquet`` — NVDA 2023-01-02 至 2024-12-31，~500 列（integration / 性能基準）。

兩者皆為 002 schema 子集（含 quality_flag），可直接餵給 ``smc_features.batch_compute``。
重建時機：data/raw/ NVDA 快照範圍變動 / 002 schema 升版。
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "data" / "raw"
DEST_DIR = REPO_ROOT / "tests" / "fixtures"


def _find_nvda_snapshot() -> Path:
    """Glob `nvda_daily_*.parquet`，避免硬編日期前綴隨 002 重抓而失效."""
    matches = sorted(DATA_ROOT.glob("nvda_daily_*.parquet"))
    matches = [p for p in matches if not p.name.endswith(".meta.json")]
    if not matches:
        raise SystemExit(
            f"找不到 NVDA 快照（pattern: nvda_daily_*.parquet @ {DATA_ROOT}）\n"
            "請先執行 002 fetch 將 NVDA 落地。"
        )
    # 多個版本時取最新（檔名按日期排序）
    return matches[-1]

# 與 002 conftest._PARQUET_WRITER_KWARGS / research R5 一致 — 確保 fixture
# 經 git checkout 後 SHA-256 穩定。
_WRITER_KWARGS = dict(
    compression="snappy",
    version="2.6",
    data_page_version="2.0",
    write_statistics=False,
    use_dictionary=False,
    coerce_timestamps="us",
)


def _slice_and_write(df: pd.DataFrame, start: str, end: str, fname: str) -> Path:
    sub = df.loc[start:end].copy()
    out = DEST_DIR / fname
    table = pa.Table.from_pandas(sub, preserve_index=True)
    pq.write_table(table, out, **_WRITER_KWARGS)
    print(f"  {fname}: {len(sub)} rows  ({sub.index.min().date()} → {sub.index.max().date()})")
    return out


def main() -> None:
    source = _find_nvda_snapshot()
    DEST_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(source)
    print(f"原始 NVDA 快照（{source.name}）：{len(df)} rows  "
          f"({df.index.min().date()} → {df.index.max().date()})")

    _slice_and_write(df, "2024-01-02", "2024-06-30", "nvda_2024H1.parquet")
    _slice_and_write(df, "2023-01-02", "2024-12-31", "nvda_2023_2024.parquet")

    print("done")


if __name__ == "__main__":
    main()
