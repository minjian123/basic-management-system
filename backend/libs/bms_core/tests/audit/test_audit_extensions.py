"""审计字段扩展（07D 需求 02-4）：记录级定位、自定义扩展位与载荷只增不删。

覆盖详细设计 §5.5 用例 1~8：
- `RecordRef` 形态校验（类型 / 主键）；
- 扩展位键形态、数量上限、值域（标量）、标准字段保留键冲突；
- `capture_extended` 返回新信封且既有实现零改动；
- 操作事件载荷：给则写两键、不给则不写；
- 哈希链构造不分支（扩展位只是被包含的载荷）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from bms_core.audit.base import (
    MAX_AUDIT_EXTENSIONS,
    AuditCapturer,
    FieldChange,
    RecordRef,
    validate_audit_extensions,
    with_audit_extensions,
)
from bms_core.audit.events import build_operation_event
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.events.base import EventEnvelope

pytestmark = pytest.mark.kiwi_id(2450)


class _StubCapturer(AuditCapturer):
    """最小审计捕获桩（旧签名，验证基线方法不改既有实现）。"""

    plugin_name: str = "stub"

    def is_audited(self, table: str) -> bool:
        """恒不纳入。

        Args:
            table: 逻辑表名。

        Returns:
            bool: False。
        """
        del table
        return False

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """产出最小事件。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段变更。
            actor: 操作人。

        Returns:
            EventEnvelope: 事件信封。
        """
        del changes, actor
        return EventEnvelope(
            event_type="audit.stub",
            payload=ConcurrentStableDict({"table": table, "model_id": str(model_id)}),
        )


def _event() -> EventEnvelope:
    """构造最小事件。

    Returns:
        EventEnvelope: 事件信封。
    """
    return EventEnvelope(
        event_type="sys.operation.logged",
        payload=ConcurrentStableDict({"action": "demo:create"}),
    )


def test_record_ref_accepts_resource_type() -> None:
    """记录级定位接受资源类型标识（两段点分）。"""
    ref = RecordRef(type="msg.message", id="123456")
    assert ref.to_payload()["type"] == "msg.message"
    assert ref.to_payload()["id"] == "123456"


@pytest.mark.parametrize(
    ("type_", "id_"),
    [("Msg.Message", "1"), ("msg", ""), ("msg.topic", "bad id"), ("msg.topic", "x" * 65)],
)
def test_record_ref_rejects_bad_shape(type_: str, id_: str) -> None:
    """类型 / 主键形态非法即拒。"""
    with pytest.raises(ParamError):
        RecordRef(type=type_, id=id_)


def test_extensions_accept_scalars() -> None:
    """标量值原样保留（str / int / float / bool / None）。"""
    validated = validate_audit_extensions({"channel": "sms", "count": 3, "ratio": 0.5, "ok": True, "empty": None})
    assert dict(validated.items()) == {"channel": "sms", "count": 3, "ratio": 0.5, "ok": True, "empty": None}


@pytest.mark.parametrize(
    "extensions",
    [
        {"Bad-Key": "x"},
        {"K": "x"},
        {"channel": ["a", "b"]},
        {"channel": {"a": 1}},
        {"channel": "x" * 256},
        {"action": "override"},
    ],
)
def test_extensions_reject_bad_input(extensions: dict[str, object]) -> None:  # bare-collections:allow（用例参数）
    """键形态 / 值域 / 保留键冲突逐项拒。"""
    with pytest.raises(ParamError):
        validate_audit_extensions(extensions)


def test_extensions_reject_too_many_keys() -> None:
    """键数量上限（防洪泛）。"""
    payload = {f"k{index}": index for index in range(MAX_AUDIT_EXTENSIONS + 1)}
    with pytest.raises(ParamError):
        validate_audit_extensions(payload)


def test_capture_extended_appends_without_changing_original() -> None:
    """基线方法追加扩展位：返回新信封，原信封不变；既有 `capture` 实现零改动。"""
    capturer = _StubCapturer()
    base = capturer.capture(table="demo", model_id=1, changes=ConcurrentStableList())
    extended = capturer.capture_extended(
        table="demo",
        model_id=1,
        changes=ConcurrentStableList(),
        record_ref=RecordRef(type="demo.record", id="1"),
        extensions={"channel": "sms"},
    )
    assert "record_ref" not in base.payload
    assert extended.payload["record_ref"] == {"type": "demo.record", "id": "1"}
    assert dict(extended.payload["extensions"].items()) == {"channel": "sms"}  # type: ignore[union-attr]


def test_without_extensions_payload_has_no_keys() -> None:
    """不传扩展位 → 载荷不含两键（不是空对象 / null）。"""
    event = with_audit_extensions(_event())
    assert "record_ref" not in event.payload
    assert "extensions" not in event.payload


def test_extensions_without_record_ref_write_only_extensions() -> None:
    """只给扩展位、不给记录级定位：只写 `extensions`（记录级分支取假，另一键不出现）。"""
    event = with_audit_extensions(_event(), extensions={"channel": "sms"})
    assert "record_ref" not in event.payload
    assert dict(event.payload["extensions"].items()) == {"channel": "sms"}  # type: ignore[union-attr]


def test_operation_event_carries_extensions() -> None:
    """操作事件：给则写 `record_ref` / `extensions`，标准字段不受影响。"""
    event = build_operation_event(
        tenant_id="1",
        user_id=2,
        username="demo",
        module="msg",
        action="msg:replay",
        method="POST",
        path="/api/v1/msg/replay",
        query=None,
        params=None,
        ip="127.0.0.1",
        user_agent="pytest",
        cost_time=1,
        status=200,
        error_msg=None,
        record_ref=RecordRef(type="msg.message", id="987"),
        extensions={"reason": "manual"},
    )
    assert event.payload["record_ref"] == {"type": "msg.message", "id": "987"}
    assert dict(event.payload["extensions"].items()) == {"reason": "manual"}  # type: ignore[union-attr]
    assert event.payload["action"] == "msg:replay"


def test_operation_event_without_extensions_keeps_payload() -> None:
    """操作事件：不给扩展位则载荷逐键不变。"""
    event = build_operation_event(
        tenant_id="1",
        user_id=None,
        username=None,
        module="msg",
        action="msg:create",
        method="POST",
        path="/api/v1/msg/topics",
        query=None,
        params=None,
        ip=None,
        user_agent=None,
        cost_time=None,
        status=200,
        error_msg=None,
    )
    assert "record_ref" not in event.payload
    assert "extensions" not in event.payload


def test_chain_construction_unchanged() -> None:
    """扩展位只进载荷：链哈希按同一算法对载荷序列化（同内容同哈希，构造不分支）。"""
    from bms_core.audit.sha256 import Sha256HashChain

    chain = Sha256HashChain()
    first = with_audit_extensions(_event(), record_ref=RecordRef(type="demo.record", id="1"))
    second = with_audit_extensions(_event(), record_ref=RecordRef(type="demo.record", id="1"))
    assert chain.compute("prev", first.payload) == chain.compute("prev", second.payload)


@pytest.fixture(autouse=True)
def _noop() -> Iterator[None]:
    """占位夹具（保持文件内用例惰性一致）。

    Yields:
        None: 用例运行期。
    """
    yield
