# Colab cell — train/eval split：2018-2024 訓練 / 2025-2026 評估

把下面整段貼進 Colab 一個 cell（建議 GPU runtime：T4 或 A100）。

跑完後 `runs/oos_split/` 會有兩個訓練好的 policy + 兩份 trajectory.csv，
最後也會自動 `git add + commit + push` 回 `004-train-test-split` 分支
（如果你給了 GitHub PAT；沒給就只下載成 zip）。

---

```python
# ====================================================================
# Cell 1 — env setup, repo clone, install deps
# ====================================================================
import os, subprocess, sys, time
from pathlib import Path

# 1. clone repo（如果已經 clone 過會更新到最新）
REPO_URL = "https://github.com/DaYi-TW/ppo-smc-asset-allocation.git"
BRANCH = "004-train-test-split"
WORK = Path("/content/ppo-smc-asset-allocation")

if WORK.exists():
    subprocess.run(["git", "-C", str(WORK), "fetch", "origin"], check=True)
    subprocess.run(["git", "-C", str(WORK), "checkout", BRANCH], check=True)
    subprocess.run(["git", "-C", str(WORK), "reset", "--hard", f"origin/{BRANCH}"], check=True)
else:
    subprocess.run(["git", "clone", "-b", BRANCH, REPO_URL, str(WORK)], check=True)

os.chdir(WORK)
print("HEAD:", subprocess.check_output(["git", "log", "-1", "--oneline"], cwd=WORK).decode())

# 2. install repo + train extras（torch GPU build 已內建在 Colab）
!pip install -q -e ".[train]"

# 3. sanity：driver + cuda 可用？
import torch
print(f"torch={torch.__version__}  cuda={torch.cuda.is_available()}  device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")

# 4. 確認資料就位（data/raw/*.parquet 已 commit 在 repo）
import glob
parquets = sorted(glob.glob("data/raw/*_daily_*.parquet"))
print(f"data/raw 有 {len(parquets)} 個 parquet：")
for p in parquets:
    print(f"  {Path(p).name}")
assert len(parquets) >= 7, "需要 6 檔資產 + dtb3 = 7 個 parquet"
```

```python
# ====================================================================
# Cell 2 — 訓練 SMC + no-SMC（OOS split：train 2018-01-01 → 2024-12-31）
# ====================================================================
# 各 500k steps；T4 GPU 約 20-25 分鐘 / 個 → 兩個共 ~50 分鐘。
# A100 約 8-12 分鐘 / 個 → 兩個共 ~25 分鐘。

import time
SEED = 42
TRAIN_START = "2018-01-01"
TRAIN_END = "2024-12-31"

# SMC 訓練
print("=" * 70)
print(f"訓練 #1：SMC (include_smc=True), seed={SEED}")
print("=" * 70)
t0 = time.time()
!python -m ppo_training.train \
    --total-timesteps 500000 \
    --seed {SEED} \
    --device cuda \
    --start-date {TRAIN_START} \
    --end-date {TRAIN_END} \
    --run-dir runs/oos_split/smc_train2018-2024_seed{SEED}
print(f"\n[smc] 訓練完成，耗時 {(time.time()-t0)/60:.1f} 分鐘")

# no-SMC 訓練（ablation）
print()
print("=" * 70)
print(f"訓練 #2：no-SMC (ablation), seed={SEED}")
print("=" * 70)
t0 = time.time()
!python -m ppo_training.train \
    --total-timesteps 500000 \
    --seed {SEED} \
    --device cuda \
    --no-smc \
    --start-date {TRAIN_START} \
    --end-date {TRAIN_END} \
    --run-dir runs/oos_split/nosmc_train2018-2024_seed{SEED}
print(f"\n[nosmc] 訓練完成，耗時 {(time.time()-t0)/60:.1f} 分鐘")
```

```python
# ====================================================================
# Cell 3 — 評估（OOS：2025-01-01 → 2026-04-29）+ in-sample baseline
# ====================================================================
SEED = 42
EVAL_START_OOS = "2025-01-01"
EVAL_END_OOS = "2026-04-29"
EVAL_START_IS = "2018-01-01"
EVAL_END_IS = "2024-12-31"

SMC_DIR = f"runs/oos_split/smc_train2018-2024_seed{SEED}"
NOSMC_DIR = f"runs/oos_split/nosmc_train2018-2024_seed{SEED}"

# SMC OOS
print("=" * 70)
print("評估 #1：SMC policy on OOS 2025-01 → 2026-04")
print("=" * 70)
!python -m ppo_training.evaluate \
    --policy {SMC_DIR}/final_policy.zip \
    --start-date {EVAL_START_OOS} \
    --end-date {EVAL_END_OOS} \
    --save-trajectory \
    --output {SMC_DIR}/eval_oos.json

# SMC IS（同訓練期跑一次當 sanity / 對比）
print()
print("=" * 70)
print("評估 #2：SMC policy on IS 2018-01 → 2024-12（訓練期，當 sanity）")
print("=" * 70)
!python -m ppo_training.evaluate \
    --policy {SMC_DIR}/final_policy.zip \
    --start-date {EVAL_START_IS} \
    --end-date {EVAL_END_IS} \
    --save-trajectory \
    --output {SMC_DIR}/eval_is.json

# no-SMC OOS
print()
print("=" * 70)
print("評估 #3：no-SMC policy on OOS 2025-01 → 2026-04")
print("=" * 70)
!python -m ppo_training.evaluate \
    --policy {NOSMC_DIR}/final_policy.zip \
    --no-smc \
    --start-date {EVAL_START_OOS} \
    --end-date {EVAL_END_OOS} \
    --save-trajectory \
    --output {NOSMC_DIR}/eval_oos.json

# no-SMC IS
print()
print("=" * 70)
print("評估 #4：no-SMC policy on IS 2018-01 → 2024-12（sanity）")
print("=" * 70)
!python -m ppo_training.evaluate \
    --policy {NOSMC_DIR}/final_policy.zip \
    --no-smc \
    --start-date {EVAL_START_IS} \
    --end-date {EVAL_END_IS} \
    --save-trajectory \
    --output {NOSMC_DIR}/eval_is.json
```

```python
# ====================================================================
# Cell 4 — 把訓練 + 評估結果上 commit 回 GitHub（需要 GitHub PAT）
# ====================================================================
# 如果沒有 PAT，跳過此 cell，改用 Cell 5 下載 zip。
#
# 拿 PAT：https://github.com/settings/tokens?type=beta
#   - Repository access: 只勾你的 repo
#   - Permissions: Contents = Read & Write
#
# Colab 用 Secret 存（左側鎖頭 icon）：key=GITHUB_PAT。

from google.colab import userdata
PAT = userdata.get('GITHUB_PAT')  # 在 Colab Secrets 面板新增
USER = "DaYi-TW"

# 配置 git author
!git config user.email "kirito203203@gmail.com"
!git config user.name "DaYi-TW (Colab)"

# 加 oos_split 結果（runs/ 預設應該不在 .gitignore；若被 ignore 用 -f）
!git add -f runs/oos_split/
!git status --short

# commit + push
!git commit -m "feat(004): OOS 2018-2024 train / 2025-2026 eval — SMC vs no-SMC ablation

訓練：2018-01-01 → 2024-12-31（1761 trading days）
評估：2025-01-01 → 2026-04-29（331 trading days, 完全 unseen）
500k timesteps each, seed 42, device cuda

🤖 Generated on Colab"

# Push（需要 PAT）
remote_url = f"https://{USER}:{PAT}@github.com/{USER}/ppo-smc-asset-allocation.git"
!git push {remote_url} HEAD:004-train-test-split
```

```python
# ====================================================================
# Cell 5 — 替代：把結果打包下載（不需 PAT）
# ====================================================================
import shutil
shutil.make_archive("/content/oos_split_runs", "zip", "runs/oos_split")
print("Done →", "/content/oos_split_runs.zip")
print("可以從 Colab 左側檔案面板下載，或用下面 cell 直接觸發瀏覽器下載：")

from google.colab import files
files.download("/content/oos_split_runs.zip")
```

```python
# ====================================================================
# Cell 6 — 摘要表（4 種情境）
# ====================================================================
import json
from pathlib import Path

print(f"{'情境':<35} {'NAV倍數':>10} {'年化':>10} {'MDD':>8} {'Sharpe':>8}")
print("-" * 75)

for tag, path in [
    ("SMC train2018-24, eval IS",     "runs/oos_split/smc_train2018-2024_seed42/eval_is.json"),
    ("SMC train2018-24, eval OOS",    "runs/oos_split/smc_train2018-2024_seed42/eval_oos.json"),
    ("no-SMC train2018-24, eval IS",  "runs/oos_split/nosmc_train2018-2024_seed42/eval_is.json"),
    ("no-SMC train2018-24, eval OOS", "runs/oos_split/nosmc_train2018-2024_seed42/eval_oos.json"),
]:
    p = Path(path)
    if not p.exists():
        print(f"{tag:<35}  (missing: {path})")
        continue
    d = json.loads(p.read_text())
    print(
        f"{tag:<35} "
        f"{d.get('final_nav', 0):>9.3f}x "
        f"{d.get('annualized_return', 0)*100:>+8.2f}% "
        f"{d.get('max_drawdown', 0)*100:>7.2f}% "
        f"{d.get('sharpe_ratio', 0):>+7.3f}"
    )

print()
print("解讀：")
print("  - SMC OOS 比 SMC IS 大幅縮水 → 主要是 memorization，paper 慎報")
print("  - SMC OOS 跟 no-SMC OOS 比 → 才是 SMC 特徵的真正貢獻")
print("  - SMC OOS Sharpe < 1 → SMC 在未見資料沒有泛化")
```
