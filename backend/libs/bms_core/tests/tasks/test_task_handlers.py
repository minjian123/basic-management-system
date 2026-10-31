"""handler 白名单护栏：注册表 / 格式 / 前缀边界 / 解析失败分支。"""

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import TaskHandlerNotRegisteredError
from bms_core.tasks.builtin import run_cleanup_orphan_parts
from bms_core.tasks.handlers import builtin_handlers, is_allowed_handler, resolve_handler

pytestmark = pytest.mark.kiwi_id(2371)

_PREFIXES: ConcurrentStableList[str] = ConcurrentStableList(["bms_core.tasks.builtin"])


def test_builtin_handlers_covers_four_tasks() -> None:
    """注册表四条，路径均为 `module:attr`。"""
    registry = builtin_handlers()
    assert isinstance(registry, ConcurrentStableDict)
    assert set(registry) == {
        "cleanup_orphan_parts",
        "archive_audit_logs",
        "precreate_shard_tables",
        "purge_soft_deleted",
    }
    for path in registry.values():
        assert path.startswith("bms_core.tasks.builtin:")
        assert is_allowed_handler(path, _PREFIXES) is True


def test_is_allowed_handler_prefix_boundary() -> None:
    """前缀按「等于或以点续接」判定，`builtinx` 这类撞名不得放行。"""
    assert is_allowed_handler("bms_core.tasks.builtin:run_x", _PREFIXES) is True
    assert is_allowed_handler("bms_core.tasks.builtinx:run_x", _PREFIXES) is False
    assert is_allowed_handler("bms_core:tasks.builtin", _PREFIXES) is False


@pytest.mark.parametrize("path", ["nocolon", ":attr", "module:", "module:attr:extra", "mod ule:attr"])
def test_is_allowed_handler_rejects_malformed(path: str) -> None:
    """格式非法直接 False（不抛错，供接口层做布尔校验）。"""
    assert is_allowed_handler(path, _PREFIXES) is False


def test_resolve_handler_returns_callable() -> None:
    """白名单内路径解析为真实可调用对象。"""
    resolved = resolve_handler("bms_core.tasks.builtin:run_cleanup_orphan_parts", _PREFIXES)
    assert resolved is run_cleanup_orphan_parts


def test_resolve_handler_rejects_outside_whitelist() -> None:
    """白名单外路径拒绝（`70003`），不导入。"""
    with pytest.raises(TaskHandlerNotRegisteredError):
        resolve_handler("os.system:run", _PREFIXES)


def test_resolve_handler_rejects_unimportable_module() -> None:
    """前缀合法但模块不存在：导入失败转 `70003`。"""
    with pytest.raises(TaskHandlerNotRegisteredError):
        resolve_handler("bms_core.tasks.builtin.not_exist:run", _PREFIXES)


def test_resolve_handler_rejects_missing_attribute() -> None:
    """模块在、属性缺失：转 `70003`。"""
    with pytest.raises(TaskHandlerNotRegisteredError):
        resolve_handler("bms_core.tasks.builtin:not_a_handler", _PREFIXES)
