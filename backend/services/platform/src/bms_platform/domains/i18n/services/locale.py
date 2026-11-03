"""语言清单管理服务：CRUD + 默认语言保护 + 连带失效 + 字段级审计。

口径（详细设计 §4.2 / §4.7 / §4.9）：

- **平台默认物化**：平台默认语言行由种子下发（`is_overridden=false`）；租户改值 / 新增即 `true`。
- **默认语言唯一**：切默认先清其它行标记、再置本条（同一事务）；不允许把唯一默认语言取消成 0 条（`44006`）。
- **保护**：默认语言不可停用（`44005`）、不可删除（`44005`）；停用 / 删除后必须仍有启用语言（`44004`）；
  仍有语言包数据的语言不可删除（`44002`）。
- **连带失效**：清单任一变更都失效「清单键 + 全部语言包键 + 版本递增 + 快照刷新」——切默认语言会改变
  所有语言的回退结果。
- **审计**：只调 `AuditCapturer.capture`（落库与哈希链归 06_01 / 06_02），失败只告警。
"""

from __future__ import annotations

from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import (
    ConcurrentConflictError,
    I18nMessageKeyInvalidError,
    LocaleCodeExistsError,
    LocaleDefaultConflictError,
    LocaleDefaultProtectedError,
    LocaleHasMessagesError,
    LocaleLastEnabledError,
    LocaleNotFoundError,
)
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.i18n.rules import is_locale_code_valid, normalize_locale
from bms_core.models.platform.i18n import SysI18nLocale
from bms_platform.domains.i18n.repositories.locale import LocaleRepository
from bms_platform.domains.i18n.schemas.i18n import (
    EnabledLocaleItem,
    LocaleCreateRequest,
    LocaleItem,
    LocalePage,
    LocaleUpdateRequest,
)

__all__ = ["LOCALE_STATUSES", "LocaleAdminService"]

_LOGGER = get_logger("bms")

LOCALE_STATUSES = ConcurrentStableList(("enabled", "disabled"))
"""语言状态取值域（`sys_i18n_locale.status`）。"""


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _to_item(row: SysI18nLocale) -> LocaleItem:
    """模型行 → 契约条目。

    Args:
        row: 语言行。

    Returns:
        LocaleItem: 契约条目。
    """
    return LocaleItem(
        id=int(row.id),
        code=row.code,
        name=row.name,
        rtl=row.rtl,
        status=row.status,
        is_default=row.is_default,
        sort=row.sort,
        is_overridden=row.is_overridden,
        version=row.version,
        updated_at=row.updated_at,
        deleted_at=row.deleted_at,
    )


def _snapshot(row: SysI18nLocale) -> ConcurrentStableDict[str, object]:
    """取审计用旧值快照。

    Args:
        row: 语言行。

    Returns:
        ConcurrentStableDict[str, object]: 字段 → 旧值。
    """
    return ConcurrentStableDict(
        {
            "name": row.name,
            "rtl": row.rtl,
            "status": row.status,
            "sort": row.sort,
            "is_default": row.is_default,
        }
    )


def _require_status(status: str) -> None:
    """校验状态取值。

    Args:
        status: 状态值。

    Raises:
        I18nMessageKeyInvalidError: 取值非法（`44003`）。
    """
    if status not in LOCALE_STATUSES:
        raise I18nMessageKeyInvalidError(f"语言状态非法：{status}（允许 enabled / disabled）")


class LocaleAdminService(BaseFrameworkObject):
    """语言清单管理服务（事务边界由调用方经工作单元开启）。"""

    def __init__(
        self,
        repository: LocaleRepository,
        uow: UnitOfWork,
        *,
        registry: BaseLocaleRegistry,
        invalidator: I18nInvalidator | None = None,
        audit: AuditCapturer | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 语言清单仓储。
            uow: 请求级工作单元（platform 服务租户库）。
            registry: 语言清单能力域（启用清单只读出口）。
            invalidator: 国际化缓存失效器（写后连带失效；None 不失效）。
            audit: 审计捕获器（字段级变更留痕；None 不留痕）。
        """
        self._repo = repository
        self._uow = uow
        self._registry = registry
        self._invalidator = invalidator
        self._audit = audit

    async def page(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        status: str | None = None,
        include_deleted: bool = False,
    ) -> LocalePage:
        """语言清单分页。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（标识 / 名称）。
            status: 状态筛选。
            include_deleted: 是否包含已软删行。

        Returns:
            LocalePage: 分页结果。
        """
        rows, total = await self._repo.page_filtered(
            page=page, size=size, keyword=keyword, status=status, include_deleted=include_deleted
        )
        return LocalePage(
            list=ConcurrentStableList(_to_item(row) for row in rows),
            total=total,
            page=page,
            size=size,
        )

    async def list_enabled(self) -> ConcurrentStableList[EnabledLocaleItem]:
        """启用语言清单（登录即可读；走能力域缓存）。

        Returns:
            ConcurrentStableList[EnabledLocaleItem]: 启用语言条目（按 sort 升序）。
        """
        locales = await self._registry.list_locales(enabled_only=True)
        return ConcurrentStableList(
            EnabledLocaleItem(code=item.code, name=item.name, rtl=item.rtl, is_default=item.is_default, sort=item.sort)
            for item in locales
        )

    async def create(self, request: LocaleCreateRequest) -> LocaleItem:
        """新增语言。

        Args:
            request: 新增请求。

        Returns:
            LocaleItem: 新建条目。

        Raises:
            I18nMessageKeyInvalidError: 标识 / 名称 / 状态非法（`44003`）。
            LocaleCodeExistsError: 标识重复（`44001`）。
        """
        code = normalize_locale(request.code)
        if not is_locale_code_valid(code):
            raise I18nMessageKeyInvalidError(f"语言标识非法：{request.code}（IETF 语言标签，如 ar-SA）")
        _require_status(request.status)
        if request.is_default and request.status != "enabled":
            raise I18nMessageKeyInvalidError("默认语言必须为启用状态")
        async with self._uow.begin():
            if await self._repo.get_by_code(code) is not None:
                raise LocaleCodeExistsError(f"语言标识已存在：{code}")
            now = _utc_now()
            if request.is_default:
                await self._repo.clear_default(exclude_id=None, now=now)
            row = await self._repo.create(
                code=code,
                name=request.name.strip(),
                rtl=request.rtl,
                status=request.status,
                sort=request.sort,
                is_default=request.is_default,
                is_overridden=True,
            )
        await self._after_write(int(row.id), None, row)
        return _to_item(row)

    async def update(self, code: str, request: LocaleUpdateRequest) -> LocaleItem:
        """修改语言（乐观锁）。

        Args:
            code: 语言标识。
            request: 修改请求（`version` 为当前版本）。

        Returns:
            LocaleItem: 修改后的条目。

        Raises:
            LocaleNotFoundError: 语言不存在（`44007`）。
            LocaleDefaultProtectedError: 默认语言被停用（`44005`）。
            LocaleLastEnabledError: 停用后无启用语言（`44004`）。
            LocaleDefaultConflictError: 取消唯一默认标记（`44006`）。
            I18nMessageKeyInvalidError: 名称 / 状态非法（`44003`）。
            ConcurrentConflictError: 版本不匹配（`10004`）。
        """
        async with self._uow.begin():
            row = await self._require(code)
            before = _snapshot(row)
            if request.status is not None:
                _require_status(request.status)
                if request.status != "enabled" and row.is_default:
                    raise LocaleDefaultProtectedError(f"默认语言不可停用：{row.code}")
                if request.status != "enabled" and row.status == "enabled" and await self._repo.count_enabled() <= 1:
                    raise LocaleLastEnabledError("至少保留一种启用的语言")
            if request.is_default is False and row.is_default:
                raise LocaleDefaultConflictError("默认语言标记不可取消：请改设其它语言为默认")
            now = _utc_now()
            values: ConcurrentStableDict[str, object] = ConcurrentStableDict({"is_overridden": True})
            if request.name is not None:
                values["name"] = request.name.strip()
            if request.rtl is not None:
                values["rtl"] = request.rtl
            if request.status is not None:
                values["status"] = request.status
            if request.sort is not None:
                values["sort"] = request.sort
            if request.is_default:
                if request.status not in (None, "enabled") or row.status != "enabled":
                    raise I18nMessageKeyInvalidError("默认语言必须为启用状态")
                await self._repo.clear_default(exclude_id=int(row.id), now=now)
                values["is_default"] = True
            updated = await self._repo.update_checked(int(row.id), expected_version=request.version, now=now, **values)
            if not updated:
                raise ConcurrentConflictError("语言已被他人修改，请刷新后重试")
            row = await self._require(code)
        await self._after_write(int(row.id), before, row)
        return _to_item(row)

    async def delete(self, code: str) -> None:
        """删除语言（默认语言 / 仍有语言包数据的语言不可删）。

        Args:
            code: 语言标识。

        Raises:
            LocaleNotFoundError: 语言不存在（`44007`）。
            LocaleDefaultProtectedError: 默认语言不可删除（`44005`）。
            LocaleHasMessagesError: 仍有语言包数据（`44002`）。
            LocaleLastEnabledError: 删除后无启用语言（`44004`）。
        """
        async with self._uow.begin():
            row = await self._require(code)
            if row.is_default:
                raise LocaleDefaultProtectedError(f"默认语言不可删除：{row.code}")
            if await self._repo.has_messages(row.code):
                raise LocaleHasMessagesError(f"语言存在语言包数据，仅可停用：{row.code}")
            if row.status == "enabled" and await self._repo.count_enabled() <= 1:
                raise LocaleLastEnabledError("至少保留一种启用的语言")
            before = _snapshot(row)
            await self._repo.soft_delete(int(row.id))
        await self._after_write(int(row.id), before, None)

    async def _require(self, code: str) -> SysI18nLocale:
        """取语言行（不存在抛 `44007`）。

        Args:
            code: 语言标识。

        Returns:
            SysI18nLocale: 语言行。

        Raises:
            LocaleNotFoundError: 语言不存在（`44007`）。
        """
        row = await self._repo.get_by_code(code)
        if row is None:
            raise LocaleNotFoundError(f"语言不存在：{code}")
        return row

    async def _after_write(
        self, item_id: int, before: ConcurrentStableDict[str, object] | None, after: SysI18nLocale | None
    ) -> None:
        """写后处理：连带失效缓存 + 字段级审计（失败只告警）。

        Args:
            item_id: 语言主键。
            before: 变更前快照（新增为 None）。
            after: 变更后行（删除为 None）。
        """
        if self._invalidator is not None:
            await self._invalidator.invalidate_all()
        changes: ConcurrentStableList[FieldChange] = ConcurrentStableList()
        keys = ("name", "rtl", "status", "sort", "is_default")
        if before is None and after is not None:
            for field in keys:
                changes.add(FieldChange(field=field, old=None, new=getattr(after, field)))
        elif before is not None and after is not None:
            for field in keys:
                new_value = getattr(after, field)
                if before.get(field) != new_value:
                    changes.add(FieldChange(field=field, old=before.get(field), new=new_value))
        elif before is not None:
            for field in keys:
                changes.add(FieldChange(field=field, old=before.get(field), new=None))
        if self._audit is None or not changes:
            return
        try:
            self._audit.capture(table="sys_i18n_locale", model_id=item_id, changes=changes, actor=current_user_id.get())
        except Exception as exc:  # 留痕失败不得反噬业务写
            _LOGGER.warning("i18n_locale_audit_capture_failed", item_id=item_id, error_type=type(exc).__name__)
