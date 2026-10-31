"""系统参数管理服务用例（Kiwi 2373）：缓存失效 / 字典失效 / 字段级审计 / 重置与保护。

服务层直测（不经 HTTP）：用临时租户库 + 内存缓存域 + 记录型失效器 / 审计捕获器，
断言写路径的**提交后动作**与失败隔离（失效或审计异常不得反噬业务写）。
"""

from collections.abc import AsyncIterator
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.cache import MemoryConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ConfigDefaultProtectedError,
    ConfigValueInvalidError,
)
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.bootstrap import apply_unit_schema
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.dict.cache import MemoryDictCacheRegion
from bms_core.dict.invalidate import DictInvalidator
from bms_core.events.base import EventEnvelope
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import ConfigCreateRequest, ConfigUpdateRequest
from bms_platform.domains.platform_config.services.config import ConfigAdminService

pytestmark = pytest.mark.kiwi_id(2373)


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
async def session(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncSession]:
    """临时租户库会话（`sys_config` 表）。

    Args:
        tmp_path_factory: 临时目录工厂。
        monkeypatch: 环境变量覆盖。

    Yields:
        AsyncSession: 会话。
    """
    url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('config_service') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", url)
    get_settings.cache_clear()
    await apply_unit_schema("platform", "tenant", url, target="config_service")
    engine = create_async_engine(url)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as db:
            yield db
    finally:
        await engine.dispose()
        get_settings.cache_clear()


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
    """落一行平台默认参数（未覆盖）。

    Args:
        session: 租户库会话。
        config_key: 参数键。
        value: 参数值。

    Returns:
        SysConfig: 参数行。
    """
    row = SysConfig(config_key=config_key, value=value, is_overridden=False)
    session.add(row)
    await session.commit()
    return row


async def test_create_invalidates_cache_and_dict_and_audits(session: AsyncSession) -> None:
    """新增：缓存版本递增 + `config` 字典失效 + 字段级审计（新增项 old 为空）。"""
    cache = MemoryConfigCacheRegion()
    invalidator = _RecordingInvalidator()
    audit = _RecordingAudit()
    await cache.aset_value_at(None, "password.min_length", "8", 0)
    before = await cache.aversion(None)

    await _service(session, cache=cache, invalidator=invalidator, audit=audit).create(
        ConfigCreateRequest(config_key="password.min_length", value="10", name="最小长度")
    )

    assert await cache.aversion(None) == before + 1
    assert await cache.aget_value_at(None, "password.min_length", before + 1) is None
    assert list(invalidator.keys) == ["config"]
    assert list(audit.tables) == ["sys_config"]
    changes = audit.calls[0]
    fields = {change.field: change for change in changes}
    assert fields["value"].old is None
    assert fields["value"].new == "10"


async def test_update_records_field_level_diff(session: AsyncSession) -> None:
    """修改：审计记录 value 旧值→新值，来源转为租户覆盖。"""
    await _seed_default(session, "password.max_age_days", "90")
    audit = _RecordingAudit()
    service = _service(session, audit=audit)
    detail = await service.detail("password.max_age_days")

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
    """重置：值回落平台默认、覆盖标记清空、来源回到 platform。"""
    await _seed_default(session, "session.max_active", "5")
    service = _service(session)
    detail = await service.detail("session.max_active")
    await service.update(detail.id, ConfigUpdateRequest(value="9", version=detail.version))

    overridden = await service.detail("session.max_active")
    reset = await service.reset(overridden.id)
    assert reset.value == "5"
    assert reset.source == "platform"

    again = await service.reset(reset.id)
    assert again.value == "5"


async def test_delete_protects_platform_default(session: AsyncSession) -> None:
    """删除：未覆盖项拒绝（`40506`），覆盖项软删后可恢复。"""
    row = await _seed_default(session, "role.code_pattern", "^[a-z]+$")
    service = _service(session)
    detail = await service.detail("role.code_pattern")

    with pytest.raises(ConfigDefaultProtectedError):
        await service.delete(detail.id)

    await service.update(detail.id, ConfigUpdateRequest(value="^[a-z0-9]+$", version=detail.version))
    overridden = await service.detail("role.code_pattern")
    await service.delete(overridden.id)

    page = await service.page(page=1, size=20, include_deleted=True)
    assert page.total == 1
    restored = await service.restore(overridden.id)
    assert restored.deleted_at is None
    assert int(row.id) == detail.id


async def test_audit_failure_does_not_break_write(session: AsyncSession) -> None:
    """审计异常被吞（记 warning），业务写仍然成功。"""
    audit = _RecordingAudit(fail=True)
    created = await _service(session, audit=audit).create(ConfigCreateRequest(config_key="custom.flag", value="true"))
    assert created.value == "true"


async def test_service_without_invalidator_and_audit(session: AsyncSession) -> None:
    """未注入失效器 / 审计时（可选依赖）写路径照常工作。"""
    service = _service(session)
    created = await service.create(ConfigCreateRequest(config_key="custom.timeout", value="30"))
    assert created.group == "custom"
    detail = await service.detail("custom.timeout")
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


async def test_update_changes_name_remark_and_status(session: AsyncSession) -> None:
    """修改：名称 / 备注 / 状态一并更新，并进入审计变更集。"""
    await _seed_default(session, "file.upload.max_size", "20971520")
    audit = _RecordingAudit()
    service = _service(session, audit=audit)
    detail = await service.detail("file.upload.max_size")

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

    listed = await service.page(page=1, size=10, status="disabled")
    assert listed.total == 1


async def test_update_rejects_invalid_status(session: AsyncSession) -> None:
    """修改：状态取值非法时拒绝（`40504`）。"""
    await _seed_default(session, "menu.tree_cache_ttl", "300")
    service = _service(session)
    detail = await service.detail("menu.tree_cache_ttl")
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
