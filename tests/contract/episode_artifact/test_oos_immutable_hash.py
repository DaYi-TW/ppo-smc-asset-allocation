"""T047 / T058 — Constitution Principle I gate (OOS scope, NON-NEGOTIABLE).

對應 spec 010 SC-008 + FR-014 + constitution.md Principle I：

> OOS ``episode_detail.json`` 必須 byte-identical sha256；任何使其變動的改動
> 都需要在 PR 走 amendment 流程。Live tracking artefact 是 mutable，**不**
> 適用此約束（spec 010 已聲明範圍區隔）。

兩條 invariants：
1. **檔案層**：committed OOS artefact 連讀 5 次 sha256 必須完全一致（檔案系統
   穩定性 — 排除 race / write-on-read）。
2. **API 層**：GET /api/v1/episodes/{oos_id} 連呼叫 5 次，response body 序列化
   後 sha256 必須一致（``EpisodeStore`` 是 eager-load + 純 in-memory，response
   只有時間欄位變動時會破口；本 gate 鎖死 envelope.data 部分）。

不在範圍內：Live ``live_tracking.json`` 是每日 mutable artefact —— 由
``test_append_only.py`` 走 INV-3 append-only 而非 byte-identical（spec
010 範圍區隔，不要把這條 gate 套到 Live 路徑上）。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from inference_service.app import create_app
from inference_service.episodes import EpisodeStore

_REPO_ROOT = Path(__file__).resolve().parents[3]
_OOS_ARTEFACT = (
    _REPO_ROOT
    / "runs"
    / "20260506_004455_659b8eb_seed42"
    / "eval_oos"
    / "episode_detail.json"
)


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


@pytest.fixture(scope="module")
def oos_artefact_path() -> Path:
    if not _OOS_ARTEFACT.exists():
        pytest.skip(f"OOS artefact not committed: {_OOS_ARTEFACT}")
    return _OOS_ARTEFACT


def _stub_state():
    class _StubState:
        policy = None
        started_at_utc = datetime.now(UTC)
        last_inference_at_utc = None

    return _StubState()


class TestOOSArtefactByteIdentical:
    """Invariant 1：committed OOS artefact 5 次 read sha256 一致。"""

    def test_five_reads_yield_same_sha256(self, oos_artefact_path: Path) -> None:
        digests = {_sha256_bytes(oos_artefact_path.read_bytes()) for _ in range(5)}
        assert len(digests) == 1, (
            f"OOS artefact byte-identical broken across reads: {digests}"
        )


class TestOOSEpisodeDetailEndpointByteIdentical:
    """Invariant 2：GET /api/v1/episodes/{oos_id} 連 5 次 envelope.data sha256 一致。

    比對 ``data`` 欄位而非整個 body，因為 ``meta.generatedAt`` 是 query 時間
    戳記（每次都不同）— 學術 baseline 鎖死的是 trajectory + summary，不是
    response wrapper。
    """

    def test_five_get_calls_yield_same_data_sha256(
        self, oos_artefact_path: Path
    ) -> None:
        store = EpisodeStore.from_file(oos_artefact_path)
        app = create_app(
            state=_stub_state(),  # type: ignore[arg-type]
            redis_client=None,
            episode_store=store,
        )
        client = TestClient(app)

        oos_id = store.episode_id
        digests: set[str] = set()
        for _ in range(5):
            resp = client.get(f"/api/v1/episodes/{oos_id}")
            assert resp.status_code == 200
            body = resp.json()
            data_canonical = json.dumps(
                body["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            digests.add(_sha256_bytes(data_canonical))

        assert len(digests) == 1, (
            f"GET /api/v1/episodes/{{oos_id}} envelope.data sha256 不一致 across "
            f"5 calls: {digests}"
        )
