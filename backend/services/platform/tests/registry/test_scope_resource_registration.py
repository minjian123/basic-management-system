"""作用域资源类型注册落库与运营期停用（07D `01_01`）：共享库 + 回滚会话用例。

覆盖详细设计 §5 用例 1 / 11 / 12 / 13 / 14 / 16：
- 注册落库：新建 `declaration_version = 1`、内容变更 +1、内容未变不写；
- 运营期停用：只改运营态、声明重放不冲掉停用、幂等且只记一次审计；
- 失败分支：未登记（10002）、已退役（10001）、运营态取值非法（10001）；
- 退役不删行：运营视图不列退役项、库中行保留。

测试库：共享平台库；类型键 / 产品键按命名空间生成，写入整体回滚，不清理他人数据。
"""

from collections.abc import AsyncIterator
from dataclasses import replace

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ConfigError, NotFoundError, ParamError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.events.base import EventEnvelope
from bms_core.models.platform.declaration import SysScopeResourceType
from bms_core.registry.declarations import DeclarationPayload, plan_declarations
from bms_core.resource_scope import (
    SCOPE_RESOURCE_DISABLED,
    SCOPE_RESOURCE_ENABLED,
    ScopeResourceTypeRecord,
    find_scope_resource_type,
    reset_scope_resource_types,
)
from bms_core.services.module_registry import ModuleRecord
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.platform_registry.repositories.declaration_repository import DeclarationRepository
from bms_platform.domains.platform_registry.services.scope_resource import ScopeResourceTypeService

_TYPE = ScopeResourceTypeRecord(
    resource_type_key="demo.topic",
    name="主题",
    name_pattern=r"^[a-z][a-z0-9_]{0,63}$",
    max_length=64,
    retention_days=30,
    removal_policy="purge",
    product_key="demo",
)


class _RecordingAudit(AuditCapturer):
    """审计捕获器替身：记录每次 capture 的入参（不产生真实事件）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.calls: ConcurrentStableList[ConcurrentStableList[FieldChange]] = ConcurrentStableList()
        self.actors: ConcurrentStableList[int | None] = ConcurrentStableList()

    def is_audited(self, table: str) -> bool:
        """恒定纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: True。
        """
        return True

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> EventEnvelope:
        """记录一次审计捕获。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段级变更。
            actor: 操作人。

        Returns:
            EventEnvelope: 占位事件（用例不消费）。
        """
        assert table == "sys_scope_resource_type"
        assert model_id > 0
        self.calls.add(changes)
        self.actors.add(actor)
        return EventEnvelope(event_type="audit.record")


@pytest.fixture
async def session(
    shared_platform_engine: AsyncEngine,
    platform_db_write: None,
) -> AsyncIterator[AsyncSession]:
    """共享平台库上的回滚会话（整条用例持写锁）。

    Args:
        shared_platform_engine: 共享平台库引擎。
        platform_db_write: 平台库整条用例写锁（回滚会话准备阶段即开写事务）。

    Yields:
        AsyncSession: 数据库会话。
    """
    del platform_db_write
    reset_scope_resource_types()
    async with rollback_session(shared_platform_engine) as db:
        yield db
    reset_scope_resource_types()


def _resource_type(ns: Namespace) -> ScopeResourceTypeRecord:
    """按命名空间派生资源类型记录（避免与其他用例的类型行相撞）。

    Args:
        ns: 本用例命名空间。

    Returns:
        ScopeResourceTypeRecord: 资源类型记录。
    """
    return replace(_TYPE, resource_type_key=f"{ns.prefix}.topic", product_key=ns.prefix)


def _payload(ns: Namespace, *records: ScopeResourceTypeRecord) -> DeclarationPayload:
    """构造注册载荷（服务行 + 资源类型）。

    Args:
        ns: 本用例命名空间。
        *records: 资源类型记录。

    Returns:
        DeclarationPayload: 注册载荷。
    """
    service = ModuleRecord(
        module_key=ns.prefix,
        name="演示服务",
        table_prefix=f"{ns.prefix}_",
        event_domain=ns.prefix,
        service_key=ns.prefix,
        product_key=ns.prefix,
    )
    return DeclarationPayload(
        product_key=ns.prefix,
        service_key=ns.prefix,
        services=ConcurrentStableFrozenList((service,)),
        resource_types=ConcurrentStableFrozenList(records),
    )


async def _apply(session: AsyncSession, payload: DeclarationPayload) -> None:
    """按当前库现状对账并落库（提交，模拟注册通道独立事务）。

    Args:
        session: 数据库会话。
        payload: 注册载荷。
    """
    repository = DeclarationRepository(session)
    current = await repository.load_snapshot()
    plan, conflicts = plan_declarations(payload, current)
    assert list(conflicts) == []
    await repository.apply(plan, product_key=payload.product_key)
    # 注册通道在自己的工作单元里提交；运营期写路径会先回滚遗留空事务，故必须显式提交
    await session.commit()


async def _row(session: AsyncSession, ns: Namespace) -> SysScopeResourceType:
    """取本用例唯一类型行。

    Args:
        session: 数据库会话。
        ns: 本用例命名空间。

    Returns:
        SysScopeResourceType: 类型行。
    """
    row = (
        (
            await session.execute(
                select(SysScopeResourceType).where(SysScopeResourceType.resource_type_key == f"{ns.prefix}.topic")
            )
        )
        .scalars()
        .one()
    )
    return row


async def test_registration_creates_then_versions(session: AsyncSession, ns: Namespace) -> None:
    """注册：新建版本 1；内容变更 +1；内容未变不写（版本不再增长）。"""
    resource_type = _resource_type(ns)
    await _apply(session, _payload(ns, resource_type))
    created = await _row(session, ns)
    assert created.declaration_version == 1
    assert created.admin_status == SCOPE_RESOURCE_ENABLED
    assert created.product_key == ns.prefix

    await _apply(session, _payload(ns, replace(resource_type, name="主题（改名）")))
    updated = await _row(session, ns)
    assert updated.declaration_version == 2
    assert updated.name == "主题（改名）"

    await _apply(session, _payload(ns, replace(resource_type, name="主题（改名）")))
    unchanged = await _row(session, ns)
    assert unchanged.declaration_version == 2, "内容未变不写库（声明版本不增长）"


async def test_admin_disable_survives_registration_replay(session: AsyncSession, ns: Namespace) -> None:
    """运营期停用不被声明重放冲掉（运营态与声明态分列、运营态不进内容指纹）。"""
    resource_type = _resource_type(ns)
    key = f"{ns.prefix}.topic"
    await _apply(session, _payload(ns, resource_type))
    service = ScopeResourceTypeService(session, uow=DbUnitOfWork(session))

    record = await service.set_admin_status(key, SCOPE_RESOURCE_DISABLED, actor=7)
    assert record.admin_status == SCOPE_RESOURCE_DISABLED
    assert record.is_active() is False
    disabled = await _row(session, ns)
    assert disabled.disabled_by == 7
    assert disabled.disabled_at is not None

    await _apply(session, _payload(ns, resource_type))
    replayed = await _row(session, ns)
    assert replayed.admin_status == SCOPE_RESOURCE_DISABLED, "声明重放不得把停用改回启用"
    assert replayed.declaration_version == 1, "运营态变化不改变声明版本"
    found = find_scope_resource_type(ns.prefix, "topic")
    assert found is not None, "停用项仍留在视图（区分未注册 / 已停用）"
    assert found.is_active() is False


async def test_disable_is_idempotent_and_audited_once(session: AsyncSession, ns: Namespace) -> None:
    """停用幂等：同值不重复写库、不重复记审计；恢复写回启用并再记一次。"""
    key = f"{ns.prefix}.topic"
    await _apply(session, _payload(ns, _resource_type(ns)))
    audit = _RecordingAudit()
    service = ScopeResourceTypeService(session, audit=audit, uow=DbUnitOfWork(session))

    await service.set_admin_status(key, SCOPE_RESOURCE_DISABLED, actor=7)
    await service.set_admin_status(key, SCOPE_RESOURCE_DISABLED, actor=7)
    assert len(audit.calls) == 1
    assert audit.actors[0] == 7
    assert [(change.field, change.old, change.new) for change in audit.calls[0]] == [
        ("admin_status", SCOPE_RESOURCE_ENABLED, SCOPE_RESOURCE_DISABLED)
    ]

    restored = await service.set_admin_status(key, SCOPE_RESOURCE_ENABLED, actor=9)
    assert restored.is_active() is True
    assert len(audit.calls) == 2


async def test_disable_rejects_unknown_retired_and_invalid_value(session: AsyncSession, ns: Namespace) -> None:
    """失败分支：未登记 10002、已退役 10001、运营态取值非法 10001。"""
    key = f"{ns.prefix}.topic"
    service = ScopeResourceTypeService(session, uow=DbUnitOfWork(session))

    with pytest.raises(NotFoundError):
        await service.set_admin_status(f"{ns.prefix}.missing", SCOPE_RESOURCE_DISABLED)

    with pytest.raises(ParamError):
        await service.set_admin_status(key, "paused")

    await _apply(session, _payload(ns, _resource_type(ns)))
    await _apply(session, _payload(ns))
    with pytest.raises(ParamError):
        await service.set_admin_status(key, SCOPE_RESOURCE_DISABLED)


async def test_list_records_excludes_retired(session: AsyncSession, ns: Namespace) -> None:
    """运营视图：退役项不列出（退役不删行，登记仍保留）。"""
    await _apply(session, _payload(ns, _resource_type(ns)))
    await _apply(session, _payload(ns))

    records = await ScopeResourceTypeService(session).list_records()

    assert [record for record in records if record.resource_type_key.startswith(ns.prefix)] == []
    row = await _row(session, ns)
    assert row.status == "retired", "退役不删行"


async def test_disable_without_audit_or_uow_follows_assembly_contract(session: AsyncSession, ns: Namespace) -> None:
    """无审计器：停用照常生效（不写审计）；无工作单元：写路径 `ConfigError`（fail-fast）。"""
    key = f"{ns.prefix}.topic"
    await _apply(session, _payload(ns, _resource_type(ns)))
    record = await ScopeResourceTypeService(session, uow=DbUnitOfWork(session)).set_admin_status(
        key, SCOPE_RESOURCE_DISABLED, actor=None
    )
    assert record.admin_status == SCOPE_RESOURCE_DISABLED

    with pytest.raises(ConfigError):
        await ScopeResourceTypeService(session).set_admin_status(key, SCOPE_RESOURCE_ENABLED)
