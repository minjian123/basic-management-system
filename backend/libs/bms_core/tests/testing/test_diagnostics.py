"""卡住现场诊断工具用例（Kiwi 2533）：开关、节流、任务栈与线程栈落盘。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bms_core.testing import diagnostics

pytestmark = pytest.mark.kiwi_id(2533)


def test_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """开关：未设置 / 非真值关闭，`1` `true` `YES` `on` 开启。"""
    monkeypatch.delenv(diagnostics.DUMP_ENV, raising=False)
    assert diagnostics.enabled() is False
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv(diagnostics.DUMP_ENV, value)
        assert diagnostics.enabled() is True
    monkeypatch.setenv(diagnostics.DUMP_ENV, "0")
    assert diagnostics.enabled() is False


def test_dump_every_seconds_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """节流间隔：缺省 / 非数字 / 非正数一律回落默认值。"""
    monkeypatch.delenv(diagnostics.DUMP_EVERY_ENV, raising=False)
    assert diagnostics.dump_every_seconds() == diagnostics.DEFAULT_EVERY_SECONDS
    monkeypatch.setenv(diagnostics.DUMP_EVERY_ENV, "abc")
    assert diagnostics.dump_every_seconds() == diagnostics.DEFAULT_EVERY_SECONDS
    monkeypatch.setenv(diagnostics.DUMP_EVERY_ENV, "0")
    assert diagnostics.dump_every_seconds() == diagnostics.DEFAULT_EVERY_SECONDS
    monkeypatch.setenv(diagnostics.DUMP_EVERY_ENV, "3.5")
    assert diagnostics.dump_every_seconds() == 3.5


async def test_dump_process_stacks_contains_tasks_and_threads(tmp_path: Path) -> None:
    """抓取内容含任务名、任务栈与线程栈。"""
    path = tmp_path / "stacks.log"

    started = asyncio.Event()
    release = asyncio.Event()

    async def _worker() -> None:
        """一个可识别的后台任务（停在事件上，供抓栈）。"""
        started.set()
        await release.wait()

    task = asyncio.create_task(_worker(), name="diag-worker")
    await started.wait()
    diagnostics.dump_process_stacks(path, reason="warn", detail="门=platform")
    release.set()
    await task

    text = path.read_text(encoding="utf-8")
    assert "warn 门=platform" in text
    assert "diag-worker" in text
    assert "--- thread" in text
    assert "(当前线程)" in text


def test_dump_process_stacks_without_loop(tmp_path: Path) -> None:
    """同步上下文（无运行中的事件循环）只抓线程栈，不报错。"""
    path = tmp_path / "sync.log"

    diagnostics.dump_process_stacks(path, reason="manual")

    assert "无运行中的事件循环" in path.read_text(encoding="utf-8")


def test_note_gate_wait_respects_switch_and_throttle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未开启不落盘；开启后同一进程按间隔节流，且带上持有者描述。"""
    path = tmp_path / "gate.log"
    diagnostics.reset_throttle()
    monkeypatch.delenv(diagnostics.DUMP_ENV, raising=False)
    assert diagnostics.note_gate_wait(path, gate_name="platform", waited=10.0, reason="warn") is None
    assert not path.exists()

    monkeypatch.setenv(diagnostics.DUMP_ENV, "1")
    monkeypatch.setenv(diagnostics.DUMP_EVERY_ENV, "3600")
    first = diagnostics.note_gate_wait(path, gate_name="platform", waited=10.0, reason="warn", holder="pid=1 mode=read")
    assert first == path
    assert diagnostics.note_gate_wait(path, gate_name="platform", waited=11.0, reason="timeout") is None
    assert "持有者=pid=1 mode=read" in path.read_text(encoding="utf-8")
