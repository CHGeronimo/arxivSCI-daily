#!/usr/bin/env python3
"""夜窗硬截止：00:00 起跑、02:30 前必须结束所有自动 LLM 消耗。

背景：自动任务拖到早上会挤占用户的 8:00 五小时个人配额窗口。
NIGHT_DEADLINE_MIN（起始后分钟数）到点后：worker 裸入库、收敛/链式步骤跳过。
"""
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.db import init_db, get_runtime_settings  # noqa: E402
init_db()

from backend import jobs  # noqa: E402


def _clean_kv():
    conn = sqlite3.connect("data/papers.db", timeout=10)
    conn.execute("DELETE FROM subscriptions WHERE key='runtime_settings'")
    conn.commit()
    conn.close()
    get_runtime_settings(force=True)


try:
    _clean_kv()

    # [1] 默认值：午夜起跑 + 150 分钟截止（02:30）
    s = get_runtime_settings()
    assert s["NIGHT_START"] == 0 and s["STAGGER_MINUTES"] == 15, s
    assert s["NIGHT_DEADLINE_MIN"] == 150
    d = jobs._night_deadline()
    expect = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=150)
    assert abs(d - expect.timestamp()) < 5, f"截止应为今日02:30: {d} vs {expect}"
    print("[1] 默认 00:00 起跑 / 02:30 截止 ✓")

    # [2] 截止=0 → 不限制
    conn = sqlite3.connect("data/papers.db", timeout=10)
    conn.execute("INSERT OR REPLACE INTO subscriptions (key,value) VALUES ('runtime_settings',?)",
                 (json.dumps({"NIGHT_DEADLINE_MIN": 0}),))
    conn.commit(); conn.close()
    get_runtime_settings(force=True)
    assert jobs._night_deadline() is None and not jobs.past_night_deadline()
    print("[2] 0=不限 ✓")

    # [3] 跨午夜窗口：23:00 起 + 180 分钟 → 截止在次日 02:00
    conn = sqlite3.connect("data/papers.db", timeout=10)
    conn.execute("INSERT OR REPLACE INTO subscriptions (key,value) VALUES ('runtime_settings',?)",
                 (json.dumps({"NIGHT_START": 23, "NIGHT_DEADLINE_MIN": 180}),))
    conn.commit(); conn.close()
    get_runtime_settings(force=True)
    now = datetime.now()
    start = now.replace(hour=23, minute=0, second=0, microsecond=0)
    if start > now:
        start -= timedelta(days=1)
    d = jobs._night_deadline()
    assert abs(d - (start + timedelta(minutes=180)).timestamp()) < 5
    # 语义断言：凌晨 1:00~2:00 之间应已过截止（23:00+180m=02:00）
    if 1 <= now.hour < 2:
        assert jobs.past_night_deadline(), "凌晨1点应已过 23:00+180min 截止"
    print("[3] 跨午夜窗口截止计算 ✓")

    # [4] 调度分布：7 任务 × 15 分钟，首个 00:00，最后一个(trend_auto) 01:30 起
    #     日报为收尾任务：02:20（截止 02:30 前 10 分、晚于全部任务槽位）
    _clean_kv()
    jobs._scheduler_instance = None
    sched = jobs.Scheduler()  # 不 start，不起线程
    t0 = sched._next_run_at("arxiv")
    assert (t0.hour, t0.minute) == (0, 0), t0
    tlast = sched._next_run_at("trend_auto")
    assert (tlast.hour, tlast.minute) == (1, 30), tlast
    tdg = sched._digest_run_at()
    assert (tdg.hour, tdg.minute) == (2, 20), tdg
    assert tdg > tlast, "日报必须晚于最后一个任务槽位"
    print("[4] 任务分布 00:00–01:30，日报收尾 02:20 ✓")

    # [5] monotonic 钳制：夜窗截止更早时取夜窗
    conn = sqlite3.connect("data/papers.db", timeout=10)
    conn.execute("INSERT OR REPLACE INTO subscriptions (key,value) VALUES ('runtime_settings',?)",
                 (json.dumps({"NIGHT_START": 0, "NIGHT_DEADLINE_MIN": 1}),))
    conn.commit(); conn.close()
    get_runtime_settings(force=True)
    far = time.monotonic() + 3600
    clamped = jobs.clamp_monotonic_to_night(far)
    assert clamped <= far
    if jobs.past_night_deadline():  # 当前时刻已过今日00:01（几乎总是成立）
        assert clamped <= time.monotonic(), "已过截止应立即到点"
    print("[5] 收敛 deadline 钳制到夜窗 ✓")
finally:
    _clean_kv()

print("\n夜窗截止测试通过 ✅")
