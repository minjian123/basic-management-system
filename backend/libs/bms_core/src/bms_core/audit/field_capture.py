"""字段级变更捕获：ORM 会话事件 → 同事务发件箱（06_02）。

- **挂载点**：`sqlalchemy.orm.Session` 的 `before_flush` / `after_flush_postexec`（异步会话与达梦同步
  门面共用同一底层会话类，一处挂载两路生效）。挂载幂等，进程内一次。
- **取值**：`before_flush` 遍历 `session.new | session.dirty | session.deleted`，按关键表白名单
  （`audit/tables.py`）读列值与属性历史——新增旧值为 `null`、删除新值为 `null`、修改取
  `history.deleted` / `history.added` 首值；`updated_at` / `version` 属噪声列不入账，`deleted_at`（软删）
  必须留痕；值经 `build_data_changed_event()` 统一编码 + 脱敏 + 截断。
- **同事务入账**：`after_flush_postexec` 把暂存项转 `sys_outbox` 行（`session.add`，随业务事务提交）。
  业务回滚则审计一起回滚，业务提交则审计必达；不引入「响应后再写」的丢审计窗口。
- **失败分档**：`[audit_capture].fail_closed`（缺省 true）——写发件箱失败抛 `InternalError`，业务事务
  回滚（宁可拒绝写，不可无审计）；置 false 时只记 ERROR 日志 `audit_capture_failed` 并放行。
- **预算**：单事务最多 `[audit_capture].max_changes_per_tx` 条字段级记录，溢出丢弃并记 WARN
  `audit_capture_truncated`（防一条批量导入把事务撑爆）。
- **覆盖边界**：只覆盖经 ORM 的写入；不经 ORM 的直连 SQL 不产生审计（口径显式声明，不假装覆盖）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from bms_core.audit.events import DATA_CHANGED_EVENT, build_data_changed_event
from bms_core.audit.tables import is_audited_table
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.core.config import Settings, get_settings
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import InternalError
from bms_core.core.logging import get_logger
from bms_core.db.tenant import current_tenant_id_str
from bms_core.events.contracts import resolve_event_version
from bms_core.models.outbox import SysOutbox

__all__ = [
    "install_field_audit",
    "is_field_audit_installed",
    "reserve_capture_key",
    "reset_capture_state",
    "uninstall_field_audit",
]

_LOGGER = get_logger("bms.audit")

_PENDING_KEY = "bms_audit_pending"
"""会话暂存键（`session.info`）：本轮 flush 待转发的字段级变更。"""

_SKIP_COLUMNS: ConcurrentStableSet[str] = ConcurrentStableSet(("updated_at", "version"))
"""不入账的噪声列：写时间与乐观锁计数无审计价值（`deleted_at` 必须留痕，不在此列）。"""

_installed = False
"""是否已挂载监听（幂等标记）。"""

_CAPTURED: ConcurrentStableSet[tuple[str, str, str]] = ConcurrentStableSet()
"""显式捕获与 ORM 捕获的去重键集合（`(表, 记录主键, 字段)`；测试可重置）。"""


@dataclass(frozen=True)
class _PendingChange:
    """一条待转发的字段级变更（flush 期暂存形态）。"""

    table: str
    model_id: int | None
    field: str
    old_value: object
    new_value: object


def reserve_capture_key(table: str, model_id: int | str | None, field: str) -> bool:
    """占位一条捕获键（ORM 捕获与显式留痕共用，保证同键只记一次）。

    Args:
        table: 逻辑表名。
        model_id: 记录主键（None / 0 按空串归并）。
        field: 字段名。

    Returns:
        bool: 首次占位 True；已存在（重复捕获）False。
    """
    key = (table, str(model_id or ""), field)
    if key in _CAPTURED:
        return False
    _CAPTURED.add(key)
    return True


def _changes_of(state: Any, *, is_new: bool, is_deleted: bool) -> ConcurrentStableList[tuple[str, object, object]]:
    """取单个对象的字段级变更（列名 → 旧值 / 新值）。

    Args:
        state: `sqlalchemy.orm.InstanceState`。
        is_new: 是否本次新增（`before_flush` 用会话三态判定：此时 `state.identity` 尚未生成）。
        is_deleted: 是否本次物理删除（`before_flush` 时 `state.deleted` 仍为 False，须由会话三态判定）。

    Returns:
        ConcurrentStableList[tuple[str, object, object]]: （列名, 旧值, 新值）列表。
    """
    changes: ConcurrentStableList[tuple[str, object, object]] = ConcurrentStableList()
    obj = state.object
    for attribute in state.mapper.column_attrs:
        key = attribute.key
        if key in _SKIP_COLUMNS:
            continue
        if is_new:
            value = getattr(obj, key, None)
            if value is not None:
                changes.add((key, None, value))
            continue
        if is_deleted:
            value = getattr(obj, key, None)
            if value is not None:
                changes.add((key, value, None))
            continue
        history = state.attrs[key].history
        if not history.has_changes():
            continue
        old_value = history.deleted[0] if history.deleted else None
        new_value = history.added[0] if history.added else None
        changes.add((key, old_value, new_value))
    return changes


def _table_of(state: Any) -> str | None:
    """取对象所属逻辑表名（无表信息返回 None）。

    Args:
        state: `sqlalchemy.orm.InstanceState`。

    Returns:
        str | None: 逻辑表名。
    """
    local_table = getattr(state.mapper, "local_table", None)
    return getattr(local_table, "name", None)


def _collect(session: Session, flush_context: object, instances: object) -> None:
    """`before_flush`：把本轮的字段级变更暂存进会话（不写库）。

    Args:
        session: ORM 会话（同步底层会话；异步会话经同一实例触发）。
        flush_context: SQLAlchemy 的 UOW 上下文（本钩子不用）。
        instances: 待处理对象集合（本钩子不用，直接遍历会话三态）。
    """
    del flush_context, instances
    if not get_settings().audit_capture.enabled:
        return
    limit = get_settings().audit_capture.max_changes_per_tx
    pending: ConcurrentStableList[_PendingChange] = session.info.setdefault(_PENDING_KEY, ConcurrentStableList())
    truncated = False
    new_ids: ConcurrentStableSet[int] = ConcurrentStableSet(id(obj) for obj in session.new)
    deleted_ids: ConcurrentStableSet[int] = ConcurrentStableSet(id(obj) for obj in session.deleted)
    targets: ConcurrentStableList[Any] = ConcurrentStableList([*session.new, *session.dirty, *session.deleted])
    for obj in targets:
        state = sa_inspect(obj, raiseerr=False)
        if state is None:  # pragma: no cover - 非映射对象（原生 SQL 结果等）不参与捕获
            continue
        table = _table_of(state)
        if table is None or not is_audited_table(table):
            continue
        model_id = state.identity[0] if state.identity is not None else None
        changes = _changes_of(state, is_new=id(obj) in new_ids, is_deleted=id(obj) in deleted_ids)
        for field, old_value, new_value in changes:
            if len(pending) >= limit:
                truncated = True
                break
            if not reserve_capture_key(table, model_id, field):
                continue
            pending.add(
                _PendingChange(table=table, model_id=model_id, field=field, old_value=old_value, new_value=new_value)
            )
        if truncated:
            break
    if truncated:
        _LOGGER.warning(
            "audit_capture_truncated",
            limit=limit,
            captured=len(pending),
            hint="单事务字段级记录超上限，溢出项已丢弃（完整操作摘要见操作日志）",
        )


def _flush_pending(session: Session, flush_context: object) -> None:
    """`after_flush_postexec`：把暂存变更转 `sys_outbox` 行（同事务）。

    Args:
        session: ORM 会话。
        flush_context: SQLAlchemy 的 UOW 上下文（本钩子不用）。

    Raises:
        InternalError: `fail_closed=true` 且写发件箱失败（业务事务随之回滚）。
    """
    del flush_context
    pending: ConcurrentStableList[_PendingChange] | None = session.info.pop(_PENDING_KEY, None)
    if not pending:
        return
    settings = get_settings().audit_capture
    tenant_id = current_tenant_id_str()
    operator_id = current_user_id.get()
    try:
        for item in pending:
            session.add(_outbox_row(item, tenant_id=tenant_id, operator_id=operator_id))
    except Exception as exc:
        if settings.fail_closed:
            _LOGGER.error("audit_capture_failed", changes=len(pending), fail_closed=True, error=repr(exc))
            raise InternalError("字段级审计写入失败（审计强一致口径下业务已中止）") from exc
        _LOGGER.error("audit_capture_failed", changes=len(pending), fail_closed=False, error=repr(exc))


def _clear_pending(session: Session) -> None:
    """`after_rollback`：丢弃本轮未结算的暂存变更（回滚后不得在下次 flush 补发）。

    Args:
        session: ORM 会话。
    """
    session.info.pop(_PENDING_KEY, None)


def _outbox_row(item: _PendingChange, *, tenant_id: str | None, operator_id: int | None) -> SysOutbox:
    """构造一条发件箱行（与 `SqlOutboxStore.enqueue` 同构）。

    Args:
        item: 字段级变更。
        tenant_id: 租户主键（字符串）。
        operator_id: 操作人主键。

    Returns:
        SysOutbox: 待投递的发件箱行。
    """
    envelope = build_data_changed_event(
        tenant_id=tenant_id,
        table=item.table,
        model_id=item.model_id,
        field=item.field,
        old_value=item.old_value,
        new_value=item.new_value,
        operator_id=operator_id,
    )
    return SysOutbox(
        event_id=envelope.event_id or uuid.uuid4().hex,
        event_type=DATA_CHANGED_EVENT,
        event_version=resolve_event_version(DATA_CHANGED_EVENT),
        aggregate_key=envelope.aggregate_key,
        tenant_id=None if tenant_id is None else int(tenant_id),
        trace_id=envelope.trace_id,
        payload=dict(envelope.payload),
        occurred_at=cast("datetime", envelope.occurred_at),
        status="pending",
    )


def install_field_audit(settings: Settings | None = None) -> bool:
    """挂载字段级变更捕获监听（幂等；`[audit_capture].enabled=false` 时不挂）。

    Args:
        settings: 应用配置（None 取全局单例）。

    Returns:
        bool: 已挂载（或本就挂载）为 True；开关关闭为 False。
    """
    global _installed
    if _installed:
        return True
    resolved = settings or get_settings()
    if not resolved.audit_capture.enabled:
        return False
    event.listen(Session, "before_flush", _collect)
    event.listen(Session, "after_flush_postexec", _flush_pending)
    event.listen(Session, "after_rollback", _clear_pending)
    _installed = True
    _LOGGER.info("audit_capture_installed", tables="base", fail_closed=resolved.audit_capture.fail_closed)
    return True


def uninstall_field_audit() -> None:
    """卸下监听（**测试隔离用**；生产不调用）。"""
    global _installed
    if not _installed:
        return
    event.remove(Session, "before_flush", _collect)
    event.remove(Session, "after_flush_postexec", _flush_pending)
    event.remove(Session, "after_rollback", _clear_pending)
    _installed = False


def is_field_audit_installed() -> bool:
    """是否已挂载捕获监听（测试 / 自检用）。

    Returns:
        bool: 已挂载 True。
    """
    return _installed


def reset_capture_state() -> None:
    """重置去重键集合（**测试隔离用**）。"""
    _CAPTURED.clear()
