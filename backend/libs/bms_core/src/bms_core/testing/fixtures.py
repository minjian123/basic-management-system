"""pytest 公共夹具（13_04）：配置隔离 / 平台库 / 请求上下文 / 插件注册表。

收编口径：与各 `conftest.py` 同名同语义，**存量用例零改动**；仓库 / 服务专属的差异
（`configure_token_env`、fakeredis、服务环境变量）由各自 conftest 覆写本模块夹具并追加，
不在包内依赖 `tests_support`（保证产品仓可直接复用）。
"""

import asyncio
import hashlib
import importlib
import inspect
import os
import shutil
import time
from collections.abc import AsyncIterator, Callable, Generator, Iterable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Final, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
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
from bms_core.core.id import MAX_WORKER_ID, id_generator
from bms_core.db.gate import db_access_gate
from bms_core.db.sqlite import create_async_engine, sqlite_busy_timeout_seconds
from bms_core.permission.cache import reset_permission_cache_store
from bms_core.testing import namespace as namespace_module
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE, GatedEngine
from bms_core.testing.namespace import Namespace
from bms_core.testing.paths import configure_project_root, project_root

__all__ = (
    "TEST_DB_DIRNAME",
    "apply_platform_db",
    "clear_shared_db_files",
    "clear_tenant_cache",
    "configure_project_root",
    "ensure_shared_db",
    "isolated_topology",
    "isolation_enabled",
    "isolation_notice",
    "needed_shared_databases",
    "ns",
    "platform_db",
    "prepare_shared_databases",
    "project_root",
    "require_shared_db",
    "reset_plugin_registry",
    "reset_request_context",
    "resolve_fixture",
    "resolve_prepare",
    "shared_db_url",
    "shared_platform_db_url",
    "shared_platform_engine",
    "shared_tenant_db_url",
    "shared_tenant_engine",
    "tenant_db",
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
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    _reset_isolated_runtime(_apply_isolated_env(monkeypatch.setenv))
    yield
    get_settings.cache_clear()
    reset_permission_cache_store()


def _apply_isolated_env(setenv: Callable[[str, str], None]) -> int:
    """把测试隔离环境逐项写入给定 setter（函数级 `monkeypatch.setenv` / 模块级 `os.environ`）。

    单一实现：函数级夹具与模块级夹具都经这里写入，避免两套环境清单漂移。

    Args:
        setenv: 环境变量写入函数。

    Returns:
        int: 按 worker 注入的雪花 WorkerId（供调用方重设生成器）。
    """
    # 单库化（04-6-2）：库一律走共享测试库 / 白名单独占库的**显式 URL**，不再按 worker 派生 sqlite_dir；
    # 连接串模板同样固定关闭（dev 默认启用「每服务每租户」模板，会让显式 URL 失效）
    setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    # 可观测真实 provider 关闭：避免单元用例引入全局 TracerProvider / 导出线程与网络噪声
    setenv("BMS_METRICS__PROVIDER", "")
    setenv("BMS_TRACER__PROVIDER", "")
    # 跨服务调用 / 会话存储 / 限流真实实现关闭：单测不真实外呼、不连 Redis
    setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    setenv("BMS_SESSION_STORE__PROVIDER", "")
    setenv("BMS_RATE_LIMITER__PROVIDER", "")
    setenv("BMS_REDIS__PROVIDER", "")
    setenv("BMS_REDIS__REQUIRED", "false")
    setenv("BMS_IDEMPOTENCY__PROVIDER", "")
    setenv("BMS_CONSISTENCY_BARRIER__PROVIDER", "")
    # 事件消费运行时关闭（13_08）：dev 环境覆盖打开真实 msg 消费，单进程测试没有消息平台对端，
    # 装配期 `BaseEventConsumerGroup.setup()` 会按组发起连接，逐个消费组等 DNS 超时（本机实测
    # `http://msg:8000` 每次 2.7s × 8 次 ≈ 21.5s，占 `test_root_returns_app_info` setup 的 86%）。
    # 只关 `enabled`、不动 `provider`：配置分层读到的实现选择仍是真实值，真实消费由
    # `tests/integration/test_event_bus_msg.py` 等专项用例显式开启。
    setenv("BMS_EVENT_CONSUMER__ENABLED", "false")
    setenv("BMS_CACHE__PROVIDER", "memory")
    setenv("BMS_CAPTCHA__PROVIDER", "")
    setenv("BMS_MASKING__PROVIDER", "")
    setenv("BMS_DISTRIBUTED_LOCK__PROVIDER", "")
    # 拓扑分发关闭（2026-11-16）：分发失败改拒启后，单测没有「平台已就绪」的对端，
    # 属「本来就该关」的配置而非降级；验证分发的用例直接构造 Settings(distribute=True)。
    setenv("BMS_TOPOLOGY__DISTRIBUTE", "false")
    # 单进程测试没有平台对端：启动期目录校验显式关闭（不是容错，是「无对端」的环境配置）；
    # 校验本身由 `tests/core/test_service_catalog_startup.py` 显式开启覆盖。
    setenv("BMS_APP__VALIDATE_CATALOG_ON_STARTUP", "false")
    # 接库初始化只做一次（13_08 T7）：共享库结构 / 表归属登记由准备集建好，每个用例再重做一遍
    # 只会把跨进程写门排队时间翻倍（实测 1.4 秒/用例，24 路并行完全不提速）。需要验证这些启动
    # 步骤的用例显式把本开关置回 false（直接调用对应函数亦可）。
    setenv("BMS_APP__SKIP_DB_INIT", "true")
    # 运行期改表结构在测试里一律关闭（13_08 T7）：结构只有「数据初始化」一次机会，请求路径只写
    # 元数据等初始化补建列。测试加载的 `config.dev.toml` 把这个开关置成了 true（开发态即时建列），
    # 必须在这里显式关回去；需要真跑建列的用例只在 `own_db` 独占临时库上单点置 true。
    setenv("BMS_APP__ALLOW_RUNTIME_DDL", "false")
    # 操作审计中间件（06_01）默认关闭：单测不因每个写请求额外写发件箱（审计专项用例显式开启）
    setenv("BMS_AUDIT_LOG__ENABLED", "false")
    # 权限 / 数据范围强制占位：`get_settings()` 是进程级单例，服务套件（platform / identity）会在
    # `prepare_settings` 里把它改成 `provider = rbac`；同进程跑其他套件（含基座自身不登记数据来源的
    # 测试应用）时若沿用该残留，装配期即按「`rbac` 却无取数实现」拒启（与用例意图无关）。
    # 置空后 `resolve_plugin` 回落到 `null` 占位实现，用例结果与套件执行顺序无关；
    # 真实 RBAC 的判定口径由各服务 `tests/permission/` 专项用例自建校验器 / 数据来源覆盖。
    setenv("BMS_PERMISSION__PROVIDER", "")
    setenv("BMS_DATA_SCOPE__PROVIDER", "")
    # 并行下 WorkerId 必须按 worker 错开（缺省 0 会让多进程同毫秒生成相同雪花 ID；见
    # `worker_id_for_snowflake`）。经配置注入，lifespan 的 `validate_startup` 会据此重设生成器；
    # **同时直接重设一次**——不启应用的用例（交易 2PC 真库用例直接构造协调器）没有 lifespan，
    # 只靠配置注入会一直用 WorkerId=0，多 worker 同毫秒仍生成相同雪花 ID（派生同一 XA `xid`，
    # MySQL 报 `XAER_DUPID`；bms#1629 实测）。
    worker_id = worker_id_for_snowflake()
    setenv("BMS_APP__WORKER_ID", str(worker_id))
    # WorkerId 动态注册（03_06）在单测里关闭：注册要连 Redis 并逐用例占号，会与上面的按 worker 注入
    # 冲突（每用例一套 fakeredis，占号无意义）；注册路径由 `tests/workerid/` 专项用例显式开启覆盖。
    setenv("BMS_WORKER_ID__ENABLED", "false")
    return worker_id


def _reset_isolated_runtime(worker_id: int) -> None:
    """应用隔离环境的进程级副作用（权限缓存 / 雪花生成器 / 配置单例）。

    Args:
        worker_id: `_apply_isolated_env` 返回的 WorkerId。
    """
    # 三层权限缓存是**进程级单份**（`04-2`）：跨套件 / 跨用例共用会串味（同租户同用户同版本命中别处数据）
    reset_permission_cache_store()
    id_generator.reconfigure(worker_id)
    get_settings.cache_clear()


@pytest.fixture(name="bms_isolated_env_module", scope="module")
def isolated_env_module() -> Iterator[None]:
    """模块级隔离环境：装配常驻（`service_app` 提 module 级）要求隔离先于装配就位。

    为什么需要：pytest 先建高作用域夹具，模块级 `service_app` 会比函数级 `bms_isolate_settings`
    先执行；若环境仍是真实配置，应用装配会按真实 Redis / 拓扑 / 令牌启动而拒启。

    单一实现：环境清单复用 `_apply_isolated_env`；退出时把环境与配置模型整体还原，
    不向其它模块泄漏。

    Yields:
        None: 模块运行期。
    """
    snapshot = dict(os.environ)
    previous_env_file = Settings.model_config.get("env_file")
    for key in [item for item in os.environ if item.startswith("BMS_") and not item.startswith("BMS_TEST_")]:
        del os.environ[key]
    Settings.model_config["env_file"] = None
    _reset_isolated_runtime(_apply_isolated_env(lambda key, value: os.environ.__setitem__(key, value)))
    try:
        yield
    finally:
        for key in [item for item in os.environ if item not in snapshot]:
            del os.environ[key]
        os.environ.update(snapshot)
        Settings.model_config["env_file"] = previous_env_file
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
def tenant_db(shared_tenant_db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """把租户库连接串指向共享租户库（单库叠加口径）。

    与各服务 conftest 的同名夹具同义：用例显式请求本夹具才注入，未请求的套件不受影响。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级）。
        monkeypatch: pytest monkeypatch 夹具。

    Returns:
        str: 共享租户库连接串。
    """
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()
    return shared_tenant_db_url


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
    """用例前后解除插件注册表冻结，防跨用例 / 跨模块导入顺序敏感。

    为什么前后都要复位：测试模块在**导入期**可能触发 `build_plugin_registry()`
    （如 `bms_core.jobs.plugins`），而导入发生在两个用例之间、不在任何用例的清理范围内；
    只在用例结束后复位，下一个用例仍可能带着冻结注册表启动（表现为装配期登记直接抛
    `PluginError`，且与 xdist 分片顺序有关）。

    Yields:
        None: 用例运行期。
    """
    from bms_core.core.plugin import default_plugin_registry

    default_plugin_registry().reset()
    yield
    default_plugin_registry().reset()


@pytest.fixture
def isolated_topology() -> Iterator[None]:
    """用例隔离：保存并恢复进程级拓扑状态（快照 / 当前版本 / 实例上下文）。

    拓扑快照与实例上下文是**进程级可变全局**：能力入站的域归属判定（`instance_domains()`）
    与单元寻址直接读它们，不经数据库。用例改写后不恢复，同 worker 的后继用例会看到被改过的
    域集合，表现为「业务域未在本实例启用」的 403——这与「本用例的库是否干净」无关，
    靠独占库无法隔离。范式与 `isolate_catalog_records` 的其余进程级表一致：用例前留存、
    用例后恢复（留存而非清空，使不经装配直调解析函数的用例仍看到与用例开始前一致的状态）。

    Yields:
        None: 用例运行期。
    """
    from bms_core.collaboration.topology import restore_topology_state, topology_state

    state = topology_state()
    yield
    restore_topology_state(state)


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


_INIT_TIMEOUT = 10.0
"""共享库初始化等待上限（秒）；超时即红，不做无限等待（2026-11-21 统一收到 10s）。"""

_LOCK_STALE = 5.0
"""残留锁判定阈值（秒）：锁文件 mtime 超过该值视为上次进程崩溃。

**必须小于 `_INIT_TIMEOUT`**：两者相等时，等待方会在超时前一刻同时判陈旧、同时 `unlink`、
同时重建，Windows 上「删除挂起 + 新建同名」会抛 `PermissionError`（13_08 实测：24 路并行
一次打出 29 个 setup 错误）。留一半余量，让回收发生在放弃等待之前。
"""

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


def shared_db_path(name: str) -> Path:
    """共享库文件路径（`<会话测试库目录>/<name>.db`）。

    Args:
        name: 逻辑数据源名（如 `platform` / `tenant`）。

    Returns:
        Path: 共享库文件路径。
    """
    return test_db_dir() / f"{name}.db"


def db_file_identity(database: str) -> str:
    """库文件路径的归一形态（门名判定的唯一口径：同库必同串、异库必异串）。

    只做「绝对化 + 正斜杠 + 小写」：不做 `resolve()`（会跟随符号链接且慢），也不读文件系统。
    Windows 大小写不敏感，故统一小写；跨进程判定因此稳定。

    Args:
        database: 库文件路径（SQLite 连接串的 `database` 段 / 引擎 URL 的 `database`）。

    Returns:
        str: 归一后的库身份串。
    """
    return Path(database).expanduser().absolute().as_posix().casefold()


def shared_db_identity(name: str) -> str:
    """共享库的归一身份串（与 `db_file_identity` 同口径，供门名判定比对）。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。

    Returns:
        str: 归一后的共享库身份串。
    """
    return db_file_identity(shared_db_path(name).as_posix())


def shared_db_url(name: str) -> str:
    """共享库连接串（固定路径，全 worker 共用）。

    **`?timeout=<当前值>`**（测试缺省 0.1s）：共享库的写排队只走读写门，SQLite 自己只做毫秒级
    兜底（建表检查 / WAL checkpoint），不承担数据排队（2026-11-22 业主口径）。
    查询参数由 SQLAlchemy 透传给 sqlite3，任何用本连接串建的引擎（夹具 / 直连辅助 / 应用会话）
    都得到同一口径；真正绕过门的长时间冲突仍会很快报 `database is locked`。

    Args:
        name: 逻辑数据源名（如 `platform` / `tenant`）。

    Returns:
        str: `sqlite+aiosqlite:///<绝对路径>?timeout=0.1`。
    """
    path = shared_db_path(name).as_posix()
    return f"sqlite+aiosqlite:///{path}?timeout={sqlite_busy_timeout_seconds():g}"


def clear_shared_db_files(*, include_databases: bool = True) -> ConcurrentStableList[str]:
    """清空会话测试库目录下的库文件、就绪标记与残留锁（会话开始调用）。

    删除失败（Windows 句柄未释放）时跳过并返回失败清单，由调用方分级处置：
    **残留锁删不掉必须阻断**（会把整轮拖成等锁超时），库文件删不掉只告警。

    目录（如历史遗留的 `cov_dummy`）走 `rmtree`——旧实现用 `unlink` 删目录必然失败，
    会被误报成「句柄占用」。

    Args:
        include_databases: 是否连库文件与就绪标记一起删（初始化阶段自己按数据源删，传 False）。

    Returns:
        ConcurrentStableList[str]: 未能删除的文件名清单。
    """
    directory = test_db_dir()
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for path in sorted(directory.glob("*")):
        name = path.name
        if name == "namespace-map.jsonl":
            continue
        if not include_databases and (path.suffix in (".db", ".ready") or name.endswith(("-wal", "-shm", "-journal"))):
            continue
        # 读写门锁文件是**常驻**的：互斥由内核字节锁保证（进程退出自动回收），文件本身无需清空。
        # 上一轮进程被强杀时句柄尚未释放会让 `unlink` 失败，若按「残留锁」判死会误把整轮拒启
        # （13_08 实测：全量进程被终止后下一次会话直接 `RuntimeError: 残留测试锁清理失败`）。
        if name.startswith("db-gate-") and name.endswith(".lock"):
            continue
        if not (
            path.suffix in (".db", ".ready", ".lock", "") or name.startswith(".init") or name.endswith(("-wal", "-shm"))
        ):
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
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
        except FileExistsError, PermissionError:
            # Windows：目标文件「删除挂起」或正被他人创建时，`O_CREAT|O_EXCL` 抛的是
            # `PermissionError`（EACCES）而不是 `FileExistsError`。按同一语义处理（视为有人
            # 持锁、继续轮询），否则一次竞争就会把整批 worker 打成 setup 错误。
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
                holder = "未知"
                with suppress(OSError):
                    holder = lock.read_text(encoding="utf-8").strip() or "空"
                raise TimeoutError(
                    f"共享库初始化锁超时（{_INIT_TIMEOUT:.0f}s）：{lock}；持有者 {holder}；目录内容 {listing}"
                ) from None
            time.sleep(_READY_POLL)
            continue
        os.close(handle)
        with suppress(OSError):
            lock.write_text(f"pid={os.getpid()} at={time.strftime('%H:%M:%S')}", encoding="utf-8")
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


def _ready_stamp(ready: Path) -> str:
    """读取就绪标记内容（探针用；读不到给 `<none>`）。

    Args:
        ready: 就绪标记路径。

    Returns:
        str: 标记内容或 `<none>`。
    """
    try:
        return ready.read_text(encoding="utf-8").strip() or "<empty>"
    except OSError:
        return "<none>"


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
        from bms_core.testing import lock_probe

        lock_probe.note(
            "rebuild",
            f"{name} old={_ready_stamp(ready)} new={version} dir={test_db_dir()} "
            f"src={_source_file(prepare) if prepare else None}",
        )
        stuck = _drop_shared_db_files(name)
        if stuck:
            raise PermissionError(
                f"[bms_testing] 共享库重建失败：{list(stuck)} 被占用删不掉；"
                f"请结束占用进程或删除 {test_db_dir()} 下的同名文件后重跑"
            )
        (prepare or _default_prepare)(url)
        ready.write_text(version, encoding="utf-8")
        lock_probe.note("rebuild-done", f"{name} {version}")
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
        """就绪判据：标记存在且版本戳一致。"""
        return ready.exists() and ready.read_text(encoding="utf-8").strip() == version

    if _is_ready():
        return url
    with _init_lock(name):
        # 抢到锁后再判一次：可能上一个持锁者已经建好
        if _is_ready():
            return url
        from bms_core.testing import lock_probe

        lock_probe.note(
            "rebuild",
            f"{name} old={_ready_stamp(ready)} new={version} dir={test_db_dir()} "
            f"src={_source_file(prepare) if prepare else None}",
        )
        stuck = _drop_shared_db_files(name)
        if stuck:
            # 版本戳重建路径：删不掉就不能沿用旧库（`create_all(checkfirst=True)` 只补表不补列，
            # 沿用会得到「表在、列缺」的库），必须显式失败而不是告警。
            raise PermissionError(
                f"[bms_testing] 共享库重建失败：{list(stuck)} 被占用删不掉；"
                f"请结束占用进程或删除 {test_db_dir()} 下的同名文件后重跑"
            )
        if prepare is None:
            await _default_prepare_async(url)
        else:
            await prepare(url)
        ready.write_text(version, encoding="utf-8")
        lock_probe.note("rebuild-done", f"{name} {version}")
    return url


def _drop_shared_db_files(name: str) -> ConcurrentStableList[str]:
    """删掉共享库文件（含 WAL / 日志伴生文件），**返回删不掉的清单**。

    为什么必须删：`prepare` 内部是 `create_all(checkfirst=True)`，**只补表不补列**；
    模型加一列后仅重跑准备集会得到「表在、列缺」的库，报 `no such column` 且永远自愈不了
    （2026-11-21 实测）。版本戳一变就删库，重建才是真正的「结构重建」。

    为什么返回而不是抛：同一段清理在两种场景下要求不同——会话入口清场（`reset_shared_databases`）
    遇到 Windows 句柄占用应**告警后继续**（《测试规范》「库文件清不掉只告警」）；版本戳重建
    （`ensure_shared_db`）遇到占用则**必须失败**（无法重建就不能沿用旧库）。判定权留给调用方。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。

    Returns:
        ConcurrentStableList[str]: 删除失败的文件名（空表示全部删净）。
    """
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    directory = test_db_dir()
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = directory / f"{name}.db{suffix}"
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except PermissionError:
            failed.add(path.name)
    return failed


_SHARED_DB_NAMES: Final = ("platform", "tenant")
"""共享测试库的数据源名（会话入口清场的固定范围）。"""


def reset_shared_databases() -> ConcurrentStableList[str]:
    """会话入口清场：删掉上一轮遗留的共享库与就绪标记（控制器 / 单进程调用一次）。

    为什么每轮重建：测试期连接是**真自动提交**（写入即落库、会话退出不回滚），同一用例在
    新会话里重跑会读到上一轮自己的行——轻则断言漂移，重则撞唯一键（实测：24 路全量后紧接着
    跑定向测试，8 条作业域用例因 `sys_job_monitor` / `sys_job_type` 残留失败）。

    时序：本函数只在**所有 worker 起来之前**执行（`pytest_configure`，非 worker 进程）；
    建库仍由初始化阶段（`pytest_collection_modifyitems`）负责——先删库、再建库、再跑用例。

    并发前提：同一时刻只跑一个 pytest 会话（多会话共用 `.cache/test` 会互相删库）。

    Returns:
        ConcurrentStableList[str]: 删不掉的条目（库文件 / 就绪标记）；空表示清场完成。
            由调用方分级处置：库文件删不掉只告警（本轮改用新建库），残留 `.lock` 删不掉才阻断。
    """
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    for name in _SHARED_DB_NAMES:
        failed.extend(_drop_shared_db_files(name))
        marker = test_db_dir() / f"{name}.ready"
        try:
            marker.unlink(missing_ok=True)
        except PermissionError:
            failed.add(marker.name)
    return failed


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


_SCHEMA_SOURCE_PACKAGES: Final = ("bms_core.models",)
"""参与共享库版本戳的模型源码包：模型加列 / 改约束必须让共享库自动重建。

产品仓若有自有模型包，可在自己的准备夹具里调用 `version_for(..., packages=(...))` 追加。
"""


def version_for(prepare: Callable[[str], None] | None, *, packages: Iterable[str] = ()) -> str:
    """派生 `.ready` 版本戳（准备集源码 + 指定模型包源码；任一变化即重建）。

    为什么自动派生：手写常量需要人记得改，忘了就是「改了种子但旧库沿用」——
    现象是诡异的断言失败而非明确报错。取准备回调所在文件的摘要，改注释也会触发一次
    重建（只影响下一次会话，可忽略）。

    **模型源码必须一起参与**（2026-11-21 实测的坑）：只摘要准备集源码时，模型加一列不会改变
    版本戳，`create_all(checkfirst=True)` 又只补表不补列，共享库便永久停在旧结构上，报
    `no such column`。把模型包源码纳入后，改模型即自动重建，不再依赖人工在准备集里 bump 注释。

    Args:
        prepare: 建库回调；`None` 表示走缺省建表。
        packages: 参与摘要的模型包名（其目录下全部 `.py` 递归计入）。

    Returns:
        str: 12 位十六进制摘要；准备集与模型包都无法定位源码时返回 `1`。
    """
    hasher = hashlib.sha256()
    digested = False
    if prepare is not None:
        source = _source_file(prepare)
        if source:
            try:
                hasher.update(Path(source).read_bytes())
                digested = True
            except OSError:
                return "1"
    for package in packages:
        digest = _package_source_digest(package)
        if digest:
            hasher.update(digest.encode("utf-8"))
            digested = True
    return hasher.hexdigest()[:12] if digested else "1"


def _source_file(obj: object) -> str | None:
    """取对象所在源文件路径（取不到返回 None，不抛错）。

    Args:
        obj: 函数 / 模块等可定位源码的对象。

    Returns:
        str | None: 源文件绝对路径；动态编译或无 `__file__` 时为 None。
    """
    try:
        return inspect.getsourcefile(obj)  # pyright: ignore[reportArgumentType]
    except OSError, TypeError:
        return None


def _package_source_digest(package: str) -> str:
    """取包目录下全部 `.py` 的源码摘要（按相对路径排序；读失败的文件跳过）。

    Args:
        package: 包名（如 `bms_core.models`）。

    Returns:
        str: 十六进制摘要；包不可导入或无 `__file__` 时返回空串。
    """
    try:
        module = importlib.import_module(package)
    except ImportError:
        return ""
    module_file = getattr(module, "__file__", None)
    if not module_file:
        return ""
    directory = Path(cast("str", module_file)).parent
    hasher = hashlib.sha256()
    for path in sorted(directory.rglob("*.py")):
        hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
        with suppress(OSError):
            hasher.update(path.read_bytes())
    return hasher.hexdigest()


def require_shared_db(name: str, *, version: str) -> str:
    """校验共享库已由**初始化阶段**建好（worker 侧只校验，绝不重建）。

    为什么不再允许 worker 重建：并发用例开跑后，任何 worker 发现版本戳不一致就删库重建，
    会在别的 worker 读写中途把共享库删掉（Windows 上是 `WinError 32`，非 Windows 上是数据被清空 /
    `database is locked`）。初始化是**独立阶段**：worker 在收集完成、跑用例前统一建库，之后只读校验。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。
        version: 当前代码期望的版本戳。

    Returns:
        str: 共享库连接串。

    Raises:
        RuntimeError: 库文件缺失、就绪标记缺失，或版本戳与当前代码不一致。
    """
    url = shared_db_url(name)
    directory = test_db_dir()
    ready = directory / f"{name}.ready"
    database = directory / f"{name}.db"
    if not database.exists():
        raise RuntimeError(
            f"共享库文件缺失：{database}。初始化阶段没跑到（须先建库、后跑用例）；"
            "请从工程根启动 pytest，或检查控制器是否加载了 bms_core.testing.plugin。"
        )
    if not ready.exists():
        raise RuntimeError(
            f"共享库未初始化：{ready} 不存在。共享库现在由**初始化阶段**在跑用例前统一建库；"
            "请从工程根启动 pytest（勿在 worker 里手工建库）。"
        )
    stamp = ready.read_text(encoding="utf-8").strip()
    if stamp != version:
        raise RuntimeError(
            f"共享库版本戳不一致：{name}.ready={stamp}，当前代码期望 {version}。"
            "初始化阶段未能完成（或库是上一版代码建的）。重新跑一次即可：初始化阶段会删库重建。"
        )
    return url


def needed_shared_databases(items: Iterable[Any]) -> ConcurrentStableList[str]:
    """从收集到的用例推断本次会话需要哪些共享库（初始化阶段用）。

    判据是用例的夹具闭包：直接或间接依赖 `shared_platform_db_url` / `shared_tenant_db_url`
    即视为需要（服务 conftest 的 `platform_db_url` / `tenant_db` 都依赖它们，闭包里一定出现）。

    Args:
        items: 收集到的用例项。

    Returns:
        ConcurrentStableList[str]: 需要建的数据源名（`platform` / `tenant`，可同时）。
    """
    closure: ConcurrentStableSet[str] = ConcurrentStableSet()
    for item in items:
        closure.update(getattr(item, "fixturenames", ()))
    needed: ConcurrentStableList[str] = ConcurrentStableList()
    if {"shared_platform_db_url", "shared_platform_engine", "platform_db", "platform_db_url"} & closure:
        needed.add("platform")
    if {"shared_tenant_db_url", "shared_tenant_engine", "tenant_db", "tenant_db_url"} & closure:
        needed.add("tenant")
    return needed


def prepare_shared_databases(names: Iterable[str]) -> ConcurrentStableList[str]:
    """**初始化阶段**：在跑任何用例之前把共享库建好（每个数据源只建一次，全程持写门）。

    为什么要单列阶段：建表 + 播种是「读 → 写」的长事务（实测 2.4s），并发用例开跑后再建，
    其它 worker 的门内写会在 SQLite 层撞上这把写锁（`database is locked`），甚至被删库。

    幂等与并发：就绪标记命中即跳过；未命中时由 `ensure_shared_db` 在 `_init_lock` 里选主重建，
    其余调用方等到就绪标记出现后直接返回——因此允许多个 worker 同时调用。

    准备回调从 `tests_support.shared_db` 取（`prepare_platform` / `prepare_tenant`）；
    产品仓可用环境变量 `BMS_TEST_SHARED_DB_MODULE` 指定自己的模块。

    Args:
        names: 需要建的数据源（`platform` / `tenant`；由收集到的用例实际用到的夹具决定）。

    Returns:
        ConcurrentStableList[str]: 本次真正建过的数据源名（已就绪的不计）。

    Raises:
        RuntimeError: 需要建库但找不到准备回调模块。
    """
    module = _load_prepare_module()
    built: ConcurrentStableList[str] = ConcurrentStableList()
    for name in names:
        attribute = f"prepare_{name}"
        prepare = getattr(module, attribute, None) if module is not None else None
        if prepare is None:
            raise RuntimeError(
                f"缺少共享库准备回调 {attribute}：初始化阶段无法建库。"
                "请在工程根提供 tests_support/shared_db.py（或设置 BMS_TEST_SHARED_DB_MODULE）。"
            )
        version = version_for(prepare, packages=_SCHEMA_SOURCE_PACKAGES)
        if _shared_db_ready(name, version):
            continue
        # 就绪标记内容可能与当前版本戳相同、但库文件已被删空（上次进程崩溃 / 手工删库）：
        # `ensure_shared_db` 以标记为「已建好」，必须先把标记清掉，让它走重建分支。
        (test_db_dir() / f"{name}.ready").unlink(missing_ok=True)
        print(f"[bms_testing_plugin] 初始化阶段：建共享库 {name}（先建库、后跑用例）", flush=True)
        asyncio.run(_build_shared_db_under_gate(name, prepare, version))
        built.add(name)
    return built


def _shared_db_ready(name: str, version: str) -> bool:
    """就绪判据：标记内容等于版本戳，且库文件存在且非空（被删空的文件不算就绪）。

    Args:
        name: 逻辑数据源名。
        version: 期望版本戳。

    Returns:
        bool: 就绪返回 True。
    """
    directory = test_db_dir()
    database = directory / f"{name}.db"
    try:
        if database.stat().st_size == 0:
            return False
        return (directory / f"{name}.ready").read_text(encoding="utf-8").strip() == version
    except OSError:
        return False


async def _build_shared_db_under_gate(name: str, prepare: Callable[[str], None], version: str) -> None:
    """在**该库自己的**写门内建一个共享库（初始化阶段唯一入口）。

    门必须按库取（「按库一把门」，门粒度是实际库文件）：建租户库若取平台门，并发的租户库写者
    不受该门约束，会在 0.1s 忙等后报 `database is locked`——实测末批 24 路会话起始数秒内成片
    失败、全部落在租户库表；探针显示 `rebuild tenant` 整段落在 `platform rw` 区间内、租户门为空。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。
        prepare: 建库与播种回调（同步实现，内部自开事件循环）。
        version: 版本戳。
    """
    # 初始化阶段只有控制器一个进程，取门只为守住「所有数据库读写都走门」的口径；
    # 真正的互斥价值在测试期：worker 侧不会再有第二个建库者。
    gate_name = TENANT_GATE if name == TENANT_GATE else PLATFORM_GATE
    async with db_access_gate(gate_name, read_only=False, wait=_INIT_TIMEOUT):
        await asyncio.to_thread(ensure_shared_db, name, prepare, version=version)


def module_prepare(name: str) -> Callable[[str], None] | None:
    """从准备模块取建库回调（`tests_support.shared_db.prepare_<name>`）。

    为什么要它与夹具回调并用：**版本戳必须两边算得一样**。初始化阶段
    （`prepare_shared_databases`）按本模块取回调；而 worker 侧夹具用的是「套件声明的
    `{name}_db_prepare`」——某些工程根（如 `libs/bms_core`）的 conftest 不声明该夹具，
    夹具侧便拿不到回调、版本戳退化成「只摘要模型包」，与初始化阶段写入的戳不一致，表现为
    `共享库版本戳不一致` 的 setup 报错。故夹具侧在拿不到套件回调时**回落到同一模块**。

    Args:
        name: 逻辑数据源名（`platform` / `tenant`）。

    Returns:
        Callable[[str], None] | None: 建库回调；模块缺失或未提供时为 None。
    """
    module = _load_prepare_module()
    candidate = getattr(module, f"prepare_{name}", None) if module is not None else None
    return cast("Callable[[str], None]", candidate) if callable(candidate) else None


def _load_prepare_module() -> Any | None:
    """载入准备回调模块（`tests_support.shared_db`，可由环境变量覆盖）。

    Returns:
        Any | None: 模块；找不到为 None。
    """
    candidates = ConcurrentStableList(
        [os.environ.get("BMS_TEST_SHARED_DB_MODULE", "").strip() or "tests_support.shared_db"]
    )
    for candidate in candidates:
        try:
            return importlib.import_module(candidate)
        except ImportError:
            continue
    return None


@pytest.fixture(scope="session")
def shared_platform_db_url(request: pytest.FixtureRequest) -> str:
    """共享平台库（`platform`，控制器在 worker 起来前建好；worker 只校验）。

    Args:
        request: pytest 夹具请求（取套件自定义建库回调，仅用于派生版本戳）。

    Returns:
        str: 平台库连接串。
    """
    prepare = resolve_prepare(request, "platform") or module_prepare("platform")
    return require_shared_db("platform", version=version_for(prepare, packages=_SCHEMA_SOURCE_PACKAGES))


@pytest.fixture(scope="session")
def shared_tenant_db_url(request: pytest.FixtureRequest) -> str:
    """共享租户库（`tenant`，控制器在 worker 起来前建好；worker 只校验）。

    Args:
        request: pytest 夹具请求（取套件自定义建库回调，仅用于派生版本戳）。

    Returns:
        str: 租户库连接串。
    """
    prepare = resolve_prepare(request, "tenant") or module_prepare("tenant")
    return require_shared_db("tenant", version=version_for(prepare, packages=_SCHEMA_SOURCE_PACKAGES))


@pytest.fixture
async def shared_platform_engine(shared_platform_db_url: str) -> AsyncIterator[AsyncEngine]:
    """共享平台库引擎（用例级，`NullPool`：用完即断，不跨用例串事务）。

    为什么放在基座：单库叠加口径下，用例**不得**自己 `create_async_engine`（护栏 G1 拦），
    需要直连共享库时一律经本夹具；`NullPool` 保证用例结束后连接不残留未提交事务。

    返回的是 `GatedEngine` 代理：`connect()` 的每次执行走读门、`begin()` 的每次执行走写门，
    读完 / 写完立即放。直连读事务若不入门，24 路并行下会长期持有 SQLite 读锁，写者在写门里
    等库锁满 10 秒（2026-11-21 实测）。

    Args:
        shared_platform_db_url: 共享平台库连接串（会话级）。

    Yields:
        AsyncEngine: 指向共享平台库的门代理引擎。
    """
    engine = create_async_engine(
        shared_platform_db_url,
        poolclass=NullPool,
        # 与 `shared_db_url` 的 `?timeout=` 同口径：数据排队只在读写门上，数据库层只做毫秒级兜底。
        # 原先硬编码 30s 会让「持门等 SQLite 写锁」最长持续 30s，其它 worker 等门 5s/10s 全超时。
        connect_args={"timeout": sqlite_busy_timeout_seconds()},
        isolation_level="AUTOCOMMIT",
    )
    gated = GatedEngine(engine, PLATFORM_GATE)
    try:
        yield cast("AsyncEngine", gated)
    finally:
        await engine.dispose()


@pytest.fixture
async def shared_tenant_engine(shared_tenant_db_url: str) -> AsyncIterator[AsyncEngine]:
    """共享租户库引擎（用例级，`NullPool`；门代理与平台库同口径）。

    Args:
        shared_tenant_db_url: 共享租户库连接串（会话级）。

    Yields:
        AsyncEngine: 指向共享租户库的门代理引擎。
    """
    engine = create_async_engine(
        shared_tenant_db_url,
        poolclass=NullPool,
        connect_args={"timeout": sqlite_busy_timeout_seconds()},
        isolation_level="AUTOCOMMIT",
    )
    gated = GatedEngine(engine, TENANT_GATE)
    try:
        yield cast("AsyncEngine", gated)
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
