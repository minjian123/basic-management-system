#!/usr/bin/env python3
"""基线读写与环境指纹（13_08 T1）。

基线只承载「可重新生成的机器事实」：环境指纹 + 运行参数 + 分批 / 阶段 / 微基准数字。任务书 §2.1 /
§2.3 的历史数字来自不同分批口径与不同改动阶段，留在任务书与实施记录，不进 JSON —— 对比口径是
「同一脚本两次运行的 diff」（详细设计 §13.5）。
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList

PHASES = ("setup", "call", "teardown")
"""阶段名固定顺序。"""


@dataclass(frozen=True)
class MetricRow:
    """一条可比指标。

    Attributes:
        name: 中文指标名。
        current: 本次值。
        baseline: 基线值（无基线时为 None）。
        delta_pct: 增减百分比（基线缺失或为 0 时为 None）。
    """

    name: str
    current: float | None
    baseline: float | None
    delta_pct: float | None


def to_jsonable(value: object) -> object:
    """把插入序集合类递归转成 JSON 可序列化的普通结构。

    Args:
        value: 任意值（可能含 `ConcurrentStable*`）。

    Returns:
        object: 普通 dict / list / 标量。
    """
    if isinstance(value, ConcurrentStableList):
        return [to_jsonable(item) for item in value]
    if isinstance(value, ConcurrentStableDict):
        return {key: to_jsonable(value.get(key)) for key in value}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    return value


def _get(value: object, key: str) -> object:
    """宽容取值（payload 既可能是运行期的插入序集合类，也可能是 JSON 读回的普通 dict）。

    Args:
        value: 容器。
        key: 键名。

    Returns:
        object: 值；不是映射或缺键时为 None。
    """
    if isinstance(value, ConcurrentStableDict):
        return value.get(key)
    if isinstance(value, dict):
        return value.get(key)
    return None


def _number(value: object) -> float | None:
    """宽容取数（布尔不算数字）。

    Args:
        value: 任意值。

    Returns:
        float | None: 数值；不可解析时为 None。
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _items(value: object) -> ConcurrentStableList[object]:
    """宽容取列表。

    Args:
        value: 任意值。

    Returns:
        ConcurrentStableList[object]: 列表元素；不是列表时为空。
    """
    result: ConcurrentStableList[object] = ConcurrentStableList()
    if isinstance(value, (ConcurrentStableList, list)):
        result.extend(value)
    return result


def save_payload(payload: ConcurrentStableDict[str, object], path: Path) -> None:
    """写出基线 JSON（固定 LF、UTF-8、两空格缩进，便于 `git diff`）。

    Args:
        payload: 待写出的结构。
        path: 目标文件。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2) + "\n"
    # `newline="\n"`：Windows 文本模式默认会把 `\n` 翻成 CRLF（实施记录 §3 踩过 `Path.write_text`）。
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def load_payload(path: Path) -> object:
    """读取基线 JSON。

    Args:
        path: 基线文件。

    Returns:
        object: 解析结果（失败时调用方按「无基线」处理）。
    """
    return json.loads(path.read_text(encoding="utf-8"))


def collect_metrics(payload: object) -> ConcurrentStableDict[str, float]:
    """把 payload 摊平成「指标名 → 数值」，供基线对比。

    Args:
        payload: 本次结果或已读入的基线。

    Returns:
        ConcurrentStableDict[str, float]: 可比指标（插入序稳定）。
    """
    metrics: ConcurrentStableDict[str, float] = ConcurrentStableDict()
    batch = _get(payload, "batch")
    total = _number(_get(batch, "total_seconds"))
    if total is not None:
        metrics.set("全量耗时(s)", total)
    for index, item in enumerate(_items(_get(batch, "items")), start=1):
        seconds = _number(_get(item, "seconds"))
        if seconds is not None:
            metrics.set(f"批次 {index:02d}(s)", seconds)
    totals = _get(payload, "phase_totals")
    for phase in PHASES:
        value = _number(_get(totals, phase))
        if value is not None:
            metrics.set(f"阶段 {phase}(s)", value)
    for item in _items(_get(payload, "micro")):
        key = _get(item, "key")
        average = _number(_get(item, "avg_ms"))
        if isinstance(key, str) and average is not None:
            metrics.set(f"微基准 {key}(ms)", average)
    return metrics


def compare_metrics(
    current: ConcurrentStableDict[str, float], baseline: ConcurrentStableDict[str, float]
) -> ConcurrentStableList[MetricRow]:
    """逐指标比较本次与基线（保留顺序：先本次指标，再基线独有项）。

    Args:
        current: 本次指标。
        baseline: 基线指标。

    Returns:
        ConcurrentStableList[MetricRow]: 对比行。
    """
    rows: ConcurrentStableList[MetricRow] = ConcurrentStableList()
    for name in current:
        value = current.get(name, 0.0)
        base = baseline.get(name)
        delta = (value - base) / base * 100 if base not in (None, 0.0) else None
        rows.add(MetricRow(name=name, current=value, baseline=base, delta_pct=delta))
    for name in baseline:
        if name in current:
            continue
        rows.add(MetricRow(name=name, current=None, baseline=baseline.get(name), delta_pct=None))
    return rows


def _git(repo_root: Path, args: ConcurrentStableList[str]) -> str:
    """跑一条 git 命令并取标准输出（失败返回空串，不抛错）。

    Args:
        repo_root: 仓库根。
        args: 参数。

    Returns:
        str: 去空白后的输出。
    """
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except OSError, subprocess.TimeoutExpired:
        return ""
    return completed.stdout.strip()


def _cpu_model() -> str:
    """CPU 型号（Windows 读注册表、Linux 读 `/proc/cpuinfo`，失败回落到 `platform.processor()`）。

    Returns:
        str: CPU 型号或 `unknown`。
    """
    if os.name == "nt":  # Windows 分支
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                text = str(value).strip()
                if text:
                    return text
        except OSError:
            pass
    else:  # POSIX 分支（本地开发机不可达）
        try:
            for line in Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def _memory_gb() -> float | None:
    """物理内存（GB，取一位小数）；取不到返回 None。

    Returns:
        float | None: 内存大小。
    """
    if os.name == "nt":  # Windows 分支
        import ctypes

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_uint32),
                ("dwMemoryLoad", ctypes.c_uint32),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.ullTotalPhys / 1024**3, 1)
        return None
    try:  # POSIX 分支（本地开发机不可达）
        page_size = os.sysconf("SC_PAGE_SIZE")
        pages = os.sysconf("SC_PHYS_PAGES")
        return round(page_size * pages / 1024**3, 1)
    except ValueError, OSError, AttributeError:
        return None


def environment_fingerprint(repo_root: Path) -> ConcurrentStableDict[str, object]:
    """采集环境指纹（耗时数字离开环境就没有意义）。

    Args:
        repo_root: 仓库根。

    Returns:
        ConcurrentStableDict[str, object]: 环境指纹。
    """
    fingerprint: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    fingerprint.set("cpu", _cpu_model())
    fingerprint.set("logical_cores", os.cpu_count() or 0)
    fingerprint.set("memory_gb", _memory_gb())
    fingerprint.set("os", platform.platform())
    fingerprint.set("python", platform.python_version())
    fingerprint.set("interpreter", Path(sys.executable).as_posix())
    fingerprint.set("commit", _git(repo_root, ConcurrentStableList(["rev-parse", "--short", "HEAD"])) or "unknown")
    fingerprint.set("dirty", bool(_git(repo_root, ConcurrentStableList(["status", "--porcelain"]))))
    return fingerprint
