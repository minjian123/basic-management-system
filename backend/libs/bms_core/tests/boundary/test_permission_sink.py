"""权限下沉边界护栏（Kiwi 2320，`04_01`，需求 07-16）。

三组断言（详细设计 §7 验收映射）：

1. **基座不依赖服务包**：`bms_core/permission/**` 与 `bms_core/scope/**` 的 import 不得出现任何
   `bms_<服务>` 包（platform / identity / tenant / file / txn / ai / report / search / notification）；
2. **基座不碰 ORM**：同上目录不得 import `models` / `repositories`（模型与仓储留服务侧）；
3. **下沉件落点固定**：引擎 / 接缝 / 校验器 / 四策略在基座、platform 侧只留取数与装配，
   且 `services/table_registry.py` 不含本任务新增表（表归属零变更）。
"""

import ast
from pathlib import Path

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.services.table_registry import TABLE_OWNERSHIP

_BACKEND = Path(__file__).resolve().parents[4]
_CORE = _BACKEND / "libs" / "bms_core" / "src" / "bms_core"
_CORE_PERMISSION = _CORE / "permission"
_CORE_SCOPE = _CORE / "scope"
_PLATFORM = _BACKEND / "services" / "platform" / "src" / "bms_platform"

_SERVICE_PACKAGES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "bms_platform",
        "bms_identity",
        "bms_tenant",
        "bms_file",
        "bms_txn",
        "bms_ai",
        "bms_report",
        "bms_search",
        "bms_notification",
    )
)
"""服务包前缀（基座不得 import 任一）。"""

_FORBIDDEN_MODULE_SEGMENTS: ConcurrentStableList[str] = ConcurrentStableList(("models", "repositories"))
"""ORM 层模块段（基座不得 import）。"""

_SUNK_MODULES: ConcurrentStableList[str] = ConcurrentStableList(
    (
        "permission/engine.py",
        "permission/sources.py",
        "permission/subject.py",
        "permission/rbac.py",
        "scope/policies_rbac.py",
        "scope/rbac.py",
    )
)
"""下沉到基座的模块（存在性断言）。"""


def _imports(path: Path) -> ConcurrentStableList[str]:
    """收集模块的全部 import 目标（含 `from x import y` 的模块部分）。

    Args:
        path: 源文件路径。

    Returns:
        ConcurrentStableList[str]: import 目标字符串。
    """
    module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: ConcurrentStableList[str] = ConcurrentStableList()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


@pytest.mark.kiwi_id(2320)
def test_core_permission_and_scope_do_not_import_service_packages() -> None:
    """基座权限 / 数据范围不得 import 任何服务包（「服务不得互相 import」的反向约束）。"""
    violations: ConcurrentStableList[str] = ConcurrentStableList()
    for base in (_CORE_PERMISSION, _CORE_SCOPE):
        for path in sorted(base.rglob("*.py")):
            for target in _imports(path):
                root = target.split(".")[0]
                if root in _SERVICE_PACKAGES:
                    violations.add(f"{path.relative_to(_BACKEND)} → {target}")
    assert list(violations) == [], f"基座权限域不得依赖服务包：{list(violations)}"


@pytest.mark.kiwi_id(2320)
def test_core_permission_and_scope_do_not_import_orm_layers() -> None:
    """基座权限 / 数据范围不得 import `models` / `repositories`（数据访问留服务侧）。"""
    violations: ConcurrentStableList[str] = ConcurrentStableList()
    for base in (_CORE_PERMISSION, _CORE_SCOPE):
        for path in sorted(base.rglob("*.py")):
            for target in _imports(path):
                segments = target.split(".")
                if any(segment in _FORBIDDEN_MODULE_SEGMENTS for segment in segments):
                    violations.add(f"{path.relative_to(_BACKEND)} → {target}")
    assert list(violations) == [], f"基座权限域不得依赖 ORM 层：{list(violations)}"


@pytest.mark.kiwi_id(2320)
def test_sunk_modules_exist_in_core() -> None:
    """下沉件落点：引擎 / 接缝 / 主体链 / 校验器 / 四策略 / 数据范围 provider 均在基座。"""
    missing = [name for name in _SUNK_MODULES if not (_CORE / name).is_file()]
    assert missing == [], f"下沉模块缺失：{missing}"


@pytest.mark.kiwi_id(2320)
def test_platform_side_keeps_only_source_and_wiring() -> None:
    """平台侧只留取数与装配：引擎 / 校验器 / 四策略实现文件已移出服务包。"""
    removed = (
        "services/permission.py",
        "scope/policies.py",
        "scope/rbac.py",
    )
    still_there = [name for name in removed if (_PLATFORM / name).is_file()]
    assert still_there == [], f"已下沉模块仍留在服务包：{still_there}"
    assert (_PLATFORM / "domains" / "permission_meta" / "permission" / "source.py").is_file(), "平台侧缺少数据来源实现"


@pytest.mark.kiwi_id(2320)
def test_table_ownership_unchanged_by_sinking() -> None:
    """表归属零变更：权限相关表仍归 platform（代码下沉不改归属）。"""
    owners = {item.table_name: item.owner for item in TABLE_OWNERSHIP}
    for table in ("sys_role", "sys_user_role", "sys_role_permission", "sys_role_field", "sys_data_scope"):
        assert owners.get(table) == "platform", f"{table} 归属应为 platform，实际：{owners.get(table)}"
