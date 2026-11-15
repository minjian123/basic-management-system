"""用例级写锁声明与持锁口径用例（Kiwi 2508）：声明去重 / 整条用例锁 / 插件取放锁。

口径见《测试规范》§2.1.6 第 9 条与 `bms_core.testing.write_locks` 模块文档。
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import plugin, write_locks

pytestmark = pytest.mark.kiwi_id(2508)


class _Node:
    """用例节点替身（只承载写锁声明属性）。"""


class _Item:
    """用例替身（插件钩子只读声明清单）。"""

    def __init__(self) -> None:
        """初始化空声明清单。"""
        self.node = _Node()


def test_declare_appends_and_dedupes() -> None:
    """声明只追加未登记过的锁名（重复声明不产生重复项）。"""
    item = cast("Any", _Item())

    write_locks.declare(item, write_locks.PLATFORM_WRITE_LOCK)
    write_locks.declare(item, write_locks.PLATFORM_WRITE_LOCK, write_locks.TENANT_WRITE_LOCK)

    assert list(write_locks.declared_locks(item.node)) == [
        write_locks.PLATFORM_WRITE_LOCK,
        write_locks.TENANT_WRITE_LOCK,
    ]


def test_declared_locks_is_stable_per_node() -> None:
    """同一节点多次读取返回同一清单（就地可变，不重复建）。"""
    node = cast("Any", _Node())

    first = write_locks.declared_locks(node)
    second = write_locks.declared_locks(node)

    assert first is second
    assert list(first) == []


def test_declaration_fixtures_register_their_lock(request: pytest.FixtureRequest) -> None:
    """`platform_db_write` / `tenant_db_write` 只做声明（按库登记锁名）。"""
    request.getfixturevalue("platform_db_write")
    request.getfixturevalue("tenant_db_write")

    assert list(write_locks.declared_locks(cast("Any", request).node)) == [
        write_locks.PLATFORM_WRITE_LOCK,
        write_locks.TENANT_WRITE_LOCK,
    ]


def test_platform_whole_lifecycle_fixture_takes_real_lock(request: pytest.FixtureRequest) -> None:
    """整条用例口径的平台库夹具真实持锁，取放均不阻塞。"""
    request.getfixturevalue("platform_db_write_whole")


def test_tenant_whole_lifecycle_fixture_takes_real_lock(request: pytest.FixtureRequest) -> None:
    """整条用例口径的租户库夹具真实持锁，取放均不阻塞。"""
    request.getfixturevalue("tenant_db_write_whole")


def test_serial_db_write_takes_both_locks(request: pytest.FixtureRequest) -> None:
    """保守出口同时持两把写锁（固定「平台 → 租户」顺序，避免死锁）。"""
    request.getfixturevalue("serial_db_write")


def test_runtest_call_acquires_declared_locks(monkeypatch: pytest.MonkeyPatch) -> None:
    """插件在用例调用阶段按声明取锁，结束后释放（顺序与声明一致）。"""
    events: ConcurrentStableList[str] = ConcurrentStableList()

    @contextmanager
    def _fake_lock(name: str, *, timeout: float | None = None) -> Generator[None]:
        del timeout
        events.append(f"acquire:{name}")
        try:
            yield
        finally:
            events.append(f"release:{name}")

    monkeypatch.setattr(plugin.write_locks, "file_lock", _fake_lock)
    item = cast("Any", _Item())
    write_locks.declared_locks(item).append(write_locks.TENANT_WRITE_LOCK)

    generator = plugin.pytest_runtest_call(item)
    next(generator)
    assert events == [f"acquire:{write_locks.TENANT_WRITE_LOCK}"]
    with pytest.raises(StopIteration):
        next(generator)
    assert events == [
        f"acquire:{write_locks.TENANT_WRITE_LOCK}",
        f"release:{write_locks.TENANT_WRITE_LOCK}",
    ]


def test_runtest_call_skips_without_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    """未声明写锁的用例不取锁（钩子直接放行）。"""
    events: ConcurrentStableList[str] = ConcurrentStableList()

    @contextmanager
    def _fake_lock(name: str, *, timeout: float | None = None) -> Generator[None]:
        del timeout
        events.append(name)
        yield

    monkeypatch.setattr(plugin.write_locks, "file_lock", _fake_lock)
    item = cast("Any", _Item())

    generator = plugin.pytest_runtest_call(item)
    next(generator)
    with pytest.raises(StopIteration):
        next(generator)
    assert events == []
