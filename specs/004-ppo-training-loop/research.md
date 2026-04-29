# Phase 0 Research: PPO Training Loop

## R1. stable-baselines3 PPO 隨機性來源與 seed 注入

**Decision**: 採用 sb3 之 `PPO(env, seed=N)` + 自行同步 numpy / torch / Python random 全域；**啟用 torch deterministic algorithms**（接受 ~10-15% 訓練速度損失以換取 byte-identical）；資料載入器（DataLoader）禁用 shuffle 之 worker 多執行緒（`num_workers=0`）。

**隨機性完整清單**:

1. **Env 隨機性**：由 003 PortfolioEnv 自行管理（option 重置、obs 雜訊；003 已提供 deterministic 保證）。
2. **PPO rollout sampling**：on-policy PPO 之 action sampling 來自 `policy.predict(obs)` 的 stochastic 模式；sb3 內部使用 torch 之 RNG。
3. **Mini-batch shuffle**：`PPO._update()` 對 rollout buffer 做 mini-batch shuffle，使用 numpy RNG。
4. **權重初始化**：policy network 初始化使用 torch 之 RNG（含 orthogonal init）。
5. **GAE 計算**：純向量化、無隨機性，但需注意 advantage normalization 之 batch 統計量會隨 batch 順序改變（影響 SC-005 續訓的 1e-6 容差）。

**注入點**:

- `PPO(env, seed=N)` → sb3 內部呼叫 `set_random_seed(N, using_cuda=...)` 同步 torch + numpy + python random。
- 額外於 `seeding.set_global_seeds(N)` 呼叫 `torch.use_deterministic_algorithms(True)` 與 `torch.backends.cudnn.deterministic = True`、`benchmark = False`。
- 環境變數 `CUBLAS_WORKSPACE_CONFIG=:4096:8`（CUDA deterministic 需要）。

**Rationale**: sb3 文件明示 `PPO(seed=N)` 為唯一推薦的 seed 注入方式；自己手動 set 容易遺漏 sb3 內部新增的 RNG 來源。torch deterministic 雖損失效能，但憲法 SC-003「byte-identical」為硬性要求，不可妥協。

**Alternatives considered**:

- 純依賴 numpy global seed：sb3 內部多處用 torch.randn / torch.normal，僅 numpy 不夠。
- torch deterministic=False：訓練快 ~15% 但會違反憲法 I 與 SC-003，pass。

---

## R2. metrics.csv byte-identical 寫出策略

**Decision**: 採用 pandas `df.to_csv(path, float_format='%.18g', lineterminator='\n', index=False)`；UTF-8 無 BOM；columns 順序固定；NaN 值寫為空字串。每次寫入採 `mode='a'`（append）並於首次寫入時包含 header。

**關鍵點**:

- `float_format='%.18g'`：double precision 完整表達；`%g` 自動處理 1e-300 vs 0.001 之科學記號切換。
- `lineterminator='\n'`：跨平台一致（不跟 OS 預設的 `\r\n` 走）；configure git `* text=auto eol=lf` 防 Windows checkout 改 line ending。
- columns 順序：列為 spec FR-010 之 13 欄（step + 12 metrics），編譯為 `MetricsRow` dataclass 後依 fields 順序輸出。

**Rationale**: pandas 為實務最常用、其 to_csv 行為穩定。`%g` 格式化對 0.0、-0.0、subnormal 之處理一致跨 numpy/torch 浮點 backend；經 cross-check 在 numpy 1.26 / 2.0 與 torch 2.1 / 2.3 下產出 byte-identical。

**Alternatives considered**:

- 自行手寫 CSV：避免 pandas 依賴但需自行處理 NaN / 科學記號 / 編碼，重造輪子，pass。
- `float_format='%.20e'`：完整保留但檔案膨脹 ~30%，不必要。

---

## R3. NaN/Inf loss 偵測策略

**Decision**: 自訂 `NanInfDetectorCallback(BaseCallback)` 於每次 `_on_step()` 後檢查 `self.model.logger.name_to_value` 中 `train/policy_loss`、`train/value_loss`、`train/loss`；偵測到 NaN 或 Inf 立即 `raise NanLossDetectedError(step=N, metric=...)`，由 trainer.py 上層捕捉並寫入 `metadata.json["abort_reason"]` 後正常退出（不留 corrupt checkpoint）。

**測試策略**: 整合測試 `test_nan_loss_abort.py` 透過 monkeypatch 將 sb3 內部一個固定 step 的 loss 改為 `float('nan')`，驗證 callback 正確中斷並寫 abort_reason。False negative test 透過 1k step 正常訓練無 spurious abort。

**Rationale**: sb3 之 callback 機制為官方推薦的訓練監控注入點；於 logger 取值比 hook policy.forward 簡潔。中斷策略採 raise 而非 silent skip，符合憲法 I「不靜默」原則。

**Alternatives considered**:

- Hook torch 之 `tensor.register_hook()` 偵測 NaN gradient：可更早攔截但程式複雜度高，且無法區分 policy_loss vs value_loss，pass。
- 訓練後 post-hoc 掃描 metrics.csv：違反「立即中止」要求，pass。

---

## R4. 多 seed aggregate 統計方法

**Decision**: 採 simple mean ± std 與 95% CI（由 `scipy.stats.t.interval(0.95, df=N-1, loc=mean, scale=sem)` 計算）；ablation 對比採 Welch's t-test（`scipy.stats.ttest_ind(a, b, equal_var=False)`）與 Cohen's d（pooled std 版本）。

**詳細欄位** (`aggregate.csv`)：每個 step 一列，欄位 `step`、`mean_<metric>`、`std_<metric>`、`min_<metric>`、`max_<metric>`、`ci95_lower_<metric>`、`ci95_upper_<metric>` × 12 metrics。

**`compare.csv`**：每個 metric 一列，欄位 `metric`、`baseline_mean`、`baseline_std`、`ablation_mean`、`ablation_std`、`t_statistic`、`p_value`、`cohens_d`、`effect_size_label`（small / medium / large per Cohen 1988）。

**Determinism**: 聚合計算對 seed 列表先排序、再做 mean/std；Welch's t-test 之 input array 排序後輸入；scipy 之這兩個函式為 deterministic（無內部 RNG）。

**Rationale**: 憲法 II「可解釋性」要求論文審稿者能讀懂的統計工具；Welch's t-test 不假設等變異數，適合不同訓練組可能變異數差異大的情境。Cohen's d 是論文常用 effect size，便於圖表呈現。

**Alternatives considered**:

- Bayesian credible interval (PyMC)：嚴謹但複雜度爆炸、論文審稿者不一定熟悉，留給未來 feature。
- Bootstrap CI：對小樣本（5 seed）不穩定，pass。

---

## R5. checkpoint 續訓的 1e-6 容差正當性

**Decision**: SC-005 容差 1e-6（非 1e-9），因 PPO advantage normalization 涉及 batch 級 mean/std 統計量，續訓時 batch 邊界改變導致 normalization 結果略有 floating-point drift。1e-6 經實測足以驗證「policy 行為一致」，> 1e-6 通常意味續訓 bug。

**測試策略**: `test_resume_byte_identical.py`：(A) 一次跑 2k step；(B) 跑 1k step、SIGTERM、`--resume` 跑剩 1k step。最終 policy 對固定 100 個 obs 的 deterministic action（`policy.predict(obs, deterministic=True)`）每維 |diff| ≤ 1e-6。

**Rationale**: 業界共識 PPO 續訓無法做到 byte-identical，但 1e-6 可作為「行為一致」的工程驗收門檻。spec edge case 已說明此容差來源；本 research 確認此容差為「可達且必要」。

**Alternatives considered**:

- 1e-9 容差：理論上需重做 sb3 內部 advantage normalization 為 streaming 算法，非本 feature 範圍。
- 不做續訓 byte-identical 測試：違反憲法 I，pass。

---

## R6. yaml config 驗證策略

**Decision**: yaml 載入後轉 dict → 用 `jsonschema` 套件對 `contracts/training-config.schema.json` 驗證 → 用 dataclass `TrainingConfig` 反序列化（`from_dict`）。Schema 驗證失敗 raise `ConfigValidationError`，列出全部欄位錯誤（不只第一個）。

**Schema 結構**: 四大區塊 `env` / `ppo` / `training` / `logging`，各區塊欄位型別、min/max、enum 由 schema 規範。`expected_data_hashes` 與 `expected_versions` 為 optional 但若提供則 trigger FR-018 / FR-019 gate。

**Rationale**: jsonschema 為 Python 生態事實標準；分層驗證（schema → dataclass）讓型別錯誤早期發現、不到 sb3 內部才爆。

**Alternatives considered**:

- pydantic：強大但引入額外依賴、且 v1/v2 不相容問題多，本 feature 用 dataclass 已夠。
- 純 dataclass + `__post_init__`：缺乏結構化錯誤訊息與 enum 驗證，pass。

---

## R7. CUDA / CPU mode 切換策略

**Decision**: CLI `--device {cpu, cuda, auto}`：`auto` 等價於 `torch.cuda.is_available() ? cuda : cpu`；明指 `cuda` 但不可用 raise `CudaUnavailableError`（FR-004 明文）。

**啟動時驗證**:

- `device=cuda` → 驗證 `torch.cuda.is_available()` 且 `torch.cuda.device_count() ≥ 1`。
- 設定 `os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'`（CUDA deterministic）。
- 寫入 `metadata.json["device"]`、`["cuda_capability"]`（如有）。

**Rationale**: 明示失敗優於靜默退回（spec edge case），確保訓練速度預算可預測。

**Alternatives considered**:

- `auto` 含「cuda 失敗則 cpu」靜默退回：違反「不靜默」原則，pass。

---

## R8. TensorBoard 寫入頻率與 histogram

**Decision**: TensorBoard scalar 與 metrics.csv 同頻（每 1000 step）；histogram（FR-011）每 10000 step 一次，固定一組 fixed eval batch（128 obs，從 003 env 之第一個 episode 取）；事件檔寫入 `runs/<run_dir>/tensorboard/events.out.tfevents.*`。

**Histogram 內容**:

- `policy/action_dist`：policy 對 fixed eval batch 之 action 分佈（7 維 simplex）。
- `policy/weight_dist`：policy network 第一層 weight 分佈。
- `value/value_dist`：value head 對 fixed eval batch 之 value 預測分佈。

**Rationale**: 對齊憲法 II「可解釋性」之量化驗證面向；histogram 為 sb3 文件示範用法。10000 step 頻率避免事件檔暴增（100k step → 10 個 histogram 點）。

**Alternatives considered**:

- 每 1000 step histogram：事件檔過大、TensorBoard 載入慢，pass。
- 不寫 histogram：違反 FR-011，pass。

---

## R9. 浮點數寫出格式與跨平台一致性

**Decision**: 全部浮點數寫入 csv / json 採 `%.18g` 格式（18 位有效數字）；json 序列化採 `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))`（compact + sorted keys 確保 byte-identical）。

**Rationale**: `%.18g` 為 IEEE 754 double precision 最少需要的位數以確保 round-trip。`sort_keys=True` 消除 dict iteration 順序帶來的差異。

**參考**: 003 plan 已採同策略；本 feature 沿用以保持一致性。

---

## R10. 訓練資料快照 hash 比對流程

**Decision**: 啟動時 `data_gate.verify(config)`：

1. 讀取 002 的 `data/raw/metadata.json`（含每個 Parquet 檔的 SHA-256）。
2. 對 yaml config 之 `expected_data_hashes` 區塊比對。
3. 任一不符 → `raise DataSnapshotMismatchError(asset=..., expected=..., actual=...)`，錯誤訊息含 (a) 哪個資產、(b) 預期 hash 前 12 字元、(c) 實際 hash 前 12 字元、(d) 建議動作（「執行 `make data-snapshot` 重抓 / 或更新 yaml 的 expected_data_hashes」）。

**錯誤訊息範例**:

```
DataSnapshotMismatchError:
  Asset: NVDA
  Expected (from config): a3f1b2c4d5e6...
  Actual   (from data/raw/metadata.json): f8e9d7c6b5a4...
  Action:  Either re-run `make data-snapshot` to refresh data/raw/, or update
           configs/baseline.yaml expected_data_hashes if the new snapshot is intended.
```

**Rationale**: 對齊 SC-008「不讀原始碼可定位問題」要求。錯誤訊息含「下一步行動」是工程實務最有效的 UX。

**Alternatives considered**:

- 僅 raise generic error：違反 SC-008，pass。
- 自動 prompt 是否更新：互動式 CLI 不適合 batch 訓練場景，pass。
