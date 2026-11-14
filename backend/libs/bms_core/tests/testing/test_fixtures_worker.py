"""测试基座的并行口径（Kiwi 2359）：旧「按 worker 派生 sqlite_dir」已删除，雪花 WorkerId 仍按 worker 派生。

单库化（04-6-2）后，库一律走共享测试库 / 白名单独占库的**显式 URL**：并行 worker 不再各持一套
`sqlite-gwN/` 目录，`isolate_settings` 也不再注入 `BMS_DATABASE__SQLITE_DIR`。
"""

import inspect
import os
from collections.abc import Callable, Generator
from typing import cast

import pytest

from bms_core.core.id_bits import WORKER_BITS, WORKER_SHIFT
from bms_core.testing import fixtures


@pytest.mark.kiwi_id(2359)
def test_worker_sqlite_dir_removed() -> None:
    """旧夹具已删除：`worker_sqlite_dir` / `configure_sqlite_basetemp` 不再对外提供。"""
    assert not hasattr(fixtures, "worker_sqlite_dir")
    assert not hasattr(fixtures, "configure_sqlite_basetemp")
    assert "worker_sqlite_dir" not in fixtures.__all__


@pytest.mark.kiwi_id(2359)
def test_isolate_settings_never_injects_sqlite_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离夹具不再注入 `BMS_DATABASE__SQLITE_DIR`（并行下也不注入），连接串模板固定关闭。"""
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
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
        assert os.environ["BMS_DATABASE__TENANTS__URL_TEMPLATE"] == ""
    finally:
        generator.close()


def test_worker_id_for_snowflake_derives_from_xdist(monkeypatch: pytest.MonkeyPatch) -> None:
    """雪花 WorkerId：串行 0、`gwN` 取 N+1（避开 0）、取值非法回落 0。"""
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    assert fixtures.worker_id_for_snowflake() == 0

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    assert fixtures.worker_id_for_snowflake() == 1

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw9")
    assert fixtures.worker_id_for_snowflake() == 10

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "master")
    assert fixtures.worker_id_for_snowflake() == 0


def test_isolate_settings_injects_worker_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离夹具把派生 WorkerId 写进 `BMS_APP__WORKER_ID`，并**直接重设生成器**（不依赖 lifespan）。

    直接重设是 2PC 真库用例的必需项：它们直接构造协调器、不走应用启动，拿不到 `validate_startup`
    的重设，多 worker 同毫秒会生成相同雪花 ID（派生同一 XA `xid`，MySQL 报 `XAER_DUPID`；bms#1629）。
    """
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw3")
    direct = cast(
        "Callable[[pytest.MonkeyPatch], Generator[None]]",
        inspect.unwrap(fixtures.isolate_settings),
    )
    generator = direct(monkeypatch)
    next(generator)
    try:
        assert os.environ["BMS_APP__WORKER_ID"] == "4"
        generated = fixtures.id_generator.next_id()
        assert (generated >> WORKER_SHIFT) & ((1 << WORKER_BITS) - 1) == 4
    finally:
        generator.close()


def test_test_db_dir_isolation_channel_under_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """隔离调试通道落 `<工程根>/.cache/test-db-isolated`（不再依赖 basetemp）。"""
    monkeypatch.setenv(fixtures.ISOLATED_ENV, "1")
    directory = fixtures.test_db_dir()
    assert directory.parent.name == ".cache"
    assert directory.name == fixtures._ISOLATED_DIRNAME  # pyright: ignore[reportPrivateUsage]
