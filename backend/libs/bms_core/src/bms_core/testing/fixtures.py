"""pytest 公共夹具（13_04）：配置隔离 / 平台库 / 请求上下文 / 插件注册表。

收编口径：与各 `conftest.py` 同名同语义，**存量用例零改动**；仓库 / 服务专属的差异
（`configure_token_env`、fakeredis、服务环境变量）由各自 conftest 覆写本模块夹具并追加，
不在包内依赖 `tests_support`（保证产品仓可直接复用）。
"""

import asyncio
import hashlib
import inspect
import os
import time
from collections.abc import AsyncIterator, Callable, Generator, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.core.context import (
    current_client_ip,
    current_request_id,
    current_tenant,
    current_tenant_context_var,
    current_tenant_id,
    current_trace_id,
    current_user_id,
)
from bms_core.core.id import MAX_WORKER_ID
from bms_core.permission.cache import reset_permission_cache_store
from bms_core.testing import namespace as namespace_module
from bms_core.testing.namespace import Namespace
from bms_core.testing.paths import configure_project_root, project_root

__all__ = (
    "TEST_DB_DIRNAME",
    "apply_platform_db",
    "clear_shared_db_files",
    "clear_tenant_cache",
    "configure_project_root",
    "ensure_shared_db",
    "isolation_enabled",
    "isolation_notice",
    "ns",
    "platform_db",
    "project_root",
    "reset_plugin_registry",
    "reset_request_context",
    "resolve_fixture",
    "resolve_prepare",
    "shared_db_url",
    "shared_platform_db_url",
    "shared_platform_engine",
    "shared_tenant_db_url",
    "shared_tenant_engine",
    "test_db_dir",
    "version_for",
    "worker_id_for_snowflake",
)


def clear_isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """删除 `BMS_` 前缀环境变量（保留 `BMS_TEST_` 前缀，供测试自身固定注入）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)


def worker_id_for_snowflake() -> int:
    """当前执行 worker 的雪花 WorkerId（串行 0，xdist `gw0`→1、`gw1`→2 …）。

    为什么需要：雪花 ID 的 WorkerId 缺省 0，而 `-n auto` 下多个 worker 会在**同一毫秒**各自从
    序列 0 开始生成 → 不同进程产出**相同 ID**。实测后果：跨库 2PC 用例的 XA `XID`
    （`<全局事务 ID>|<分支>` 派生）撞上另一 worker 已开的同名分支，报 MySQL `XAER_DUPID`。
    按 worker 编号错开工作节点位后，并行进程的 ID 空间互不相交。

    Returns:
        int: 0 ~ 2^40-1 的 WorkerId。
    """
    name = os.environ.get("PYTEST_XDIST_WORKER", "")
    index = int(name[2:]) + 1 if name.startswith("gw") and name[2:].isdigit() else 0
    return index % (MAX_WORKER_ID + 1)


@pytest.fixture(name="bms_isolate_settings")
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清 `BMS_` 环境变量与 `.env` 读取、关闭真实 provider、重置配置单例。

    夹具名为 `bms_isolate_settings`（避免与仓库 / 服务 conftest 的 `isolate_settings` 覆盖冲突：
    后者需显式依赖本夹具以「先公共隔离、后服务追加」）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    clear_isolated_env(monkeypatch)
    # 单库化（04-6-2）：库一律走共享测试库 / 白名单独占库的**显式 URL**，不再按 worker 派生 sqlite_dir；
    # 连接串模板同样固定关闭（dev 默认启用「每服务每租户」模板，会让显式 URL 失效）
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # 可观测真实 provider 关闭：避免单元用例引入全局 TracerProvider / 导出线程与网络噪声
    monkeypatch.setenv("BMS_METRICS__PROVIDER", "")
    monkeypatch.setenv("BMS_TRACER__PROVIDER", "")
    # 跨服务调用 / 会话存储 / 限流真实实现关闭：单测不真实外呼、不连 Redis
    monkeypatch.setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    monkeypatch.setenv("BMS_SESSION_STORE__PROVIDER", "")
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "")
    monkeypatch.setenv("BMS_REDIS__PROVIDER", "")
    monkeypatch.setenv("BMS_REDIS__REQUIRED", "false")
    monkeypatch.setenv("BMS_IDEMPOTENCY__PROVIDER", "")
    monkeypatch.setenv("BMS_CONSISTENCY_BARRIER__PROVIDER", "")
    monkeypatch.setenv("BMS_CACHE__PROVIDER", "memory")
    monkeypatch.setenv("BMS_CAPTCHA__PROVIDER", "")
    monkeypatch.setenv("BMS_MASKING__PROVIDER", "")
    monkeypatch.setenv("BMS_DISTRIBUTED_LOCK__PROVIDER", "")
    # 操作审计中间件（06_01）默认关闭：单测不因每个写请求额外写发件箱（审计专项用例显式开启）
    monkeypatch.setenv("BMS_AUDIT_LOG__ENABLED", "false")
    # 权限 / 数据范围强制占位：`get_settings()` 是进程级单例，服务套件（platform / identity）会在
    # `prepare_settings` 里把它改成 `provider = rbac`；同进程跑其他套件（含基座自身不登记数据来源的
    # 测试应用）时若沿用该残留，装配期即按「`rbac` 却无取数实现」拒启（与用例意图无关）。
    # 置空后 `resolve_plugin` 回落到 `null` 占位实现，用例结果与套件执行顺序无关；
    # 真实 RBAC 的判定口径由各服务 `tests/permission/` 专项用例自建校验器 / 数据来源覆盖。
    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "")
    monkeypatch.setenv("BMS_DATA_SCOPE__PROVIDER", "")
    # 三层权限缓存是**进程级单份**（`04-2`）：跨套件 / 跨用例共用会串味（同租户同用户同版本命中别处数据）
    reset_permission_cache_store()
    # 并行下 WorkerId 必须按 worker 错开（缺省 0 会让多进程同毫秒生成相同雪花 ID；见
    # `worker_id_for_snowflake`）。经配置注入，lifespan 的 `validate_startup` 会据此重设生成器。
    monkeypatch.setenv("BMS_APP__WORKER_ID", str(worker_id_for_snowflake()))
    # WorkerId 动态注册（03_06）在单测里关闭：注册要连 Redis 并逐用例占号，会与上面的按 worker 注入
    # 冲突（每用例一套 fakeredis，占号无意义）；注册路径由 `tests/workerid/` 专项用例显式开启覆盖。
    monkeypatch.setenv("BMS_WORKER_ID__ENABLED", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    reset_permission_cache_store()


def resolve_fixture(request: pytest.FixtureRequest, name: str) -> Any | None:
    """尝试解析指定夹具；套件未提供该夹具时返回 `None`（不报错）。

    注意：不能用 `request.fixturenames` 判断——它只含**已解析**的夹具（依赖链），
    不含「可用但尚未请求」的夹具（如仅定义在 conftest 里的 `platform_db_url`）。

    Args:
        request: pytest 夹具请求。
        name: 夹具名。

    Returns:
        Any | None: 夹具值；缺失时为 `None`。
    """
    try:
        return request.getfixturevalue(name)
    except pytest.FixtureLookupError:
        return None


def apply_platform_db(url: Any, monkeypatch: pytest.MonkeyPatch) -> bool:
    """把平台库 URL 注入 `BMS_DATABASE__PLATFORM__URL` 并重置配置单例。

    Args:
        url: 会话级平台库连接串；`None` 表示本套件不使用平台库。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        bool: 是否已应用（`False` 表示无平台库、已跳过）。
    """
    if url is None:
        return False
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", str(url))
    get_settings.cache_clear()
    return True


@pytest.fixture
def platform_db(
    isolate_settings: None, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """平台库隔离：把平台库 URL 指向会话级种子库。

    - 显式依赖 `bms_isolate_settings`：保证「先清环境、后设 URL」的顺序；
    - 无 `platform_db_url` 的套件（如交易服务单测不依赖平台库）自动跳过，不报夹具缺失。

    Args:
        isolate_settings: 配置隔离夹具（仅用于排序）。
        request: pytest 夹具请求（判断是否需要平台库）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    if not apply_platform_db(resolve_fixture(request, "platform_db_url"), monkeypatch):
        yield
        return
    yield
    get_settings.cache_clear()


@pytest.fixture
def reset_request_context() -> Iterator[None]:
    """用例结束后复位请求上下文（链路 / 请求 / 来源 / 租户 / 用户），防跨用例污染。

    Yields:
        None: 用例运行期。
    """
    yield
    current_trace_id.set(None)
    current_request_id.set(None)
    current_client_ip.set(None)
    current_tenant.set(None)
    current_tenant_id.set(None)
    current_tenant_context_var.set(None)
    current_user_id.set(None)


@pytest.fixture
def reset_plugin_registry() -> Iterator[None]:
    """用例结束后解除插件注册表冻结，防跨用例顺序敏感。

    Yields:
        None: 用例运行期。
    """
    yield
    from bms_core.core.plugin import default_plugin_registry

    default_plugin_registry().reset()


def clear_tenant_cache(app: object) -> None:
    """清空应用租户源的进程内缓存 Region（进程级缓存实例，防跨用例残留）。

    Args:
        app: 应用实例（取 `state.tenant_source.cache`）。
    """
    state = getattr(app, "state", None)
    source = getattr(state, "tenant_source", None)
    cache = getattr(source, "cache", None)
    if isinstance(cache, MemoryCacheRegion):
        cache.clear()


TEST_DB_DIRNAME = "test"
"""会话测试库子目录名（落 `<仓内>/.cache/test/`，与覆盖率产物 `.cache/coverage/` 同区）。"""

ISOLATED_ENV = "BMS_TEST_ISOLATED_DB"
"""隔离调试开关（需求 04-6 第 3 条）：置 `1` 时共享库改落 basetemp 下的独立目录。"""

_ISOLATED_DIRNAME = "test-db-isolated"
"""隔离调试库目录名（`<basetemp>/test-db-isolated/`，仅单例调 bug 时使用）。"""

_FALSE_VALUES = frozenset({"", "0", "false", "no"})


def isolation_enabled() -> bool:
    """是否处于隔离调试模式（`BMS_TEST_ISOLATED_DB=1`）。

    仅用于单例调特定 bug 时拿一套干净库；默认关闭，单文件 / 单用例调试与 CI 同口径。

    Returns:
        bool: 开关是否打开。
    """
    return os.environ.get(ISOLATED_ENV, "").strip().lower() not in _FALSE_VALUES


def isolation_notice() -> str:
    """隔离调试模式的会话头提示（未开启时返回空串）。

    Returns:
        str: 空串或一行醒目提示。
    """
    if not isolation_enabled():
        return ""
    return f"[bms_testing_plugin] 当前为隔离调试模式（{ISOLATED_ENV}=1）：测试库落 {test_db_dir()}，结果不代表 CI 口径"


_INIT_TIMEOUT = 120.0
"""共享库初始化等待上限（秒）；超时即红，不做无限等待。"""

_LOCK_STALE = 120.0
"""残留锁判定阈值（秒）：锁文件 mtime 超过该值视为上次进程崩溃。"""

_READY_POLL = 0.2
"""非选主 worker 轮询 `.ready` 的间隔（秒）。"""


def test_db_dir() -> Path:
    """会话测试库目录。

    常规模式落 `<工程根>/.cache/test`（工程根由插件在会话起始钉定，缺省即当前工作目录）；
    隔离调试模式（`BMS_TEST_ISOLATED_DB=1`）落 `<工程根>/.cache/test-db-isolated`。

    Returns:
        Path: 已创建的目录。
    """
    subdir = _ISOLATED_DIRNAME if isolation_enabled() else TEST_DB_DIRNAME
    directory = project_root() / ".cache" / subdir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def shared_db_url(name: str) -> str:
    """共享库连接串（固定路径，全 worker 共用）。

    Args:
        name: 逻辑数据源名（如 `platform` / `tenant`）。

    Returns:
        str: `sqlite+aiosqlite:///<绝对路径>`。
    """
    return f"sqlite+aiosqlite:///{(test_db_dir() / f'{name}.db').as_posix()}"


def clear_shared_db_files() -> ConcurrentStableList[str]:
    """清空会话测试库目录下的库文件与就绪标记（会话开始调用）。

    删除失败（Windows 句柄未释放）时跳过并返回失败清单，由调用方告警，不中断整轮。

    Returns:
        ConcurrentStableList[str]: 未能删除的文件名清单。
    """
    directory = test_db_dir()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(directory.glob("*")):
        name = path.name
        if name == "namespace-map.jsonl":
            continue
        if not (
            path.suffix in (".db", ".ready", ".lock", "") or name.startswith(".init") or name.endswith(("-wal", "-shm"))
        ):
            continue
        try:
            path.unlink()
        except OSError:
            failed.append(path.name)
    return failed


@contextmanager
def _init_lock(name: str) -> Generator[None]:
    """文件锁选主（`O_CREAT|O_EXCL`）；残留锁按 mtime 判过期后重抢一次。

    Args:
        name: 逻辑数据源名。

    Yields:
        None: 持有锁期间。

    Raises:
        TimeoutError: 120 秒内未抢到锁。
    """
    lock = test_db_dir() / f"{name}.init.lock"
    deadline = time.monotonic() + _INIT_TIMEOUT
    while True:
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = time.time() - lock.stat().st_mtime > _LOCK_STALE
            except OSError:
                stale = False
            if stale:
                with suppress(OSError):
                    lock.unlink()
                continue
            if time.monotonic() > deadline:
                listing = sorted(p.name for p in test_db_dir().glob("*"))
                raise TimeoutError(f"共享库初始化锁超时（{_INIT_TIMEOUT:.0f}s）：{lock}；目录内容 {listing}") from None
            time.sleep(_READY_POLL)
            continue
        os.close(handle)
        break
    try:
        yield
    finally:
        with suppress(OSError):
            lock.unlink()


def _default_prepare(url: str) -> None:
    """缺省建库（同步入口）：按已导入模型的 `Base.metadata` 建表（不含业务种子）。

    Args:
        url: 共享库连接串。
    """
    asyncio.run(_default_prepare_async(url))


async def _default_prepare_async(url: str) -> None:
    """缺省建库（异步入口）：同步版在事件循环里调用会撞 `asyncio.run`。

    Args:
        url: 共享库连接串。
    """
    from bms_core.models.base import Base

    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def ensure_shared_db(
    name: str,
    prepare: Callable[[str], None] | None = None,
    *,
    version: str = "1",
) -> str:
    """确保共享库已就绪（全 worker 只建一次），返回连接串（同步入口）。

    同步入口自己跑选主与等待：准备回调多为**同步**包装（内部再 `asyncio.run` 建库播种），
    交给异步版本会与外层事件循环嵌套冲突。异步夹具请改用 `ensure_shared_db_async`。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。
        prepare: 建库与播种回调（缺省只建表）；只在选主 worker 上执行一次。
        version: schema 版本戳；与 `.ready` 内容不一致即重建。

    Returns:
        str: 共享库连接串。

    Raises:
        TimeoutError: 等待初始化就绪超时。
    """
    url = shared_db_url(name)
    ready = test_db_dir() / f"{name}.ready"

    def _is_ready() -> bool:
        """就绪判据：标记存在且版本戳一致。"""
        return ready.exists() and ready.read_text(encoding="utf-8").strip() == version

    if _is_ready():
        return url
    with _init_lock(name):
        # 抢到锁后再判一次：可能上一个持锁者已经建好
        if _is_ready():
            return url
        (prepare or _default_prepare)(url)
        ready.write_text(version, encoding="utf-8")
    deadline = time.monotonic() + _INIT_TIMEOUT
    while not _is_ready():
        if time.monotonic() > deadline:
            listing = sorted(p.name for p in test_db_dir().glob("*"))
            raise TimeoutError(f"共享库就绪标记未出现：{ready}（目录内容 {listing}）") from None
        time.sleep(_READY_POLL)
    return url


async def ensure_shared_db_async(
    name: str,
    prepare: Callable[[str], Any] | None = None,
    *,
    version: str = "1",
) -> str:
    """确保共享库已就绪（异步版）：协程回调直接 `await`，同步回调退化为同步实现。

    为什么需要异步版：准备集本身是异步的（建表 + 播种走 SQLAlchemy async 引擎），
    而异步夹具（`pytest_asyncio` 的 `async def` 夹具）里不能再 `asyncio.run`——
    同步包装器内部一 `asyncio.run` 就会撞上外层事件循环。

    与同步版的差异：异步版自己抢初始化锁阻塞等待（锁内已完成准备），因此不需要再轮询
    `.ready`——本进程写完标记即可返回。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。
        prepare: 建库与播种回调（协程函数优先；同步回调走同步实现）；只在选主者上执行一次。
        version: schema 版本戳；与 `.ready` 内容不一致即重建。

    Returns:
        str: 共享库连接串。
    """
    if prepare is not None and not inspect.iscoroutinefunction(prepare):
        return ensure_shared_db(name, prepare, version=version)
    url = shared_db_url(name)
    ready = test_db_dir() / f"{name}.ready"

    def _is_ready() -> bool:
        """就绪判据：标记存在且版本戳一致（库文件完整性由准备集自身负责）。"""
        return ready.exists() and ready.read_text(encoding="utf-8").strip() == version

    if _is_ready():
        return url
    with _init_lock(name):
        # 抢到锁后再判一次：可能上一个持锁者已经建好
        if _is_ready():
            return url
        if prepare is None:
            await _default_prepare_async(url)
        else:
            await prepare(url)
        ready.write_text(version, encoding="utf-8")
    return url


def resolve_prepare(request: pytest.FixtureRequest, name: str) -> Callable[[str], None] | None:
    """解析套件自定义的建库回调。

    解析顺序（04-6-2 决策 15）：`{name}_db_prepare` → `shared_db_prepare`（兼容回退）。
    platform / tenant 的准备内容不同（建表集与种子各异），故按数据源分别取名，
    避免共用单一回调后靠库文件名猜数据源。

    Args:
        request: pytest 夹具请求。
        name: 逻辑数据源名（`platform` / `tenant`）。

    Returns:
        Callable[[str], None] | None: 回调；套件未提供时为 `None`（走缺省建表）。
    """
    for fixture_name in (f"{name}_db_prepare", "shared_db_prepare"):
        candidate = resolve_fixture(request, fixture_name)
        if candidate is not None and callable(candidate):
            return cast("Callable[[str], None]", candidate)
    return None


def version_for(prepare: Callable[[str], None] | None) -> str:
    """由准备集所在模块的源码派生 `.ready` 版本戳（准备内容一改即变）。

    为什么自动派生：手写常量需要人记得改，忘了就是「改了种子但旧库沿用」——
    现象是诡异的断言失败而非明确报错。取准备回调所在文件的摘要，改注释也会触发一次
    重建（只影响下一次会话，可忽略）。

    Args:
        prepare: 建库回调；`None` 表示走缺省建表（版本戳固定 `1`）。

    Returns:
        str: 12 位十六进制摘要；无法定位源文件时返回 `1`。
    """
    if prepare is None:
        return "1"
    try:
        source = inspect.getsourcefile(prepare)
    except OSError, TypeError:
        # 内置函数 / `exec` 动态编译的函数取不到源文件：退回缺省版本戳
        return "1"
    if not source:
        return "1"
    try:
        return hashlib.sha256(Path(source).read_bytes()).hexdigest()[:12]
    except OSError:
        return "1"


@pytest.fixture(scope="session")
def shared_platform_db_url(request: pytest.FixtureRequest) -> str:
    """共享平台库（`platform`，全 worker 共用、会话开始删库重建）。

    Args:
        request: pytest 夹具请求（取套件自定义建库回调）。

    Returns:
        str: 平台库连接串。
    """
    prepare = resolve_prepare(request, "platform")
    return ensure_shared_db("platform", prepare, version=version_for(prepare))


@pytest.fixture(scope="session")
def shared_tenant_db_url(request: pytest.FixtureRequest) -> str:
    """共享租户库（`tenant`，全 worker 共用、会话开始删库重建）。

    Args:
        request: pytest 夹具请求（取套件自定义建库回调）。

    Returns:
        str: 租户库连接串。
    """
    prepare = resolve_prepare(request, "tenant")
    return ensure_shared_db("tenant", prepare, version=version_for(prepare))


@pytest.fixture
async def shared_platform_engine(shared_platform_db_url: str) -> AsyncIterator[AsyncEngine]:
    """共享平台库引擎（用例级，`NullPool`：用完即断，不跨用例串事务）。

    为什么放在基座：单库叠加口径下，用例**不得**自己 `create_async_engine`（护栏 G1 拦），
    需要直连共享库时一律经本夹具；`NullPool` 保证用例结束后连接不残留未提交事务。

    Args:
        shared_platform_db_url: 共享平台库连接串（会话级）。

    Yields:
        AsyncEngine: 指向共享平台库的引擎。
    """
    engine = create_async_engine(shared_platform_db_url, poolclass=NullPool, connect_args={"timeout": 30})
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def shared_tenant_engine(shared_tenant_db_url: str) -> AsyncIterator[AsyncEngine]:
    """共享租户库引擎（用例级，`NullPool`）。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级）。

    Yields:
        AsyncEngine: 指向共享租户库的引擎。
    """
    engine = create_async_engine(shared_tenant_db_url, poolclass=NullPool, connect_args={"timeout": 30})
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
def ns(request: pytest.FixtureRequest) -> Iterator[Namespace]:
    """当前用例的命名空间（单库叠加下生成唯一编码 / 限定断言）。

    Args:
        request: pytest 夹具请求。

    Yields:
        Namespace: 用例命名空间。
    """
    yield namespace_module.for_test(request)
