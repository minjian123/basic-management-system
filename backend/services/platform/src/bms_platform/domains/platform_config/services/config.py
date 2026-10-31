"""系统参数管理域服务：CRUD + 重置回落平台默认 + 回收站恢复 + 缓存/字典失效 + 字段级审计。

口径（详细设计 §4）：

- **两层取值**：平台默认值由种子下发为租户库行（`is_overridden=false`）；修改即转覆盖（`true`）；
  重置按 `PLATFORM_CONFIG_DEFAULTS` 回填并置回 `false`；未覆盖项**不可删除**（删了等于删平台默认）。
- **唯一性靠应用层判重**：`(code, deleted_at)` 复合唯一在 `deleted_at IS NULL` 时不生效（NULL 互不相等）。
- **失效顺序**：事务提交后 → `invalidate_config`（DEL 参数键 + INCR 版本）→ 失效 `config` 字典 → 审计留痕；
  后两步失败只 `warning`，不得反噬业务写。
- **审计**：只调 `AuditCapturer.capture` 生成字段级事件（落库与哈希链归 06_01 / 06_02），不自行投递。
"""

from __future__ import annotations

from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.config.base import ConfigCacheRegion
from bms_core.config.models import SysConfig
from bms_core.config.rules import (
    CONFIG_DEPENDS,
    infer_value_kind,
    is_config_key_valid,
    is_sensitive_key,
    is_value_valid,
)
from bms_core.config.seed import PLATFORM_CONFIG_DEFAULTS
from bms_core.config.service import invalidate_config
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    ConfigDefaultProtectedError,
    ConfigDependencyUnsatisfiedError,
    ConfigKeyExistsError,
    ConfigKeyInvalidError,
    ConfigKeyNotFoundError,
    ConfigNoPlatformDefaultError,
    ConfigValueInvalidError,
)
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.datasource.keys import DataSourceKey
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.dict.invalidate import DictInvalidator
from bms_platform.domains.platform_config.repositories.config import ConfigRepository
from bms_platform.domains.platform_config.schemas.config import (
    ConfigCreateRequest,
    ConfigItem,
    ConfigPage,
    ConfigUpdateRequest,
)

__all__ = ["CONFIG_STATUSES", "ConfigAdminService"]

_LOGGER = get_logger("bms")

CONFIG_STATUSES = ConcurrentStableList(("enabled", "disabled"))
"""参数状态取值域（`sys_config.status`）。"""

_PLATFORM_DEFAULTS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    (item.config_key, item.value) for item in PLATFORM_CONFIG_DEFAULTS
)
"""平台默认值索引（`config_key` → 默认值；重置回落与依赖兜底的来源）。"""

_PLATFORM_DEFAULT_REMARKS: ConcurrentStableDict[str, str] = ConcurrentStableDict(
    (item.config_key, item.remark) for item in PLATFORM_CONFIG_DEFAULTS if item.remark
)
"""平台默认备注索引（重置时一并回填）。"""

_TRUE_TEXT = "true"


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _is_on(value: str | None) -> bool:
    """判断开关值是否「开启」（`true` 视为开启）。

    Args:
        value: 参数值。

    Returns:
        bool: 开启 True。
    """
    return isinstance(value, str) and value.strip().lower() == _TRUE_TEXT


def _same_text(left: str | None, right: str) -> bool:
    """文本比较（忽略首尾空白与大小写，布尔 / 数字取值友好）。

    Args:
        left: 左值（可为 None）。
        right: 右值。

    Returns:
        bool: 相等 True。
    """
    return isinstance(left, str) and left.strip().lower() == right.strip().lower()


class ConfigAdminService(BaseFrameworkObject):
    """系统参数管理服务（事务边界由调用方经工作单元开启）。"""

    def __init__(
        self,
        repository: ConfigRepository,
        uow: UnitOfWork,
        *,
        cache: ConfigCacheRegion,
        invalidator: DictInvalidator | None = None,
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 系统参数仓储。
            uow: 请求级工作单元（platform 服务租户库）。
            cache: 系统参数缓存域（写后失效参数键）。
            invalidator: 字典版本化失效器（写后失效 `config` 字典；None 不失效）。
            audit: 审计捕获器（字段级变更留痕；None 不留痕）。
        """
        self._repo = repository
        self._uow = uow
        self._cache = cache
        self._invalidator = invalidator
        self._audit = audit

    async def page(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        group: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> ConfigPage:
        """分页查询参数（可按回收站视图含已删行）。

        Args:
            page: 页码。
            size: 每页条数。
            keyword: 关键字（参数键 / 名称 / 备注）。
            group: 分组前缀。
            status: 状态。
            include_deleted: 是否包含已软删行。

        Returns:
            ConfigPage: 分页结果。
        """
        async with self._uow.begin():
            rows, total = await self._repo.page_filtered(
                page=page, size=size, keyword=keyword, group=group, status=status, include_deleted=include_deleted
            )
        items: ConcurrentStableList[ConfigItem] = ConcurrentStableList(_to_item(row) for row in rows)
        return ConfigPage(list=items, total=total, page=page, size=size)

    async def detail(self, config_key: str) -> ConfigItem:
        """按参数键取详情（页面回显）。

        Args:
            config_key: 参数键。

        Returns:
            ConfigItem: 参数条目。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
        """
        async with self._uow.begin():
            row = await self._require_by_key(config_key)
        return _to_item(row)

    async def create(self, request: ConfigCreateRequest) -> ConfigItem:
        """新增参数（租户自建；覆盖未覆盖项应走修改）。

        Args:
            request: 新增请求。

        Returns:
            ConfigItem: 新建条目。

        Raises:
            ConfigKeyInvalidError: 参数键格式非法（`40503`）。
            ConfigValueInvalidError: 参数值非法（`40504`）。
            ConfigKeyExistsError: 参数键重复（`40502`）。
            ConfigDependencyUnsatisfiedError: 参数依赖不满足（`40505`）。
        """
        _require_key(request.config_key)
        _require_status(request.status)
        self._require_value(request.config_key, request.value)
        async with self._uow.begin():
            if await self._repo.get_by_key(request.config_key) is not None:
                raise ConfigKeyExistsError(f"参数键已存在：{request.config_key}")
            await self._require_dependencies(request.config_key, request.value)
            row = await self._repo.create(
                config_key=request.config_key,
                name=request.name or "",
                value=request.value,
                remark=request.remark,
                status=request.status,
                is_overridden=True,
            )
        await self._after_write(row.config_key, int(row.id), _changes_for(None, row))
        return _to_item(row)

    async def update(self, item_id: int, request: ConfigUpdateRequest) -> ConfigItem:
        """修改参数（乐观锁；值变更即转覆盖态）。

        Args:
            item_id: 参数主键。
            request: 修改请求（`version` 为当前版本）。

        Returns:
            ConfigItem: 修改后的条目。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
            ConcurrentConflictError: 版本不匹配（`10004`）。
            ConfigValueInvalidError: 参数值非法（`40504`）。
            ConfigDependencyUnsatisfiedError: 参数依赖不满足（`40505`）。
        """
        if request.status is not None:
            _require_status(request.status)
        async with self._uow.begin():
            row = await self._require(item_id)
            before = _snapshot(row)
            value = request.value if request.value is not None else row.value
            self._require_value(row.config_key, value)
            await self._require_dependencies(row.config_key, value)
            # 只有「值变了」才转覆盖态：仅改名称 / 备注 / 状态不应剥夺默认项保护（删除保护看 is_overridden）
            overridden = row.is_overridden or value != row.value
            values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
                {"value": value, "is_overridden": overridden}
            )
            if request.name is not None:
                values["name"] = request.name
            if request.remark is not None:
                values["remark"] = request.remark
            if request.status is not None:
                values["status"] = request.status
            updated = await self._repo.update_checked(
                item_id, expected_version=request.version, now=_utc_now(), **dict(values)
            )
            if not updated:
                raise ConcurrentConflictError(f"系统参数已被他人修改：{row.config_key}")
            detail = await self._require(item_id)
        await self._after_write(detail.config_key, int(detail.id), _changes_for(before, detail))
        return _to_item(detail)

    async def reset(self, item_id: int) -> ConfigItem:
        """重置为平台默认值（仅覆盖项生效；未覆盖项幂等返回）。

        Args:
            item_id: 参数主键。

        Returns:
            ConfigItem: 重置后的条目。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
            ConfigNoPlatformDefaultError: 参数无平台默认值（租户自建，`40507`）。
            ConfigDependencyUnsatisfiedError: 参数依赖不满足（`40505`）。
        """
        async with self._uow.begin():
            row = await self._require(item_id)
            if not row.is_overridden:
                return _to_item(row)
            default_value = _PLATFORM_DEFAULTS.get(row.config_key)
            if default_value is None:
                raise ConfigNoPlatformDefaultError(f"参数无平台默认值，无法重置：{row.config_key}")
            await self._require_dependencies(row.config_key, default_value)
            before = _snapshot(row)
            updated = await self._repo.update_checked(
                item_id,
                expected_version=row.version,
                now=_utc_now(),
                value=default_value,
                remark=_PLATFORM_DEFAULT_REMARKS.get(row.config_key),
                is_overridden=False,
            )
            if not updated:
                raise ConcurrentConflictError(f"系统参数已被他人修改：{row.config_key}")
            detail = await self._require(item_id)
        await self._after_write(detail.config_key, int(detail.id), _changes_for(before, detail))
        return _to_item(detail)

    async def delete(self, item_id: int) -> None:
        """删除参数（覆盖项软删进回收站；平台默认项拒绝）。

        Args:
            item_id: 参数主键。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
            ConfigDefaultProtectedError: 平台默认项不可删（`40506`）。
        """
        async with self._uow.begin():
            row = await self._require(item_id)
            if not row.is_overridden:
                raise ConfigDefaultProtectedError(f"平台默认参数不可删除，请改用重置：{row.config_key}")
            before = _snapshot(row)
            await self._repo.soft_delete(item_id)
        await self._after_write(row.config_key, item_id, _changes_for(before, row))

    async def restore(self, item_id: int) -> ConfigItem:
        """从回收站恢复参数（同键已有活行则拒绝）。

        Args:
            item_id: 参数主键。

        Returns:
            ConfigItem: 恢复后的条目。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
            ConfigKeyExistsError: 同键已有未删除行（`40502`）。
        """
        async with self._uow.begin():
            row = await self._repo.get_including_deleted(item_id)
            if row is None:
                raise ConfigKeyNotFoundError(f"系统参数不存在：{item_id}")
            if row.deleted_at is None:
                return _to_item(row)
            if await self._repo.get_by_key(row.config_key) is not None:
                raise ConfigKeyExistsError(f"参数键已存在未删除行，无法恢复：{row.config_key}")
            before = _snapshot(row)
            await self._repo.restore(item_id)
            detail = await self._require(item_id)
        await self._after_write(detail.config_key, int(detail.id), _changes_for(before, detail))
        return _to_item(detail)

    async def _require(self, item_id: int) -> SysConfig:
        """按主键取未删除行或抛不存在。

        Args:
            item_id: 参数主键。

        Returns:
            SysConfig: 参数行。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
        """
        row = await self._repo.get(item_id)
        if row is None:
            raise ConfigKeyNotFoundError(f"系统参数不存在或已删除：{item_id}")
        return row

    async def _require_by_key(self, config_key: str) -> SysConfig:
        """按参数键取未删除行或抛不存在。

        Args:
            config_key: 参数键。

        Returns:
            SysConfig: 参数行。

        Raises:
            ConfigKeyNotFoundError: 参数不存在（`40501`）。
        """
        row = await self._repo.get_by_key(config_key)
        if row is None:
            raise ConfigKeyNotFoundError(f"系统参数不存在或已删除：{config_key}")
        return row

    def _require_value(self, config_key: str, value: str) -> None:
        """校验参数值（类型按平台默认值推断；租户自建键只校验长度）。

        Args:
            config_key: 参数键。
            value: 参数值。

        Raises:
            ConfigValueInvalidError: 值非法（`40504`）。
        """
        kind = infer_value_kind(_PLATFORM_DEFAULTS.get(config_key))
        if not is_value_valid(value, kind=kind):
            raise ConfigValueInvalidError(f"参数值不合法（{kind}）：{config_key}")

    async def _require_dependencies(self, config_key: str, value: str) -> None:
        """校验参数依赖（正向「开启需依赖开启」+ 反向「关闭被依赖项前先关依赖项」）。

        Args:
            config_key: 本次写入的参数键。
            value: 本次写入的参数值。

        Raises:
            ConfigDependencyUnsatisfiedError: 依赖不满足（`40505`）。
        """
        dependency = CONFIG_DEPENDS.get(config_key)
        if dependency is not None and _is_on(value):
            required = await self._repo.get_by_key(dependency.depends_on)
            actual = required.value if required is not None else _PLATFORM_DEFAULTS.get(dependency.depends_on)
            if not _same_text(actual, dependency.expected):
                raise ConfigDependencyUnsatisfiedError(
                    f"{config_key} 需先开启 {dependency.depends_on}={dependency.expected}"
                )
        for item in CONFIG_DEPENDS.values():
            if item.depends_on != config_key:
                continue
            dependent = await self._repo.get_by_key(item.config_key)
            if dependent is None or not _is_on(dependent.value):
                continue
            if not _same_text(value, item.expected):
                raise ConfigDependencyUnsatisfiedError(
                    f"{item.config_key} 仍处于开启状态，须先关闭才能修改 {config_key}"
                )

    async def _after_write(self, config_key: str, item_id: int, changes: ConcurrentStableList[FieldChange]) -> None:
        """写后处理：失效参数缓存 → 失效 config 字典 → 字段级审计（后两步失败只告警）。

        Args:
            config_key: 参数键。
            item_id: 参数主键（审计事件定位用）。
            changes: 字段级变更（空表示无值变化）。
        """
        await invalidate_config(self._cache, config_key)
        await self._invalidate_dict()
        self._capture(config_key, item_id, changes)

    async def _invalidate_dict(self) -> None:
        """失效 `config` 字典（02_01 归口：参数写路径提交后必须失效）。"""
        if self._invalidator is None:
            return
        await self._invalidator.invalidate(ConcurrentStableList((DataSourceKey.CONFIG.value,)))

    def _capture(self, config_key: str, item_id: int, changes: ConcurrentStableList[FieldChange]) -> None:
        """生成字段级审计事件（不投递：落库与哈希链归 06_01 / 06_02）。

        Args:
            config_key: 参数键。
            item_id: 参数主键。
            changes: 字段级变更。
        """
        if self._audit is None or not changes:
            return
        try:
            self._audit.capture(table="sys_config", model_id=item_id, changes=changes, actor=current_user_id.get())
        except Exception as exc:  # 留痕失败不得反噬业务写
            _LOGGER.warning("config_audit_capture_failed", config_key=config_key, error_type=type(exc).__name__)
        if is_sensitive_key(config_key):
            _LOGGER.info("config_sensitive_changed", config_key=config_key, actor=current_user_id.get())


def _require_key(config_key: str) -> None:
    """校验参数键格式。

    Args:
        config_key: 参数键。

    Raises:
        ConfigKeyInvalidError: 格式非法（`40503`）。
    """
    if not is_config_key_valid(config_key):
        raise ConfigKeyInvalidError(f"参数键须为点分小写（如 password.max_age_days）：{config_key}")


def _require_status(status: str) -> None:
    """校验参数状态取值。

    Args:
        status: 状态。

    Raises:
        ConfigValueInvalidError: 状态非法（`40504`）。
    """
    if status not in CONFIG_STATUSES:
        raise ConfigValueInvalidError(f"参数状态非法：{status}")


def _snapshot(row: SysConfig) -> ConcurrentStableDict[str, object]:
    """取行快照（审计变更比对用）。

    Args:
        row: 参数行。

    Returns:
        ConcurrentStableDict[str, object]: 字段 → 旧值。
    """
    return ConcurrentStableDict(
        {
            "value": row.value,
            "name": row.name,
            "remark": row.remark,
            "status": row.status,
            "is_overridden": row.is_overridden,
        }
    )


def _changes_for(before: ConcurrentStableDict[str, object] | None, row: SysConfig) -> ConcurrentStableList[FieldChange]:
    """比对快照与当前行，产出字段级变更（新建时 before 为 None）。

    Args:
        before: 变更前快照（None 表示新建）。
        row: 变更后参数行。

    Returns:
        ConcurrentStableList[FieldChange]: 字段级变更列表（无变化为空）。
    """
    current = _snapshot(row)
    changes: ConcurrentStableList[FieldChange] = ConcurrentStableList()
    for field, new_value in current.items():
        old_value = None if before is None else before.get(field)
        if old_value != new_value:
            changes.add(FieldChange(field=field, old=old_value, new=new_value))
    return changes


def _to_item(row: SysConfig) -> ConfigItem:
    """行 → 接口条目（派生分组 / 来源 / 敏感标记）。

    Args:
        row: 参数行。

    Returns:
        ConfigItem: 接口条目。
    """
    return ConfigItem(
        id=int(row.id),
        config_key=row.config_key,
        name=row.name or row.config_key,
        value=row.value,
        remark=row.remark,
        status=row.status,
        group=row.config_key.split(".")[0],
        source="tenant" if row.is_overridden else "platform",
        is_sensitive=is_sensitive_key(row.config_key),
        version=row.version,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )
