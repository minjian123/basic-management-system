"""字段级审计能力域护栏（06_02）：白名单判定 / 值编码脱敏 / 事件构造 / 捕获暂存。

Kiwi 2515（与平台侧链写入 / 查询用例共用同一编号）。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from bms_core.audit.base import FieldChange
from bms_core.audit.db_capturer import TOUCH_FIELD, DbAuditCapturer
from bms_core.audit.events import DATA_CHANGED_EVENT, build_data_changed_event, encode_audit_value
from bms_core.audit.staging import drain_staged, reset_staged, staged_count
from bms_core.audit.tables import (
    is_audited_table,
    register_audited_tables,
    reset_audited_tables,
)
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError

pytestmark = pytest.mark.kiwi_id(2515)


def test_audited_table_whitelist_and_hard_excludes() -> None:
    """基座常量纳入；基础设施表与审计自身表硬排除；配置排除优先。"""
    assert is_audited_table("sys_role") is True
    assert is_audited_table("sys_outbox") is False
    assert is_audited_table("sys_data_audit_log") is False
    assert is_audited_table("sys_not_registered") is False


def test_register_and_reset_audited_tables() -> None:
    """产品注册口幂等生效，重置后回落。"""
    reset_audited_tables()
    assert is_audited_table("biz_purchase_order") is False
    register_audited_tables(("biz_purchase_order",))
    register_audited_tables(("biz_purchase_order",))
    assert is_audited_table("biz_purchase_order") is True
    reset_audited_tables()
    assert is_audited_table("biz_purchase_order") is False


def test_encode_value_types_and_masking() -> None:
    """值类型归一；敏感字段按名单脱敏；超长截断。"""
    assert encode_audit_value("name", None) is None
    assert encode_audit_value("name", "角色") == "角色"
    assert encode_audit_value("flag", True) == "true"
    assert encode_audit_value("count", 7) == "7"
    assert encode_audit_value("email", "a@b.com") == "***"
    assert encode_audit_value("at", datetime(2026, 11, 16, 1, 2, 3, tzinfo=UTC)) == "2026-11-16T01:02:03.000000"
    assert encode_audit_value("blob", b"\x00\x01") == "AAE="
    assert encode_audit_value("meta", {"b": 1, "a": 2}) == '{"a": 2, "b": 1}'
    long_text = "x" * 2100
    truncated = encode_audit_value("note", long_text)
    assert truncated is not None
    assert truncated.endswith("…(truncated)")


def test_build_data_changed_event_payload() -> None:
    """载荷字段：表 / 字段 / 主键字符串 / 域归属 / 旧新值；缺表名或字段名即拒。"""
    event = build_data_changed_event(
        tenant_id="1001",
        table="sys_role",
        model_id=42,
        field="name",
        old_value="旧名",
        new_value="新名",
        operator_id=7,
    )
    assert event.event_type == DATA_CHANGED_EVENT
    assert event.payload.get("table") == "sys_role"
    assert event.payload.get("model_id") == "42"
    assert event.payload.get("operator_id") == "7"
    assert event.payload.get("old_value") == "旧名"
    assert event.payload.get("new_value") == "新名"
    assert event.payload.get("domain_key") == "role"
    assert event.tenant_id == "1001"
    assert event.aggregate_key == "tenant:1001"
    with pytest.raises(ParamError):
        build_data_changed_event(tenant_id=None, table="", model_id=1, field="name")


def test_capturer_capture_stages_and_dedupes() -> None:
    """显式留痕：非空变更入暂存且同键去重；空变更不入暂存。"""
    reset_staged()
    capturer = DbAuditCapturer()
    assert capturer.is_audited("sys_role") is True
    assert capturer.is_audited("sys_outbox") is False
    changes: ConcurrentStableList[FieldChange] = ConcurrentStableList(
        [FieldChange(field="name", old="旧名", new="新名")]
    )
    event = capturer.capture(table="sys_role", model_id=123456789, changes=changes, actor=9)
    assert event.payload.get("field") == "name"
    assert staged_count() == 1
    capturer.capture(table="sys_role", model_id=123456789, changes=changes, actor=9)
    assert staged_count() == 1
    staged = drain_staged()
    assert len(staged) == 1
    assert staged[0].payload.get("operator_id") == "9"
    assert staged_count() == 0
    touch = capturer.capture(table="sys_user", model_id=1, changes=ConcurrentStableList(), actor=None)
    assert touch.payload.get("field") == TOUCH_FIELD
    assert staged_count() == 0


async def test_drain_staged_emits_all_events() -> None:
    """暂存排空：逐条发射并清空缓冲（失败不影响计数口径由发射器决定）。"""
    from bms_core.audit.emit import drain_staged as emit_drain

    reset_staged()
    capturer = DbAuditCapturer()
    for field in ("name", "code"):
        capturer.capture(
            table="sys_role",
            model_id=987654321,
            changes=ConcurrentStableList([FieldChange(field=field, old="a", new="b")]),
            actor=1,
        )
    assert staged_count() == 2

    class _Emitter:
        """假发射器：只记调用次数。"""

        def __init__(self) -> None:
            self.count = 0

        async def emit(self, event: object, *, required: bool = False) -> bool:
            self.count += 1
            return True

    emitter = _Emitter()
    published = await emit_drain(emitter)  # type: ignore[arg-type]
    assert published == 2
    assert emitter.count == 2
    assert staged_count() == 0


def test_encode_unknown_type_and_excluded_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """未识别类型降级 `str()`；配置排除的表不进审计（白名单三层合并可减）。"""
    from bms_core.core.config import get_settings

    class _Custom:
        """自定义对象（未识别类型的兜底路径）。"""

        def __str__(self) -> str:
            return "custom"

    assert encode_audit_value("note", _Custom()) == "custom"
    extra = get_settings().audit_capture.extra_tables
    monkeypatch.setattr(extra, "clear", extra.clear)
    extra.add("sys_role")
    excluded = get_settings().audit_capture.exclude_tables
    monkeypatch.setattr(excluded, "clear", excluded.clear)
    excluded.add("sys_role")
    assert is_audited_table("sys_role") is False
    extra.clear()
    excluded.clear()


def test_collect_skips_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """捕获开关关闭时 `before_flush` 直接返回（不读白名单、不落暂存）。"""
    from bms_core.audit import field_capture
    from bms_core.core.config import get_settings

    class _Session:
        """`before_flush` 最小会话替身（只需 `info` 与三态集合）。"""

        def __init__(self) -> None:
            self.info: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            self.new: ConcurrentStableList[object] = ConcurrentStableList()
            self.dirty: ConcurrentStableList[object] = ConcurrentStableList()
            self.deleted: ConcurrentStableList[object] = ConcurrentStableList()

    monkeypatch.setattr(get_settings().audit_capture, "enabled", False)
    session = _Session()
    field_capture._collect(session, None, None)  # type: ignore[arg-type]
    assert session.info == {}


def test_query_range_guards() -> None:
    """范围收敛：结束早于开始即拒（90203）；默认回看天数生效。"""
    from datetime import UTC, datetime, timedelta

    from bms_core.audit.query_range import resolve_query_range
    from bms_core.core.config import get_settings
    from bms_core.core.exceptions import LogTimeRangeExceededError

    settings = get_settings().audit_log
    now = datetime(2026, 11, 16, 12, 0, 0)
    start, end = resolve_query_range(settings, None, None, now=now)
    assert end == now
    assert (now - start).days == settings.query_default_days
    with pytest.raises(LogTimeRangeExceededError):
        resolve_query_range(settings, datetime(2026, 11, 16, tzinfo=UTC), datetime(2026, 11, 1), now=now)
    start_only, _ = resolve_query_range(settings, now - timedelta(days=1), None, now=now)
    assert start_only == now - timedelta(days=1)
