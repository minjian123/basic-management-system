"""任务调度命令行护栏：清单输出 / 单轮诊断两种结果 / 动作互斥。"""

from collections.abc import Callable

import pytest

import ops.task_scheduler as cli
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.roots import BaseFrameworkObject
from bms_core.tasks.scheduler import TenantTick, TickReport

pytestmark = pytest.mark.kiwi_id(2371)


class _StubScheduler(BaseFrameworkObject):
    """调度器替身（按构造时的结果返回 tick 报告）。"""

    def __init__(self, *, lock_held: bool = True) -> None:
        """初始化。

        Args:
            lock_held: tick 报告的取锁结果。
        """
        self._lock_held = lock_held
        self.ticked = 0

    async def tick(self) -> TickReport:
        """返回预置报告。

        Returns:
            TickReport: 报告。
        """
        self.ticked += 1
        tenants = ConcurrentStableList([TenantTick(db_key="platform", dispatched=1)])
        return TickReport(lock_held=self._lock_held, tenants=tenants)

    async def aclose(self) -> None:
        """释放（空操作）。"""


class _StubRegistry(BaseFrameworkObject):
    """引擎注册表替身。"""

    async def aclose(self) -> None:
        """释放（空操作）。"""


def _builder(scheduler: _StubScheduler) -> Callable[[Settings], tuple[_StubScheduler, _StubRegistry]]:
    """构造与 `_build_scheduler` 同签名的替身工厂。

    Args:
        scheduler: 调度器替身。

    Returns:
        Callable[[Settings], tuple[_StubScheduler, _StubRegistry]]: 工厂函数。
    """

    def _factory(settings: Settings) -> tuple[_StubScheduler, _StubRegistry]:
        _ = settings
        return scheduler, _StubRegistry()

    return _factory


def test_list_prints_builtin_tasks(capsys: pytest.CaptureFixture[str]) -> None:
    """`--list` 打印四条内置任务并返回 0（不连库）。"""
    assert cli.main(ConcurrentStableList(["--list"])) == 0
    output = capsys.readouterr().out
    assert "内置任务清单" in output
    assert "cleanup_orphan_parts" in output
    assert "purge_soft_deleted" in output


def test_once_reports_dispatch(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`--beat --once`：取到锁时打印派发与回收条数并返回 0。"""
    scheduler = _StubScheduler()
    monkeypatch.setattr(cli, "_build_scheduler", _builder(scheduler))
    assert cli.main(ConcurrentStableList(["--beat", "--once"])) == 0
    assert "单轮派发 1 条" in capsys.readouterr().out
    assert scheduler.ticked == 1


def test_once_reports_busy_lock(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """`--beat --once`：锁被占用时提示并返回 1（不静默当成成功）。"""
    scheduler = _StubScheduler(lock_held=False)
    monkeypatch.setattr(cli, "_build_scheduler", _builder(scheduler))
    assert cli.main(ConcurrentStableList(["--beat", "--once"])) == 1
    assert "调度锁被占用" in capsys.readouterr().out


def test_modes_are_mutually_exclusive() -> None:
    """`--list` 与 `--beat` 同时给：参数解析即拒（退出码 2）。"""
    with pytest.raises(SystemExit) as excinfo:
        cli.main(ConcurrentStableList(["--list", "--beat"]))
    assert excinfo.value.code == 2
