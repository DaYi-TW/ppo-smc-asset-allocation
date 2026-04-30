# Quickstart: PPO Training Loop

5 分鐘內跑通一次 PPO smoke 訓練。

## 前置條件

1. **002 已完成**：`data/raw/` 含全部 Parquet 快照（`{symbol}_daily_*.parquet` × 7 個）與 `metadata.json`。
2. **003 已完成**：`src/portfolio_env/` package 已實作、`pip install -e .` 可載入、`gymnasium.envs.registration` 已註冊 `PortfolioEnv-v0`。
3. **Python 3.11+**、NVIDIA GPU 為選項（不必）。

## 安裝

```bash
# 在專案根目錄
pip install -e ".[train]"  # 安裝 ppo_training 套件 + 訓練所需依賴
```

`pyproject.toml` 之 optional dependencies `[train]` 包含：
`stable-baselines3>=2.3,<3`、`tensorboard`、`scipy`、`matplotlib`、`PyYAML`、`jsonschema`。

## 5-min smoke training

```bash
# 1. 確認 002 / 003 連通：跑 dry-run
python -m ppo_training train --config configs/smoke.yaml --dry-run
# 預期：載入 config、建構 env、印 rollout 資訊、不寫 artefact、exit 0

# 2. 真跑 smoke（100 step × 1 seed，CPU < 30 秒）
python -m ppo_training train --config configs/smoke.yaml

# 3. 檢視結果
ls runs/                    # 應有 1 個 <timestamp>_<git_hash>_seed1 目錄
cat runs/<run>/metadata.json | jq '.final_mean_episode_return'
```

## 範例 `configs/smoke.yaml`

```yaml
env:
  data_root: data/raw
  symbols: [NVDA, AMD, TSM, MU, GLD, TLT]
  start_date: "2018-01-01"
  end_date: "2018-06-30"     # 半年快速 smoke
  include_smc: true
  position_cap: 0.4
  transaction_cost_bps: 5.0
  initial_cash: 1.0

ppo:
  learning_rate: 3.0e-4
  n_steps: 64                # 小 rollout for smoke
  batch_size: 32
  n_epochs: 4
  gamma: 0.99
  gae_lambda: 0.95
  clip_range: 0.2
  ent_coef: 0.0
  vf_coef: 0.5
  max_grad_norm: 0.5
  policy_kwargs:
    net_arch: [32, 32]

training:
  total_timesteps: 1024      # 16 × n_steps
  seed: 1
  checkpoint_freq: 1024
  eval_freq: 256
  device: cpu
  log_dir: runs/

logging:
  tensorboard: true
  wandb_project: null
  metrics_csv_freq: 64
```

## 驗證 reproducibility

```bash
# 同 seed 跑兩次，metrics.csv 必 byte-identical
python -m ppo_training train --config configs/smoke.yaml --seeds 1 --log-dir runs/test_a/
python -m ppo_training train --config configs/smoke.yaml --seeds 1 --log-dir runs/test_b/

diff runs/test_a/*/metrics.csv runs/test_b/*/metrics.csv
# 預期：無差異（exit 0）
```

## 多 seed 訓練 + 聚合

```bash
# 5 seed × 100k step（CPU 約 2.5 hr，GPU 約 50 min）
python -m ppo_training train --config configs/baseline.yaml --seeds 1,2,3,4,5
# 結束後自動產生：
#   runs/<timestamp>_<hash>_seed1/
#   runs/<timestamp>_<hash>_seed2/
#   ...
#   runs/aggregate_baseline_<timestamp>/
#     ├── aggregate.csv
#     ├── aggregate.png       <- 看這張驗證收斂
#     └── metadata_aggregate.json
```

## SMC ablation 對比

```bash
# Step 1: 跑 baseline（已含 SMC）
python -m ppo_training train --config configs/baseline.yaml --seeds 1,2,3,4,5

# Step 2: 跑 ablation（去 SMC）
python -m ppo_training train --config configs/ablation_no_smc.yaml --seeds 1,2,3,4,5 \
    --compare-baseline runs/aggregate_baseline_<timestamp>/

# 結果：
cat runs/aggregate_ablation_<timestamp>/compare.csv
# 預期欄位：metric, baseline_mean, ablation_mean, p_value, cohens_d, ...
# 論文 Findings 章節主要證據：mean_episode_return p_value < 0.05
```

## TensorBoard

```bash
tensorboard --logdir runs/
# 開啟 http://localhost:6006
# 重點 panel：
#   train/policy_loss        — 應隨 step 下降
#   train/value_loss         — 應隨 step 下降
#   custom/mean_log_return    — 應隨 step 上升
#   custom/mean_drawdown_penalty — 應隨 step 下降（懲罰減少）
#   policy/action_dist (histogram, 每 10k step) — 觀察分佈是否退化
```

## 從 checkpoint 續訓

```bash
# 假設訓練到 50k step 中斷
python -m ppo_training train --config configs/baseline.yaml \
    --resume runs/20260429_141523_a0acd02_seed1/checkpoint_step_50000.zip
# 自動讀取同目錄之 replay_buffer.pkl + prng_state.pkl + step_count.txt
# 訓練從 step 50001 繼續，metrics.csv append 在原檔末尾
```

## 跑單元測試

```bash
pytest tests/ -v --cov=src/ppo_training --cov-report=term-missing
# 預期：覆蓋率 ≥ 85%（憲法 SC-006）
```

## 常見問題

**Q: 啟動時報 `DataSnapshotMismatchError`？**
A: 你的 `data/raw/` 與 yaml `expected_data_hashes` 不一致。要嘛重抓資料（`make data-snapshot`），要嘛更新 yaml 中的預期 hash（若新快照是預期的）。

**Q: GPU 訓練 NaN loss？**
A: CUDA deterministic 模式偶見浮點異常。檢查 `os.environ['CUBLAS_WORKSPACE_CONFIG']` 是否設為 `:4096:8`；若無，加上後重試。

**Q: 跨機重跑 metrics.csv 不 byte-identical？**
A: 檢查 (a) git commit 是否相同、(b) Python / numpy / torch / sb3 版本是否相同（看 metadata.json 之 `package_versions`）、(c) torch deterministic 是否啟用（看 `metadata.json["device"]` 與 trainer 啟動 log）。

**Q: 多 seed 訓練可以平行跑嗎？**
A: CLI 預設**序列**執行（避免 GPU 爭用、log 混雜）。若要平行，請手動 launch 多個 process 並各自指定獨立 `--log-dir`。
