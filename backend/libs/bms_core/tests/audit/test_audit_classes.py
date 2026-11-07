"""审计留痕类别与强审计失败处置（07D 需求 02-4）。

覆盖详细设计 §5.5 用例 9~11：
- 类别查询（精确动作 → 动词 → 类别键 → 缺省普通写）；产品覆盖合并；
- 强审计写入失败 → `InternalError`（业务失败即失败）；
- 普通审计写入失败 → 返回 `False`（不抛、不阻塞业务）。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.audit import emit as emit_module
from bms_core.audit.classes import (
    AUDIT_CLASS_RECORD_OPERATION,
    AUDIT_CLASS_WRITE,
    AuditClass,
    audit_class_for,
    merge_audit_classes,
)
from bms_core.audit.emit import METRIC_AUDIT_EMIT_FAILED, AuditEventEmitter
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import InternalError
from bms_core.events.base import EventEnvelope

pytestmark = pytest.mark.kiwi_id(2450)


class _Boom:
    """会话上下文桩：进入即抛错（模拟审计写库失败）。"""

    async def __aenter__(self) -> Any:
        """进入即失败。

        Raises:
            RuntimeError: 恒定。
        """
        raise RuntimeError("audit store down")

    async def __aexit__(self, *args: object) -> bool:
        """退出（不吞错）。

        Args:
            *args: 异常信息。

        Returns:
            bool: False。
        """
        del args
        return False


def _emitter() -> AuditEventEmitter:
    """构造不接库的发射器（仅测失败分支）。

    Returns:
        AuditEventEmitter: 发射器实例。
    """
    emitter = object.__new__(AuditEventEmitter)
    for name, value in (
        ("_registry", None),
        ("_session_factory", None),
        ("_db_key", "platform"),
        ("_metrics", None),
        ("_store", None),
    ):
        setattr(emitter, name, value)
    return emitter


def _event() -> EventEnvelope:
    """最小事件。

    Returns:
        EventEnvelope: 事件信封。
    """
    return EventEnvelope(
        event_type="sys.operation.logged",
        payload=ConcurrentStableDict({"action": "msg:replay"}),
    )


def test_class_for_exact_action() -> None:
    """精确动作命中优先。"""
    classes = ConcurrentStableDict(
        {"msg:replay": AuditClass(AUDIT_CLASS_RECORD_OPERATION, strong=True, record_level=True)}
    )
    assert audit_class_for("msg:replay", classes).record_level is True


def test_class_for_verb_fallback() -> None:
    """未命中动作时按动词匹配。"""
    classes = merge_audit_classes({"consume": AuditClass("consume", strong=True)})
    assert audit_class_for("msg:consume", classes).strong is True


def test_class_default_is_write() -> None:
    """未命中任何声明 → 普通写（不强审计）。"""
    assert audit_class_for("msg:create").class_key == AUDIT_CLASS_WRITE
    assert audit_class_for("msg:create").strong is False


def test_merge_overrides_default() -> None:
    """合并视图：同名覆盖、其余保留。"""
    merged = merge_audit_classes({"write": AuditClass(AUDIT_CLASS_WRITE, strong=True)})
    assert merged[AUDIT_CLASS_WRITE].strong is True
    assert AUDIT_CLASS_RECORD_OPERATION in merged


def _boom_scope(**kwargs: object) -> _Boom:
    """构造失败的会话上下文（吸收任意关键字参数）。

    Args:
        **kwargs: 原调用参数（忽略）。

    Returns:
        _Boom: 失败上下文。
    """
    del kwargs
    return _Boom()


async def test_required_emit_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """强审计写入失败 → `InternalError`（10000 / 500）。"""
    monkeypatch.setattr(emit_module, "session_scope", _boom_scope)
    with pytest.raises(InternalError) as excinfo:
        await _emitter().emit(_event(), required=True)
    assert excinfo.value.http_status == 500


async def test_optional_emit_failure_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """普通审计写入失败 → 返回 False（业务不受影响）。"""
    monkeypatch.setattr(emit_module, "session_scope", _boom_scope)
    assert await _emitter().emit(_event()) is False


def test_metric_name_registered() -> None:
    """失败指标名稳定（监控接线引用常量）。"""
    assert METRIC_AUDIT_EMIT_FAILED == "bms_audit_emit_failed_total"


class _RecordingMetrics:
    """记录计数调用的指标桩（覆盖失败计数分支）。"""

    def __init__(self) -> None:
        """初始化（空记录）。"""
        self.names: ConcurrentStableList[str] = ConcurrentStableList()
        self.labels: ConcurrentStableList[str] = ConcurrentStableList()

    async def counter(self, name: str, *, labels: Any = None) -> None:
        """记录一次计数。

        Args:
            name: 指标名。
            labels: 标签（映射）。
        """
        self.names.add(name)
        if labels:
            self.labels.add(str(labels.get("event_type")))


async def test_optional_emit_failure_counts_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    """普通审计失败：返回 False 并记一次失败指标（装配指标器时）。"""
    monkeypatch.setattr(emit_module, "session_scope", _boom_scope)
    emitter = _emitter()
    metrics = _RecordingMetrics()
    cast("Any", emitter)._metrics = metrics

    assert await emitter.emit(_event()) is False
    assert list(metrics.names) == [METRIC_AUDIT_EMIT_FAILED]
    assert list(metrics.labels) == ["sys.operation.logged"]


def test_emitter_constructor_accepts_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    """构造函数接受指标器（覆盖 `_metrics` 赋值与发件箱解析）。"""
    monkeypatch.setattr(emit_module, "resolve_plugin", _stub_resolve)
    emitter = AuditEventEmitter(
        registry=cast("Any", None),
        session_factory=cast("Any", None),
        settings=cast("Any", SimpleNamespace(outbox_store=SimpleNamespace(provider="null"))),
        metrics=cast("Any", _RecordingMetrics()),
    )
    assert emitter is not None


def _stub_resolve(*args: object, **kwargs: object) -> object:
    """解析替身：固定返回占位对象（不触注册表）。

    Args:
        *args: 原位置参数（忽略）。
        **kwargs: 原关键字参数（忽略）。

    Returns:
        object: 占位对象。
    """
    del args, kwargs
    return object()
