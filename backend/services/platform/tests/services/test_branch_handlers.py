"""平台 XA 分支处理器用例（`02_02/_02`）：参数解包 / 处理器登记 / 写入器载荷桥接。

`services/branch_handlers.py` 的两个处理器只做**载荷解包 + 调用已有服务层写入器**（不复制业务逻辑），
故本文件以替身承接写入器、断言解包后的分段入参；参数解包器（整数 / 可选字符串 / 标识集合 / 分段）
单独直测其合法与非法形态（非法一律 10001）。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from fastapi import FastAPI

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_platform.domains.role.services.role_assignments import ROLE_ASSIGNMENTS_OP
from bms_platform.domains.user.services.user_assignments import USER_ASSIGNMENTS_OP
from bms_platform.services import branch_handlers as bh
from bms_platform.services.branch_handlers import (
    BRANCH_OPS,
    _ids_arg,  # pyright: ignore[reportPrivateUsage]
    _int_arg,  # pyright: ignore[reportPrivateUsage]
    _optional_str_arg,  # pyright: ignore[reportPrivateUsage]
    _profile_arg,  # pyright: ignore[reportPrivateUsage]
    _role_profile_arg,  # pyright: ignore[reportPrivateUsage]
    build_branch_handlers,
)


def _args(**values: object) -> ConcurrentStableDict[str, object]:
    """构造分支载荷。

    Args:
        **values: 载荷键值。

    Returns:
        ConcurrentStableDict[str, object]: 分支载荷。
    """
    return ConcurrentStableDict(values)


def test_int_arg_unpacks_int_and_numeric_string() -> None:
    """整数解包：整数与数字字符串皆接受（收敛为 `int`）。"""
    assert _int_arg(_args(user_id=7), "user_id") == 7
    assert _int_arg(_args(user_id="7"), "user_id") == 7


def test_int_arg_rejects_missing_bool_and_non_integer() -> None:
    """整数解包：缺失 / 布尔 / 浮点一律拒（10001）。"""
    with pytest.raises(ParamError):
        _int_arg(_args(), "user_id")
    with pytest.raises(ParamError):
        _int_arg(_args(user_id=True), "user_id")
    with pytest.raises(ParamError):
        _int_arg(_args(user_id=1.5), "user_id")


def test_optional_str_arg_handles_absent_and_rejects_non_string() -> None:
    """可选字符串解包：缺失 → `None`；非字符串拒（10001）。"""
    assert _optional_str_arg(_args(), "name") is None
    assert _optional_str_arg(_args(name="n"), "name") == "n"
    with pytest.raises(ParamError):
        _optional_str_arg(_args(name=1), "name")


def test_ids_arg_handles_absent_and_validates_members() -> None:
    """标识集合解包：缺失 → 空集合；非列表 / 元素非法拒（10001）。"""
    assert list(_ids_arg(_args(), "role_ids")) == []
    assert list(_ids_arg(_args(role_ids=[1, "2"]), "role_ids")) == [1, 2]
    with pytest.raises(ParamError):
        _ids_arg(_args(role_ids="x"), "role_ids")
    with pytest.raises(ParamError):
        _ids_arg(_args(role_ids=[True]), "role_ids")


def test_profile_arg_handles_absent_non_mapping_and_mapping() -> None:
    """基础资料分段解包：缺失 → `None`；非对象拒；对象 → 契约分段。"""
    assert _profile_arg(_args()) is None
    with pytest.raises(ParamError):
        _profile_arg(_args(profile="x"))

    profile = _profile_arg(_args(profile={"name": "昵称", "version": 1}))
    assert profile is not None
    assert profile.name == "昵称"
    assert profile.version == 1
    assert profile.status is None


def test_role_profile_arg_handles_absent_non_mapping_and_mapping() -> None:
    """角色本体分段解包：缺失 → `None`；非对象拒；对象 → 契约分段。"""
    assert _role_profile_arg(_args()) is None
    with pytest.raises(ParamError):
        _role_profile_arg(_args(role="x"))

    profile = _role_profile_arg(_args(role={"code": "ops", "version": 1}))
    assert profile is not None
    assert profile.code == "ops"
    assert profile.version == 1


async def test_user_assignments_handler_bridges_payload(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """用户保存编排处理器：解包分段并交写入器（只做载荷桥接）。"""
    captured: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    class _WriterStub:
        """用户写入器替身（记录分段入参）。"""

        def __init__(self, *args: object) -> None:
            del args

        async def write(self, *, user_id: int, profile: object, role_ids: object) -> None:
            """记录一次写入调用。"""
            entry: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            entry.set("user_id", user_id)
            entry.set("profile", profile)
            entry.set("role_ids", role_ids)
            captured.add(entry)

    monkeypatch.setattr(bh, "UserAssignmentWriter", _WriterStub)
    registry = build_branch_handlers(service_app)
    # 07B 02_03：同一注册表另登记 9 个**种子**分支 op（种子编排与业务编排共用注册通道），
    # 故此处断言「业务 op 属于已登记集合」，而非全等。
    assert set(BRANCH_OPS) <= set(registry.ops())
    handler = registry.resolve(USER_ASSIGNMENTS_OP)
    assert handler is not None

    await handler(
        cast("Any", object()),
        _args(user_id=7, profile={"name": "昵称", "version": 1}, role_ids=[11, 12]),
    )

    assert len(captured) == 1
    entry = captured[0]
    assert entry.get("user_id") == 7
    assert entry.get("role_ids") == [11, 12]
    profile = entry.get("profile")
    assert profile is not None


async def test_role_assignments_handler_skips_absent_segments(
    service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """角色保存编排处理器：缺省分段保持 `None`（不改），只透传角色本体。"""
    captured: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    class _WriterStub:
        """角色写入器替身（记录分段入参）。"""

        def __init__(self, *args: object) -> None:
            del args

        async def write(self, *, role_id: int, profile: object, user_ids: object) -> None:
            """记录一次写入调用。"""
            entry: ConcurrentStableDict[str, object] = ConcurrentStableDict()
            entry.set("role_id", role_id)
            entry.set("profile", profile)
            entry.set("user_ids", user_ids)
            captured.add(entry)

    def _writer_factory(**kwargs: object) -> _WriterStub:
        """写入器工厂替身（忽略参数）。

        Args:
            **kwargs: 关键字参数。

        Returns:
            _WriterStub: 替身写入器。
        """
        del kwargs
        return _WriterStub()

    monkeypatch.setattr(bh, "role_assignment_writer", _writer_factory)
    registry = build_branch_handlers(service_app)
    handler = registry.resolve(ROLE_ASSIGNMENTS_OP)
    assert handler is not None

    await handler(cast("Any", object()), _args(role_id=5, role={"code": "ops", "version": 1}))

    assert len(captured) == 1
    entry = captured[0]
    assert entry.get("role_id") == 5
    assert entry.get("user_ids") is None
    assert entry.get("profile") is not None
