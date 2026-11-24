"""测试基座插件（13_04）：夹具注册与并行 SQLite 隔离的公共实现。

加载方式有两种，按仓库形态选择：

- **bms 仓**：`addopts = "-p bms_testing_plugin"`（`backend/bms_testing_plugin.py`）——该启动插件
  在**最早**阶段启动覆盖率采集，再在 `pytest_configure` 里注册本模块；这样被测模块的「导入期执行行」
  也能被采集（13_02）。
- **产品仓**：可直接 `-p bms_core.testing.plugin`（本模块）复用夹具；覆盖率采集时机由产品仓自管。

为什么不用各 conftest 写 `pytest_plugins`：pytest 7+ 禁止**非顶层 conftest** 声明
`pytest_plugins`，而本项目有 10 个测试根（每个工程一个 conftest），故统一由 `-p` 加载。

注意：`pytest_plugins` 在「由 `-p` 加载的插件模块」中**不会**再被处理（该机制只对 conftest 生效），
故这里的夹具必须显式导入到本模块命名空间，pytest 才会收集注册。
"""

import hashlib
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import AbstractAsyncContextManager, suppress
from typing import Any, cast

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.db.gate import set_gate_hook, set_gate_requirement
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.testing import ddl, fixtures
from bms_core.testing.fixtures import (
    clear_shared_db_files,
    clear_tenant_cache,
    configure_project_root,
    ensure_shared_db,
    isolate_settings,
    isolated_topology,
    ns,
    platform_db,
    project_root,
    reset_plugin_registry,
    reset_request_context,
    resolve_prepare,
    shared_db_url,
    shared_platform_db_url,
    shared_platform_engine,
    shared_tenant_db_url,
    shared_tenant_engine,
    shared_tenant_writable_db_url,
    tenant_db,
    test_db_dir,
)
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE, close_gates, gate_scope
from bms_core.testing.write_locks import platform_db_write, tenant_db_write

__all__ = (
    "clear_shared_db_files",
    "clear_tenant_cache",
    "configure_project_root",
    "ensure_shared_db",
    "isolate_settings",
    "isolated_topology",
    "ns",
    "platform_db",
    "platform_db_write",
    "project_root",
    "reset_plugin_registry",
    "reset_request_context",
    "resolve_prepare",
    "shared_db_url",
    "shared_platform_db_url",
    "shared_platform_engine",
    "shared_tenant_db_url",
    "shared_tenant_engine",
    "shared_tenant_writable_db_url",
    "tenant_db",
    "tenant_db_write",
    "test_db_dir",
)


_OWN_GATE_PREFIX = "own-"
"""私有库（非共享测试库）的门名前缀。"""


def _db_identity(url: str) -> str:
    """把连接串归一成「库的身份」（库文件绝对路径小写串；非文件库退回 URL 主体）。

    归一的目的：同一个库经不同写法（`sqlite+aiosqlite:///D:/…` 与 `sqlite:///D:/…`、带不带
    `?timeout=`）必须落到同一个门名，否则同一个库会出现两把门、又回到互相争用。

    Args:
        url: 数据库连接串。

    Returns:
        str: 库身份（跨进程稳定）。
    """
    text = url.split("?", 1)[0]
    try:
        database = make_url(url).database or ""
    except ArgumentError, ValueError:
        return text.casefold()
    if not database:
        return text.casefold()
    if database.startswith("file:"):
        database = database[len("file:") :]
    return fixtures.db_file_identity(database)


def gate_name_for(db_key: str, url: str | None = None) -> str:
    """把「数据源键 + 实际库连接串」归一到门名（**按库排队**，见 `bms_core.testing.gates`）。

    共享测试库（`.cache/test/platform.db` / `tenant.db`）映射为 `platform` / `tenant`，诊断文本
    与既有采样汇总保持不变；其余库（`own_db` / `tmp_path` 建的一次性库）按库文件路径哈希得到
    `own-xxxxxxxx`，与共享库的门彻底分开——私有库的建表 / 播种不再占住共享库的排队路径。

    Args:
        db_key: 数据源键（调用方掌握的唯一信息；不掌握实际库时作为回落依据）。
        url: 本次操作实际指向的库连接串；None 按数据源键回落。

    Returns:
        str: 门名。
    """
    if not url:
        return PLATFORM_GATE if db_key == PLATFORM_DB_KEY else TENANT_GATE
    identity = _db_identity(url)
    for name in (PLATFORM_GATE, TENANT_GATE):
        if identity == fixtures.shared_db_identity(name):
            return name
    digest = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:8]
    return f"{_OWN_GATE_PREFIX}{digest}"


def _gate_hook(
    db_key: str, read_only: bool, wait: float | None = None, url: str | None = None
) -> AbstractAsyncContextManager[None]:
    """把会话入口的「数据源键 + 实际库」映射到读写门（13_08 注入点）。

    Args:
        db_key: 数据源键（平台库键或租户库键）。
        read_only: 是否只读。
        wait: 等待上限（秒）；None 走默认（写门 5s / 读门 10s）。
        url: 实际库连接串（决定门名）；None 按数据源键回落。

    Returns:
        AbstractAsyncContextManager[None]: 读门或写门上下文。
    """
    return gate_scope(gate_name_for(db_key, url), read_only=read_only, wait=wait)


def _gate_required(session: object) -> bool:
    """判定该会话是否必须经过门：只有指向**共享库**的会话才必须。

    独占库（`own_db` / `tmp_path` 的一次性库）与其它 worker 无共享状态，不取门也不会抢锁；
    共享库（平台 / 租户）必须排队，否则绕过写门直接与 `write_session` 抢 SQLite 写锁。

    Args:
        session: 会话对象（需有 `bind` 属性）。

    Returns:
        bool: True 表示绑工作单元前必须已过门。
    """
    bind = getattr(session, "bind", None)
    raw_url = getattr(bind, "url", None)
    if raw_url is None:
        return False
    return gate_name_for(PLATFORM_DB_KEY, str(raw_url)) in (PLATFORM_GATE, TENANT_GATE)


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True, name="assembled_system")
async def _assembled_system_fixture(shared_platform_db_url: str, shared_tenant_db_url: str) -> AsyncIterator[Any]:
    """全系统装配（13_10）：初始化之后、用例之前，把本仓全部后端服务装配一次。

    实现在 `fixtures.assembled_system`；本夹具只负责绑定为 pytest 夹具（autouse session 级），
    这样各服务套件自成 rootdir 时也能取到同一份装配，不依赖根 conftest。

    Args:
        shared_platform_db_url: 会话级共享平台库连接串（保证初始化先完成）。
        shared_tenant_db_url: 会话级共享租户库连接串。

    Yields:
        Any: `AssembledSystem` 或 `None`（被 `BMS_TEST_ASSEMBLED=0` 关闭）。
    """
    generator = fixtures.assembled_system(shared_platform_db_url, shared_tenant_db_url)
    try:
        yield await anext(generator)
    finally:
        await generator.aclose()


@pytest.fixture(autouse=True)
def _reset_audit_staging() -> Iterator[None]:
    """每例清空审计事件暂存区（13_10：装配常驻后的每例复位项）。

    装配的系统在后台运行时也会 `stage_event`；暂存区是 ContextVar，与用例同 context 时
    会在用例请求收尾被一并 drain，表现为「本用例多出不属于它的事件」。

    Yields:
        None: 用例运行期。
    """
    from bms_core.audit.staging import reset_staged

    reset_staged()
    yield
    reset_staged()


@pytest.fixture(autouse=True)
def _reset_assembled_per_test() -> Iterator[None]:
    """每例复位已装配系统里跨用例存活的缓存（不重建应用；13_10）。

    装配常驻后 `service_app` 是会话级的「取实例」夹具，原先挂在它上面的每例清理没有执行点，
    统一收到这里：前后各复位一次，保证用例之间不串租户缓存。

    Yields:
        None: 用例运行期。
    """
    from bms_core.testing.system import get_assembled_system

    def _reset() -> None:
        try:
            system = get_assembled_system()
        except RuntimeError:  # pragma: no cover - 未装配时直通（装配由会话夹具保证）
            return
        system.reset_per_test()

    _reset()
    yield
    _reset()


def pytest_configure(config: pytest.Config) -> None:
    """把 pytest basetemp 交给测试基座（并行执行按 worker 派生独立 SQLite 目录；13_02）。

    xdist worker 的 basetemp 形如 `<根>/popen-gwN`，天然按 worker 隔离；交由
    `fixtures.worker_sqlite_dir` 派生 `<basetemp>/sqlite-gwN` 作为该 worker 的 `sqlite_dir`。

    同时补齐 `--basetemp` 的父目录：`addopts` 里的 `--basetemp=.cache/pytest` 指向仓内
    缓存目录，而 pytest 的 `TmpPathFactory.getbasetemp()` 只 `mkdir` 末级目录、**不递归建父目录**
    （`tmpdir.py` 中 `basetemp.mkdir(mode=0o700)`），父目录 `.cache` 不存在时 xdist 起 worker
    即 `FileNotFoundError` 崩掉。此处在本钩子里 `makedirs(exist_ok=True)`——本钩子早于
    `pytest_sessionstart`（xdist 在后者里才取 basetemp），故能保证父目录就位。

    Args:
        config: pytest 配置对象。
    """
    # 覆盖率入口守卫最先执行：`pytest --cov` / 换覆盖率落点在本钩子里直接终止（code=2）。
    # 本钩子被**所有**子工程 addopts（`-p bms_core.testing.plugin`）与工程根插件转调，是唯一全覆盖入口。
    from bms_core.testing.coverage_guard import assert_entrypoint

    assert_entrypoint(config)
    # 13_08：把会话入口的数据库访问接到跨进程读写门（生产侧是直通钩子，只在测试会话注入）
    set_gate_hook(_gate_hook)
    set_gate_requirement(_gate_required)
    # 2026-11-21 业主拍板：**测试里的读写全部按操作、autocommit**。应用请求会话的生产工厂是
    # 「一个请求一个事务」，事务未提交前会一直持有 SQLite 写锁，24 路并行下别的写者只能排队；
    # 测试会话统一换成 autocommit，每条 SQL 立即落库、立即释放数据库锁。
    _patch_session_factory_autocommit()
    _patch_sqlite_connections()
    # 2026-11-22 业主口径：**数据库层不再是排队主路径**。测试库忙等缺省 0.1s：只吸收 SQLite
    # 自身的瞬时独占（建表检查 / WAL checkpoint）；数据读写的排队仍只在读写门上发生。
    # `BMS_TEST_SQLITE_BUSY_TIMEOUT` 仅用于定位期调整（秒），缺省 0.1。
    from bms_core.db.sqlite import set_sqlite_busy_timeout

    set_sqlite_busy_timeout(_busy_timeout_from_env())
    _maybe_install_lock_probe()
    # 共享测试库基址钉在会话起始的工程根：用例 `chdir` 后解析夹具也不会把库落到临时目录
    # （否则表现为随机的「no such table」；见 `fixtures.configure_project_root`）。
    fixtures.configure_project_root(os.getcwd())
    # 单库叠加：DDL 串行化。并发 worker 同时首次建同一张表时，`create_all(checkfirst=True)` 的存在性
    # 判断看不到他人未提交的建表事务，后提交方撞 `table ... already exists`（服务子流水线实测）。
    ddl.serialize_ddl()
    basetemp = getattr(config.option, "basetemp", "") or ""
    if basetemp:
        # `abspath` 结果必然含父目录，无需再判空
        os.makedirs(os.path.dirname(os.path.abspath(os.fspath(basetemp))), exist_ok=True)
    # 13_10：全系统装配夹具（autouse session 级）随基座插件注册。服务套件自成 rootdir 时只加载
    # 本模块，根 conftest 不可见；实现在 `fixtures.assembled_system`，此处只做夹具绑定。
    manager = getattr(config, "pluginmanager", None)
    if manager is not None and manager.get_plugin("bms_testing_assembled_system") is None:
        manager.register(_assembled_system_fixture, "bms_testing_assembled_system")
    notice = fixtures.isolation_notice()
    if notice:
        print(notice)
    if not os.environ.get("PYTEST_XDIST_WORKER"):
        _prepare_test_dir()


_BUSY_TIMEOUT_DEFAULT = 0.1
"""测试库忙等上限缺省值（秒）：只吸收 SQLite 自身的瞬时独占，排队走读写门。"""


def _busy_timeout_from_env() -> float:
    """从环境变量解析测试库忙等上限（秒；非法值回落缺省 0.1）。

    Returns:
        float: 忙等上限（秒）。
    """
    raw = os.environ.get("BMS_TEST_SQLITE_BUSY_TIMEOUT", "").strip()
    try:
        return float(raw) if raw else _BUSY_TIMEOUT_DEFAULT
    except ValueError:
        return _BUSY_TIMEOUT_DEFAULT


def _prepare_test_dir() -> None:
    """会话入口的测试目录准备：**一次测试运行只在开始时删库重建**，同运行内的会话叠加复用。

    口径（2026-11-01 拍板原意）：「整个测试运行开始、数据初始化之前」可以删库重建；**同一次运行
    的后续会话必须叠加运行**，不得再删。判定靠 `BMS_TEST_RUN_ID`：与 `.cache/test/run.id` 一致即
    同一次运行（复用），否则视为新运行（删库重建并记下新 id）。未设该变量时（手工窄跑）每次
    pytest 调用自成一次运行。

    为什么必须在**所有 worker 起来之前**（控制器 / 单进程）做：否则删库会撞上正在跑用例的 worker。
    残留 `.lock` 直接失败——带锁开跑会把「一行启动错误」拖成一堆假超时（bms#1659 续修实测：
    8 worker × 300s）。

    Raises:
        RuntimeError: 残留 `.lock` 清不掉（有进程占着）。
    """
    failed: ConcurrentStableList[str] = ConcurrentStableList()
    if not _same_run():
        failed = fixtures.reset_shared_databases()
        _remember_run()
    failed.extend(fixtures.clear_shared_db_files(include_databases=False))
    stuck_locks = [name for name in failed if name.endswith(".lock")]
    if stuck_locks:
        raise RuntimeError(
            f"[bms_testing_plugin] 残留测试锁清理失败：{stuck_locks}；"
            f"请结束占用进程或手工删除 {fixtures.test_db_dir()} 下的同名 .lock 后重跑"
        )
    if failed:
        # 库文件删不掉只告警（《测试规范》：残留锁才阻断）：本轮会在新建库上继续跑。
        print(f"[bms_testing_plugin] 共享测试库清理失败（Windows 句柄占用）：{failed}；本轮改用新建库继续")


_RUN_ID_ENV = "BMS_TEST_RUN_ID"
"""测试运行标识：同一次运行（如一次推送预检的多批）由入口脚本写入同一值。"""

_RUN_MARKER = "run.id"
"""运行标识落点（`<测试库目录>/run.id`）：与当前 `BMS_TEST_RUN_ID` 一致即同一次运行。"""


def _same_run() -> bool:
    """本次会话是否与上一次建库属于同一次测试运行。

    Returns:
        bool: 运行标识非空且与标记一致返回 True（复用共享库）。
    """
    run_id = os.environ.get(_RUN_ID_ENV, "").strip()
    if not run_id:
        return False
    try:
        return (fixtures.test_db_dir() / _RUN_MARKER).read_text(encoding="utf-8").strip() == run_id
    except OSError:
        return False


def _remember_run() -> None:
    """把本次运行的标识写入标记（未设 `BMS_TEST_RUN_ID` 时清掉旧标记）。"""
    marker = fixtures.test_db_dir() / _RUN_MARKER
    run_id = os.environ.get(_RUN_ID_ENV, "").strip()
    with suppress(OSError):
        if run_id:
            marker.write_text(run_id, encoding="utf-8")
        else:
            marker.unlink(missing_ok=True)


def _maybe_install_lock_probe() -> None:  # pragma: no cover - 仅诊断期按环境变量开启，默认关闭
    """按 `BMS_TEST_LOCK_PROBE=1` 安装 SQLite 语句 / 门外写探针。"""
    if os.environ.get("BMS_TEST_LOCK_PROBE", "").strip() == "1":
        from bms_core.testing import lock_probe

        lock_probe.install()


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],  # bare-collections:allow - pytest 钩子签名（框架约定）
) -> None:
    """初始化阶段：**在跑任何用例之前**把共享库建好（首个进程建、其余等就绪）。

    放在收集完成时：此时才知道本次会话用不用共享库（纯单元测试不该为建库多花数秒）；
    xdist 下各 worker 都会走到这里，且都还没开始跑用例；幂等由 `_init_lock` 选主 +
    `.ready` 轮询保证。

    Args:
        config: pytest 配置（未使用，保留钩子签名）。
        items: 本次收集到的用例（读它们的夹具闭包）。
    """
    del config
    needed = fixtures.needed_shared_databases(items)
    if not needed:
        return
    fixtures.prepare_shared_databases(needed)


_original_session_create: Any = None
"""被替换前的 `SessionFactory.create`（会话结束时恢复）。"""


def _patch_session_factory_autocommit() -> None:
    """把测试用的会话工厂改成 autocommit（每条 SQL 立即落库、立即释放数据库锁）。"""
    global _original_session_create
    if _original_session_create is not None:
        return
    from bms_core.db.session import SessionFactory

    original = SessionFactory.create
    _original_session_create = original

    def _create(self: SessionFactory, engine: Any) -> Any:
        """SQLite 下按 autocommit 建会话工厂；正式数据库保持原事务语义。"""
        typed = cast("AsyncEngine", engine)
        if typed.url.get_backend_name() != "sqlite":  # pragma: no cover - 正式数据库不经测试基座的 autocommit 包装
            return original(self, typed)
        return original(self, typed.execution_options(isolation_level="AUTOCOMMIT"))

    SessionFactory.create = _create  # type: ignore[method-assign]


_original_sqlite_connect: Any = None
"""被替换前的 `sqlite3.connect`（会话结束时恢复）。"""


def _patch_sqlite_connections() -> None:
    """把测试期**每一个** SQLite 连接建成自动提交，并关掉 WAL 自动检查点。

    为什么改在最底层 `sqlite3.connect`：SQLAlchemy 的引擎工厂有多个入口（`bms_core.db.sqlite`
    统一入口、各处 `from sqlalchemy.ext.asyncio import create_async_engine` 的既有绑定），
    只包一层工厂函数覆盖不全——实测 `bms_core.testing.fixtures` 在插件导入时就绑定了原函数，
    共享库引擎因此一直是 SERIALIZABLE（事务跨语句开着、门已放但 SQLite 写锁还占着）。
    改在 DBAPI 建连处，无论引擎从哪条路径创建都生效。

    两项设置都是**连接级**、且都是测试口径：

    - `isolation_level=None`：每条 SQL 立即提交、立即放锁。显式要求隔离级别的引擎
      （如 `test_unit_of_work` 用真实事务验证回滚）由 SQLAlchemy 在建连后自行覆盖，不受影响。
    - `wal_autocheckpoint=0`：自动检查点由「最后一个提交的连接」顺手触发，与读写门无关；
      检查点期间别的连接会报 `SQLITE_BUSY`（探针里既找不到门外写者，也找不到持门的进程）。
      测试库只有几 MB，不检查点不会撑爆磁盘，会话结束删库时 WAL 一并清掉。

    作用域只到测试会话（`pytest_configure` 调用）；正式运行不经过本函数。
    """
    global _original_sqlite_connect
    if _original_sqlite_connect is not None:
        return
    import sqlite3

    original = sqlite3.connect
    _original_sqlite_connect = original

    def _connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        """建连时注入自动提交与测试 pragma。

        Args:
            *args: 透传 `sqlite3.connect`。
            **kwargs: 透传；未显式给隔离级别时按自动提交。

        Returns:
            sqlite3.Connection: 建好的连接。
        """
        kwargs.setdefault("isolation_level", None)
        connection = original(*args, **kwargs)
        # 只读 / 特殊 VFS 连接可能不支持该 pragma；失败不影响测试主流程
        with suppress(sqlite3.Error):
            connection.execute("PRAGMA wal_autocheckpoint=0")
        return connection

    sqlite3.connect = _connect  # type: ignore[assignment]


def _restore_sqlite_connections() -> None:
    """恢复被替换的 `sqlite3.connect`。"""
    global _original_sqlite_connect
    if _original_sqlite_connect is None:
        return
    import sqlite3

    sqlite3.connect = _original_sqlite_connect  # type: ignore[assignment]
    _original_sqlite_connect = None


def _restore_session_factory() -> None:
    """恢复被替换的 `SessionFactory.create`。"""
    global _original_session_create
    if _original_session_create is None:
        return
    from bms_core.db.session import SessionFactory

    SessionFactory.create = _original_session_create  # type: ignore[method-assign]
    _original_session_create = None


def pytest_sessionstart(session: pytest.Session) -> None:
    """会话开始：钉住分组调度模式（`xdist_group` 只在 loadgroup 下生效）。

    为什么不在 `pytest_configure`：xdist 自己的配置钩子会在其后重置 `dist`，这里已过全部
    配置阶段、早于 worker 派发，赋值才真正生效。

    Args:
        session: pytest 会话（取 config）。
    """
    session.config.option.dist = "loadgroup"


def pytest_unconfigure(config: pytest.Config) -> None:
    """会话结束：撤销数据库门钩子并关闭门句柄。

    Args:
        config: pytest 配置对象（未使用，保留签名）。
    """
    del config
    set_gate_hook(None)
    set_gate_requirement(None)  # pragma: no cover - pytest 退出钩子，覆盖率采集已停止
    _restore_session_factory()
    _restore_sqlite_connections()
    close_gates()
