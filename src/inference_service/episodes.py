"""Episode store — feature 009 (T031-T035)。

Eager-load ``episode_detail.json`` 到記憶體，提供 ``GET /api/v1/episodes`` 與
``GET /api/v1/episodes/{id}`` 兩個 endpoint 用的存取介面。

設計：
* Image build 時把 artefact COPY 進 container 固定路徑；服務啟動時一次性
  load 並 strict-validate（fail-fast）。
* MVP 僅一份 episode（OOS run）；list endpoint 永遠回 1 筆。
* 沒有 DB / 沒有 cache 失效 / 沒有 reload — 重新部署 = 重 build image。

對應 spec FR-006、FR-008、FR-009、FR-013（startup-fail-fast）。
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from live_tracking.store import LiveTrackingStore

from .episode_schemas import (
    DetailMeta,
    EpisodeDetail,
    EpisodeDetailEnvelope,
    EpisodeListEnvelope,
    EpisodeSummary,
    ListMeta,
)

logger = logging.getLogger(__name__)


class EpisodeStore:
    """Eager-loaded episode artefact 容器。

    呼叫 ``EpisodeStore.from_file(path)`` 讀檔並驗證；之後每次 list/get 都從
    記憶體取，不會再碰檔案系統（FR-008 latency budget）。
    """

    def __init__(
        self,
        *,
        envelope: EpisodeDetailEnvelope,
        loaded_at_utc: datetime,
    ) -> None:
        self._envelope = envelope
        self._loaded_at_utc = loaded_at_utc

    @classmethod
    def from_file(cls, artefact_path: Path) -> EpisodeStore:
        """從 ``episode_detail.json`` 載入並 strict-validate。

        Raises:
            FileNotFoundError: 檔案不存在（startup fail-fast，FR-013）。
            pydantic.ValidationError: schema 不符（startup fail-fast）。
        """
        if not artefact_path.exists():
            raise FileNotFoundError(
                f"episode artefact not found: {artefact_path}. "
                "Image build must COPY runs/<run>/eval_oos/episode_detail.json "
                "to this path."
            )
        raw = json.loads(artefact_path.read_text(encoding="utf-8"))
        envelope = EpisodeDetailEnvelope.model_validate(raw)
        loaded_at = datetime.now(UTC)
        logger.info(
            "episode artefact loaded: id=%s frames=%d size=%d bytes",
            envelope.data.summary.id,
            len(envelope.data.trajectoryInline),
            artefact_path.stat().st_size,
        )
        return cls(envelope=envelope, loaded_at_utc=loaded_at)

    @property
    def episode_id(self) -> str:
        return self._envelope.data.summary.id

    def list_envelope(self) -> EpisodeListEnvelope:
        """``GET /api/v1/episodes`` 回應 body。"""
        return EpisodeListEnvelope(
            items=[self._envelope.data.summary],
            meta=ListMeta(
                count=1,
                generatedAt=_iso(self._loaded_at_utc),
            ),
        )

    def get_envelope(self, episode_id: str) -> EpisodeDetailEnvelope | None:
        """``GET /api/v1/episodes/{id}`` 回應；找不到回 ``None``。"""
        if episode_id != self.episode_id:
            return None
        # 用 store 載入的 envelope；只覆寫 generatedAt 為這次 query 時間是不必要
        # ——artefact 自身的 meta 已經是 deterministic（builder 端決定），重用即可。
        return self._envelope

    @property
    def summary(self) -> EpisodeSummary:
        return self._envelope.data.summary

    @property
    def detail(self) -> EpisodeDetail:
        return self._envelope.data

    @property
    def detail_meta(self) -> DetailMeta:
        return self._envelope.meta


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- 010 MultiSourceEpisodeStore (OOS + Live dual source) ----------


class MultiSourceEpisodeStore:
    """OOS + Live 雙源 episode store — spec 010 FR-012 / FR-013。

    * ``oos`` 為 None 時：list/get 不含 OOS。
    * ``live`` 為 None 時：list/get 不含 Live。
    * ``list_envelope`` 排序：OOS 在前，Live 在後（research §R5）。
    * ``get_envelope(id)``：以 ``_live`` 後綴判斷分流；Live 每次 read-through，
      確保 background pipeline 寫入後立刻可見（FR-013 / SC-006）。
    """

    LIVE_SUFFIX = "_live"

    def __init__(
        self,
        *,
        oos: EpisodeStore | None,
        live: LiveTrackingStore | None,
    ) -> None:
        self._oos = oos
        self._live = live

    @property
    def oos(self) -> EpisodeStore | None:
        return self._oos

    @property
    def live(self) -> LiveTrackingStore | None:
        return self._live

    def list_envelope(self) -> EpisodeListEnvelope:
        items: list[EpisodeSummary] = []
        if self._oos is not None:
            items.append(self._oos.summary)
        if self._live is not None:
            live_detail = self._live.load()
            if live_detail is not None:
                items.append(live_detail.summary)
        return EpisodeListEnvelope(
            items=items,
            meta=ListMeta(
                count=len(items),
                generatedAt=_iso(datetime.now(UTC)),
            ),
        )

    def get_envelope(self, episode_id: str) -> EpisodeDetailEnvelope | None:
        if episode_id.endswith(self.LIVE_SUFFIX):
            if self._live is None:
                return None
            detail = self._live.load()
            if detail is None or detail.summary.id != episode_id:
                return None
            return EpisodeDetailEnvelope(
                data=detail,
                meta=DetailMeta(generatedAt=_iso(datetime.now(UTC))),
            )
        if self._oos is None:
            return None
        return self._oos.get_envelope(episode_id)


__all__ = ["EpisodeStore", "MultiSourceEpisodeStore"]
