#!/usr/bin/env python3
"""CCF 标注：IMWUT（目录条目 UbiComp/IMWUT，CCF-A）各种写法都必须命中。

回归背景：RF-HeartSSL 论文的 venue 是 Crossref 无逗号写法
"Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies"，
映射表缺 IMWUT 条目 + 子串匹配对标点敏感，导致 A 类期刊被漏标。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.paper_store import _match_ccf  # noqa: E402

# [1] 数据库中实际的无逗号 Crossref 写法
assert _match_ccf(
    "Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies", ""
) == "A"

# [2] 标准带逗号写法 / 缩写 / 目录合并写法 / Crossref 缩略写法
assert _match_ccf(
    "Proceedings of the ACM on Interactive, Mobile, Wearable and Ubiquitous Technologies", ""
) == "A"
assert _match_ccf("IMWUT", "") == "A"
assert _match_ccf("UbiComp/IMWUT", "") == "A"
assert _match_ccf("Proc. ACM Interact. Mob. Wearable Ubiquitous Technol.", "") == "A"
print("[1-2] IMWUT 五种写法 → A ✓")

# [3] 标点不敏感不能引入误标：近似 PACM 系列其它刊物保持原判级
assert _match_ccf("Proceedings of the ACM on Programming Languages", "") == "C"
assert _match_ccf("Personal and Ubiquitous Computing", "") == "C"  # 另一本同名近邻期刊
assert _match_ccf("Nature Biomedical Engineering", "") == ""       # 非 CCF 不标
print("[3] 负例：PACMPL=C、PUC=C、非CCF=空 ✓")

# [4] 原有匹配路径不受影响（直接命中/缩写归一/年份后缀剥离）
assert _match_ccf("CVPR 2025", "") == "A"
assert _match_ccf("", "IEEE Transactions on Mobile Computing") == "A"
print("[4] 既有路径回归 ✓")

print("\nIMWUT CCF 标注测试通过 ✅")
