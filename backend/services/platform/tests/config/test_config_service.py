"""系统参数管理服务用例（Kiwi 2373）：缓存失效 / 字典失效 / 字段级审计 / 重置与保护。

服务层直测（不经 HTTP）：用内存缓存域 + 记录型失效器 / 审计捕获器，
断言写路径的**提交后动作**与失败隔离（失效或审计异常不得反噬业务写）。

单库叠加口径（04-6-2）：库用共享租户库、写入走 `rollback_session`（整体回滚不残留）；
参数键带命名空间前缀（`<group>.<ns>`），分页断言按参数键过滤。
"""

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ConfigDefaultProtectedError,
    ConfigValueInvalidError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.invalidate import DictInvalidator
from bms_core.events.base import EventEnvelope
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import ConfigCreateRequest, ConfigUpdateRequest
from bms_platform.domains.platform_config.services.config import ConfigAdminService

pytestmark = pytest.mark.kiwi_id(2373)

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList((SysConfig.__table__,))
"""本文件涉及的表（共享租户库幂等补齐）。"""


def _key(ns: Namespace, group: str) -> str:
    """按命名空间派生参数键（保留分组前缀，叠加下不与他人参数相撞）。

    Args:
        ns: 用例命名空间。
        group: 参数分组（键的第一段）。

    Returns:
        str: 参数键。
    """
    return f"{group}.{ns.prefix}"


class _RecordingInvalidator(DictInvalidator):
    """记录失效调用的字典失效器（不触碰真实缓存）。"""

    def __init__(self) -> None:
        super().__init__(MemoryDictCacheRegion())
        self.keys: ConcurrentStableList[str] = ConcurrentStableList()

    async def invalidate(self, keys: ConcurrentStableList[str], *, tenant: str | None = None) -> int:
        """记录传入的数据源键（不递增版本）。

        Args:
            keys: 数据源键。
            tenant: 租户标识（忽略）。

        Returns:
            int: 固定 1。
        """
        for key in keys:
            self.keys.add(key)
        return 1


class _RecordingAudit(AuditCapturer):
    """记录字段级变更的审计捕获器（不投递）。

    不声明 `plugin_name`：声明了会被插件注册表自动收集，污染 `/api/v1/plugins` 的 `audit` 分组。
    """

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: ConcurrentStableList[ConcurrentStableList[FieldChange]] = ConcurrentStableList()
        self.tables: ConcurrentStableList[str] = ConcurrentStableList()
        self._fail = fail

    def is_audited(self, table: str) -> bool:
        """所有表均视为纳入审计。

        Args:
            table: 逻辑表名。

        Returns:
            bool: 恒 True。
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
        """记录一次捕获（`fail=True` 时抛错，验证失败隔离）。

        Args:
            table: 逻辑表名。
            model_id: 记录主键。
            changes: 字段级变更。
            actor: 操作者。

        Returns:
            EventEnvelope: 占位事件。

        Raises:
            RuntimeError: 构造时指定 `fail=True`。
        """
        if self._fail:
            raise RuntimeError("audit boom")
        self.tables.add(table)
        self.calls.add(changes)
        return EventEnvelope(event_type="audit.test", payload=ConcurrentStableDict())


@pytest_asyncio.fixture
async def session(shared_tenant_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """共享租户库上的回滚会话（`sys_config` 表幂等补齐）。

    Args:
        shared_tenant_engine: 共享租户库引擎。

    Yields:
        AsyncSession: 回滚会话。
    """
    async with shared_tenant_engine.begin() as connection:
        await connection.run_sync(lambda conn: SysConfig.metadata.create_all(conn, tables=list(_TABLES)))
    async with rollback_session(shared_tenant_engine) as db:
        yield db


def _service(
    session: AsyncSession,
    *,
    cache: MemoryConfigCacheRegion | None = None,
    invalidator: DictInvalidator | None = None,
    audit: AuditCapturer | None = None,
) -> ConfigAdminService:
    """构造管理服务（请求级会话 + 内存缓存域）。

    Args:
        session: 租户库会话。
        cache: 缓存域（缺省新建内存域）。
        invalidator: 字典失效器。
        audit: 审计捕获器。

    Returns:
        ConfigAdminService: 服务实例。
    """
    return ConfigAdminService(
        ConfigRepository(session),
        DbUnitOfWork(session),
        cache=cache if cache is not None else MemoryConfigCacheRegion(),
        invalidator=invalidator,
        audit=audit,
    )


async def _seed_default(session: AsyncSession, config_key: str, value: str) -> SysConfig:
    """落一行平台默认参数（未覆盖）；共享库里已有同键行时改为复位到默认态。

    单库叠加口径：`prepare_tenant` 已播种平台默认参数，固定键（如 `ai.auto_execute`）不能重复插入——
    故这里按「存在即复位、不存在则新建」准备前置数据（用例内写入仍随回滚会话整体回滚）。

    Args:
        session: 租户库会话。
        config_key: 参数键。
        value: 参数值。

    Returns:
        SysConfig: 参数行。
    """
    row = (await session.execute(select(SysConfig).where(SysConfig.config_key == config_key))).scalars().first()
    if row is None:
        row = SysConfig(config_key=config_key, value=value, is_overridden=False)
        session.add(row)
    else:
        row.value = value
        row.is_overridden = False
        row.deleted_at = None
    await session.commit()
    return row


async def test_create_invalidates_cache_and_dict_and_audits(session: AsyncSession, ns: Namespace) -> None:
    """新增：缓存版本递增 + `config` 字典失效 + 字段级审计（新增项 old 为空）。"""
    key = _key(ns, "password")
    cache = MemoryConfigCacheRegion()
    invalidator = _RecordingInvalidator()
    audit = _RecordingAudit()
    await cache.aset_value_at(None, key, "8", 0)
    before = await cache.aversion(None)

    await _service(session, cache=cache, invalidator=invalidator, audit=audit).create(
        ConfigCreateRequest(config_key=key, value="10", name="最小长度")
    )

    assert await cache.aversion(None) == before + 1
    assert await cache.aget_value_at(None, key, before + 1) is None
    assert list(invalidator.keys) == ["config"]
    assert list(audit.tables) == ["sys_config"]
    changes = audit.calls[0]
    fields = {change.field: change for change in changes}
    assert fields["value"].old is None
    assert fields["value"].new == "10"


async def test_update_records_field_level_diff(session: AsyncSession, ns: Namespace) -> None:
    """修改：审计记录 value 旧值→新值，来源转为租户覆盖。"""
    key = _key(ns, "password")
    await _seed_default(session, key, "90")
    audit = _RecordingAudit()
    service = _service(session, audit=audit)
    detail = await service.detail(key)

    updated = await service.update(
        detail.id, ConfigUpdateRequest(value="30", version=detail.version, remark="缩短有效期")
    )
    assert updated.value == "30"
    assert updated.source == "tenant"
    fields = {change.field: change for change in audit.calls[0]}
    assert fields["value"].old == "90"
    assert fields["value"].new == "30"
    assert fields["is_overridden"].new is True


async def test_reset_restores_default_and_clears_flag(session: AsyncSession) -> None:
    """重置：值回落平台默认、覆盖标记清空、来源回到 platform。

    单库叠加口径：重置的落点是**平台默认值表**里的参数键（`_PLATFORM_DEFAULTS`），故这里用
    平台默认键并按需复位（共享库已播种同键行，重复插入会撞唯一键）。
    """
    key = "session.max_active"
    await _seed_default(session, key, "5")
    service = _service(session)
    detail = await service.detail(key)
    await service.update(detail.id, ConfigUpdateRequest(value="9", version=detail.version))

    overridden = await service.detail(key)
    reset = await service.reset(overridden.id)
    assert reset.value == "5"
    assert reset.source == "platform"

    again = await service.reset(reset.id)
    assert again.value == "5"


async def test_delete_protects_platform_default(session: AsyncSession, ns: Namespace) -> None:
    """删除：未覆盖项拒绝（`40506`），覆盖项软删后可恢复。"""
    key = _key(ns, "role")
    row = await _seed_default(session, key, "^[a-z]+$")
    service = _service(session)
    detail = await service.detail(key)

    with pytest.raises(ConfigDefaultProtectedError):
        await service.delete(detail.id)

    await service.update(detail.id, ConfigUpdateRequest(value="^[a-z0-9]+$", version=detail.version))
    overridden = await service.detail(key)
    await service.delete(overridden.id)

    page = await service.page(page=1, size=20, include_deleted=True, keyword=key)
    assert page.total == 1
    restored = await service.restore(overridden.id)
    assert restored.deleted_at is None
    assert int(row.id) == detail.id


async def test_audit_failure_does_not_break_write(session: AsyncSession, ns: Namespace) -> None:
    """审计异常被吞（记 warning），业务写仍然成功。"""
    audit = _RecordingAudit(fail=True)
    created = await _service(session, audit=audit).create(
        ConfigCreateRequest(config_key=_key(ns, "custom"), value="true")
    )
    assert created.value == "true"


async def test_service_without_invalidator_and_audit(session: AsyncSession, ns: Namespace) -> None:
    """未注入失效器 / 审计时（可选依赖）写路径照常工作。"""
    key = _key(ns, "custom")
    service = _service(session)
    created = await service.create(ConfigCreateRequest(config_key=key, value="30"))
    assert created.group == "custom"
    detail = await service.detail(key)
    assert detail.id == created.id


class _AlwaysConflictingRepository(ConfigRepository):
    """乐观锁恒失败的仓储替身（覆盖重置路径的并发冲突分支）。"""

    async def update_checked(self, item_id: int, *, expected_version: int, now: datetime, **values: object) -> bool:
        """恒返回失败。

        Args:
            item_id: 参数主键。
            expected_version: 期望版本。
            now: 当前时刻。
            **values: 待更新字段。

        Returns:
            bool: 恒 False。
        """
        return False


async def test_update_changes_name_remark_and_status(session: AsyncSession, ns: Namespace) -> None:
    """修改：名称 / 备注 / 状态一并更新，并进入审计变更集。"""
    key = _key(ns, "file")
    await _seed_default(session, key, "20971520")
    audit = _RecordingAudit()
    service = _service(session, audit=audit)
    detail = await service.detail(key)

    updated = await service.update(
        detail.id,
        ConfigUpdateRequest(
            value="10485760", name="整包上限", remark="10MB", status="disabled", version=detail.version
        ),
    )
    assert updated.name == "整包上限"
    assert updated.remark == "10MB"
    assert updated.status == "disabled"
    fields = {change.field for change in audit.calls[0]}
    assert {"value", "name", "remark", "status"} <= fields

    listed = await service.page(page=1, size=10, status="disabled", keyword=key)
    assert listed.total == 1


async def test_update_rejects_invalid_status(session: AsyncSession, ns: Namespace) -> None:
    """修改：状态取值非法时拒绝（`40504`）。"""
    key = _key(ns, "menu")
    await _seed_default(session, key, "300")
    service = _service(session)
    detail = await service.detail(key)
    with pytest.raises(ConfigValueInvalidError):
        await service.update(detail.id, ConfigUpdateRequest(status="archived", version=detail.version))


async def test_reset_raises_conflict_when_version_stale(session: AsyncSession) -> None:
    """重置：乐观锁失败时抛并发冲突（`10004`）。"""
    await _seed_default(session, "account.inactive_lock_days", "180")
    service = _service(session)
    detail = await service.detail("account.inactive_lock_days")
    await service.update(detail.id, ConfigUpdateRequest(value="90", version=detail.version))
    overridden = await service.detail("account.inactive_lock_days")

    conflicting = ConfigAdminService(
        _AlwaysConflictingRepository(session),
        DbUnitOfWork(session),
        cache=MemoryConfigCacheRegion(),
    )
    with pytest.raises(ConcurrentConflictError):
        await conflicting.reset(overridden.id)


async def test_dependency_reverse_allows_close_when_dependent_off(session: AsyncSession) -> None:
    """依赖反向校验：被依赖项可关闭（依赖项存在但未开启）。"""
    execute = await _seed_default(session, "ai.auto_execute", "true")
    await _seed_default(session, "ai.auto_approve", "false")
    service = _service(session)
    detail = await service.detail("ai.auto_execute")

    updated = await service.update(detail.id, ConfigUpdateRequest(value="false", version=detail.version))
    assert updated.value == "false"
    assert int(execute.id) == detail.id


async def test_dependency_reverse_passes_when_keeping_dependency_on(session: AsyncSession) -> None:
    """依赖反向校验：被依赖项保持开启值时不拦截（只有关闭才拦）。"""
    await _seed_default(session, "ai.auto_execute", "true")
    await _seed_default(session, "ai.auto_approve", "true")
    service = _service(session)
    detail = await service.detail("ai.auto_execute")

    updated = await service.update(detail.id, ConfigUpdateRequest(value="true", version=detail.version))
    assert updated.value == "true"


async def test_dependency_reverse_when_dependent_missing(session: AsyncSession) -> None:
    """依赖反向校验：依赖项参数不存在时直接放行（不 phantom 拦截）。

    单库叠加口径：共享库已播种被依赖项（`ai.auto_approve`），故显式软删该行构造「依赖项不存在」。
    """
    await _seed_default(session, "ai.auto_execute", "true")
    dependent = await _seed_default(session, "ai.auto_approve", "false")
    dependent.soft_delete()
    await session.commit()
    service = _service(session)
    detail = await service.detail("ai.auto_execute")

    updated = await service.update(detail.id, ConfigUpdateRequest(value="false", version=detail.version))
    assert updated.value == "false"


async def test_rename_keeps_platform_default_protection(session: AsyncSession) -> None:
    """只改名称 / 备注不转覆盖态：默认项仍受删除保护（避免误删唯一承载平台默认的行）。"""
    await _seed_default(session, "menu.tree_cache_ttl", "300")
    service = _service(session)
    detail = await service.detail("menu.tree_cache_ttl")

    updated = await service.update(detail.id, ConfigUpdateRequest(name="菜单树缓存 TTL", version=detail.version))
    assert updated.name == "菜单树缓存 TTL"
    assert updated.source == "platform"

    with pytest.raises(ConfigDefaultProtectedError):
        await service.delete(updated.id)


async def test_repository_restore_missing_returns_false(session: AsyncSession) -> None:
    """仓储恢复：记录不存在时返回 False（服务层不会走到，但出口需自洽）。"""
    assert await ConfigRepository(session).restore(999999) is False


def test_service_is_base_object() -> None:
    """服务继承基座对象（架构铁律：自定义类必须有基类）。"""
    assert issubclass(ConfigAdminService, BaseFrameworkObject)
