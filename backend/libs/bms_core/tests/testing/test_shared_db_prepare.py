"""共享测试库准备集与例外通道（04-6-2 · Kiwi 2400）。

覆盖：`resolve_prepare` 按数据源分派、`.ready` 版本戳自动派生、`BMS_TEST_ISOLATED_DB=1`
例外通道、`tests_support.shared_db` 的 platform / tenant 准备集（建表 + 种子 + 主键对齐 + 幂等）。

本模块自建库属「建库即被测」（被测对象就是准备集本身），故整体进 `own_db` 白名单。
"""

import types
from collections.abc import Callable, Generator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.testing import fixtures

pytestmark = [pytest.mark.kiwi_id(2400), pytest.mark.own_db("被测对象就是共享库准备集：建表与种子本身")]


@pytest.fixture(autouse=True)
def _restore_basetemp(tmp_path: Path) -> Iterator[None]:
    """把测试产物基址钉到临时目录，并在用例结束后复位工程根记录。"""
    fixtures.configure_project_root(str(tmp_path))
    yield
    fixtures.configure_project_root("")


def _prepare(_url: str) -> None:
    """占位准备回调（仅用于取源文件路径）。"""


class _FakeRequest:
    """最小夹具请求替身：按名返回预置对象（缺失即抛 `FixtureLookupError`）。"""

    def __init__(self, mapping: ConcurrentStableDict[str, object]) -> None:
        """初始化。

        Args:
            mapping: 夹具名 → 值。
        """
        self._mapping = mapping

    def _get_fixturestack(self) -> ConcurrentStableList[object]:
        """`FixtureLookupError` 构造所需的最小实现。

        Returns:
            ConcurrentStableList[object]: 固定空栈。
        """
        return ConcurrentStableList()

    def getfixturevalue(self, name: str) -> object:
        """取夹具值（缺失即抛 `FixtureLookupError`）。

        Args:
            name: 夹具名。

        Returns:
            object: 夹具值。

        Raises:
            FixtureLookupError: 名称不在预置表内。
        """
        if name not in self._mapping:
            raise pytest.FixtureLookupError(name, cast("Any", self))
        return self._mapping[name]


def test_isolation_off_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """默认关闭：库落仓内 `.cache/test`，无提示。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(fixtures.ISOLATED_ENV, raising=False)
    assert fixtures.isolation_enabled() is False
    assert fixtures.isolation_notice() == ""
    assert fixtures.test_db_dir() == tmp_path / ".cache" / "test"


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_isolation_false_values(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    """假值一律视为关闭（避免 `BMS_TEST_ISOLATED_DB=0` 被误当开启）。"""
    monkeypatch.setenv(fixtures.ISOLATED_ENV, value)
    assert fixtures.isolation_enabled() is False


def test_isolation_moves_db_dir_under_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """开启后：库落 `<工程根>/.cache/test-db-isolated`（不再依赖 basetemp），会话头提示含落点。"""
    monkeypatch.setenv(fixtures.ISOLATED_ENV, "1")
    directory = fixtures.test_db_dir()
    assert directory.name == "test-db-isolated"
    assert directory.parent.name == ".cache"
    assert directory != fixtures.project_root() / ".cache" / fixtures.TEST_DB_DIRNAME
    notice = fixtures.isolation_notice()
    assert "隔离调试模式" in notice
    assert "不代表 CI 口径" in notice


def test_resolve_prepare_prefers_data_source_fixture() -> None:
    """按数据源解析：`platform_db_prepare` 优先于 `shared_db_prepare`。"""
    platform = _FakeRequest(ConcurrentStableDict({"platform_db_prepare": _prepare, "shared_db_prepare": print}))
    assert fixtures.resolve_prepare(cast("Any", platform), "platform") is _prepare
    tenant = _FakeRequest(ConcurrentStableDict({"tenant_db_prepare": fixtures.version_for}))
    assert fixtures.resolve_prepare(cast("Any", tenant), "tenant") is fixtures.version_for


def test_resolve_prepare_falls_back_and_handles_absence() -> None:
    """回退与缺失：无同名夹具时用 `shared_db_prepare`；都没有返回 `None`。"""
    fallback = _FakeRequest(ConcurrentStableDict({"shared_db_prepare": _prepare}))
    assert fixtures.resolve_prepare(cast("Any", fallback), "tenant") is _prepare
    assert fixtures.resolve_prepare(cast("Any", _FakeRequest(ConcurrentStableDict())), "platform") is None
    not_callable = _FakeRequest(ConcurrentStableDict({"platform_db_prepare": "非可调用"}))
    assert fixtures.resolve_prepare(cast("Any", not_callable), "platform") is None


def test_version_for_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    """版本戳：无回调 / 无源文件 → `1`；有源文件 → 12 位摘要。"""
    assert fixtures.version_for(None) == "1"
    assert fixtures.version_for(len) == "1"  # pyright: ignore[reportArgumentType]
    digest = fixtures.version_for(_prepare)
    assert len(digest) == 12
    assert all(char in "0123456789abcdef" for char in digest)

    def _boom(_self: Path) -> bytes:
        raise OSError("读失败")

    monkeypatch.setattr(Path, "read_bytes", _boom)
    assert fixtures.version_for(_prepare) == "1"


def test_version_for_dynamic_and_anonymous_sources() -> None:
    """动态编译的函数（无真实源文件）与无 `__file__` 的模块：一律退回 `1`。"""
    code = compile("lambda url: None", "<dyn>", "eval")
    dynamic = types.LambdaType(code, {})
    assert fixtures.version_for(cast("Callable[[str], None]", dynamic)) == "1"
    module = types.ModuleType("no_file_module")
    assert fixtures.version_for(cast("Callable[[str], None]", module)) == "1"


def test_root_conftest_exposes_prepare_fixtures() -> None:
    """工程根 conftest 暴露的准备夹具即 `tests_support.shared_db` 的单源实现（薄壳不复制逻辑）。

    直接加载工程根 `conftest.py` 模块断言，而非经夹具注入：本目录自带 `pyproject.toml`，
    自成 rootdir 时根级 conftest 不参与加载，注入式断言会随调用方式漂移。
    """
    import importlib.util

    from tests_support.shared_db import prepare_platform, prepare_tenant

    root_conftest = Path(__file__).resolve().parents[4] / "conftest.py"
    spec = importlib.util.spec_from_file_location("_root_conftest_probe", root_conftest)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.platform_db_prepare.__wrapped__() is prepare_platform
    assert module.tenant_db_prepare.__wrapped__() is prepare_tenant


async def test_ensure_shared_db_async_awaits_coroutine_prepare(tmp_path: Path) -> None:
    """异步入口：协程准备集被 await（异步夹具里不能再 `asyncio.run`）。"""
    from tests_support.shared_db import prepare_platform_async

    url = await fixtures.ensure_shared_db_async("platform", prepare_platform_async, version="v1")
    assert (tmp_path / ".cache" / "test" / "platform.ready").read_text(encoding="utf-8").strip() == "v1"
    again = await fixtures.ensure_shared_db_async("platform", prepare_platform_async, version="v1")
    assert again == url


async def test_ensure_shared_db_async_delegates_sync_prepare(tmp_path: Path) -> None:
    """同步回调：退化为同步实现（避免在外层事件循环里嵌套 `asyncio.run`）。"""
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    def prepare(url: str) -> None:
        calls.append(url)

    url = await fixtures.ensure_shared_db_async("tenant", prepare, version="v2")
    assert list(calls) == [url]
    assert (tmp_path / ".cache" / "test" / "tenant.ready").read_text(encoding="utf-8").strip() == "v2"


async def test_ensure_shared_db_async_default_prepare_and_peer_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """异步入口：无回调走缺省建表；抢锁后若别处已建好则直接返回（不重复准备）。"""
    url = await fixtures.ensure_shared_db_async("platform", None, version="v3")
    assert url.endswith("test/platform.db")
    assert (tmp_path / ".cache" / "test" / "platform.db").is_file()

    @contextmanager
    def _peer_built(name: str) -> Generator[None]:
        """替身锁：进入时假装别的 worker 已写好就绪标记。"""
        (fixtures.test_db_dir() / f"{name}.ready").write_text("v3", encoding="utf-8")
        yield

    monkeypatch.setattr(fixtures, "_init_lock", _peer_built)
    calls: ConcurrentStableList[str] = ConcurrentStableList()

    async def _prepare(target: str) -> None:
        calls.append(target)

    peer_url = await fixtures.ensure_shared_db_async("tenant", _prepare, version="v3")
    assert peer_url.endswith("tenant.db")
    assert list(calls) == []


async def test_shared_engines_point_at_shared_db(
    shared_platform_engine: AsyncEngine, shared_tenant_engine: AsyncEngine
) -> None:
    """共享库引擎夹具：两个数据源各一条可用连接（且落 `.cache/test` 下的同名库）。"""
    async with shared_platform_engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    async with shared_tenant_engine.connect() as connection:
        assert (await connection.execute(text("SELECT 1"))).scalar() == 1
    assert str(shared_platform_engine.url).endswith("test/platform.db")
    assert str(shared_tenant_engine.url).endswith("test/tenant.db")


async def test_prepare_tenant_async_creates_tables_and_configs(tmp_path: Path) -> None:
    """租户库准备集的异步入口：域并集建表 + 系统参数种子（幂等）。"""
    from tests_support.shared_db import prepare_tenant_async

    url = f"sqlite+aiosqlite:///{(tmp_path / 'tenant.db').as_posix()}"
    await prepare_tenant_async(url)
    first = await _count_async(url, "SELECT COUNT(*) FROM sys_config")
    await prepare_tenant_async(url)
    assert first > 0
    assert await _count_async(url, "SELECT COUNT(*) FROM sys_config") == first


def test_prepare_platform_seeds_and_aligns(tmp_path: Path) -> None:
    """平台库准备集：种子租户 + 主键对齐 + 服务目录，重复执行幂等。"""
    from bms_core.models.base import SQLITE_PADDED_WIDTH
    from tests_support.shared_db import SEED_TENANT_IDS, prepare_platform

    url = f"sqlite+aiosqlite:///{(tmp_path / 'platform.db').as_posix()}"
    prepare_platform(url)
    prepare_platform(url)
    rows = _query(url, "SELECT code, id FROM sys_tenant WHERE deleted_at IS NULL ORDER BY code")
    expected = {code: str(tenant_id).zfill(SQLITE_PADDED_WIDTH) for code, tenant_id in SEED_TENANT_IDS}
    assert {row[0]: row[1] for row in rows} == expected
    assert _query(url, "SELECT COUNT(*) FROM sys_module")[0][0] > 0


def test_prepare_tenant_creates_tables_and_configs(tmp_path: Path) -> None:
    """租户库准备集：域并集建表 + 系统参数种子，重复执行幂等。"""
    from tests_support.shared_db import prepare_tenant

    url = f"sqlite+aiosqlite:///{(tmp_path / 'tenant.db').as_posix()}"
    prepare_tenant(url)
    first = _query(url, "SELECT COUNT(*) FROM sys_config")[0][0]
    prepare_tenant(url)
    assert first > 0
    assert _query(url, "SELECT COUNT(*) FROM sys_config")[0][0] == first


def test_tenant_metadata_falls_back_when_layout_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """域布局不可用：回落到全模型并集并打印提示（不静默少建表）。"""
    from bms_core.core.exceptions import ConfigError
    from bms_core.models.base import Base
    from tests_support import shared_db

    def _raise(_domains: object, _datasource: object) -> object:
        raise ConfigError("布局缺失")

    monkeypatch.setattr(shared_db, "domains_metadata", _raise)
    assert shared_db._tenant_metadata() is Base.metadata  # pyright: ignore[reportPrivateUsage]


async def _count_async(url: str, statement: str) -> int:
    """异步取单值计数（异步用例里不能再 `asyncio.run`）。

    Args:
        url: 连接串。
        statement: 单值 SQL。

    Returns:
        int: 计数值。
    """
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return int((await connection.execute(text(statement))).scalar_one())
    finally:
        await engine.dispose()


def _query(url: str, statement: str) -> ConcurrentStableList[ConcurrentStableList[Any]]:
    """同步执行只读查询（用例断言用）。

    Args:
        url: 连接串。
        statement: SQL 文本。

    Returns:
        ConcurrentStableList[ConcurrentStableList[Any]]: 结果行（插入序；每行是单元格列表）。
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    async def _run() -> ConcurrentStableList[ConcurrentStableList[Any]]:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(statement))
                rows: ConcurrentStableList[ConcurrentStableList[Any]] = ConcurrentStableList()
                for row in result:
                    cells: ConcurrentStableList[Any] = ConcurrentStableList()
                    for cell in row:
                        cells.add(cell)
                    rows.add(cells)
                return rows
        finally:
            await engine.dispose()

    return asyncio.run(_run())
