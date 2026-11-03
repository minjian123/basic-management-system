"""语言包管理服务：运行时下发 + 维护列表 + 差异三段批量保存 + 缓存失效。

口径（详细设计 §4.4 / §4.5 / §4.6）：

- **下发合并兜底**：默认语言包打底、请求语言覆盖——前端即使不配 `fallbackLocale` 也不会看到 key 原文。
- **批量保存**：`adds` 命中已存在 `(key, locale)` 时转为更新（幂等 upsert）；`updates` 走行级乐观锁；
  `deletes` 只允许删租户自建行（`is_overridden=true`），平台默认行拒绝（`44008`）。
- **幂等**：`Idempotency-Key` 缺省按请求内容派生（同变更集同键），重复提交直接返回首次结果。
- **失效**：事务提交后按受影响语言 `DEL` 语言包键 + `INCR` 版本；失败只告警（`degraded=true`）。
- **审计**：逐行 `capture`（落库与哈希链归 06_01 / 06_02）。
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.context import current_user_id
from bms_core.core.exceptions import ConcurrentConflictError, I18nMessageKeyInvalidError, I18nMessageNotFoundError
from bms_core.core.logging import get_logger
from bms_core.core.roots import BaseFrameworkObject
from bms_core.db.tenant import current_tenant_id_str
from bms_core.db.unit_of_work import UnitOfWork
from bms_core.i18n.base import BaseTranslator
from bms_core.i18n.cache import I18nCacheRegion
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.registry import BaseLocaleRegistry
from bms_core.i18n.rules import is_message_key_valid, is_message_value_valid, message_module, normalize_locale
from bms_core.i18n.seed import default_message
from bms_core.idempotency.base import IdempotencyStore, build_idempotency_key
from bms_core.models.platform.i18n import SysI18nMessage
from bms_platform.domains.i18n.repositories.locale import LocaleRepository
from bms_platform.domains.i18n.repositories.message import MessageRepository
from bms_platform.domains.i18n.schemas.i18n import (
    CacheInvalidateResult,
    MessageItem,
    MessagePage,
    MessageSaveRequest,
    MessageSaveResult,
    MessagesPayload,
)

__all__ = ["MessageAdminService"]

_LOGGER = get_logger("bms")

_IDEMPOTENCY_SCOPE = "i18n-messages"
"""幂等键作用域前缀（与接口对应）。"""

type AuditBatch = ConcurrentStableList[tuple[int, str, ConcurrentStableList[FieldChange]]]
"""审计批次：`(行主键, 语言, 字段级变更)` 清单（服务内部传递用）。"""


def _utc_now() -> datetime:
    """当前 UTC 时间（naive）。

    Returns:
        datetime: 当前时刻。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def _as_int(value: object) -> int:
    """把幂等载荷里的数值字段转 int（脏值按 0）。

    Args:
        value: 载荷字段值。

    Returns:
        int: 整数值。
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _digest(request: MessageSaveRequest) -> str:
    """按变更集内容派生幂等摘要（同变更集同键）。

    Args:
        request: 批量保存请求。

    Returns:
        str: 32 位十六进制摘要。
    """
    return hashlib.sha256(request.model_dump_json().encode("utf-8")).hexdigest()[:32]


def _to_item(row: SysI18nMessage) -> MessageItem:
    """模型行 → 维护列表条目。

    Args:
        row: 文案行。

    Returns:
        MessageItem: 契约条目。
    """
    return MessageItem(
        id=int(row.id),
        msg_key=row.msg_key,
        module=message_module(row.msg_key),
        locale=row.locale,
        value=row.value,
        remark=row.remark,
        is_overridden=row.is_overridden,
        version=row.version,
    )


def _overridden(msg_key: str, locale: str, value: str) -> bool:
    """按「值是否等于种子值」派生覆盖标记。

    Args:
        msg_key: 文案 key。
        locale: 语言标识。
        value: 文案。

    Returns:
        bool: 与平台默认不同（或不在种子里）为 True。
    """
    return (value or "").strip() != (default_message(msg_key, locale) or "").strip()


class MessageAdminService(BaseFrameworkObject):
    """语言包管理服务（事务边界由调用方经工作单元开启）。"""

    def __init__(
        self,
        repository: MessageRepository,
        locale_repository: LocaleRepository,
        uow: UnitOfWork,
        *,
        translator: BaseTranslator,
        registry: BaseLocaleRegistry,
        cache: I18nCacheRegion,
        invalidator: I18nInvalidator | None = None,
        audit: AuditCapturer | None = None,
        idempotency: IdempotencyStore | None = None,
    ) -> None:
        """初始化。

        Args:
            repository: 语言包仓储。
            locale_repository: 语言清单仓储（语言存在性校验用）。
            uow: 请求级工作单元（platform 服务租户库）。
            translator: 翻译能力域（语言包缓存读取）。
            registry: 语言清单能力域（语言归一 / 默认语言）。
            cache: 国际化缓存域（下发响应带版本号）。
            invalidator: 国际化缓存失效器（写后失效；None 不失效）。
            audit: 审计捕获器（字段级变更留痕；None 不留痕）。
            idempotency: 幂等存储（None 不做幂等）。
        """
        self._repo = repository
        self._locales = locale_repository
        self._uow = uow
        self._translator = translator
        self._registry = registry
        self._cache = cache
        self._invalidator = invalidator
        self._audit = audit
        self._idempotency = idempotency

    async def page(
        self,
        *,
        page: int,
        size: int,
        keyword: str | None = None,
        module: str | None = None,
        locale: str | None = None,
        missing_only: bool = False,
    ) -> MessagePage:
        """语言包维护列表（按 key / 模块 / 语言 / 缺失筛选）。

        Args:
            page: 页码（从 1 起）。
            size: 每页条数。
            keyword: 关键字（文案 key 模糊匹配）。
            module: 模块前缀。
            locale: 语言精确匹配。
            missing_only: 只看缺失。

        Returns:
            MessagePage: 分页结果。
        """
        rows, total = await self._repo.page_filtered(
            page=page, size=size, keyword=keyword, module=module, locale=locale, missing_only=missing_only
        )
        return MessagePage(list=ConcurrentStableList(_to_item(row) for row in rows), total=total, page=page, size=size)

    async def payload(self, *, locale: str | None = None, accept_language: str | None = None) -> MessagesPayload:
        """运行时下发（默认语言兜底 + 请求语言覆盖）。

        Args:
            locale: 显式指定语言（优先）。
            accept_language: 请求 `Accept-Language` 头（未指定 `locale` 时使用）。

        Returns:
            MessagesPayload: 语言包载荷。
        """
        requested = normalize_locale(locale) if locale else ""
        if requested:
            target = await self._registry.ensure_supported(requested)
            fallback = target.lower() != requested.lower()
        else:
            target = self._registry.resolve_locale(accept_language)
            fallback = False
        default_code = self._registry.default_locale()
        merged = await self._translator.load_messages(default_code)
        if target.lower() != default_code.lower():
            override = await self._translator.load_messages(target)
            merged.update(override.items())
        tenant = current_tenant_id_str()
        version = await self._cache.aversion(tenant)
        return MessagesPayload(locale=target, fallback=fallback, version=version, messages=merged)

    async def save(self, request: MessageSaveRequest, *, idempotency_key: str | None = None) -> MessageSaveResult:
        """批量保存（差异三段 + 幂等 + 行级乐观锁）。

        Args:
            request: 批量保存请求。
            idempotency_key: 幂等键（缺省按变更集内容派生）。

        Returns:
            MessageSaveResult: 保存结果（含失效后的版本号）。

        Raises:
            I18nMessageKeyInvalidError: key / 语言 / 值格式非法（`44003`）。
            I18nMessageNotFoundError: 文案不存在 / 平台默认行不可删（`44008`）。
            ConcurrentConflictError: 行版本不匹配（`10004`）。
        """
        key = build_idempotency_key(key=f"{_IDEMPOTENCY_SCOPE}:{idempotency_key or _digest(request)}")
        if self._idempotency is not None:
            first = await self._idempotency.begin(key)
            if not first:
                cached = await self._idempotency.load(key)
                if cached is not None:
                    return MessageSaveResult(
                        created=_as_int(cached.get("created")),
                        updated=_as_int(cached.get("updated")),
                        deleted=_as_int(cached.get("deleted")),
                        version=_as_int(cached.get("version")),
                    )
        created = 0
        updated = 0
        deleted = 0
        locales: ConcurrentStableList[str] = ConcurrentStableList()
        changes: AuditBatch = ConcurrentStableList()
        try:
            async with self._uow.begin():
                now = _utc_now()
                created, updated, locales, changes = await self._apply_adds(request, now, locales, changes)
                upd_count, locales, changes = await self._apply_updates(request, now, locales, changes)
                del_count, locales, changes = await self._apply_deletes(request, locales, changes)
                updated += upd_count
                deleted += del_count
        except Exception:
            if self._idempotency is not None:
                await self._idempotency.release(key)
            raise
        version = 0
        if self._invalidator is not None:
            version = await self._invalidator.invalidate_messages(locales)
        self._capture(changes)
        result = MessageSaveResult(created=created, updated=updated, deleted=deleted, version=version)
        if self._idempotency is not None:
            await self._idempotency.save(key, result.model_dump())
        return result

    async def invalidate_cache(self) -> CacheInvalidateResult:
        """主动失效语言清单与全部语言包缓存。

        Returns:
            CacheInvalidateResult: 失效结果（Redis 不可用时 `degraded=true`）。
        """
        version = 0
        if self._invalidator is not None:
            version = await self._invalidator.invalidate_all()
        return CacheInvalidateResult(version=version, degraded=version == 0)

    async def _apply_adds(
        self,
        request: MessageSaveRequest,
        now: datetime,
        locales: ConcurrentStableList[str],
        changes: AuditBatch,
    ) -> tuple[int, int, ConcurrentStableList[str], AuditBatch]:
        """处理新增段（已存在则转为更新，幂等）。

        Args:
            request: 批量保存请求。
            now: 当前时刻。
            locales: 受影响语言（累积）。
            changes: 审计变更（累积）。

        Returns:
            tuple[int, int, ...]: （新增数, 更新数, 语言, 审计变更）。

        Raises:
            I18nMessageKeyInvalidError: key / 语言 / 值格式非法，或语言未登记（`44003`）。
            ConcurrentConflictError: 转更新时行版本冲突（`10004`）。
        """
        created = 0
        updated = 0
        for add in request.adds:
            msg_key = add.msg_key.strip()
            if not is_message_key_valid(msg_key):
                raise I18nMessageKeyInvalidError(f"文案 key 格式非法：{add.msg_key}（模块.页面.字段）")
            if not is_message_value_valid(add.value):  # pragma: no cover - schema max_length 已前置拦截
                raise I18nMessageKeyInvalidError("文案值超出长度上限（4000）")
            locale = normalize_locale(add.locale)
            if not locale or await self._locales.get_by_code(locale) is None:
                raise I18nMessageKeyInvalidError(f"语言未登记或标识非法：{add.locale}")
            existing = await self._repo.get_by_key_locale(msg_key, locale)
            if existing is not None:
                if existing.value != add.value or (add.remark is not None and existing.remark != add.remark):
                    before = existing.value
                    ok = await self._repo.update_checked(
                        int(existing.id),
                        expected_version=existing.version,
                        now=now,
                        value=add.value,
                        remark=add.remark if add.remark is not None else existing.remark,
                        is_overridden=_overridden(msg_key, existing.locale, add.value),
                    )
                    if not ok:
                        raise ConcurrentConflictError("文案已被他人修改，请刷新后重试")
                    updated += 1
                    changes.add(
                        (
                            int(existing.id),
                            existing.locale,
                            ConcurrentStableList((FieldChange(field="value", old=before, new=add.value),)),
                        )
                    )
                locales.add(existing.locale)
                continue
            row = await self._repo.create(
                msg_key=msg_key,
                name=msg_key,
                locale=locale,
                value=add.value,
                remark=add.remark,
                status="enabled",
                is_overridden=_overridden(msg_key, locale, add.value),
            )
            created += 1
            locales.add(locale)
            changes.add(
                (
                    int(row.id),
                    locale,
                    ConcurrentStableList((FieldChange(field="value", old=None, new=add.value),)),
                )
            )
        return created, updated, locales, changes

    async def _apply_updates(
        self,
        request: MessageSaveRequest,
        now: datetime,
        locales: ConcurrentStableList[str],
        changes: AuditBatch,
    ) -> tuple[int, ConcurrentStableList[str], AuditBatch]:
        """处理修改段（行级乐观锁）。

        Args:
            request: 批量保存请求。
            now: 当前时刻。
            locales: 受影响语言（累积）。
            changes: 审计变更（累积）。

        Returns:
            tuple[int, ...]: （修改数, 语言, 审计变更）。
        """
        updated = 0
        for item in request.updates:
            row = await self._repo.get_including_deleted(int(item.id))
            if row is None or row.deleted_at is not None:
                raise I18nMessageNotFoundError(f"文案不存在：{item.id}")
            if not is_message_value_valid(item.value):  # pragma: no cover - schema max_length 已前置拦截
                raise I18nMessageKeyInvalidError("文案值超出长度上限（4000）")
            before = row.value
            ok = await self._repo.update_checked(
                int(item.id),
                expected_version=item.version,
                now=now,
                value=item.value,
                remark=item.remark,
                is_overridden=_overridden(row.msg_key, row.locale, item.value),
            )
            if not ok:
                raise ConcurrentConflictError("文案已被他人修改，请刷新后重试")
            updated += 1
            locales.add(row.locale)
            if before != item.value:
                changes.add(
                    (
                        int(item.id),
                        row.locale,
                        ConcurrentStableList((FieldChange(field="value", old=before, new=item.value),)),
                    )
                )
        return updated, locales, changes

    async def _apply_deletes(
        self,
        request: MessageSaveRequest,
        locales: ConcurrentStableList[str],
        changes: AuditBatch,
    ) -> tuple[int, ConcurrentStableList[str], AuditBatch]:
        """处理删除段（仅租户自建行可删）。

        Args:
            request: 批量保存请求。
            locales: 受影响语言（累积）。
            changes: 审计变更（累积）。

        Returns:
            tuple[int, ...]: （删除数, 语言, 审计变更）。
        """
        deleted = 0
        for item_id in request.deletes:
            row = await self._repo.get_including_deleted(int(item_id))
            if row is None or row.deleted_at is not None:
                raise I18nMessageNotFoundError(f"文案不存在：{item_id}")
            if not row.is_overridden:
                raise I18nMessageNotFoundError("平台默认文案不可删除（仅可改值）")
            before = row.value
            await self._repo.soft_delete(int(item_id))
            deleted += 1
            locales.add(row.locale)
            changes.add(
                (
                    int(item_id),
                    row.locale,
                    ConcurrentStableList((FieldChange(field="value", old=before, new=None),)),
                )
            )
        return deleted, locales, changes

    def _capture(self, changes: ConcurrentStableList[tuple[int, str, ConcurrentStableList[FieldChange]]]) -> None:
        """逐行生成字段级审计事件（不投递；失败只告警）。

        Args:
            changes: `(行主键, 语言, 字段级变更)` 清单。
        """
        if self._audit is None or not changes:
            return
        for item_id, _locale, fields in changes:
            try:
                self._audit.capture(
                    table="sys_i18n_message", model_id=item_id, changes=fields, actor=current_user_id.get()
                )
            except Exception as exc:  # 留痕失败不得反噬业务写
                _LOGGER.warning("i18n_message_audit_capture_failed", item_id=item_id, error_type=type(exc).__name__)
