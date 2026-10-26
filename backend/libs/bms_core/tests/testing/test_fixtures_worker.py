"""并行 worker 的 SQLite 目录隔离（Kiwi 2359）：串行不介入、并行按 worker 建目录。

口径：SQLite 文件库在并行 worker 间共享同一路径会互相看到对方写入的行；隔离目录由
`worker_sqlite_dir()` 按 `PYTEST_XDIST_WORKER` 派生，串行（无该变量）沿配置原值。
"""

import inspect
import os
from collections.abc import Callable, Generator
from pathlib import Path
from typing import cast

import pytest

from bms_core.testing import fixtures


@pytest.mark.kiwi_id(2359)
def test_worker_sqlite_dir_serial_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """串行执行（无 xdist worker）：返回空串，表示沿用配置原值。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)

    assert fixtures.worker_sqlite_dir() == ""


@pytest.mark.kiwi_id(2359)
def test_worker_sqlite_dir_parallel_creates_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """并行执行：目录落在 `<basetemp>/sqlite-<worker>` 并自动创建；同一 worker 稳定复用。"""
    original = fixtures._sqlite_basetemp  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    try:
        fixtures.configure_sqlite_basetemp(str(tmp_path))
        directory = fixtures.worker_sqlite_dir()
        assert directory == str(tmp_path / "sqlite-gw9")
        assert Path(directory).is_dir()

        fixtures.configure_sqlite_basetemp("")
        fallback = Path(fixtures.worker_sqlite_dir())
        assert fallback.name == "sqlite-gw9"
        assert fallback.parent.name == "bms-pytest-sqlite"
    finally:
        fixtures.configure_sqlite_basetemp(original)


@pytest.mark.kiwi_id(2359)
def test_isolate_settings_serial_keeps_sqlite_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """串行隔离：不改写 `BMS_DATABASE__SQLITE_DIR`（沿用配置原值），其余隔离项照常生效。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("BMS_DATABASE__SQLITE_DIR", raising=False)
    direct = cast(
        "Callable[[pytest.MonkeyPatch], Generator[None]]",
        inspect.unwrap(fixtures.isolate_settings),
    )
    generator = direct(monkeypatch)
    next(generator)
    try:
        assert "BMS_DATABASE__SQLITE_DIR" not in os.environ
        assert os.environ["BMS_DATABASE__PLATFORM__URL_TEMPLATE"] == ""
    finally:
        generator.close()
