"""共享单库夹具边缘用例：删除失败 / 锁状态异常 / 并发就绪 / 等待超时 / 夹具入口。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.testing import fixtures
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE

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
            directory = fixtures.test_db_dir()
            (directory / "platform.db").write_text("x", encoding="utf-8")
            (directory / "platform.ready").write_text("1", encoding="utf-8")

        def __exit__(self, *args: object) -> None:
            del args

    def _lock_factory(name: str) -> _Lock:
        del name
        return _Lock()

    monkeypatch.setattr(fixtures, "_init_lock", _lock_factory)
    url = fixtures.ensure_shared_db("platform", _prepare)
    assert calls == [] and url.split("?", 1)[0].endswith("platform.db")


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
    """夹具入口：平台 / 租户各取对应逻辑数据源连接串，并把准备集版本戳透传下去（只校验不建库）。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _require(name: str, *, version: str) -> str:
        calls.append(f"{name}:{version}")
        return f"url-{name}"

    def _no_prepare(request: object, name: str) -> None:
        del request, name

    monkeypatch.setattr(fixtures, "require_shared_db", _require)
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


def test_require_shared_db_verifies_stamp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """worker 侧只校验：库文件 / 标记缺失、版本戳不符都拒跑，绝不在此建库。"""
    monkeypatch.chdir(tmp_path)

    def _url(name: str) -> str:
        """按数据源名给一个假连接串。

        Args:
            name: 数据源名。

        Returns:
            str: 假连接串。
        """
        return f"url-{name}"

    monkeypatch.setattr(fixtures, "shared_db_url", _url)
    directory = fixtures.test_db_dir()
    ready = directory / "platform.ready"
    database = directory / "platform.db"

    with pytest.raises(RuntimeError, match="共享库文件缺失"):
        fixtures.require_shared_db("platform", version="v1")
    database.write_text("x", encoding="utf-8")
    with pytest.raises(RuntimeError, match="共享库未初始化"):
        fixtures.require_shared_db("platform", version="v1")
    ready.write_text("old", encoding="utf-8")
    with pytest.raises(RuntimeError, match="版本戳不一致"):
        fixtures.require_shared_db("platform", version="v1")
    ready.write_text("v1", encoding="utf-8")
    assert fixtures.require_shared_db("platform", version="v1") == "url-platform"


def test_needed_shared_databases_reads_fixture_closure() -> None:
    """初始化阶段按用例夹具闭包决定建哪些库（纯单元用例不建库）。"""

    class _Item:
        """最小用例替身（只带夹具闭包）。"""

        def __init__(self, names: ConcurrentStableList[str]) -> None:
            self.fixturenames = names

    assert list(fixtures.needed_shared_databases([_Item(ConcurrentStableList(["platform_db_url", "ns"]))])) == [
        "platform"
    ]
    assert list(fixtures.needed_shared_databases([_Item(ConcurrentStableList(["tenant_db"]))])) == ["tenant"]
    assert list(fixtures.needed_shared_databases([_Item(ConcurrentStableList(["shared_tenant_engine"]))])) == ["tenant"]
    assert list(fixtures.needed_shared_databases([_Item(ConcurrentStableList(["ns", "tmp_path"]))])) == []


def test_prepare_shared_databases_builds_when_not_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化阶段：未就绪时调建库（全程持写门由 `_build_shared_db_under_gate` 负责）。"""
    monkeypatch.chdir(tmp_path)

    def _prepare(url: str) -> None:
        """假准备回调（本用例只验调用编排）。

        Args:
            url: 库连接串。
        """
        del url

    module = SimpleNamespace(prepare_platform=_prepare)
    monkeypatch.setattr(fixtures, "_load_prepare_module", lambda: module)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _build(name: str, prepare: object, version: str) -> None:
        del prepare, version
        calls.add(name)

    monkeypatch.setattr(fixtures, "_build_shared_db_under_gate", _build)
    built = fixtures.prepare_shared_databases(["platform"])

    assert list(built) == ["platform"]
    assert list(calls) == ["platform"]


@pytest.mark.kiwi_id(2548)
def test_build_shared_db_takes_gate_of_its_own_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化阶段建库**按库取门**：平台库取平台门、租户库取租户门（一门一库文件）。

    建租户库若取平台门，并发的租户库写者不受该门约束，会在 0.1s 忙等后报
    `database is locked`——实测末批会话起始数秒内成片失败、全部落在租户库表，
    探针显示 `rebuild tenant` 整段落在 `platform rw` 区间内、租户门为空。
    """
    monkeypatch.chdir(tmp_path)
    acquired: ConcurrentStableList[str] = ConcurrentStableList()

    class _Gate:
        """最小门替身（只记录取门名）。"""

        async def __aenter__(self) -> None:
            """进入门区间（无操作）。"""
            return None

        async def __aexit__(self, *exc: object) -> None:
            """退出门区间（无操作）。"""
            del exc
            return None

    def _gate(name: str, *, read_only: bool, wait: float | None = None) -> _Gate:
        """门替身：记录门名。

        Args:
            name: 门名。
            read_only: 只读标记（忽略）。
            wait: 等待上限（忽略）。

        Returns:
            _Gate: 门上下文替身。
        """
        del read_only, wait
        acquired.add(name)
        return _Gate()

    def _prepare(url: str) -> None:
        """假准备回调（本用例不建库）。

        Args:
            url: 库连接串。
        """
        del url

    def _ensure(name: str, prepare_callback: object, *, version: str) -> None:
        """假建库实现（本用例只验取门）。

        Args:
            name: 数据源名。
            prepare_callback: 准备回调。
            version: 版本戳。
        """
        del name, prepare_callback, version

    monkeypatch.setattr(fixtures, "db_access_gate", _gate)
    monkeypatch.setattr(fixtures, "ensure_shared_db", _ensure)

    asyncio.run(fixtures._build_shared_db_under_gate("platform", _prepare, "v1"))  # pyright: ignore[reportPrivateUsage]
    asyncio.run(fixtures._build_shared_db_under_gate("tenant", _prepare, "v1"))  # pyright: ignore[reportPrivateUsage]

    assert list(acquired) == [PLATFORM_GATE, TENANT_GATE]


def test_prepare_shared_databases_skips_when_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化阶段幂等：就绪标记命中即跳过（多个 worker 同时调用只有一个建库）。"""
    monkeypatch.chdir(tmp_path)

    def _prepare(url: str) -> None:
        """假准备回调（只作版本戳来源）。

        Args:
            url: 库连接串。
        """
        del url

    module = SimpleNamespace(prepare_platform=_prepare)
    monkeypatch.setattr(fixtures, "_load_prepare_module", lambda: module)
    version = fixtures.version_for(_prepare, packages=fixtures._SCHEMA_SOURCE_PACKAGES)  # pyright: ignore[reportPrivateUsage]
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("x", encoding="utf-8")
    (directory / "platform.ready").write_text(version, encoding="utf-8")

    async def _build(name: str, prepare_callback: object, version_text: str) -> None:
        raise AssertionError(f"已就绪不应再建库：{name} {prepare_callback} {version_text}")

    monkeypatch.setattr(fixtures, "_build_shared_db_under_gate", _build)
    assert list(fixtures.prepare_shared_databases(["platform"])) == []


def test_prepare_shared_databases_requires_prepare_callback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """需要建库但找不到准备回调：明确报错（不静默跳过、留一个未初始化的库）。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(fixtures, "_load_prepare_module", lambda: None)
    with pytest.raises(RuntimeError, match="缺少共享库准备回调"):
        fixtures.prepare_shared_databases(["tenant"])


def test_load_prepare_module_returns_none_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """准备回调模块导入失败：返回 None（不抛错，由调用方给出可读的缺回调提示）。"""
    monkeypatch.setenv("BMS_TEST_SHARED_DB_MODULE", "no.such.module")
    assert fixtures._load_prepare_module() is None  # pyright: ignore[reportPrivateUsage]


def test_ready_stamp_reads_text_or_placeholder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """探针用的标记读取：返回去空白内容；空文件与读不到分别给占位串。"""
    monkeypatch.chdir(tmp_path)
    ready = fixtures.test_db_dir() / "platform.ready"
    ready.write_text(" v1 ", encoding="utf-8")
    assert fixtures._ready_stamp(ready) == "v1"  # pyright: ignore[reportPrivateUsage]
    ready.write_text("", encoding="utf-8")
    assert fixtures._ready_stamp(ready) == "<empty>"  # pyright: ignore[reportPrivateUsage]
    ready.unlink()
    assert fixtures._ready_stamp(ready) == "<none>"  # pyright: ignore[reportPrivateUsage]


def test_shared_db_ready_false_when_stat_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """就绪判定读文件属性失败（句柄异常 / 权限）：按未就绪处理，由初始化阶段重建。"""
    monkeypatch.chdir(tmp_path)
    (fixtures.test_db_dir() / "platform.ready").write_text("v1", encoding="utf-8")

    def _raise(self: Path, *args: object, **kwargs: object) -> object:
        del self, args, kwargs
        raise OSError("gone")

    monkeypatch.setattr(Path, "stat", _raise)
    assert fixtures._shared_db_ready("platform", "v1") is False  # pyright: ignore[reportPrivateUsage]


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


@pytest.mark.kiwi_id(2540)
def test_drop_shared_db_files_returns_stuck_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库文件被占用删不掉时**返回失败清单**（由调用方分级：清场告警 / 重建失败）。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("x", encoding="utf-8")

    def _deny(self: Path, missing_ok: bool = False) -> None:
        if self.name == "platform.db":
            raise PermissionError("占用")
        if not missing_ok:
            raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "unlink", _deny)
    assert list(fixtures._drop_shared_db_files("platform")) == ["platform.db"]  # pyright: ignore[reportPrivateUsage]


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


def _deny_platform_db(self: Path, missing_ok: bool = False) -> None:
    """`Path.unlink` 替身：`platform.db` 一律占用（其余按原语义）。

    Args:
        self: 目标路径。
        missing_ok: 是否允许不存在。

    Raises:
        PermissionError: 目标是 `platform.db`。
        FileNotFoundError: 其它目标且不存在。
    """
    if self.name == "platform.db":
        raise PermissionError("占用")
    if not missing_ok:
        raise FileNotFoundError(self)


@pytest.mark.kiwi_id(2543)
def test_ensure_shared_db_fails_when_rebuild_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """版本戳不一致但旧库删不掉：**显式失败**（沿用旧库会变成永久的 `no such column`）。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("stale", encoding="utf-8")
    (directory / "platform.ready").write_text("old", encoding="utf-8")
    monkeypatch.setattr(Path, "unlink", _deny_platform_db)
    with pytest.raises(PermissionError, match="共享库重建失败"):
        fixtures.ensure_shared_db("platform", lambda url: None, version="new-version")


@pytest.mark.kiwi_id(2543)
async def test_ensure_shared_db_async_fails_when_rebuild_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """异步版同口径：删不掉旧库即失败，不静默沿用。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("stale", encoding="utf-8")
    (directory / "platform.ready").write_text("old", encoding="utf-8")
    monkeypatch.setattr(Path, "unlink", _deny_platform_db)

    async def _prepare(url: str) -> None:
        del url

    with pytest.raises(PermissionError, match="共享库重建失败"):
        await fixtures.ensure_shared_db_async("platform", _prepare, version="new-version")


@pytest.mark.kiwi_id(2542)
def test_reset_shared_databases_reports_stuck_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """就绪标记删不掉也要进失败清单（清场后不得留下「库已就绪」的假标记）。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.ready").write_text("v1", encoding="utf-8")

    def _deny(self: Path, missing_ok: bool = False) -> None:
        """只拦就绪标记。

        Args:
            self: 目标路径。
            missing_ok: 是否允许不存在。
        """
        if self.name == "platform.ready":
            raise PermissionError("占用")
        if not missing_ok:
            raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "unlink", _deny)
    assert list(fixtures.reset_shared_databases()) == ["platform.ready"]


def test_shared_db_ready_false_when_file_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """就绪判定：库文件存在但为 0 字节（上次崩溃 / 手工截断）按未就绪处理。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_bytes(b"")
    (directory / "platform.ready").write_text("v1", encoding="utf-8")
    assert fixtures._shared_db_ready("platform", "v1") is False  # pyright: ignore[reportPrivateUsage]


async def test_build_shared_db_under_gate_calls_ensure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """初始化建库入口：在写门内调准备回调（门是唯一写排队路径）。"""
    monkeypatch.chdir(tmp_path)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def _ensure(name: str, prepare: object, *, version: str) -> None:
        del prepare
        calls.add(f"{name}:{version}")

    monkeypatch.setattr(fixtures, "ensure_shared_db", _ensure)
    await fixtures._build_shared_db_under_gate("platform", lambda url: None, "v1")  # pyright: ignore[reportPrivateUsage]
    assert list(calls) == ["platform:v1"]


def test_reset_shared_databases_removes_files_and_markers(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话入口清场：库文件（含 WAL 伴生）与就绪标记一并删掉，下一轮由初始化阶段重建。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    for name in ("platform", "tenant"):
        (directory / f"{name}.db").write_text("x", encoding="utf-8")
        (directory / f"{name}.ready").write_text("v1", encoding="utf-8")
    (directory / "platform.db-wal").write_text("x", encoding="utf-8")

    assert list(fixtures.reset_shared_databases()) == []

    for name in ("platform", "tenant"):
        assert not (directory / f"{name}.db").exists()
        assert not (directory / f"{name}.ready").exists()
    assert not (directory / "platform.db-wal").exists()


@pytest.mark.kiwi_id(2541)
def test_reset_shared_databases_reports_stuck_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """清场遇到句柄占用：返回失败清单而不抛错（库文件只告警由调用方决定）。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("x", encoding="utf-8")

    def _deny(self: Path, missing_ok: bool = False) -> None:
        if self.name == "platform.db":
            raise PermissionError("占用")
        if not missing_ok:
            raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "unlink", _deny)
    assert list(fixtures.reset_shared_databases()) == ["platform.db"]


def test_clear_shared_db_files_keeps_databases_when_excluded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话入口清场：`include_databases=False` 时保留库文件 / 就绪标记 / WAL 伴生，只清临时产物。"""
    monkeypatch.chdir(tmp_path)
    directory = fixtures.test_db_dir()
    (directory / "platform.db").write_text("x", encoding="utf-8")
    (directory / "platform.ready").write_text("v1", encoding="utf-8")
    (directory / "platform.db-wal").write_text("x", encoding="utf-8")
    (directory / "stale").write_text("x", encoding="utf-8")

    failed = fixtures.clear_shared_db_files(include_databases=False)

    assert list(failed) == []
    assert (directory / "platform.db").exists()
    assert (directory / "platform.ready").exists()
    assert (directory / "platform.db-wal").exists()
    assert not (directory / "stale").exists()


@pytest.mark.own_db("建表入口即被测：临时库验证 AUTOCOMMIT 逐表建与幂等")
async def test_bootstrap_apply_async_creates_and_reports(tmp_path: Path) -> None:
    """异步建表入口：逐表 AUTOCOMMIT 建成、重跑只报已存在（结构初始化不取数据门）。"""
    from sqlalchemy import Column, Integer, MetaData, Table

    from bms_core.db import bootstrap

    metadata = MetaData()
    Table("async_probe", metadata, Column("id", Integer, primary_key=True))
    url = f"sqlite+aiosqlite:///{tmp_path / 'async.db'}"

    created, existing = await bootstrap._apply_async(url, metadata)  # pyright: ignore[reportPrivateUsage]
    assert (created, existing) == (1, 0)
    again, kept = await bootstrap._apply_async(url, metadata)  # pyright: ignore[reportPrivateUsage]
    assert (again, kept) == (0, 1)


@pytest.mark.own_db("启动建表入口即被测：以替身校验按库类别调建表并回报库键")
async def test_ensure_unit_schema_applies_declared_unit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """启动建表入口：单元已登记域时按库类别调建表并回报已处理库键。"""
    from bms_core.core.config import get_settings
    from bms_core.db import bootstrap

    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _apply(unit: str, datasource: str, url: str, *, target: str = "", schema: str = "") -> object:
        del url, schema
        calls.add(f"{unit}:{datasource}:{target}")
        return bootstrap.SchemaOutcome(target=target, total=1, created=1, existing=0)

    def _unit_key(settings: object) -> str:
        """固定单元键。

        Args:
            settings: 应用配置（未使用）。

        Returns:
            str: 单元键。
        """
        del settings
        return "platform"

    def _unit_domains(unit: str) -> ConcurrentStableList[str]:
        """固定域清单。

        Args:
            unit: 单元键（未使用）。

        Returns:
            ConcurrentStableList[str]: 域清单。
        """
        del unit
        return ConcurrentStableList(["role"])

    def _db_keys(datasource: str, settings: object) -> ConcurrentStableList[str]:
        """只回报平台库键（其余库类别为空）。

        Args:
            datasource: 数据源段。
            settings: 应用配置（未使用）。

        Returns:
            ConcurrentStableList[str]: 库键清单。
        """
        del settings
        return ConcurrentStableList(["platform"]) if datasource == "platform" else ConcurrentStableList()

    monkeypatch.setattr(bootstrap, "unit_key", _unit_key)
    monkeypatch.setattr(bootstrap, "unit_domains", _unit_domains)
    monkeypatch.setattr(bootstrap, "db_keys_for", _db_keys)
    monkeypatch.setattr(bootstrap, "apply_unit_schema", _apply)
    settings = get_settings()
    settings.database.auto_create = True

    handled = await bootstrap.ensure_unit_schema(settings)

    assert "platform" in handled
    assert list(calls) == ["platform:platform:platform"]


def test_module_prepare_reads_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    """准备模块里有对应回调即返回它；没有该数据源的回调返回 None。"""

    def prepare(url: str) -> None:
        """桩准备回调（不建库）。

        Args:
            url: 连接串（忽略）。
        """
        del url

    module = SimpleNamespace(prepare_platform=prepare)
    monkeypatch.setattr(fixtures, "_load_prepare_module", lambda: module)
    assert fixtures.module_prepare("platform") is prepare
    assert fixtures.module_prepare("tenant") is None


def test_module_prepare_returns_none_without_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """准备模块缺失（产品仓未提供 / 未装）时返回 None，由调用方退化为缺省口径。"""
    monkeypatch.setattr(fixtures, "_load_prepare_module", lambda: None)
    assert fixtures.module_prepare("platform") is None
