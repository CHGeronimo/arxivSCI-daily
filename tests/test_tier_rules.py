#!/usr/bin/env python3
"""分层规则回归：默认视图 ~15 篇/天（2026-11-02 二次校准）。

档位由 tier_from_scores 确定性裁决，LLM 只打分——比例可控、不漂移。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ai.enhance import tier_from_scores as T  # noqa: E402

# [1] 特长生通道：相关度顶尖不看质量
assert T(9, 4) == "must-read", "rel=9 质量再差也是特长生 must-read"
assert T(10, 3) == "must-read"
# [2] 全面发展通道：双 8 门槛
assert T(8, 8) == "must-read"
assert T(8, 7) == "recommended", "rel=8 qua=7 → recommended（双8才 must）"
# [3] recommended 双通道（收紧后）
assert T(7, 7) == "recommended"          # 全面型：双 7
assert T(7, 6) == "reference", "rel=7 qua=6 → reference（qua 门槛提高到 7）"
assert T(6, 9) == "recommended"          # 质量特长生：qua 门槛提高到 9
assert T(6, 8) == "reference", "rel=6 qua=8 → reference（特长生通道收紧）"
# [4] reference 底座与 ignore 线
assert T(6, 3) == "reference"
assert T(5, 9) == "ignore", "rel=5 质量再高也 ignore（相关度一票否决）"
assert T(0, 0) == "ignore"
print("[1-4] 特长生/全面发展/底座/一票否决 全部 ✓")

# [5] 通道完备性：rel 0-10 × qua 0-10 全组合无异常值
for rel in range(11):
    for qua in range(11):
        t = T(rel, qua)
        assert t in ("must-read", "recommended", "reference", "ignore"), (rel, qua, t)
        if rel <= 5:
            assert t == "ignore", (rel, qua)
        if rel >= 9:
            assert t == "must-read", (rel, qua)
print("[5] 121 组合遍历，单调性正确 ✓")

print("\n分层规则测试通过 ✅")
