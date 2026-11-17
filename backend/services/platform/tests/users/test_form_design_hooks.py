"""用户域接入表单定制（Kiwi 2526）：写前动态校验拒收 / 放行、导入列无解析回调时回退基线列集。

补齐两条经 HTTP 不便构造的路径：`UserAdminService` 携带校验器时的「校验失败即拒」与
「校验通过放行」，以及 `derive_user_import_columns` 在未登记布局列解析回调时的基线回退。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.formdesign import import_columns
from bms_core.formdesign.validator import FieldError, ValidationResult
from bms_core.outbox.null import NullOutboxStore
from bms_core.password.base import BasePasswordPolicy
from bms_core.security.base import BasePasswordHasher
from bms_core.transfer.base import ColumnSpec
from bms_platform.domains.user.imports import derive_user_import_columns
from bms_platform.domains.user.repositories.account_lock import AccountLockRepository
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.user_sessions import UserSessionClient
from bms_platform.domains.user.services.users_admin import UserAdminService
from bms_platform.wiring import role_assignment, role_query
from tests.role import helpers

pytestmark = pytest.mark.kiwi_id(2526)


class _StubValidator:
    """表单动态校验替身（按构造时的错误清单返回结果）。"""

    def __init__(self, errors: ConcurrentStableFrozenList[FieldError]) -> None:
        """初始化。

        Args:
            errors: 校验错误清单。
        """
        self._errors = errors

    async def validate(self, form_code: str, values: ConcurrentStableDict[str, object], **kwargs: Any) -> Any:
        """返回预设结果（入参忽略）。

        Args:
            form_code: 表单标识（忽略）。
            values: 待校验值（忽略）。
            kwargs: 其余关键字（忽略）。

        Returns:
            ValidationResult: 预设结果。
        """
        del form_code, values, kwargs
        return ValidationResult(errors=self._errors)


class _Hasher:
    """口令哈希器替身（回显可辨串）。"""

    def hash(self, password: str) -> str:
        """生成可辨哈希串。

        Args:
            password: 口令明文。

        Returns:
            str: 可辨哈希串。
        """
        return f"hash:{password}"

    def verify(self, password: str, hashed: str) -> bool:
        """恒定通过。

        Args:
            password: 口令明文（忽略）。
            hashed: 哈希串（忽略）。

        Returns:
            bool: True。
        """
        del password, hashed
        return True


class _Policy:
    """密码策略替身（恒定通过）。"""

    async def validate(self, password: str, *, username: str) -> ConcurrentStableList[str]:
        """恒定无违规。

        Args:
            password: 口令明文（忽略）。
            username: 登录账号（忽略）。

        Returns:
            ConcurrentStableList[str]: 空清单。
        """
        del password, username
        return ConcurrentStableList()


class _Sessions:
    """会话失效客户端替身（无操作）。"""

    async def revoke_all(self, user_id: int, reason: str) -> bool:
        """撤销会话（替身不做事）。

        Args:
            user_id: 用户主键（忽略）。
            reason: 撤销原因（忽略）。

        Returns:
            bool: True。
        """
        del user_id, reason
        return True


def _service(target: AsyncSession, *, validator: Any) -> UserAdminService:
    """构造带校验器的用户完整域服务（哈希器 / 策略 / 会话客户端全替换身）。

    Args:
        target: 会话。
        validator: 表单动态校验替身。

    Returns:
        UserAdminService: 用户完整域服务。
    """
    return UserAdminService(
        target,
        DbUnitOfWork(target),
        UserRepository(target),
        role_assignment(target),
        role_query(target),
        AccountLockRepository(target),
        cast("BasePasswordHasher", _Hasher()),
        cast("BasePasswordPolicy", _Policy()),
        NullOutboxStore(),
        cast("UserSessionClient", _Sessions()),
        validator,
    )


async def test_create_user_rejects_when_dynamic_validation_fails() -> None:
    """动态校验失败 → 10001 且带字段级明细（不落库）。"""
    target, engine = await helpers.session()
    try:
        service = _service(
            target,
            validator=_StubValidator(ConcurrentStableFrozenList((FieldError(field_key="phone", rule="pattern"),))),
        )
        with pytest.raises(ParamError) as excinfo:
            await service.create_user(
                username="dv1",
                name="校验一",
                password="Abcd1234!x",
                pwd_reset_required=False,
                email=None,
                phone="13800000000",
                status="enabled",
            )
        payload = excinfo.value.data
        assert isinstance(payload, ConcurrentStableDict)
        details = cast("ConcurrentStableList[ConcurrentStableDict[str, object]]", payload["errors"])
        assert details[0]["field_key"] == "phone"
        assert details[0]["rule"] == "pattern"
    finally:
        await engine.dispose()


async def test_create_user_passes_dynamic_validation() -> None:
    """动态校验通过 → 正常建用户。"""
    target, engine = await helpers.session()
    try:
        service = _service(target, validator=_StubValidator(ConcurrentStableFrozenList(())))
        user, _generated = await service.create_user(
            username="dv2",
            name="校验二",
            password="Abcd1234!x",
            pwd_reset_required=False,
            email=None,
            phone=None,
            status="enabled",
        )
        assert user.username == "dv2"
    finally:
        await engine.dispose()


async def test_derive_user_import_columns_without_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """未登记布局列解析回调时回退基线列集（导入模板列不变）。"""
    base: ConcurrentStableFrozenList[ColumnSpec] = ConcurrentStableFrozenList(
        (ColumnSpec(key="username", title="登录账号", required=True),)
    )
    monkeypatch.setattr(import_columns, "_RESOLVER", ConcurrentStableList())
    target, engine = await helpers.session()
    try:
        derived = await derive_user_import_columns(target, base=base)
    finally:
        await engine.dispose()
    assert [spec.key for spec in derived] == ["username"]
