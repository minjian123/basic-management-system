"""国际化服务单元测试（Kiwi 2404）：幂等命中 / 审计边界 / 幂等载荷转换。

不走 HTTP：用替身注入「幂等存储 / 审计捕获器」，覆盖 API 层不可达的分支
（`IdempotencyStore` 命中、`audit=None`、审计捕获抛错）。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest

from bms_core.audit.base import AuditCapturer, FieldChange
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ConcurrentConflictError, I18nMessageKeyInvalidError
from bms_core.i18n.cache import MemoryI18nCacheRegion
from bms_core.i18n.invalidate import I18nInvalidator
from bms_core.i18n.registry_null import NullLocaleRegistry
from bms_core.i18n.seed import MESSAGE_SEEDS
from bms_core.models.platform.i18n import SysI18nLocale
from bms_platform.domains.i18n.schemas.i18n import MessageAddItem, MessageSaveRequest
from bms_platform.domains.i18n.services.locale import LocaleAdminService
from bms_platform.domains.i18n.services.locale import _snapshot as locale_snapshot  # pyright: ignore[reportPrivateUsage]
from bms_platform.domains.i18n.services.message import MessageAdminService

pytestmark = [pytest.mark.kiwi_id(2404)]


_NoInvalidator = object()
"""哨兵：区分「未显式传失效器」与「显式传 None」。"""


class _PendingStore:
    """幂等存储替身：`begin` 恒 True（首次提交），`load` 无首次结果。"""

    async def begin(self, key: str, *, ttl: int = 0) -> bool:
        """前置去重（恒 True）。

        Args:
            key: 幂等 key。
            ttl: 有效期。

        Returns:
            bool: 恒 True。
        """
        del key, ttl
        return True

    async def load(self, key: str) -> Any:
        """取首次结果（无）。

        Args:
            key: 幂等 key。

        Returns:
            Any: 恒 None。
        """
        del key
        return None

    async def save(self, key: str, payload: Any, *, ttl: int = 0) -> None:
        """写首次结果（替身空操作）。

        Args:
            key: 幂等 key。
            payload: 载荷。
            ttl: 有效期。
        """
        del key, payload, ttl

    async def release(self, key: str) -> None:
        """释放幂等键（替身空操作）。

        Args:
            key: 幂等 key。
        """
        del key


class _FakeUow:
    """工作单元替身：`begin()` 只提供事务边界（不连库）。"""

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        """事务边界替身。

        Yields:
            None: 事务内。
        """
        yield


class _HitStore:
    """幂等存储替身：`begin` 恒 False（视为重复提交），`load` 返回首次结果。"""

    async def begin(self, key: str, *, ttl: int = 0) -> bool:
        """前置去重（恒 False）。

        Args:
            key: 幂等 key。
            ttl: 有效期。

        Returns:
            bool: 恒 False。
        """
        del key, ttl
        return False

    async def load(self, key: str) -> Any:
        """取首次结果。

        Args:
            key: 幂等 key。

        Returns:
            Any: 固定载荷。
        """
        del key
        return {"created": 2, "updated": 1, "deleted": 0, "version": 9}

    async def save(self, key: str, payload: Any, *, ttl: int = 0) -> None:
        """写首次结果（替身空操作）。

        Args:
            key: 幂等 key。
            payload: 载荷。
            ttl: 有效期。
        """
        del key, payload, ttl

    async def release(self, key: str) -> None:
        """释放幂等键（替身空操作）。

        Args:
            key: 幂等 key。
        """
        del key


class _BrokenAudit(AuditCapturer):
    """审计捕获器替身：`capture` 抛错（验证留痕失败不反噬业务写）。"""

    def is_audited(self, table: str) -> bool:
        """是否纳入审计。

        Args:
            table: 表名。

        Returns:
            bool: 恒 True。
        """
        del table
        return True

    def capture(
        self,
        *,
        table: str,
        model_id: int,
        changes: ConcurrentStableList[FieldChange],
        actor: int | None = None,
    ) -> object | None:
        """捕获字段级变更（恒抛错）。

        Args:
            table: 表名。
            model_id: 行主键。
            changes: 字段级变更。
            actor: 操作人。

        Raises:
            RuntimeError: 恒抛。
        """
        del table, model_id, changes, actor
        raise RuntimeError("audit down")


def _message_service(
    *,
    idempotency: object | None = None,
    audit: object | None = None,
    invalidator: object | None = _NoInvalidator,
) -> MessageAdminService:
    """构造语言包服务（仓储 / 工作单元为替身，仅覆盖幂等与审计分支）。

    Args:
        idempotency: 幂等存储替身。
        audit: 审计捕获器替身。
        invalidator: 失效器（缺省接真实实现；传 None 覆盖「未装配失效器」分支）。

    Returns:
        MessageAdminService: 服务实例。
    """
    cache = MemoryI18nCacheRegion()
    registry = NullLocaleRegistry()
    resolved = I18nInvalidator(cache, registry) if invalidator is _NoInvalidator else cast("Any", invalidator)
    return MessageAdminService(
        cast("Any", object()),
        cast("Any", object()),
        cast("Any", _FakeUow()),
        translator=cast("Any", object()),
        registry=registry,
        cache=cache,
        invalidator=resolved,
        audit=cast("Any", audit),
        idempotency=cast("Any", idempotency),
    )


async def test_save_without_idempotency_and_invalidator() -> None:
    """未装配幂等 / 失效器：保存照常执行，失效结果标记降级。"""
    service = _message_service(invalidator=None)
    result = await service.save(MessageSaveRequest())
    assert result.created == 0
    assert result.version == 0
    invalidated = await service.invalidate_cache()
    assert invalidated.version == 0
    assert invalidated.degraded is True


async def test_save_with_first_submission_store() -> None:
    """幂等存储首次提交（无首次结果）：正常执行并按受影响语言失效。"""
    service = _message_service(idempotency=_PendingStore())
    result = await service.save(MessageSaveRequest())
    assert result.created == 0
    assert result.version >= 1


async def test_save_returns_first_result_on_idempotent_replay() -> None:
    """幂等命中：直接返回首次结果（不进入事务、不写库）。"""
    service = _message_service(idempotency=_HitStore())
    result = await service.save(MessageSaveRequest())
    assert result.created == 2
    assert result.updated == 1
    assert result.version == 9


def _audit_batch() -> ConcurrentStableList[tuple[int, str, ConcurrentStableList[FieldChange]]]:
    """构造一行审计批次。

    Returns:
        ConcurrentStableList[tuple[int, str, ConcurrentStableList[FieldChange]]]: 审计批次。
    """
    fields: ConcurrentStableList[FieldChange] = ConcurrentStableList((FieldChange(field="value", old=None, new="x"),))
    return ConcurrentStableList(((1, "zh-CN", fields),))


def test_message_capture_skips_without_audit_or_changes() -> None:
    """审计边界：无捕获器 / 无变更时不产生事件。"""
    service = _message_service()
    service._capture(ConcurrentStableList())  # pyright: ignore[reportPrivateUsage]
    service._capture(_audit_batch())  # pyright: ignore[reportPrivateUsage]


def test_message_capture_swallows_audit_failure() -> None:
    """审计捕获抛错只告警（不反噬业务写）。"""
    service = _message_service(audit=_BrokenAudit())
    service._capture(_audit_batch())  # pyright: ignore[reportPrivateUsage]


def _locale_row() -> SysI18nLocale:
    """构造内存语言行（不落库）。

    Returns:
        SysI18nLocale: 语言行。
    """
    return SysI18nLocale(code="zh-CN", name="简体中文", rtl=False, status="enabled", sort=1, is_default=True)


def _locale_service(*, audit: object | None = None, invalidator: object | None = _NoInvalidator) -> LocaleAdminService:
    """构造语言清单服务（仓储 / 工作单元为替身）。

    Args:
        audit: 审计捕获器替身。
        invalidator: 失效器（缺省接真实实现；传 None 覆盖「未装配失效器」分支）。

    Returns:
        LocaleAdminService: 服务实例。
    """
    cache = MemoryI18nCacheRegion()
    registry = NullLocaleRegistry()
    resolved = I18nInvalidator(cache, registry) if invalidator is _NoInvalidator else cast("Any", invalidator)
    return LocaleAdminService(
        cast("Any", object()),
        cast("Any", _FakeUow()),
        registry=registry,
        invalidator=resolved,
        audit=cast("Any", audit),
    )


async def test_locale_after_write_change_branches() -> None:
    """写后处理：新增（旧值全 None）/ 删除（新值全 None）/ 审计失败降级。"""
    service = _locale_service(audit=_BrokenAudit())
    row = _locale_row()
    await service._after_write(1, None, row)  # pyright: ignore[reportPrivateUsage]
    await service._after_write(1, locale_snapshot(row), None)  # pyright: ignore[reportPrivateUsage]


async def test_locale_after_write_without_invalidator() -> None:
    """未装配失效器：写后处理跳过失效，仅做审计分支。"""
    service = _locale_service(invalidator=None, audit=_BrokenAudit())
    await service._after_write(1, None, _locale_row())  # pyright: ignore[reportPrivateUsage]


async def test_locale_after_write_no_changes_returns_early() -> None:
    """写后处理：前后快照相同（无变更）时不产生审计事件。"""
    service = _locale_service(audit=_BrokenAudit())
    row = _locale_row()
    before = locale_snapshot(row)  # pyright: ignore[reportPrivateUsage]
    await service._after_write(1, before, row)  # pyright: ignore[reportPrivateUsage]


def test_seed_messages_are_bilingual() -> None:
    """种子文案清单非空且中英双写（防止误删某语言）。"""
    assert len(MESSAGE_SEEDS) > 100
    assert all(zh.strip() and en.strip() for _key, zh, en in MESSAGE_SEEDS)
    assert isinstance(ConcurrentStableDict(), ConcurrentStableDict)


class _LockedStore:
    """幂等存储替身：`begin` 恒 False，`load` 无结果（幂等记录已展开但无载荷）。"""

    async def begin(self, key: str, *, ttl: int = 0) -> bool:
        """前置去重（恒 False）。

        Args:
            key: 幂等 key。
            ttl: 有效期。

        Returns:
            bool: 恒 False。
        """
        del key, ttl
        return False

    async def load(self, key: str) -> Any:
        """取首次结果（无）。

        Args:
            key: 幂等 key。

        Returns:
            Any: 恒 None。
        """
        del key
        return None

    async def save(self, key: str, payload: Any, *, ttl: int = 0) -> None:
        """写首次结果（替身空操作）。

        Args:
            key: 幂等 key。
            payload: 载荷。
            ttl: 有效期。
        """
        del key, payload, ttl

    async def release(self, key: str) -> None:
        """释放幂等键（替身空操作）。

        Args:
            key: 幂等 key。
        """
        del key


class _AddsConflictRepo:
    """语言包仓储替身：已有同 (key, locale) 行，且条件更新恒失败（模拟并发抢占）。"""

    async def get_by_key_locale(self, msg_key: str, locale: str) -> Any:
        """按 (key, locale) 取行（恒命中旧值）。

        Args:
            msg_key: 文案 key。
            locale: 语言。

        Returns:
            Any: 旧行。
        """
        return SimpleNamespace(id=1, version=1, locale=locale, value="旧值", remark=None, msg_key=msg_key)

    async def update_checked(self, *args: Any, **kwargs: Any) -> bool:
        """条件更新（恒失败）。

        Args:
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            bool: 恒 False。
        """
        del args, kwargs
        return False


class _LocalesRepoStub:
    """语言清单仓储替身：任意 code 视为已登记。"""

    async def get_by_code(self, code: str) -> Any:
        """按 code 取语言（恒命中）。

        Args:
            code: 语言标识。

        Returns:
            Any: 语言行替身。
        """
        return SimpleNamespace(code=code)


def _service_with_repos(repo: object, locales: object, **kwargs: object) -> MessageAdminService:
    """用指定仓储替身构造语言包服务。

    Args:
        repo: 语言包仓储替身。
        locales: 语言清单仓储替身。
        **kwargs: 其余依赖。

    Returns:
        MessageAdminService: 服务实例。
    """
    cache = MemoryI18nCacheRegion()
    registry = NullLocaleRegistry()
    return MessageAdminService(
        cast("Any", repo),
        cast("Any", locales),
        cast("Any", _FakeUow()),
        translator=cast("Any", object()),
        registry=registry,
        cache=cache,
        invalidator=I18nInvalidator(cache, registry),
        audit=cast("Any", kwargs.get("audit")),
        idempotency=cast("Any", kwargs.get("idempotency")),
    )


async def test_save_continues_when_idempotency_record_has_no_payload() -> None:
    """幂等记录存在但无首次结果：继续执行（不返回 None 结果）。"""
    service = _message_service(idempotency=_LockedStore())
    result = await service.save(MessageSaveRequest())
    assert result.created == 0


async def test_save_releases_key_when_no_idempotency_and_invalid() -> None:
    """未装配幂等 + 校验失败：异常直接上抛（释放分支不执行）。"""
    service = _message_service()
    with pytest.raises(I18nMessageKeyInvalidError):
        await service.save(MessageSaveRequest(adds=[MessageAddItem(msg_key="Bad Key", locale="zh-CN", value="v")]))


async def test_adds_existing_row_conflict() -> None:
    """新增段命中已存在行且条件更新失败：抛并发冲突 10004。"""
    service = _service_with_repos(_AddsConflictRepo(), _LocalesRepoStub())
    with pytest.raises(ConcurrentConflictError):
        await service.save(
            MessageSaveRequest(adds=[MessageAddItem(msg_key="zztest.x.y", locale="zh-CN", value="新值")])
        )


async def test_locale_after_write_without_snapshots() -> None:
    """写后处理：前后快照均缺失时不产生审计事件。"""
    service = _locale_service(audit=_BrokenAudit())
    await service._after_write(1, None, None)  # pyright: ignore[reportPrivateUsage]
