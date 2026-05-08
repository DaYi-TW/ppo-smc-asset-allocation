"""LiveTrackingStore — read / atomic_write of live_tracking.json.

對應 spec 010 FR-001 / FR-009、data-model §1。schema 重用 009 ``EpisodeDetail``
是 SC-007 的硬約束（OOS 與 Live 同 DTO，前端不分支即可渲染）。

Atomic write strategy（research §R1）：
1. 寫 ``<path>.tmp`` 完整內容
2. fsync 該 tmp 檔
3. ``os.replace(tmp, path)``（POSIX rename(2) atomic；Windows MoveFileExW
   atomic same-volume only — tmp 與目標都在同一資料夾保證同 volume）
4. 任一步驟例外 → tmp 清掉 + 既有檔案 byte 不變
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from inference_service.episode_schemas import EpisodeDetail


class LiveTrackingStore:
    """File-backed live tracking artefact store."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> EpisodeDetail | None:
        if not self._path.exists():
            return None
        text = self._path.read_text(encoding="utf-8")
        return EpisodeDetail.model_validate_json(text)

    def atomic_write(self, envelope: EpisodeDetail) -> None:
        """Atomically replace the artefact file. Rolls back on any error.

        On exception the existing file (if any) is byte-identical to its prior
        state — INV-2 / FR-009 / SC-005.
        """
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")

        # 用 mode='json' 把 datetime / date 序列化為 ISO 字串（與 OOS 一致）
        data = envelope.model_dump(mode="json", by_alias=True)
        text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)

        # Step 1: write + fsync tmp
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            # Cleanup tmp on failure during write
            tmp.unlink(missing_ok=True)
            raise

        # Step 2: atomic replace
        try:
            os.replace(tmp, self._path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise


__all__ = ["LiveTrackingStore"]
