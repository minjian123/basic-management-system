"""测试基座护栏（13_10）：收集期模块 loop 标记 / 模块级隔离环境 / 可写租户库夹具。

为什么单列：三者属公共基座（`bms_core/testing/fixtures.py`），只在**服务侧收集钩子**或
**破坏性操作用例**里被触发；bms_core 自身测试目录默认跑不到，模块级覆盖率门禁会判缺。
本文件用直接调用 / 显式启用把这几条路径固定下来。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import bms_core.testing.fixtures as fixtures_module
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing.fixtures import (
    apply_module_loop_scope,
    isolated_env_module,
    needed_shared_databases,
    shared_tenant_writable_db_url,
)

pytestmark = pytest.mark.kiwi_id(2556)


def _scope_item(path: Path, function: Any, fixturenames: ConcurrentStableList[str] | None = None) -> SimpleNamespace:
    """构造收集项替身（`path` / `function` / `fixturenames` / `add_marker`）。

    Args:
        path: 用例文件路径。
        function: 用例函数（同步 / 异步）。
        fixturenames: 该用例引用的夹具名（缺省空）。

    Returns:
        SimpleNamespace: 收集项替身。
    """
    markers: ConcurrentStableList[Any] = ConcurrentStableList()
    return SimpleNamespace(
        path=path,
        function=function,
        fixturenames=fixturenames if fixturenames is not None else ConcurrentStableList[str](),
        markers=markers,
        add_marker=markers.add,
    )


def test_apply_module_loop_scope_only_marks_async_items_under_dir(tmp_path: Path) -> None:
    """只给「目录内的异步用例」加模块级 loop 标记；目录外与同步用例不动。"""

    async def _async() -> None: ...

    def _sync() -> None: ...

    inside = _scope_item(tmp_path / "pkg" / "test_a.py", _async)
    outside = _scope_item(tmp_path.parent / "test_b.py", _async)
    sync_item = _scope_item(tmp_path / "test_c.py", _sync)

    apply_module_loop_scope(ConcurrentStableList([inside, outside, sync_item]), tmp_path)

    assert len(inside.markers) == 1
    assert len(outside.markers) == 0
    assert len(sync_item.markers) == 0


def test_needed_shared_databases_includes_writable_tenant() -> None:
    """收集期按夹具名推导建库清单：引用可写租户库即需 `tenant_writable`。"""
    items = ConcurrentStableList(
        [_scope_item(Path("probe.py"), None, ConcurrentStableList(["shared_tenant_writable_db_url"]))]
    )
    assert list(needed_shared_databases(items)) == ["tenant_writable"]


def test_shared_tenant_writable_db_url_targets_dedicated_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """可写租户库夹具按 `tenant_writable` 取连接串（版本戳取自已注册准备集）。"""
    prepared: ConcurrentStableList[str] = ConcurrentStableList()

    def _require_shared_db(name: str, version: str | None = None) -> str:
        """建库结果替身：记录请求名并返回连接串。"""
        prepared.add(name)
        return f"url:{name}:{version}"

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
        assert os.environ.get("BMS_DATABASE__PLATFORM__URL_TEMPLATE") == ""
        # 夹具期间的**新增** `BMS_*` 变量须在退出时清掉（覆盖清理循环）
        os.environ["BMS_PROBE_EXTRA"] = "1"
    finally:
        next(generator, None)
    assert "BMS_PROBE_EXTRA" not in os.environ
