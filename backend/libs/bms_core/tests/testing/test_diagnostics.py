# pyright: reportPrivateUsage=false

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


def test_hang_every_seconds_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """定时抓栈间隔：未设置 / 非法 / 非正数一律视为关闭。"""
    monkeypatch.delenv(diagnostics.HANG_ENV, raising=False)
    assert diagnostics.hang_every_seconds() == 0.0
    monkeypatch.setenv(diagnostics.HANG_ENV, "abc")
    assert diagnostics.hang_every_seconds() == 0.0
    monkeypatch.setenv(diagnostics.HANG_ENV, "-1")
    assert diagnostics.hang_every_seconds() == 0.0
    monkeypatch.setenv(diagnostics.HANG_ENV, "2.5")
    assert diagnostics.hang_every_seconds() == 2.5


async def test_watch_tick_writes_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """看守的一次抓取：在活动循环上调度并落盘。"""
    path = tmp_path / "hang.log"
    diagnostics.reset_watchdogs()
    monkeypatch.setenv(diagnostics.HANG_ENV, "0.01")
    diagnostics._current_loop = asyncio.get_running_loop()
    diagnostics._watch_path = path

    diagnostics._watch_tick(0.01)
    await asyncio.to_thread(lambda: None)
    await asyncio.to_thread(lambda: None)

    assert path.exists() and "watchdog" in path.read_text(encoding="utf-8")
    diagnostics.reset_watchdogs()


async def test_ensure_watchdog_skips_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置间隔时不起看守。"""
    monkeypatch.delenv(diagnostics.HANG_ENV, raising=False)
    diagnostics.reset_watchdogs()

    diagnostics.ensure_watchdog(tmp_path / "off.log")

    assert diagnostics._watch_path is None
    assert diagnostics._watch_started is False


async def test_ensure_watchdog_updates_path_once_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """启用后重复调用只更新落点，不重复起线程。"""
    monkeypatch.setenv(diagnostics.HANG_ENV, "5")
    diagnostics.reset_watchdogs()

    diagnostics.ensure_watchdog(tmp_path / "a.log")
    diagnostics.ensure_watchdog(tmp_path / "b.log")

    assert diagnostics._watch_path == tmp_path / "b.log"
    assert diagnostics._watch_started is True
    diagnostics.reset_watchdogs()


def test_note_hold_writes_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """持有时长采样：开启后写一行（时长 / 模式 / 门名 / 用例）。"""
    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)

    diagnostics.note_hold("tenant", 0.25, read_only=False, wait_read=0.01, wait_write=0.2, held=0.04)

    text = (tmp_path / ".cache/test/gate-hold.log").read_text(encoding="utf-8")
    assert "0.250" in text
    assert "write" in text
    assert "tenant" in text
    # 三段分开落盘：总时长 / 等读 / 等写 / 实占，缺一段就无法区分排队与真持有
    assert "\t0.010\t0.200\t0.040" in text


def test_note_hold_respects_switch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """未开启时不写文件。"""
    monkeypatch.delenv(diagnostics.HOLD_ENV, raising=False)
    monkeypatch.chdir(tmp_path)

    diagnostics.note_hold("tenant", 0.25, read_only=True, wait_read=0.0, wait_write=0.0, held=0.25)

    assert not (tmp_path / ".cache/test/gate-hold.log").exists()


def test_note_slow_hold_only_when_over_one_second(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """慢持有：不足 1s 不记，超过 1s 记（带调用栈）。"""
    monkeypatch.setenv(diagnostics.HOLD_ENV, "1")
    monkeypatch.chdir(tmp_path)

    diagnostics.note_slow_hold("tenant", 0.5, read_only=True, wait_read=0.0, wait_write=0.0, held=0.5, frames="a <- b")
    assert not (tmp_path / ".cache/test/gate-hold-slow.log").exists()

    diagnostics.note_slow_hold("tenant", 1.5, read_only=True, wait_read=0.1, wait_write=1.0, held=0.4, frames="a <- b")
    text = (tmp_path / ".cache/test/gate-hold-slow.log").read_text(encoding="utf-8")
    assert "1.500" in text
    assert "a <- b" in text


def test_watch_tick_without_loop_returns(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """看守在没有活动循环指针时直接返回（不写文件、不抛错）。"""
    monkeypatch.setenv(diagnostics.HANG_ENV, "0.01")
    diagnostics.reset_watchdogs()

    diagnostics._watch_tick(0.01)

    assert diagnostics._watch_path is None
