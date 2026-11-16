"""ORM 字段级捕获用例（06_02）：同事务写发件箱 / 回滚不残留 / 直连 SQL 不覆盖。"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.audit.events import DATA_CHANGED_EVENT
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.role import SysRole

pytestmark = pytest.mark.kiwi_id(2515)


async def _outbox_rows(session: AsyncSession) -> ConcurrentStableList[ConcurrentStableDict[str, object]]:
    """取当前发件箱行（插入序）。"""
    result = await session.execute(select(SysOutbox).order_by(SysOutbox.id))
    rows: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()
    for row in result.scalars().all():
        payload: ConcurrentStableDict[str, object] = ConcurrentStableDict(dict(row.payload))
        payload.set("event_type", row.event_type)
        rows.add(payload)
    return rows


async def test_insert_captures_new_values(log_session: AsyncSession, field_audit: None) -> None:
    """新增关键表记录 → 逐字段产生审计事件（旧值为空），随业务事务一起提交。"""
    log_session.add(SysRole(code="r1", name="角色一"))
    await log_session.commit()
    payloads = await _outbox_rows(log_session)
    assert payloads
    assert {item["event_type"] for item in payloads} == {DATA_CHANGED_EVENT}
    fields = {item["field"] for item in payloads}
    assert {"code", "name"} <= fields
    name_row = next(item for item in payloads if item["field"] == "name")
    assert name_row["new_value"] == "角色一"
    assert "old_value" not in name_row
    assert name_row["table"] == "sys_role"
    assert name_row["domain_key"] == "role"


async def test_update_captures_old_and_new(log_session: AsyncSession, field_audit: None) -> None:
    """修改字段 → 同时记录旧值与新值；噪声列（updated_at / version）不入账。"""
    role = SysRole(code="r2", name="旧名")
    log_session.add(role)
    await log_session.commit()
    before = len(await _outbox_rows(log_session))
    role.name = "新名"
    await log_session.commit()
    payloads = await _outbox_rows(log_session)
    added = payloads[before:]
    assert len(added) == 1
    assert added[0]["field"] == "name"
    assert added[0]["old_value"] == "旧名"
    assert added[0]["new_value"] == "新名"


async def test_rollback_leaves_no_audit(log_session: AsyncSession, field_audit: None) -> None:
    """业务事务回滚 → 发件箱无残留（同生共死）。"""
    log_session.add(SysRole(code="r3", name="回滚角色"))
    await log_session.flush()
    await log_session.rollback()
    assert await _outbox_rows(log_session) == []


async def test_soft_delete_is_captured(log_session: AsyncSession, field_audit: None) -> None:
    """软删除置 `deleted_at` → 该列必须留痕。"""
    role = SysRole(code="r4", name="待删")
    log_session.add(role)
    await log_session.commit()
    before = len(await _outbox_rows(log_session))
    role.soft_delete()
    await log_session.commit()
    payloads = await _outbox_rows(log_session)
    added = payloads[before:]
    assert [item["field"] for item in added] == ["deleted_at"]
    assert added[0]["new_value"]


async def test_raw_sql_update_is_not_captured(log_session: AsyncSession, field_audit: None) -> None:
    """不经 ORM 的直连 SQL 不产生审计（口径显式声明，不假装覆盖）。"""
    role = SysRole(code="r5", name="直连前")
    log_session.add(role)
    await log_session.commit()
    before = len(await _outbox_rows(log_session))
    await log_session.execute(
        update(SysRole).where(SysRole.code == "r5").values(name="直连后").execution_options(synchronize_session=False)
    )
    await log_session.commit()
    assert len(await _outbox_rows(log_session)) == before


async def test_install_is_idempotent_and_uninstall_is_safe() -> None:
    """挂载幂等（重复调用返回 True）；未挂载时卸下无副作用。"""
    from bms_core.audit import field_capture

    field_capture.reset_capture_state()
    assert field_capture.install_field_audit() is True
    assert field_capture.is_field_audit_installed() is True
    assert field_capture.install_field_audit() is True
    field_capture.uninstall_field_audit()
    assert field_capture.is_field_audit_installed() is False
    field_capture.uninstall_field_audit()
    assert field_capture.is_field_audit_installed() is False


async def test_truncation_limits_records_per_transaction(
    log_session: AsyncSession, field_audit: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单事务记录数超上限 → 只留预算内条目（溢出丢弃并告警）。"""
    from bms_core.core.config import get_settings

    settings = get_settings().audit_capture
    monkeypatch.setattr(settings, "max_changes_per_tx", 1)
    log_session.add(SysRole(code="r6", name="超限角色"))
    await log_session.commit()
    payloads = await _outbox_rows(log_session)
    assert len(payloads) == 1


async def test_fail_closed_rolls_back_business(
    log_session: AsyncSession, field_audit: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`fail_closed=true` 下发件箱写失败使业务回滚；置 false 时放行且不写审计。"""
    from bms_core.audit import field_capture
    from bms_core.core.config import get_settings
    from bms_core.core.exceptions import InternalError

    def _boom(*_args: object, **_kwargs: object) -> SysOutbox:
        raise RuntimeError("outbox down")

    monkeypatch.setattr(field_capture, "_outbox_row", _boom)
    log_session.add(SysRole(code="r7", name="强一致失败"))
    with pytest.raises(InternalError):
        await log_session.commit()
    await log_session.rollback()
    assert await _outbox_rows(log_session) == []

    monkeypatch.setattr(get_settings().audit_capture, "fail_closed", False)
    field_capture.reset_capture_state()
    log_session.add(SysRole(code="r8", name="放行"))
    await log_session.commit()
    assert await _outbox_rows(log_session) == []


async def test_hard_delete_captures_old_values(log_session: AsyncSession, field_audit: None) -> None:
    """物理删除 → 旧值留痕、新值为空。"""
    role = SysRole(code="r9", name="物理删")
    log_session.add(role)
    await log_session.commit()
    before = len(await _outbox_rows(log_session))
    await log_session.delete(role)
    await log_session.commit()
    payloads = await _outbox_rows(log_session)
    added = payloads[before:]
    assert added
    assert all("new_value" not in item for item in added)
    assert {item["field"] for item in added} >= {"code", "name"}


async def test_same_field_twice_in_one_transaction_records_once(log_session: AsyncSession, field_audit: None) -> None:
    """同事务内两次 flush 改同一字段 → 只记一次（去重键）。"""
    role = SysRole(code="r10", name="第一次")
    log_session.add(role)
    await log_session.commit()
    before = len(await _outbox_rows(log_session))
    role.name = "第二次"
    await log_session.flush()
    role.name = "第三次"
    await log_session.commit()
    added = (await _outbox_rows(log_session))[before:]
    assert len(added) == 1


async def test_install_skipped_when_disabled(log_session: AsyncSession, monkeypatch: pytest.MonkeyPatch) -> None:
    """`[audit_capture].enabled=false` 时不挂监听。"""
    from bms_core.audit import field_capture
    from bms_core.core.config import get_settings

    field_capture.uninstall_field_audit()
    monkeypatch.setattr(get_settings().audit_capture, "enabled", False)
    assert field_capture.install_field_audit() is False
    assert field_capture.is_field_audit_installed() is False
