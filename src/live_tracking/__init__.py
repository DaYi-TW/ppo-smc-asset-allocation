"""live_tracking — 010 daily prediction tracking pipeline.

每日 PPO inference → single-step env → append frame → 全段重算 SMC overlay → atomic write。
Spec: ``specs/010-live-tracking-dashboard/spec.md``。
"""

from __future__ import annotations

__version__ = "0.1.0"
