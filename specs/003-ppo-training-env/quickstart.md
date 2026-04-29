# Quickstart: 003-ppo-training-env

**Goal**: 5 分鐘內讓新成員從零跑通一個完整 episode（隨機策略），並驗證 reward
三項分量、observation 維度、跨次重設可重現性。

**Prerequisites**:
- 002-data-ingestion 已執行 `fetch`，`data/raw/` 下有 6 檔股票 Parquet + DTB3
  Parquet + 對應 metadata sidecar（由 002 quickstart 完成）。
- 001-smc-feature-engine 已實作完成、可 `from smc_features import batch_compute` import。
- Python 3.11+、虛擬環境啟動。

---

## §1 安裝

```bash
# 從 repo 根目錄
pip install -e .                                    # 安裝 portfolio_env package（含 002、001 dependency）
python -c "import portfolio_env; print(portfolio_env.__version__)"
```

## §2 建立預設環境

```python
from pathlib import Path
from portfolio_env import make_default_env

env = make_default_env(data_root=Path("data/raw"))
print("Observation space:", env.observation_space)   # Box(63,)
print("Action space:", env.action_space)             # Box(7,)
```

`make_default_env` 等價於：

```python
from portfolio_env import PortfolioEnv, PortfolioEnvConfig

config = PortfolioEnvConfig(data_root=Path("data/raw"))
env = PortfolioEnv(config)
```

`__init__` 階段會：
1. 讀取 6 檔股票 + DTB3 Parquet 並比對 SHA-256（research R6，失敗 raise）。
2. 過濾 quality_flag != ok 的股票日（research R5）。
3. 一次性計算所有 SMC 特徵（research R7）。
4. 預組價格特徵與 macro 特徵到 numpy 陣列。

預期耗時 < 10 秒（取決於 SMC 計算成本）。

## §3 跑一個隨機策略 episode

```python
import numpy as np

obs, info = env.reset(seed=42)
assert obs.shape == (63,)
assert info["is_initial_step"] is True
assert info["nav"] == 1.0

rng = np.random.default_rng(42)
total_reward = 0.0
steps = 0
while True:
    action = rng.dirichlet(np.ones(7)).astype(np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    total_reward += reward
    steps += 1
    if terminated:
        break

print(f"Episode finished: {steps} steps, total reward = {total_reward:.4f}")
print(f"Final NAV = {info['nav']:.4f}, peak NAV = {info['peak_nav']:.4f}")
```

預期輸出（具體數值因 seed 而定，但結構固定）：

```
Episode finished: 2089 steps, total reward = -0.1234
Final NAV = 1.7563, peak NAV = 1.9821
```

## §4 驗證 reward 三項分量（憲法 Principle III）

```python
obs, info = env.reset(seed=42)
action = np.array([0.1, 0.1, 0.1, 0.1, 0.2, 0.2, 0.2], dtype=np.float32)
obs, reward, terminated, truncated, info = env.step(action)

components = info["reward_components"]
recomputed = (
    components["log_return"]
    - components["drawdown_penalty"]
    - components["turnover_penalty"]
)
assert abs(recomputed - reward) < 1e-9, "Reward 三項加總必須等於 reward"
print(f"log_return       = {components['log_return']:+.6f}")
print(f"drawdown_penalty = {components['drawdown_penalty']:.6f}")
print(f"turnover_penalty = {components['turnover_penalty']:.6f}")
print(f"reward           = {reward:+.6f}")
```

## §5 驗證可重現性（憲法 Principle I）

```python
def run_episode(seed):
    env = make_default_env(data_root=Path("data/raw"))
    obs, _ = env.reset(seed=seed)
    rng = np.random.default_rng(seed)
    navs = [1.0]
    while True:
        action = rng.dirichlet(np.ones(7)).astype(np.float32)
        obs, reward, terminated, _, info = env.step(action)
        navs.append(info["nav"])
        if terminated:
            return navs

navs_a = run_episode(seed=42)
navs_b = run_episode(seed=42)
assert navs_a == navs_b, "兩次 seed=42 的 NAV 序列必須完全相同（byte-identical）"
print(f"OK — {len(navs_a)} 個 NAV 點 byte-identical")
```

## §6 SMC ablation 開關（Principle II 視覺化驗證對照組）

```python
from portfolio_env import PortfolioEnv, PortfolioEnvConfig

# 含 SMC：63 維
env_full = PortfolioEnv(PortfolioEnvConfig(
    data_root=Path("data/raw"),
    include_smc=True,
))
assert env_full.observation_space.shape == (63,)

# 純價格 ablation：33 維
env_price = PortfolioEnv(PortfolioEnvConfig(
    data_root=Path("data/raw"),
    include_smc=False,
))
assert env_price.observation_space.shape == (33,)

# 兩者首日 obs 的非 SMC 段必須完全相同
obs_full, _ = env_full.reset(seed=42)
obs_price, _ = env_price.reset(seed=42)
assert np.allclose(obs_full[:24], obs_price[:24], atol=0.0)        # 價格
assert np.allclose(obs_full[54:], obs_price[26:], atol=0.0)        # macro + weights
print("OK — SMC 段切除後其他維度 byte-identical")
```

## §7 將 info 序列化為 JSON（feature 005/007 介面）

```python
import json
from portfolio_env import info_to_json_safe

obs, info = env.reset(seed=42)
obs, reward, _, _, info = env.step(action)
json_safe = info_to_json_safe(info)
print(json.dumps(json_safe, indent=2)[:300], "...")
```

對 `info_to_json_safe` 的輸出做 `json.dumps()` 不應 raise；任何 numpy 物件都
已轉為 Python native types（list / float / int / bool）。

## §8 跑單元與整合測試

```bash
pytest tests/ -v --cov=src/portfolio_env --cov-report=term-missing
```

預期：所有測試通過，覆蓋率 ≥ 90%（憲法 SC-006）。重點測試：

| 測試檔 | 對應 spec |
|---|---|
| `tests/contract/test_gym_check_env.py` | SC-003（include_smc 兩種 config 都過 env_checker） |
| `tests/integration/test_random_episode.py` | US1 |
| `tests/integration/test_reward_components.py` | US2、SC-004 |
| `tests/integration/test_smc_ablation.py` | US3 |
| `tests/integration/test_info_completeness.py` | US4 |
| `tests/integration/test_cross_platform_trajectory.py` | FR-020、SC-002（CI 跨三平台） |
| `tests/integration/test_episode_perf.py` | SC-001（< 30 秒） |
| `tests/integration/test_data_hash_mismatch.py` | FR-021（hash 不符 raise） |

## §9 常見錯誤排查

| 症狀 | 可能原因 | 修法 |
|---|---|---|
| `RuntimeError: Snapshot hash mismatch` | `data/raw/` 下 Parquet 已被改動（與 002 metadata 不一致） | `python -m data_ingestion.cli verify`；若失敗重跑 002 fetch |
| `ImportError: cannot import name 'batch_compute' from 'smc_features'` | 001 尚未實作 | 先完成 001 implement |
| `ValueError: Action contains NaN` | agent 輸出未 sanitize | 檢查 PPO policy head；訓練前期可加 nan_to_num |
| `ValueError: Action sum near zero` | agent 輸出全零向量（exploration bug） | 檢查 PPO entropy bonus 設定 |
| 跨機器 NAV 序列差異 > 1e-9 | BLAS thread 數未鎖定 | export `OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1`（research R2） |
| 同機器 reward 三項加總 ≠ reward（差 > 1e-12） | 浮點累加順序未遵守 R2 | 檢查實作是否走 `numpy.sum` 而非 Python `−` 運算子 |

## §10 容差語意速查表

| 場景 | 容差 | 出處 |
|---|---|---|
| 同機器純算術一致性 | 1e-12 | research R8、US2 |
| 跨平台 byte-identical | 1e-9 | FR-020、SC-002 |
| Action 觸發 L1 normalize 門檻 | 1e-6 | FR-014 |
