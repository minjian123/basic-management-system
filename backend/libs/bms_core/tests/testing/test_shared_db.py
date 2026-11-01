"""共享单库夹具用例（04-6-1 / Kiwi 2399）：建库一次 / 版本戳 / 残留锁 / 清理 / 命名空间夹具。"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import fixtures
from bms_core.testing.namespace import Namespace

pytestmark = [
    pytest.mark.kiwi_id(2399),
    pytest.mark.own_db("被测对象是共享库夹具：需用临时库验证建库一次 / 版本戳 / 残留锁 / 清理"),
]


@pytest.fixture(autouse=True)
def _pin_project_root(tmp_path: Path) -> Iterator[None]:
    """把测试产物基址钉到临时目录：本文件验证目录行为，不得碰仓内 `.cache/test`。"""
    fixtures.configure_project_root(str(tmp_path))
    yield
    fixtures.configure_project_root("")


def test_shared_db_created_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一逻辑数据源只建一次；连接串指向 `.cache/test/`；版本戳落 `.ready`。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def prepare(url: str) -> None:
        calls.append(url)

    url = fixtures.ensure_shared_db("platform", prepare)
    assert calls == [url]
    assert url.endswith(".cache/test/platform.db")
    assert (tmp_path / ".cache/test/platform.ready").read_text(encoding="utf-8").strip() == "1"

    assert fixtures.ensure_shared_db("platform", prepare) == url
    assert len(calls) == 1


def test_shared_db_version_mismatch_rebuilds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`.ready` 版本戳不一致即重建（schema 变更后的自愈路径）。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def prepare(url: str) -> None:
        calls.append(url)

    fixtures.ensure_shared_db("tenant", prepare, version="1")
    fixtures.ensure_shared_db("tenant", prepare, version="2")
    assert len(calls) == 2
    assert (tmp_path / ".cache/test/tenant.ready").read_text(encoding="utf-8").strip() == "2"


def test_init_lock_timeout_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """锁被占且未过期时按上限超时报错，并给出目录清单（不无限等待）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixtures, "_INIT_TIMEOUT", 0.05)
    monkeypatch.setattr(fixtures, "_READY_POLL", 0.01)
    directory = fixtures.test_db_dir()
    (directory / "platform.init.lock").write_text("held", encoding="utf-8")

    with pytest.raises(TimeoutError, match="初始化锁超时"):
        fixtures.ensure_shared_db("platform", lambda url: None)


def test_stale_lock_is_taken_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """残留锁（mtime 超阈值）判过期后重抢，不阻塞整轮。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixtures, "_LOCK_STALE", 0.01)
    directory = fixtures.test_db_dir()
    lock = directory / "platform.init.lock"
    lock.write_text("crashed", encoding="utf-8")
    old = time.time() - 60
    os.utime(lock, (old, old))

    url = fixtures.ensure_shared_db("platform", lambda _: None)
    assert url.endswith("platform.db")
    assert not lock.exists()


def test_clear_shared_db_files_keeps_namespace_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话开始清理库文件与就绪标记，但保留命名空间映射与无关文件。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    for name in ("platform.db", "platform.db-wal", "tenant.db", "platform.ready", "namespace-map.jsonl", "keep.txt"):
        (directory / name).write_text("x", encoding="utf-8")

    failed = fixtures.clear_shared_db_files()
    assert failed == []
    remaining = sorted(path.name for path in directory.iterdir())
    assert remaining == ["keep.txt", "namespace-map.jsonl"]


def test_clear_shared_db_files_without_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """目录不存在时直接返回空清单（首跑路径）。"""
    monkeypatch.chdir(tmp_path)
    assert fixtures.clear_shared_db_files() == []


def test_default_prepare_creates_tables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """缺省建库回调按已导入模型的并集建表（套件未提供 `shared_db_prepare` 时的兜底）。"""
    monkeypatch.chdir(tmp_path)
    url = fixtures.shared_db_url("platform")
    fixtures._default_prepare(url)  # pyright: ignore[reportPrivateUsage]
    assert (tmp_path / ".cache/test/platform.db").exists()


def test_resolve_prepare_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    """套件未提供回调 → None；提供非可调用对象 → None；提供可调用对象 → 原样返回。"""

    class _Request:
        pass

    def prepare(url: str) -> None:
        del url

    def no_fixture(request: Any, name: str) -> None:
        del request, name

    def non_callable(request: Any, name: str) -> int:
        del request, name
        return 42

    monkeypatch.setattr(fixtures, "resolve_fixture", no_fixture)
    assert fixtures.resolve_prepare(_Request(), "platform") is None  # type: ignore[arg-type]

    monkeypatch.setattr(fixtures, "resolve_fixture", non_callable)
    assert fixtures.resolve_prepare(_Request(), "platform") is None  # type: ignore[arg-type]

    def with_fixture(request: Any, name: str) -> Any:
        del request, name
        return prepare

    monkeypatch.setattr(fixtures, "resolve_fixture", with_fixture)
    assert fixtures.resolve_prepare(_Request(), "platform") is prepare  # type: ignore[arg-type]


def test_ns_fixture_generates_namespace(ns: Namespace) -> None:
    """`ns` 夹具给出当前用例的命名空间（前缀形态合法、编码带前缀）。"""
    assert ns.prefix.startswith("w")
    assert ns.code("demo").startswith(f"{ns.prefix}-")


def test_shared_db_url_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """连接串形态：`sqlite+aiosqlite:///` + 仓内绝对路径。"""
    monkeypatch.chdir(tmp_path)
    url = fixtures.shared_db_url("tenant")
    assert url.startswith("sqlite+aiosqlite:///") and url.endswith("tenant.db")
    assert (tmp_path / ".cache/test").is_dir()


def test_test_db_dir_creates_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`test_db_dir` 首次解析自动建目录。"""
    monkeypatch.chdir(tmp_path)
    directory: Path = fixtures.test_db_dir()
    assert directory.is_dir()
