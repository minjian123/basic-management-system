"""pytest 公共夹具（13_04）：配置隔离 / 平台库 / 请求上下文 / 插件注册表。

收编口径：与各 `conftest.py` 同名同语义，**存量用例零改动**；仓库 / 服务专属的差异
（`configure_token_env`、fakeredis、服务环境变量）由各自 conftest 覆写本模块夹具并追加，
不在包内依赖 `tests_support`（保证产品仓可直接复用）。
"""

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from bms_core.cache.memory import MemoryCacheRegion
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


def clear_isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """删除 `BMS_` 前缀环境变量（保留 `BMS_TEST_` 前缀，供测试自身固定注入）。

    Args:
        monkeypatch: pytest monkeypatch 夹具。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)


_sqlite_basetemp = ""
"""pytest basetemp（xdist worker 下为 `<basetemp>/popen-gwN`）；由 `plugin.pytest_configure` 注入。"""

_SQLITE_TEMP_SUBDIR = "bms-pytest-sqlite"
"""无 basetemp 时的兜底目录（系统临时目录下，按 worker 再分一层）。"""


def configure_sqlite_basetemp(value: str) -> None:
    """记录 pytest basetemp，供 `worker_sqlite_dir` 派生 worker 目录。

    Args:
        value: pytest basetemp 路径（空串表示不介入）。
    """
    global _sqlite_basetemp
    _sqlite_basetemp = value or ""


def worker_sqlite_dir() -> str:
    """并行执行（pytest-xdist）下本 worker 专属的 SQLite 文件目录。

    SQLite 文件库在并行 worker 间共享同一路径会产生跨 worker 行级干扰（用例互相看到对方写入的行），
    表现为随机的断言失败；按 worker 分配独立目录后每个 worker 拥有独立库文件。

    目录 = `<basetemp>/sqlite-<worker>`（无 basetemp 时落系统临时目录下 `bms-pytest-sqlite/`），
    首次解析自动建目录。

    Returns:
        str: 目录路径；串行执行（无 `PYTEST_XDIST_WORKER`）时返回空串（沿配置原值）。
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER", "")
    if not worker:
        return ""
    base = Path(_sqlite_basetemp) if _sqlite_basetemp else Path(tempfile.gettempdir()) / _SQLITE_TEMP_SUBDIR
    directory = base / f"sqlite-{worker}"
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory)


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
    # 并行执行：SQLite 文件库按 worker 隔离（串行时为空串，沿配置原值）
    sqlite_dir = worker_sqlite_dir()
    if sqlite_dir:
        monkeypatch.setenv("BMS_DATABASE__SQLITE_DIR", sqlite_dir)
    # 固定关闭库连接串模板（dev 默认启用「每服务每租户」模板，会让显式 URL 失效）
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
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
