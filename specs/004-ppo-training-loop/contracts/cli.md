# CLI Contract: ppo_training

CLI 入口：`python -m ppo_training <subcommand> [args]`

## Subcommands

### `train` — 啟動 PPO 訓練

```bash
python -m ppo_training train --config <path> [options]
```

**必填**:

| Flag | Type | 說明 |
|---|---|---|
| `--config` | path | yaml 配置檔路徑（必填）。對應 `contracts/training-config.schema.json` 驗證。 |

**選填**:

| Flag | Type | Default | 說明 |
|---|---|---|---|
| `--seeds` | str | `1` | 單一整數（如 `42`）或逗號分隔列表（`1,2,3,4,5`）或範圍展開（`5` 等價於 `1,2,3,4,5`，需配合 `--seeds-expand`）。 |
| `--seeds-expand` | flag | False | 若提供，`--seeds 5` 解釋為 `1..5`；否則 `5` 視為單一 seed=5。 |
| `--resume` | path | None | 從 checkpoint zip 路徑續訓；自動載入 policy + replay buffer + PRNG state + step counter。 |
| `--device` | enum | `auto` | `cpu` / `cuda` / `auto`；`cuda` 不可用時 raise（不退回 cpu）。 |
| `--dry-run` | flag | False | 完整載入 config、建構 env+model、跑 1 個 rollout、不寫 artefact。 |
| `--log-dir` | path | `runs/` | 覆寫 yaml 中的 `training.log_dir`。 |
| `--force-version-mismatch` | flag | False | 跳過 FR-018 套件版本 gate（仍 warning）。 |
| `--compare-baseline` | path | None | 多 seed 結束後 vs. 既有 baseline aggregate 目錄做 Welch t-test、Cohen's d，產出 `compare.csv`。 |

**Exit codes**:

| Code | 含義 |
|---|---|
| 0 | 全部 seeds 訓練成功完成 |
| 1 | 一般錯誤（unhandled exception） |
| 2 | Config 驗證失敗（`ConfigValidationError`） |
| 3 | 資料 hash 不符（`DataSnapshotMismatchError`） |
| 4 | 套件版本不符且未指定 `--force-version-mismatch`（`PackageVersionMismatchError`） |
| 5 | CUDA 不可用且明指 `--device cuda`（`CudaUnavailableError`） |
| 6 | 訓練中 NaN/Inf loss（`NanLossDetectedError`） |
| 7 | 磁碟空間不足（`DiskFullError`） |
| 130 | SIGINT 中止（POSIX 標準） |

**Stdout**: 訓練進度由 sb3 內建 progress bar 顯示；每 `metrics_csv_freq` step 輸出單行 summary。
**Stderr**: 警告與錯誤（含 stack trace）。同步寫入 `<run_dir>/stderr.log`。

---

### `compare` — 比較兩組 aggregate

```bash
python -m ppo_training compare --baseline <dir> --ablation <dir> [--output <path>]
```

| Flag | Type | 必填 | 說明 |
|---|---|---|---|
| `--baseline` | path | ✓ | baseline aggregate 目錄（含 `aggregate.csv`） |
| `--ablation` | path | ✓ | ablation aggregate 目錄 |
| `--output` | path | ✗ | `compare.csv` 寫入路徑；預設為 `<ablation>/compare_vs_baseline.csv` |

**輸出 `compare.csv` 欄位**: `metric, baseline_mean, baseline_std, ablation_mean, ablation_std, t_statistic, p_value, cohens_d, effect_size_label`。

**Exit codes**: 0 成功、1 一般錯誤、2 目錄結構錯誤。

---

## CLI 行為規約（FR + spec edge cases 對應）

1. **Multi-seed 序列執行**：`--seeds 1,2,3` → 依序跑 seed=1、seed=2、seed=3，**不平行**（避免 GPU 爭用、log 混雜）。每個 seed 獨立 run 目錄。
2. **資料 hash gate**：所有 subcommand 啟動前 MUST 跑 `data_gate.verify(config)`；不符 raise 並 exit 3。
3. **套件版本 gate**：同上；不符 exit 4。可由 `--force-version-mismatch` 跳過。
4. **CUDA gate**：`--device cuda` 啟動時 MUST 驗證 `torch.cuda.is_available()`；不可用 exit 5。
5. **SIGINT handling**：訓練中收到 SIGINT MUST 寫出當前 checkpoint + metadata（abort_reason="sigint_at_step_N"）後 exit 130；不留 corrupt artefact。
6. **--dry-run**：執行至 sb3 model.learn() 第一個 rollout 結束即停；不寫任何 artefact；exit 0。
7. **--resume**：載入 checkpoint zip 同目錄之 `replay_buffer.pkl`、`prng_state.pkl`；step counter 從 `step_count.txt` 讀。寫出位置同原 run 目錄（append metrics.csv）。

## 範例

```bash
# 1. 單 seed smoke test
python -m ppo_training train --config configs/smoke.yaml

# 2. 多 seed baseline 訓練
python -m ppo_training train --config configs/baseline.yaml --seeds 1,2,3,4,5

# 3. SMC ablation vs baseline
python -m ppo_training train --config configs/ablation_no_smc.yaml --seeds 1,2,3,4,5 \
    --compare-baseline runs/aggregate_baseline_20260429_150000/

# 4. 從 checkpoint 續訓
python -m ppo_training train --config configs/baseline.yaml \
    --resume runs/20260429_141523_a0acd02_seed1/checkpoint_step_50000.zip

# 5. GPU 訓練
python -m ppo_training train --config configs/baseline.yaml --device cuda

# 6. 獨立比較
python -m ppo_training compare \
    --baseline runs/aggregate_baseline_20260429_150000/ \
    --ablation runs/aggregate_ablation_20260429_180000/
```
