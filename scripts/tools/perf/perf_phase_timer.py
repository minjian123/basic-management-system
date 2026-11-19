#!/usr/bin/env python3
"""阶段计时插件（`-p perf_phase_timer`）：把每条用例的 setup / call / teardown 耗时落 JSONL。

为什么单独成插件：`--durations` 是给人读的文本，靠正则解析、pytest 改版即可能悄悄失效（失效表现为
「最慢项为空」而不是报错）；`--junitxml` 只有整条用例总时长，分不出「最慢项几乎全在 setup」这一历史
口径（任务书 §2.2）。

落点：环境变量 `BMS_PERF_PHASE_DIR` 指向目录，按 xdist worker 各写一份 `phase-<worker>.jsonl`
（多进程同写一个文件会互相截断）。每条记录一行 JSON：

- `{"event": "start", "test": <nodeid>}`：用例开始（超时定位靠它算「已开始未结束」）；
- `{"event": "phase", "test": <nodeid>, "phase": "setup|call|teardown", "duration": 秒, "outcome": ...}`。

**本模块刻意不 import `bms_core`**：它由 `-p` 在覆盖率探针启动前后加载，过早导入被测包会漏计导入期
执行的行（历史实测漏计导致全仓覆盖率长期停在 93.36%）。同理，本文件不写集合类型标注——裸集合护栏
只查声明（含类字段 / 参数 / 返回 / 带注解的局部变量），不查未标注的模块级变量与局部变量。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_PHASE_DIR_ENV = "BMS_TEST_PERF_PHASE_DIR"
"""阶段记录落点目录（由 `perf_runner` 设置；未设置时插件完全不动作）。

**必须用 `BMS_TEST_` 前缀**：逐用例夹具 `clear_isolated_env` 会删掉所有 `BMS_` 前缀变量
（只保留 `BMS_TEST_`），否则 setup / call 阶段变量消失、只剩 teardown 能记（实测）。"""

_handle: Any = None
"""已打开的输出句柄（进程内单例；xdist 每个 worker 各一个进程）。"""

_disabled = False
"""写盘失败后置位：记录是旁路产物，不能因为它让用例失败。"""

_controller = False
"""当前进程是不是「xdist controller」——它只转发 worker 的报告，再记一遍就会重复计数。"""


def pytest_configure(config: Any) -> None:
    """判定当前进程是否需要记录（xdist 下只由 worker 记录）。

    Args:
        config: pytest 配置对象。
    """
    global _controller
    _controller = config.pluginmanager.hasplugin("xdist") and not os.environ.get("PYTEST_XDIST_WORKER")


def _target() -> Path | None:
    """当前进程的输出文件（按 xdist worker 名区分）。

    Returns:
        Path | None: 输出文件；未启用采样时为 None。
    """
    directory = os.environ.get(_PHASE_DIR_ENV, "").strip()
    if not directory:
        return None
    worker = os.environ.get("PYTEST_XDIST_WORKER", "").strip() or "main"
    return Path(directory) / f"phase-{worker}.jsonl"


def _emit(payload: str) -> None:
    """追加一行记录并立即刷盘（刷盘才能让卡住现场的「最后一条 start」可见）。

    Args:
        payload: 已序列化的单行 JSON。
    """
    global _handle, _disabled
    if _disabled or _controller:
        return
    path = _target()
    if path is None:
        return
    try:
        if _handle is None:
            path.parent.mkdir(parents=True, exist_ok=True)
            _handle = path.open("a", encoding="utf-8")
        _handle.write(payload + "\n")
        _handle.flush()
    except OSError:
        _disabled = True


def pytest_runtest_logstart(nodeid: str, location: object) -> None:
    """用例开始：落一条 `start`（用于超时后点名「已开始未结束」的用例）。

    Args:
        nodeid: 用例节点 ID。
        location: pytest 传入的位置三元组（本插件不使用）。
    """
    del location
    _emit(json.dumps({"event": "start", "test": nodeid, "at": round(time.time(), 3)}, ensure_ascii=False))


def pytest_runtest_logreport(report: Any) -> None:
    """用例阶段结束：按 setup / call / teardown 各落一条耗时。

    Args:
        report: pytest 的 `TestReport`（只取 `when` / `duration` / `outcome` / `nodeid`）。
    """
    if report.when not in ("setup", "call", "teardown"):
        return
    record = {
        "event": "phase",
        "test": report.nodeid,
        "phase": report.when,
        "duration": round(float(report.duration), 6),
        "outcome": report.outcome,
    }
    _emit(json.dumps(record, ensure_ascii=False))


def pytest_sessionfinish(session: object, exitstatus: int) -> None:
    """会话结束：关闭句柄（不强制 flush——每条记录已刷盘）。

    Args:
        session: pytest 会话（本插件不使用）。
        exitstatus: 退出码（本插件不使用）。
    """
    del session, exitstatus
    global _handle
    if _handle is not None:
        try:
            _handle.close()
        finally:
            _handle = None
