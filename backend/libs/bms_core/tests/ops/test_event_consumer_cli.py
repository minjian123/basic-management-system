# pyright: reportPrivateUsage=false, reportArgumentType=false, reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

"""事件消费 CLI 用例：组清单诊断 / 单轮 / worker 宿主 / 未知服务退码 / 无声明时的安全返回。

不起消费后端、不消费——只验「声明装载 + 校验 + 输出 + 宿主分支」这条链路；真实消费交互由
`tests/integration/test_event_bus_msg.py` 覆盖。
"""

import asyncio
from types import SimpleNamespace
from typing import cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.events.base import ConsumedTally
from ops import event_consumer
from ops.event_consumer import _create_app, _groups, _once, _worker, main

pytestmark = pytest.mark.kiwi_id(2370)


def test_groups_lists_declarations(capsys: pytest.CaptureFixture[str]) -> None:
    """`--groups` 打印服务声明与开关；平台服务当前未声明消费组（0 条）。"""
    code = main(ConcurrentStableList(["--service", "platform", "--groups"]))
    assert code == 0
    out = capsys.readouterr().out
    assert "服务 platform" in out
    assert "消费开关" in out


def test_unknown_service_exits_with_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    """未知服务包 → 退出码 2（不静默当作 0 条声明）。"""
    with pytest.raises(SystemExit) as excinfo:
        main(ConcurrentStableList(["--service", "no_such_service", "--groups"]))
    assert excinfo.value.code == 2
    assert "服务包不存在" in capsys.readouterr().err


def test_mode_is_mutually_exclusive() -> None:
    """必须且只能选一个动作（防误跑）。"""
    with pytest.raises(SystemExit):
        main(ConcurrentStableList(["--service", "platform"]))


class _FakeGroup:
    """消费组替身：记录装载 / 启停 / 单轮调用，可切开关。"""

    def __init__(self, *, enabled: bool = True, tally: ConsumedTally | None = None) -> None:
        """初始化替身。"""
        self.enabled = enabled
        self.loaded: ConcurrentStableList[object] = ConcurrentStableList()
        self.started = 0
        self.closed = 0
        self.max_messages: int | None = None
        self._tally = tally or ConsumedTally(received=2, succeeded=1, skipped=1)

    def load(self, records: object) -> None:
        """记录装载。"""
        self.loaded.add(records)

    async def start(self) -> None:
        """记录启动。"""
        self.started += 1

    async def consume_once(self, *, max_messages: int) -> ConsumedTally:
        """记录单轮上限并返回预设汇总。"""
        self.max_messages = max_messages
        return self._tally

    async def aclose(self) -> None:
        """记录关闭。"""
        self.closed += 1


class _FakeRegistry:
    """引擎注册表替身：只记录关闭。"""

    def __init__(self) -> None:
        """初始化替身。"""
        self.closed = 0

    async def aclose(self) -> None:
        """记录关闭。"""
        self.closed += 1


def _settings() -> Settings:
    """最小配置替身（消费组前缀 / 开关 / 宿主 / 并发）。"""
    return cast(
        "Settings",
        SimpleNamespace(
            event_consumer=SimpleNamespace(group_prefix="bms-", enabled=True, host="worker", concurrency=4)
        ),
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch, group: _FakeGroup, registry: _FakeRegistry, records: object) -> None:
    """打桩配置 / 声明装载 / 运行时构造（单轮与 worker 共用）。"""
    monkeypatch.setattr(event_consumer, "get_settings", _settings)
    monkeypatch.setattr(event_consumer, "load_records", lambda *args, **kwargs: records)
    monkeypatch.setattr(event_consumer, "service_factory", lambda service: cast("object", None))
    monkeypatch.setattr(event_consumer, "_build_group", lambda loaded, app: (group, registry))
    monkeypatch.setattr(event_consumer, "_create_app", lambda factory: cast("object", None))


def test_create_app_requires_create_method(capsys: pytest.CaptureFixture[str]) -> None:
    """服务工厂未实现 `create` → 退出码 1（不手搓第二套装配）。"""
    with pytest.raises(SystemExit) as excinfo:
        _create_app(cast("object", SimpleNamespace()))
    assert excinfo.value.code == 1
    assert "未实现 create" in capsys.readouterr().err

    app = SimpleNamespace()
    assert _create_app(cast("object", SimpleNamespace(create=lambda *_: app))) is app


def test_groups_renders_ordered_and_concurrency(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """组清单：有序组显示「有序」，并发组显示显式值或配置缺省值。"""
    records: ConcurrentStableList[object] = ConcurrentStableList(
        [
            SimpleNamespace(
                consumer="bms-audit-chain",
                event_type="sys.operation.logged",
                ordered=True,
                concurrency=None,
                description="审计链",
            ),
            SimpleNamespace(
                consumer="bms-notify",
                event_type="notification.requested",
                ordered=False,
                concurrency=8,
                description="通知",
            ),
            SimpleNamespace(
                consumer="bms-file",
                event_type="file.uploaded",
                ordered=False,
                concurrency=None,
                description="文件",
            ),
        ]
    )
    monkeypatch.setattr(event_consumer, "get_settings", _settings)
    monkeypatch.setattr(event_consumer, "load_records", lambda *args, **kwargs: records)

    code = asyncio.run(_groups(cast("object", SimpleNamespace(service="platform"))))

    assert code == 0
    out = capsys.readouterr().out
    assert "有序" in out
    assert "并发 8" in out
    assert "并发 4" in out
    assert "enabled=True" in out and "host=worker" in out


def test_once_no_records_and_disabled(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """单轮消费：无声明直接返回 0；开关关闭时关闭运行时与注册表后返回 0。"""
    group = _FakeGroup(enabled=False)
    registry = _FakeRegistry()
    _patch_common(monkeypatch, group, registry, ConcurrentStableList())

    args = SimpleNamespace(service="platform", max_messages=8)
    assert asyncio.run(_once(args)) == 0
    assert "无可消费的组声明" in capsys.readouterr().out

    _patch_common(monkeypatch, group, registry, ConcurrentStableList([cast("object", None)]))
    assert asyncio.run(_once(args)) == 0
    assert "消费未启用" in capsys.readouterr().out
    assert group.closed == 1 and registry.closed == 1


def test_once_consumes_and_prints_tally(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """单轮消费：按上限拉取一批并打印计数，结束时关闭运行时与注册表。"""
    group = _FakeGroup()
    registry = _FakeRegistry()
    _patch_common(monkeypatch, group, registry, ConcurrentStableList([cast("object", None)]))

    code = asyncio.run(_once(SimpleNamespace(service="platform", max_messages=16)))

    assert code == 0
    assert group.max_messages == 16
    out = capsys.readouterr().out
    assert "拉取 2 / 成功 1 / 跳过 1" in out
    assert group.closed == 1 and registry.closed == 1


class _ImmediateStop:
    """即停事件替身：`wait()` 立即返回，避免 worker 用例挂住。"""

    def set(self) -> None:
        """置位（无实际作用）。"""
        return None

    async def wait(self) -> None:
        """立即返回。"""
        return None


def test_worker_no_records_and_disabled(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """worker 宿主：无声明返回 0；开关关闭时关闭运行时与注册表后返回 0。"""
    group = _FakeGroup(enabled=False)
    registry = _FakeRegistry()
    _patch_common(monkeypatch, group, registry, ConcurrentStableList())
    args = SimpleNamespace(service="platform")

    assert asyncio.run(_worker(args)) == 0
    assert "无可消费的组声明" in capsys.readouterr().out

    _patch_common(monkeypatch, group, registry, ConcurrentStableList([cast("object", None)]))
    assert asyncio.run(_worker(args)) == 0
    assert "消费未启用" in capsys.readouterr().out
    assert group.closed == 1 and registry.closed == 1


def test_worker_starts_and_stops_on_signal(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """worker 宿主：启动运行时、注册信号、收到停止后关闭并打印停止信息。"""
    group = _FakeGroup()
    registry = _FakeRegistry()
    _patch_common(monkeypatch, group, registry, ConcurrentStableList([cast("object", None)]))
    monkeypatch.setattr(
        event_consumer,
        "asyncio",
        SimpleNamespace(
            Event=_ImmediateStop,
            get_running_loop=lambda: SimpleNamespace(add_signal_handler=lambda *args: None),
        ),
    )

    code = asyncio.run(_worker(SimpleNamespace(service="platform")))

    assert code == 0
    assert group.started == 1
    out = capsys.readouterr().out
    assert "worker 已启动" in out and "worker 已停止" in out
    assert group.closed == 1 and registry.closed == 1


def test_build_group_loads_records_and_returns_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """运行时构造：复用应用工厂装配产物，装载声明并返回引擎注册表。"""
    group = _FakeGroup()
    registry = _FakeRegistry()
    app = SimpleNamespace(state=SimpleNamespace(engine_registry=registry))

    class _Factory:
        """运行时工厂替身。"""

        def __init__(self, settings: object, target: object) -> None:
            """记录参数。"""
            self.target = target

        def create(self) -> _FakeGroup:
            """返回预设运行时。"""
            return group

    records: ConcurrentStableList[object] = ConcurrentStableList([cast("object", None)])
    monkeypatch.setattr(event_consumer, "get_settings", _settings)
    monkeypatch.setattr(event_consumer, "MsgEventConsumerGroupFactory", _Factory)

    built, built_registry = event_consumer._build_group(records, app)  # pyright: ignore[reportPrivateUsage]

    assert built is group and built_registry is registry
    assert list(group.loaded[0]) == list(records)


def test_main_dispatches_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    """命令行分发：--groups / --once / --worker 各走对应实现。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    async def _groups_mode(args: object) -> int:
        seen.add("groups")
        return 0

    async def _once_mode(args: object) -> int:
        seen.add("once")
        return 1

    async def _worker_mode(args: object) -> int:
        seen.add("worker")
        return 2

    monkeypatch.setattr(event_consumer, "_groups", _groups_mode)
    monkeypatch.setattr(event_consumer, "_once", _once_mode)
    monkeypatch.setattr(event_consumer, "_worker", _worker_mode)
    monkeypatch.setattr(event_consumer, "run_with_worker_id", lambda fn: asyncio.run(fn()))

    assert main(ConcurrentStableList(["--groups"])) == 0
    assert main(ConcurrentStableList(["--once"])) == 1
    assert main(ConcurrentStableList(["--worker"])) == 2
    assert list(seen) == ["groups", "once", "worker"]
