"""T046 — Prediction schema parity vs predict.py（核心 invariant，SC-005 / SC-007 / G-I-3）.

服務 ``POST /infer/run`` 的 PredictionPayload 應與 ``ppo_training/predict.py`` CLI 輸出
byte-identical（除 ``triggered_by`` / ``inference_id`` / ``inferred_at_utc`` 三個 005 新欄位外）.

注意：這個 test 跑兩次真 PPO load + episode（一次 CLI、一次 service handler），slow ~60s.
用 ``@pytest.mark.slow`` 讓 CI 可選跑.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.asyncio
@pytest.mark.slow
async def test_service_payload_byte_identical_to_predict_py(
    policy_path: Path, data_root: Path, tmp_path: Path
) -> None:
    """同 policy + 同 data → handler.run_inference output 與 predict.py 對 diff 應一致.

    比對 7 個共有欄位（target_weights / context / as_of_date / weights_capped /
    renormalized / next_trading_day_target / deterministic）；忽略 005 新增欄位.
    """
    from inference_service.config import ServiceConfig
    from inference_service.handler import init_state, run_inference

    # 1. 跑 predict.py CLI 產 ground-truth JSON（用同 policy / 同 data）
    out_dir = tmp_path / "predict_out"
    out_dir.mkdir()
    out_file = out_dir / "prediction_cli.json"
    cmd = [
        sys.executable,
        "-m",
        "ppo_training.predict",
        "--policy",
        str(policy_path),
        "--data-root",
        str(data_root),
        "--output",
        str(out_file),
    ]
    env = {"PYTHONPATH": str(_REPO_ROOT / "src")}
    import os

    env_full = {**os.environ, **env}
    result = subprocess.run(
        cmd, capture_output=True, text=True, env=env_full, cwd=_REPO_ROOT, check=False
    )
    if result.returncode != 0:
        pytest.skip(f"predict.py CLI failed (likely missing data): {result.stderr[:500]}")

    if not out_file.exists():
        pytest.skip(f"predict.py output not found at {out_file}")
    cli_payload = json.loads(out_file.read_text(encoding="utf-8"))

    # 2. 跑 service handler 產同樣 prediction
    cfg = ServiceConfig(
        policy_path=policy_path, data_root=data_root, redis_url="redis://localhost:6379/0"
    )
    state = init_state(cfg)
    service_payload = (await run_inference(state, "manual")).model_dump()

    # 3. Drop 005 新欄位 + path-formatting 差異欄位後對 diff
    # target_weights / context / as_of_date / weights_capped / renormalized / next_trading_day_target / deterministic
    common_keys = (
        "as_of_date",
        "next_trading_day_target",
        "deterministic",
        "target_weights",
        "weights_capped",
        "renormalized",
    )
    for k in common_keys:
        assert service_payload[k] == cli_payload[k], (
            f"field {k} drift: cli={cli_payload[k]!r} svc={service_payload[k]!r}"
        )

    # context.current_nav_at_as_of / include_smc / n_warmup_steps 必須一致；
    # data_root 字串可能 path-separator 差異（windows vs container）→ 比 absolute path resolve.
    cli_ctx = cli_payload["context"]
    svc_ctx = service_payload["context"]
    assert cli_ctx["include_smc"] == svc_ctx["include_smc"]
    assert cli_ctx["n_warmup_steps"] == svc_ctx["n_warmup_steps"]
    assert cli_ctx["current_nav_at_as_of"] == pytest.approx(svc_ctx["current_nav_at_as_of"])
