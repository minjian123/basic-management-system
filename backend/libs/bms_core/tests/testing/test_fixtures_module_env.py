"""测试基座护栏（13_10）：收集期模块 loop 标记 / 模块级隔离环境 / 可写租户库夹具。

为什么单列：三者属公共基座（`bms_core/testing/fixtures.py`），只在**服务侧收集钩子**或
**破坏性操作用例**里被触发；bms_core 自身测试目录默认跑不到，模块级覆盖率门禁会判缺。
本文件用直接调用 / 显式启用把这几条路径固定下来。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import pytest

import bms_core.testing.fixtures as fixtures_module
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.testing.fixtures import (
    apply_module_loop_scope,
    isolated_env_module,
    needed_shared_databases,
    shared_tenant_writable_db_url,
)

pytestmark = pytest.mark.kiwi_id(2556)


class _ScopeItem:
    """收集项替身（只带 `path` / `function` / `fixturenames` / `add_marker`）。"""

    def __init__(self, path: Path, function: Any, fixturenames: ConcurrentStableList[str] | None = None) -> None:
        """初始化。

        Args:
            path: 用例文件路径。
            function: 用例函数（同步 / 异步）。
            fixturenames: 该用例引用的夹具名（缺省空）。
        """
        self.path = path
        self.function = function
        self.fixturenames = fixturenames if fixturenames is not None else ConcurrentStableList[str]()
        self.markers: ConcurrentStableList[Any] = ConcurrentStableList()

    def add_marker(self, marker: Any) -> None:
        """登记标记（记录到 `markers` 供断言）。

        Args:
            marker: pytest 标记。
        """
        self.markers.add(marker)


def _no_prepare(request: object, key: str) -> None:
    """准备集替身：未注册（返回 `None`）。"""
    del request, key


def _module_prepare(key: str) -> object:
    """模块级准备集替身：返回占位对象。"""
    del key
    return object()


def _version_for(prepare: object, packages: object) -> str:
    """版本戳替身：固定值。"""
    del prepare, packages
    return "v1"


def test_apply_module_loop_scope_only_marks_async_items_under_dir(tmp_path: Path) -> None:
    """只给「目录内的异步用例」加模块级 loop 标记；目录外与同步用例不动。"""

    async def _async() -> None: ...

    def _sync() -> None: ...

    inside = _ScopeItem(tmp_path / "pkg" / "test_a.py", _async)
    outside = _ScopeItem(tmp_path.parent / "test_b.py", _async)
    sync_item = _ScopeItem(tmp_path / "test_c.py", _sync)

    apply_module_loop_scope(ConcurrentStableList([inside, outside, sync_item]), tmp_path)

    assert len(inside.markers) == 1
    assert len(outside.markers) == 0
    assert len(sync_item.markers) == 0


def test_needed_shared_databases_includes_writable_tenant() -> None:
    """收集期按夹具名推导建库清单：引用可写租户库即需 `tenant_writable`。"""
    items = ConcurrentStableList(
        [_ScopeItem(Path("probe.py"), None, ConcurrentStableList(["shared_tenant_writable_db_url"]))]
    )
    assert list(needed_shared_databases(items)) == ["tenant_writable"]


def test_shared_tenant_writable_db_url_targets_dedicated_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """可写租户库夹具按 `tenant_writable` 取连接串（版本戳取自已注册准备集）。"""
    prepared: ConcurrentStableList[str] = ConcurrentStableList()

    def _require_shared_db(name: str, version: str | None = None) -> str:
        """建库结果替身：记录请求名并返回连接串。"""
        prepared.add(name)
        return f"url:{name}:{version}"

    monkeypatch.setattr(fixtures_module, "resolve_prepare", cast("Any", _no_prepare))
    monkeypatch.setattr(fixtures_module, "module_prepare", cast("Any", _module_prepare))
    monkeypatch.setattr(fixtures_module, "version_for", cast("Any", _version_for))
    monkeypatch.setattr(fixtures_module, "require_shared_db", cast("Any", _require_shared_db))

    factory = shared_tenant_writable_db_url._fixture_function  # pyright: ignore[reportPrivateUsage]
    result = factory(object())

    assert result == "url:tenant_writable:v1"
    assert list(prepared) == ["tenant_writable"]


def test_module_env_applies_isolated_values() -> None:
    """模块级隔离环境在运行期生效（装配常驻 B1 要求隔离先于装配就位），退出还原。"""
    generator = isolated_env_module._fixture_function()  # pyright: ignore[reportPrivateUsage]
    next(generator)
    try:
        assert os.environ.get("BMS_LOG__LEVEL") == "INFO"
        assert get_settings().log.level.lower() == "info"
    finally:
        next(generator, None)
