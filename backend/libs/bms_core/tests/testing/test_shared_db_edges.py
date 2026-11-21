"""共享单库夹具边缘用例：删除失败 / 锁状态异常 / 并发就绪 / 等待超时 / 夹具入口。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import fixtures

pytestmark = [
    pytest.mark.kiwi_id(2399),
    pytest.mark.own_db("被测对象是共享库夹具：需用临时库验证选主 / 清理 / 就绪等待"),
]


@pytest.fixture(autouse=True)
def _pin_project_root(tmp_path: Path) -> Iterator[None]:
    """把测试产物基址钉到临时目录：本文件验证目录行为，不得碰仓内 `.cache/test`。"""
    fixtures.configure_project_root(str(tmp_path))
    yield
    fixtures.configure_project_root("")


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
    """夹具入口：平台 / 租户各取对应逻辑数据源连接串，并把准备集版本戳透传下去。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _ensure(name: str, prepare: object, *, version: str = "1") -> str:
        del prepare
        calls.append(f"{name}:{version}")
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
    # 版本戳含模型源码摘要（不再是固定 "1"）：两个数据源同戳，且随模型变更
    platform_name, platform_version = calls[0].split(":")
    tenant_name, tenant_version = calls[1].split(":")
    assert (platform_name, tenant_name) == ("platform", "tenant")
    assert platform_version == tenant_version
    assert platform_version != "1"


def test_drop_shared_db_files_removes_db_and_siblings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """版本戳变化时删库重建：主文件与 WAL / 日志伴生文件一并清掉。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    for suffix in ("", "-wal", "-shm", "-journal"):
        (directory / f"platform.db{suffix}").write_text("x", encoding="utf-8")
    fixtures._drop_shared_db_files("platform")  # pyright: ignore[reportPrivateUsage]
    assert not list(directory.glob("platform.db*"))


def test_drop_shared_db_files_missing_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库文件不存在时静默跳过（首启路径）。"""
    monkeypatch.chdir(tmp_path)
    fixtures._drop_shared_db_files("platform")  # pyright: ignore[reportPrivateUsage]
    assert not list(fixtures.test_db_dir().glob("platform.db*"))


def test_drop_shared_db_files_propagates_permission_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库文件被占用删不掉时显式失败——静默沿用旧库会变成永久的 `no such column`。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("x", encoding="utf-8")

    def _deny(_self: Path) -> None:
        raise PermissionError("占用")

    monkeypatch.setattr(Path, "unlink", _deny)
    with pytest.raises(PermissionError):
        fixtures._drop_shared_db_files("platform")  # pyright: ignore[reportPrivateUsage]


def test_init_lock_acquires_and_releases(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """文件锁：正常获取后释放，锁文件不残留。"""
    monkeypatch.chdir(tmp_path)
    lock = fixtures.test_db_dir() / "platform.init.lock"
    with fixtures._init_lock("platform"):  # pyright: ignore[reportPrivateUsage]
        assert lock.exists()
        # 持锁者信息落盘：等锁超时时能点名是哪个进程
        assert "pid=" in lock.read_text(encoding="utf-8")
    assert not lock.exists()


def test_init_lock_treats_permission_error_as_contended(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows 竞争：`O_CREAT|O_EXCL` 抛 `PermissionError` 按「有人持锁」处理，继续排队。

    实测（13_08 T7）：两个等待方同刻判陈旧、同刻重建时，Windows 会抛 `EACCES` 而不是
    `FileExistsError`；只捕获后者会把整批 worker 打成 setup 错误。
    """
    monkeypatch.chdir(tmp_path)
    lock = fixtures.test_db_dir() / "platform.init.lock"
    lock.write_text("pid=999 at=00:00:00", encoding="utf-8")
    real_open = fixtures.os.open
    attempts: ConcurrentStableList[int] = ConcurrentStableList()

    def _open(path: object, flags: int, mode: int = 0o777) -> int:
        if Path(cast("Any", path)) == lock:
            if len(attempts) < 2:
                attempts.add(1)
                raise PermissionError("正在被创建")
            # 模拟持锁方释放：文件消失后本次创建才能成功
            lock.unlink(missing_ok=True)
        return real_open(cast("Any", path), flags, mode)

    monkeypatch.setattr(fixtures.os, "open", _open)
    # 锁文件是新鲜的（mtime 未过陈旧阈值）→ 只能不断重试；第二次放开即成功
    with fixtures._init_lock("platform"):  # pyright: ignore[reportPrivateUsage]
        assert lock.exists()
    assert len(attempts) == 2
    assert not lock.exists()


async def test_shared_platform_engine_is_gated(shared_platform_engine: AsyncEngine) -> None:
    """共享平台库引擎夹具返回门代理引擎：连接上的执行可用且走 SQLite。"""
    assert shared_platform_engine.url.get_backend_name() == "sqlite"
    async with shared_platform_engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1


async def test_ensure_shared_db_async_rebuilds_on_version_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """异步版本戳不一致：先删库再重建（建表只补表不补列，必须真重建）。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("stale", encoding="utf-8")
    (directory / "platform.ready").write_text("old", encoding="utf-8")
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _prepare(url: str) -> None:
        calls.add(url)

    url = await fixtures.ensure_shared_db_async("platform", _prepare, version="new-version")
    assert url.startswith("sqlite+aiosqlite:///")
    assert list(calls) == [url]
    assert (directory / "platform.ready").read_text(encoding="utf-8").strip() == "new-version"
