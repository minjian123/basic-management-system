"""达梦客户端通信加密模块加载路径单元用例（需求 05-5；Kiwi 2271）。

覆盖：目录定位（包形态 / 命名空间形态 / 未安装）、平台自适应（Windows 运行期修复 / POSIX 自检）、
幂等与边界、修复文案，以及**引擎工厂建连前自检接线**（达梦同步引擎触发、非达梦不触发）。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.db import engine as engine_module
from bms_core.db.dialects import dm_ssl
from bms_core.db.dialects.dm_ssl import (
    DM_SSL_MISSING,
    DM_SSL_OK,
    DM_SSL_UNAVAILABLE,
    dm_ssl_dir,
    dm_ssl_hint,
    ensure_dm_ssl_module,
)
from bms_core.db.engine import EngineFactory, _ensure_dm_ssl  # pyright: ignore[reportPrivateUsage]

pytestmark = [pytest.mark.kiwi_id(2271)]


def _patch_find_spec(monkeypatch: pytest.MonkeyPatch, spec: Any) -> None:
    """把 `dm_ssl` 内的 `importlib.util.find_spec` 换成固定返回值的替身（不导入真实模块）。"""

    def _find_spec(_name: str) -> Any:
        return spec

    monkeypatch.setattr(dm_ssl, "importlib", SimpleNamespace(util=SimpleNamespace(find_spec=_find_spec)))


def test_dm_ssl_dir_from_package_origin(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Windows 轮子形态：`dmssl` 为常规包 ⇒ 由 `spec.origin` 的父目录定位。"""
    origin = tmp_path / "dmssl" / "__init__.py"
    _patch_find_spec(monkeypatch, SimpleNamespace(origin=str(origin), submodule_search_locations=None))
    assert dm_ssl_dir() == tmp_path / "dmssl"


def test_dm_ssl_dir_from_namespace_locations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """POSIX 轮子形态：`dmssl` 为命名空间目录 ⇒ 由 `spec.submodule_search_locations` 定位。"""
    directory = tmp_path / "dmssl"
    _patch_find_spec(monkeypatch, SimpleNamespace(origin=None, submodule_search_locations=[str(directory)]))
    assert dm_ssl_dir() == directory


def test_dm_ssl_dir_absent_or_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """未安装 `dmPython`（spec 为 None）与布局异常（无目录项）均返回 None。"""
    _patch_find_spec(monkeypatch, None)
    assert dm_ssl_dir() is None
    _patch_find_spec(monkeypatch, SimpleNamespace(origin=None, submodule_search_locations=[]))
    assert dm_ssl_dir() is None


def test_dm_ssl_dir_real_installation() -> None:
    """本仓后端依赖已装 `dmpython` ⇒ 真实定位到存在的 `dmssl` 目录（两种轮子形态同口径）。"""
    directory = dm_ssl_dir()
    assert directory is not None
    assert directory.is_dir()
    assert directory.name == dm_ssl.DM_SSL_MODULE


def test_search_path_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    """路径环境变量名按平台取值：Windows `PATH` / POSIX `LD_LIBRARY_PATH`。"""
    monkeypatch.setattr(dm_ssl, "_WINDOWS", True)
    assert dm_ssl._search_path_env() == "PATH"  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setattr(dm_ssl, "_WINDOWS", False)
    assert dm_ssl._search_path_env() == "LD_LIBRARY_PATH"  # pyright: ignore[reportPrivateUsage]


def test_on_search_path_semantics(tmp_path: Path) -> None:
    """条目判定：空值 / 空串为假、命中为真、未命中为假、空条目忽略。"""
    directory = tmp_path / "dmssl"
    on_search_path = dm_ssl._on_search_path  # pyright: ignore[reportPrivateUsage]
    assert on_search_path(directory, None) is False
    assert on_search_path(directory, "") is False
    assert on_search_path(directory, f"{tmp_path}{os.pathsep}/usr/bin") is False
    assert on_search_path(directory, f"{os.pathsep}{directory}{os.pathsep}") is True


def test_ensure_windows_prepends_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Windows：未在路径内即前置 `PATH`（幂等，第二次不重复前置）。"""
    directory = tmp_path / "dmssl"
    monkeypatch.setattr(dm_ssl, "_WINDOWS", True)
    monkeypatch.setattr(dm_ssl, "dm_ssl_dir", lambda: directory)
    monkeypatch.setenv("PATH", "/usr/bin")
    assert ensure_dm_ssl_module() == DM_SSL_OK
    assert os.environ["PATH"].startswith(f"{directory}{os.pathsep}")
    assert ensure_dm_ssl_module() == DM_SSL_OK
    assert os.environ["PATH"].split(os.pathsep).count(str(directory)) == 1


def test_ensure_windows_keeps_existing_entry(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Windows：已在路径内 ⇒ 原样返回（不重复前置）。"""
    directory = tmp_path / "dmssl"
    monkeypatch.setattr(dm_ssl, "_WINDOWS", True)
    monkeypatch.setattr(dm_ssl, "dm_ssl_dir", lambda: directory)
    monkeypatch.setenv("PATH", f"{directory}{os.pathsep}/usr/bin")
    assert ensure_dm_ssl_module() == DM_SSL_OK
    assert os.environ["PATH"] == f"{directory}{os.pathsep}/usr/bin"


def test_ensure_posix_reports_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """POSIX：未注入 `LD_LIBRARY_PATH` ⇒ `missing`（运行期无法修复）；已注入 ⇒ `ok`。"""
    directory = tmp_path / "dmssl"
    monkeypatch.setattr(dm_ssl, "_WINDOWS", False)
    monkeypatch.setattr(dm_ssl, "dm_ssl_dir", lambda: directory)
    monkeypatch.delenv("LD_LIBRARY_PATH", raising=False)
    assert ensure_dm_ssl_module() == DM_SSL_MISSING
    monkeypatch.setenv("LD_LIBRARY_PATH", f"/opt/lib{os.pathsep}{directory}")
    assert ensure_dm_ssl_module() == DM_SSL_OK


def test_ensure_unavailable_without_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """未定位到目录 ⇒ `unavailable`（非达梦环境不误报）。"""
    monkeypatch.setattr(dm_ssl, "dm_ssl_dir", lambda: None)
    assert ensure_dm_ssl_module() == DM_SSL_UNAVAILABLE


def test_hint_text(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """修复文案：给定目录时含该目录与启动前注入口径；未定位时给占位目录。"""
    directory = tmp_path / "dmssl"
    text = dm_ssl_hint(directory)
    assert str(directory) in text
    assert "LD_LIBRARY_PATH" in text
    assert "达梦环境.sh" in text
    monkeypatch.setattr(dm_ssl, "dm_ssl_dir", lambda: None)
    assert "<site-packages>/dmssl" in dm_ssl_hint()


def test_engine_hook_warns_only_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """引擎工厂自检接线：`missing` 触发告警文案（不抛错）；`ok` 不取文案。"""
    steps: ConcurrentStableList[str] = ConcurrentStableList()

    def _fake_state() -> str:
        steps.add("ensure")
        return DM_SSL_MISSING

    def _fake_hint(*args: object, **kwargs: object) -> str:
        steps.add("hint")
        return "HINT"

    monkeypatch.setattr(engine_module, "ensure_dm_ssl_module", _fake_state)
    monkeypatch.setattr(engine_module, "dm_ssl_hint", _fake_hint)
    _ensure_dm_ssl("dmxa")
    assert list(steps) == ["ensure", "hint"]

    monkeypatch.setattr(engine_module, "ensure_dm_ssl_module", lambda: DM_SSL_OK)
    _ensure_dm_ssl("dm")
    assert list(steps) == ["ensure", "hint"]


def test_create_sync_checks_dm_ssl_for_dm_dialect(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_sync` 对达梦方言触发自检（`dm` 连接串归一为 `dmxa`）；非同步方言不触发。"""
    seen: ConcurrentStableList[str] = ConcurrentStableList()

    def _record(dialect: str) -> None:
        seen.add(dialect)

    monkeypatch.setattr(engine_module, "_ensure_dm_ssl", _record)

    settings = Settings()
    settings.database.platform.url = "dm+dmPython://SYSDBA:pwd@127.0.0.1:5236"
    dm_engine = EngineFactory(settings).create_sync()
    try:
        assert dm_engine.dialect.name == "dmxa"
        assert list(seen) == ["dmxa"]
    finally:
        dm_engine.dispose()

    sqlite_settings = Settings()
    sqlite_settings.database.platform.url = "sqlite+aiosqlite:///:memory:"
    sqlite_engine = EngineFactory(sqlite_settings).create_sync()
    try:
        assert sqlite_engine.dialect.name == "sqlite"
        assert list(seen) == ["dmxa"]
    finally:
        sqlite_engine.dispose()
