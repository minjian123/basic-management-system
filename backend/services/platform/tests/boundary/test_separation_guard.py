"""三权分立机器护栏（Kiwi 2314，`03_02`，需求 07-6）。

四组断言（详细设计 §8.1 用例 7）：

1. **写入口必调护栏且前置**：静态 AST 断言三处 `sys_user_role` 写入口
   （`RoleAssignService.assign_users` / `RoleAssignmentWriter._apply_users` /
   `UserAssignmentWriter._apply_roles`）都调用了 `SeparationGuard` 的校验方法，且调用行号
   **早于**任何分配写入调用（`soft_delete_*` / `restore` / `create`）；
2. **授权入口**：`RoleGrantService.replace_permissions` 调用 `ensure_grant_scope` 且早于
   `delete_by_role`；
3. **内置角色保护**：`RoleService.update_role` / `delete_role` 的 `role_type != ROLE_TYPE_CUSTOM`
   判定保留（`30043`），且 `role_type` 无写入口；
4. **平台超管边界**：`TIER_PLATFORM_ADMIN` 全仓唯一产生点为 `RbacPermissionChecker.aprepare`
   的 `user_id is None` 分支（不经租户 RBAC 计算）；`sys_admin` 登记为平台库 `PLANNED` 且归属
   `identity`、不在任何租户库表清单内。
"""

import ast
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.permission.snapshot import TIER_PLATFORM_ADMIN, TIER_SYSTEM_ADMIN
from bms_core.services.table_registry import TABLE_OWNERSHIP, Datasource

_PLATFORM_SRC = Path(__file__).resolve().parents[2] / "src" / "bms_platform"
_SERVICES = _PLATFORM_SRC / "services"
_API = _PLATFORM_SRC / "api"
_CORE_PERMISSION = Path(__file__).resolve().parents[4] / "libs" / "bms_core" / "src" / "bms_core" / "permission"
"""基座权限能力域（`04_01` 下沉后校验器与引擎的落点）。"""

_GUARD_PREFIX = "ensure_"
"""三权校验方法名前缀（`SeparationGuard.ensure_*`）。"""

_WRITE_CALLS = ("soft_delete_by_user_except", "soft_delete_by_role_except", "restore", "create")
"""分配写入调用名（`sys_user_role` 的实际写入动作）。"""


def _parse(path: Path) -> ast.Module:
    """解析源文件为 AST。

    Args:
        path: 源文件路径。

    Returns:
        ast.Module: 模块节点。
    """
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_function(module: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    """按名取函数节点（类方法亦命中）。

    Args:
        module: 模块 AST。
        name: 函数名。

    Returns:
        ast.FunctionDef | ast.AsyncFunctionDef: 函数节点。
    """
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"未找到函数：{name}")


def _guard_call_lines(function: ast.FunctionDef | ast.AsyncFunctionDef) -> ConcurrentStableList[int]:
    """取函数体内 `SeparationGuard.ensure_*` 调用行号。

    Args:
        function: 函数节点。

    Returns:
        tuple[int, ...]: 调用行号（升序）。
    """
    lines: ConcurrentStableList[int] = ConcurrentStableList()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr.startswith(_GUARD_PREFIX) and "_guard" in ast.unparse(node.func.value):
            lines.add(node.lineno)
    return ConcurrentStableList(sorted(lines))


def _write_call_lines(function: ast.FunctionDef | ast.AsyncFunctionDef) -> ConcurrentStableList[int]:
    """取函数体内分配写入调用行号。

    Args:
        function: 函数节点。

    Returns:
        tuple[int, ...]: 调用行号（升序）。
    """
    lines: ConcurrentStableList[int] = ConcurrentStableList()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in _WRITE_CALLS:
            lines.add(node.lineno)
    return ConcurrentStableList(sorted(lines))


@pytest.mark.kiwi_id(2314)
@pytest.mark.parametrize(
    ("module_name", "function_name"),
    [
        ("role_assign.py", "assign_users"),
        ("role_assignments.py", "_apply_users"),
        ("user_assignments.py", "_apply_roles"),
    ],
)
def test_assignment_entrypoints_call_guard_before_write(module_name: str, function_name: str) -> None:
    """三处分配写入口：均调用三权校验，且调用行号早于任何分配写入调用。"""
    module = _parse(_SERVICES / module_name)
    function = _find_function(module, function_name)

    guard_lines = _guard_call_lines(function)
    write_lines = _write_call_lines(function)

    assert guard_lines, f"{module_name}::{function_name} 未调用 SeparationGuard.ensure_*（三权前置校验缺失）"
    assert write_lines, f"{module_name}::{function_name} 未见分配写入调用（护栏断言失效，请同步 _WRITE_CALLS）"
    assert min(guard_lines) < min(write_lines), (
        f"{module_name}::{function_name} 三权校验晚于写入：guard={min(guard_lines)} write={min(write_lines)}"
    )


@pytest.mark.kiwi_id(2314)
def test_grant_entrypoint_calls_guard_before_delete() -> None:
    """授权入口：`replace_permissions` 调用 `ensure_grant_scope` 且早于 `delete_by_role`。"""
    module = _parse(_SERVICES / "role_grant.py")
    function = _find_function(module, "replace_permissions")

    guard_lines = _guard_call_lines(function)
    delete_lines = [
        node.lineno
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "delete_by_role"
    ]

    assert guard_lines, "replace_permissions 未调用 SeparationGuard.ensure_grant_scope（`role` 归属 / 防自锁缺失）"
    assert delete_lines and min(guard_lines) < min(delete_lines), "三权校验晚于授权写入（先删后插之前必须校验）"


@pytest.mark.kiwi_id(2314)
def test_builtin_role_protection_kept() -> None:
    """内置角色保护保留（`30043`）：角色服务三处 `role_type != ROLE_TYPE_CUSTOM` 判定不缺失。"""
    module = _parse(_SERVICES / "role.py")
    source = ast.unparse(module)

    assert source.count("ROLE_TYPE_CUSTOM") >= 3
    assert "RoleProtectedError" in source
    # `role_type` 无任何写入口（创建恒 custom、更新面不含该字段）
    for function_name in ("create_role", "update_role"):
        function_source = ast.unparse(_find_function(module, function_name))
        assert "role_type=" not in function_source.replace("role_type=ROLE_TYPE_CUSTOM", "")


@pytest.mark.kiwi_id(2314)
def test_platform_tier_has_single_production_point() -> None:
    """平台超管层级唯一产生点：`aprepare` 的 `user_id is None` 分支（不经租户 RBAC 计算）。"""
    hits: ConcurrentStableList[tuple[str, str, int]] = ConcurrentStableList()
    for path in sorted(_CORE_PERMISSION.rglob("*.py")):
        module = _parse(path)
        for node in ast.walk(module):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id != "PermissionSnapshot":
                continue
            if not any(
                keyword.arg == "tier"
                and isinstance(keyword.value, ast.Name)
                and keyword.value.id == "TIER_PLATFORM_ADMIN"
                for keyword in node.keywords
            ):
                continue
            hits.add((path.name, "", node.lineno))
    assert len(hits) == 1, f"TIER_PLATFORM_ADMIN 快照产生点应唯一，实际：{hits}"
    assert hits[0][0] == "rbac.py"

    module = _parse(_CORE_PERMISSION / "rbac.py")
    prepare = _find_function(module, "aprepare")
    prepare_source = ast.unparse(prepare)
    assert "TIER_PLATFORM_ADMIN" in prepare_source
    # 仅在 `user_id is None` 之后产生（有用户上下文的租户请求走租户 RBAC 计算）
    assert prepare_source.index("user_id is None") < prepare_source.index("TIER_PLATFORM_ADMIN")
    assert "PermissionEngine(" in prepare_source

    # 平台服务包内不再自行产生平台层快照（`04_01` 下沉后唯一产生点在基座）
    for path in sorted(_PLATFORM_SRC.rglob("*.py")):
        assert "TIER_PLATFORM_ADMIN" not in path.read_text(encoding="utf-8"), f"平台侧不得再产生平台层快照：{path}"

    assert TIER_PLATFORM_ADMIN != TIER_SYSTEM_ADMIN


@pytest.mark.kiwi_id(2314)
def test_sys_admin_not_in_tenant_tables() -> None:
    """平台超管边界：不采用独立 `sys_admin` 表；平台超管为平台租户 `sys_user` + `platform_admin` 角色类型。"""
    names = {item.table_name for item in TABLE_OWNERSHIP}
    assert "sys_admin" not in names, "`sys_admin` 已改为平台租户账号（不采用独立表）"

    from bms_core.models.platform.role import ROLE_TYPE_PLATFORM_ADMIN, SEPARATION_ROLE_TYPES

    assert ROLE_TYPE_PLATFORM_ADMIN == "platform_admin"
    assert ROLE_TYPE_PLATFORM_ADMIN not in SEPARATION_ROLE_TYPES, "平台超管不参与三权互斥"

    from bms_core.models.tenant.tenant import TENANT_KIND_PLATFORM

    assert TENANT_KIND_PLATFORM == "platform"
    tenant_tables = {item.table_name for item in TABLE_OWNERSHIP if item.datasource is Datasource.TENANT}
    assert "sys_tenant" not in tenant_tables, "平台租户注册表在平台服务库，不在租户库表集"
