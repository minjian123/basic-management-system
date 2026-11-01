"""共享单库夹具边缘用例：删除失败 / 锁状态异常 / 并发就绪 / 等待超时 / 夹具入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import fixtures

pytestmark = pytest.mark.kiwi_id(2399)


def test_clear_shared_db_files_reports_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """删除失败（句柄占用）：跳过并记入失败清单，不中断整轮。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    target = directory / "platform.db"
    target.write_text("x", encoding="utf-8")
    (directory / "tenant.db").write_text("x", encoding="utf-8")

    original_unlink = Path.unlink

    def _fail_once(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == "platform.db":
            raise OSError("in use")
        original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", _fail_once)
    failed = fixtures.clear_shared_db_files()
    assert list(failed) == ["platform.db"]


def test_stale_lock_stat_failure_is_not_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """锁状态读取失败：按未过期处理，等待到超时后报错。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixtures, "_INIT_TIMEOUT", 0.05)
    monkeypatch.setattr(fixtures, "_READY_POLL", 0.01)
    directory = fixtures.test_db_dir()
    (directory / "platform.init.lock").write_text("held", encoding="utf-8")

    original_stat = Path.stat

    def _raise(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name.endswith(".lock"):
            raise OSError("gone")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _raise)
    with pytest.raises(TimeoutError, match="初始化锁超时"):
        fixtures.ensure_shared_db("platform", lambda url: None)


def test_ready_created_while_waiting_for_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """抢到锁后再判一次：上一个持锁者已建好时直接返回。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _prepare(url: str) -> None:
        calls.append(url)

    class _Lock:
        def __enter__(self) -> None:
            (fixtures.test_db_dir() / "platform.ready").write_text("1", encoding="utf-8")

        def __exit__(self, *args: object) -> None:
            del args

    def _lock_factory(name: str) -> _Lock:
        del name
        return _Lock()

    monkeypatch.setattr(fixtures, "_init_lock", _lock_factory)
    url = fixtures.ensure_shared_db("platform", _prepare)
    assert calls == [] and url.endswith("platform.db")


def test_ready_wait_times_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """就绪标记始终未出现：按上限超时报错（不无限等待）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixtures, "_INIT_TIMEOUT", 0.05)
    monkeypatch.setattr(fixtures, "_READY_POLL", 0.01)

    class _Lock:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            del args

    def _lock_factory(name: str) -> _Lock:
        del name
        return _Lock()

    monkeypatch.setattr(fixtures, "_init_lock", _lock_factory)
    original_write = Path.write_text

    def _skip_ready(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.suffix == ".ready":
            return 0
        return original_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _skip_ready)
    with pytest.raises(TimeoutError, match="就绪标记未出现"):
        fixtures.ensure_shared_db("platform", lambda url: None)


def test_shared_db_url_fixtures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """夹具入口：平台 / 租户各取对应逻辑数据源连接串。"""
    monkeypatch.chdir(tmp_path)

    def _ensure(name: str, prepare: object) -> str:
        del prepare
        return f"url-{name}"

    def _no_prepare(request: object, name: str) -> None:
        del request, name

    monkeypatch.setattr(fixtures, "ensure_shared_db", _ensure)
    monkeypatch.setattr(fixtures, "resolve_prepare", _no_prepare)

    class _Request:
        pass

    request = cast("Any", _Request())
    platform_fixture = cast("Any", fixtures.shared_platform_db_url)
    tenant_fixture = cast("Any", fixtures.shared_tenant_db_url)
    assert platform_fixture.__wrapped__(request) == "url-platform"
    assert tenant_fixture.__wrapped__(request) == "url-tenant"


def test_init_lock_acquires_and_releases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """文件锁：正常获取后释放，锁文件不残留。"""
    monkeypatch.chdir(tmp_path)
    lock = fixtures.test_db_dir() / "platform.init.lock"
    with fixtures._init_lock("platform"):  # pyright: ignore[reportPrivateUsage]
        assert lock.exists()
    assert not lock.exists()
