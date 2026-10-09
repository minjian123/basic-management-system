"""平台服务 **XA 分支处理器**（跨服务强一致参与方；子任务 `02_02/_02`）。

把分支 `op` 映射到本服务**已有服务层**（`UserAssignmentWriter`，**不复制业务逻辑**），由基座分支
执行器在**已开启的两阶段分支事务**的连接上调用：

- 执行器传入的 `session` 绑定该分支连接 ⇒ 写入器内 `UnitOfWork.begin()` 收敛为 **SAVEPOINT**，
  外层 XA 分支保持打开、仍可 `prepare`；
- 参数解包失败一律 `ParamError`（10001）——分支载荷由调用方（编排）生成，非法即拒；
- 未登记的 `op` 由执行器返回 `rejected`（不静默成功）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import ParamError
from bms_core.core.plugin import resolve_plugin
from bms_core.db.session import DbSession
from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.outbox.base import BaseOutboxStore
from bms_core.transaction.base import BranchHandlerRegistry
from bms_platform.repositories.role import RoleRepository, UserRoleRepository
from bms_platform.repositories.user import UserRepository
from bms_platform.schemas.users import UserAssignmentProfile
from bms_platform.services.user_assignments import USER_ASSIGNMENTS_OP, UserAssignmentWriter

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["BRANCH_OPS", "build_branch_handlers"]

BRANCH_OPS = (USER_ASSIGNMENTS_OP,)
"""本服务登记的全部分支操作名（顺序稳定，供用例断言）。"""


def _int_arg(args: ConcurrentStableDict[str, object], key: str) -> int:
    """解包整数参数（缺失 / 类型非法即拒）。

    Args:
        args: 分支载荷。
        key: 参数名。

    Returns:
        int: 参数值。

    Raises:
        ParamError: 缺失 / 非整数（10001）。
    """
    value = args.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ParamError(f"分支参数非法：{key}")
    return int(value)


def _optional_str_arg(args: ConcurrentStableDict[str, object], key: str) -> str | None:
    """解包可选字符串参数（缺失 / `None` → `None`；类型非法即拒）。

    Args:
        args: 分支载荷。
        key: 参数名。

    Returns:
        str | None: 参数值。

    Raises:
        ParamError: 类型非法（10001）。
    """
    value = args.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ParamError(f"分支参数非法：{key}")
    return value


def _ids_arg(args: ConcurrentStableDict[str, object], key: str) -> ConcurrentStableList[int]:
    """解包标识集合参数（缺失 → 空集合；非集合 / 元素非法即拒）。

    Args:
        args: 分支载荷。
        key: 参数名。

    Returns:
        ConcurrentStableList[int]: 标识集合。

    Raises:
        ParamError: 非集合或元素非法（10001）。
    """
    value = args.get(key)
    if value is None:
        return ConcurrentStableList()
    if not isinstance(value, list):
        raise ParamError(f"分支参数非法：{key}")
    items: ConcurrentStableList[int] = ConcurrentStableList()
    for item in cast("list[object]", value):
        if isinstance(item, bool) or not isinstance(item, (int, str)):
            raise ParamError(f"分支参数非法：{key} 元素")
        items.add(int(item))
    return items


def _profile_arg(args: ConcurrentStableDict[str, object]) -> UserAssignmentProfile | None:
    """解包基础资料分段（缺失 → `None` = 不改）。

    Args:
        args: 分支载荷。

    Returns:
        UserAssignmentProfile | None: 基础资料分段。

    Raises:
        ParamError: 载荷形态非法（10001）。
    """
    value = args.get("profile")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ParamError("分支参数非法：profile")
    raw = cast("dict[str, object]", value)
    status = _optional_str_arg(cast("ConcurrentStableDict[str, object]", raw), "status")
    version = _int_arg(cast("ConcurrentStableDict[str, object]", raw), "version")
    return UserAssignmentProfile(
        name=_optional_str_arg(cast("ConcurrentStableDict[str, object]", raw), "name"),
        email=_optional_str_arg(cast("ConcurrentStableDict[str, object]", raw), "email"),
        phone=_optional_str_arg(cast("ConcurrentStableDict[str, object]", raw), "phone"),
        status=cast("object", status),  # type: ignore[arg-type] - 取值由 pydantic 复核
        version=version,
    )


def _outbox_of(app: FastAPI) -> BaseOutboxStore:
    """取应用装配的发件箱存储（与 `get_outbox_store` 同源解析）。

    Args:
        app: 应用实例。

    Returns:
        BaseOutboxStore: 发件箱存储。
    """
    settings = cast("Settings", app.state.settings)
    return cast(
        "BaseOutboxStore",
        resolve_plugin(
            "outbox_store", settings.outbox_store.provider, expected_version=BaseOutboxStore.contract_version
        ),
    )


def build_branch_handlers(app: FastAPI) -> BranchHandlerRegistry:
    """构造并登记本服务的分支处理器（**只调已有服务层**）。

    Args:
        app: 应用实例（取发件箱存储；分支事务由执行器持有）。

    Returns:
        BranchHandlerRegistry: 分支处理器注册表。
    """

    async def apply_user_assignments(session: DbSession, args: ConcurrentStableDict[str, object]) -> None:
        """用户保存编排：platform 侧分段写入（基础资料 + 角色全量覆盖）。"""
        user_id = _int_arg(args, "user_id")
        profile = _profile_arg(args)
        role_ids = _ids_arg(args, "role_ids") if args.get("role_ids") is not None else None
        writer = UserAssignmentWriter(
            session,
            DbUnitOfWork(session),
            UserRepository(session),
            UserRoleRepository(session),
            RoleRepository(session),
            _outbox_of(app),
        )
        await writer.write(user_id=user_id, profile=profile, role_ids=role_ids)

    registry = BranchHandlerRegistry()
    registry.register(USER_ASSIGNMENTS_OP, apply_user_assignments)
    return registry
