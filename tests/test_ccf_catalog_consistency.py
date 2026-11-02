#!/usr/bin/env python3
"""CCF 映射 vs 第七版官方目录（2026）一致性回归。

背景：映射表生成时混入了旧版等级，且缺少 IMWUT/PVLDB 等条目和
Crossref 风格全称别名；本测试锁定按官方 PDF 核实后的正确值。
同名缩写歧义条目（FSE/ASE/CSCW/CL/CC/TCC/ToCS 等）同时锁死取值。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.ccf_map import CCF_MAP  # noqa: E402
from backend.paper_store import _match_ccf, _IEEE_ABBREV  # noqa: E402

T = lambda k: CCF_MAP[k]["tier"]  # noqa: E731

# [1] 第七版等级修正（旧版残留）
assert T("HiPEAC") == "B" and T("ICS") == "B"          # 体系结构 B (原C)
assert T("AsiaCCS") == "C" and T("EuroS&P") == "C"     # 安全 C (原B)
assert T("MSR") == "C" and T("TASE") == "B"            # 软工会议C / T-ASE期刊B
assert T("WISE") == "B" and T("SAT") == "B" and T("PG") == "B"  # 升B
assert T("IROS") == "C"                                # 2025版降C
assert CCF_MAP["CSL"]["type"] == "conference" and T("CSL") == "C"  # 理论会议
assert CCF_MAP["DCC"]["domain"] == "计算机图形学与多媒体" and CCF_MAP["DCC"]["type"] == "conference"
print("[1] 等级/类型修正锁定 ✓")

# [2] 第七版本身如此、容易被误"修"的条目（同名歧义防护）
assert T("IJCAI") == "B"      # 2025版降为B，映射表本来就对
assert T("FSE") == "A" and T("FSE_crypto") == "B"      # 软工FSE≠密码FSE
assert T("ASE") == "A" and T("ASE_J") == "B"           # 会议≠期刊
assert T("CSCW") == "A" and T("CL") == "B"             # 会议A / Computational Linguistics B
assert T("ToCS") == "C" and T("TOCS") == "A"           # 两本不同期刊，大小写即不同键
assert T("FM") == "A" and T("HPDC") == "A" and T("PACMPL") == "C"
print("[2] 同名歧义条目取值锁定 ✓")

# [3] 新增条目 + 全称别名（数据库实际出现过的 venue 形态）
assert _match_ccf("Proceedings of the VLDB Endowment", "") == "A"
assert _match_ccf("PVLDB", "") == "A"
assert _match_ccf("Proceedings of the ACM on Human-Computer Interaction", "") == "C"
assert _match_ccf("International Conference on Architectural Support for Programming Languages and Operating Systems", "") == "A"
assert _match_ccf("IEEE International Conference on Computer Vision", "") == "A"
assert _match_ccf("International Conference on Learning Representations", "") == "A"
assert _match_ccf("International Symposium on Computer Architecture", "") == "A"
assert _match_ccf("Neural Information Processing Systems", "") == "A"
assert _match_ccf("Advances in Neural Information Processing Systems", "") == "A"
assert _match_ccf("International Conference on 3D Vision", "") == "C"
assert _match_ccf("Design, Automation and Test in Europe", "") == "B"
assert _match_ccf("Design, Automation & Test in Europe", "") == "B"
assert _match_ccf("IEEE International Conference on Parallel and Distributed Systems", "") == "C"
assert T("MSST") == "B" and T("SIGMETRICS") == "B" and T("ICPADS") == "C" and T("ISLPED") == "C"
print("[3] 新增条目与全称别名 ✓")

# [4] _IEEE_ABBREV 不再有断链目标（第七版已除名的 CSUR/TIM/TSP/TIS 已删）
broken = [f"{s}->{d}" for s, d in _IEEE_ABBREV.items()
          if d not in CCF_MAP and d.upper() != s]
assert not broken, f"断链: {broken}"
assert _match_ccf("", "ACM Transactions on Intelligent Systems and Technology") == "C"
assert _match_ccf("", "IEEE Transactions on Automation Science and Engineering") == "B"
assert _match_ccf("", "ACM Computing Surveys") == ""   # 不在第七版，不标
print("[4] _IEEE_ABBREV 全链路通 ✓")

# [5] IMWUT 修复不回退
assert _match_ccf("Proceedings of the ACM on Interactive Mobile Wearable and Ubiquitous Technologies", "") == "A"
print("[5] IMWUT 回归 ✓")

print("\nCCF 目录一致性测试通过 ✅")
