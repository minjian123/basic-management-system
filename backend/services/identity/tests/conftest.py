"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

import asyncio
import os
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.cache.memory import MemoryCacheRegion
from bms_core.core.concurrent import ConcurrentStableDict
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
from bms_core.db.tenant import DEMO_TENANT, TenantContext, TenantNotFoundError
from bms_identity.main import ApplicationFactory
from ops.seed_tenant import seed_tenants
from tests_support.auth import auth_headers, configure_token_env

DEMO_TENANT_ID = "1001"
"""演示租户主键（雪花 id 字符串；与测试令牌 / 身份映射口径一致）。"""

ACME_TENANT_ID = "2002"
"""示例租户主键（雪花 id 字符串）。"""


class _SeedTenantSource:
    """身份服务单测租户源替身：返回带雪花主键的演示 / 示例租户上下文。

    身份服务单测禁用真实跨服务调用（`service_client` 为 Null），远端租户契约不可达时
    仅回落无主键的演示租户；而 `code → id` 边界解析要求租户上下文带主键，故用例统一注入本替身。
    """

    async def by_code(self, code: str) -> TenantContext:
        """按编码取租户（demo / acme）。"""
        for tenant in self._tenants().values():
            if tenant.code == code:
                return tenant
        raise TenantNotFoundError(f"未知租户：{code}")

    async def by_domain(self, domain: str) -> TenantContext:
        """按子域名取租户（demo / acme）。"""
        for tenant in self._tenants().values():
            if tenant.domain == domain:
                return tenant
        raise TenantNotFoundError(f"未知租户域名：{domain}")

    async def by_id(self, tenant_id: str) -> TenantContext:
        """按租户主键（雪花 id 字符串）取租户。"""
        for tenant in self._tenants().values():
            if tenant.tenant_id is not None and str(tenant.tenant_id) == tenant_id:
                return tenant
        raise TenantNotFoundError(f"未知租户主键：{tenant_id}")

    def _tenants(self) -> ConcurrentStableDict[str, TenantContext]:
        """演示 / 示例租户上下文（带雪花主键与固定库键）。"""
        return {
            "demo": TenantContext(
                code="demo",
                db_key=DEMO_TENANT.db_key,
                name="演示租户",
                domain="demo.bms.example.com",
                tenant_id=int(DEMO_TENANT_ID),
            ),
            "acme": TenantContext(
                code="acme",
                db_key="tenant_acme",
                name="示例租户",
                domain="acme.bms.example.com",
                tenant_id=int(ACME_TENANT_ID),
            ),
        }


@pytest.fixture(autouse=True)
def isolate_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """隔离配置：清除 `BMS_` 环境变量与 `.env` 读取，重置配置单例。

    Args:
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    for key in list(os.environ):
        if key.startswith("BMS_") and not key.startswith("BMS_TEST_"):
            monkeypatch.delenv(key, raising=False)
    # 测试会话固定关闭库连接串模板：dev 默认启用「每服务每租户」模板（06_01），
    # 会让用例显式指定的 `BMS_DATABASE__*__URL` 失效；模板行为由专门用例显式开启覆盖。
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL_TEMPLATE", "")
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL_TEMPLATE", "")
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # 可观测真实 provider 关闭（08_01）：避免单元用例引入全局 TracerProvider / 后台导出线程与网络噪声；
    # 真实实现用例显式开启（monkeypatch 覆盖 provider / 端点或注入 in-memory exporter）。
    monkeypatch.setenv("BMS_METRICS__PROVIDER", "")
    monkeypatch.setenv("BMS_TRACER__PROVIDER", "")
    # 跨服务调用 / 会话存储 / 限流真实实现关闭（01_03）：单测不真实外呼、不连 Redis
    monkeypatch.setenv("BMS_SERVICE_CLIENT__PROVIDER", "")
    monkeypatch.setenv("BMS_SESSION_STORE__PROVIDER", "")
    monkeypatch.setenv("BMS_RATE_LIMITER__PROVIDER", "")
    # 验证码真实实现关闭（03_01）：单测不连 Redis，回落 Null
    monkeypatch.setenv("BMS_CAPTCHA__PROVIDER", "")
    # 脱敏真实实现关闭（04_01）：单测回落 null 占位（真实实现用例显式开启）
    monkeypatch.setenv("BMS_MASKING__PROVIDER", "")
    # SSO 流程状态存储（02_01）：单测不连 Redis，回落 Null
    monkeypatch.setenv("BMS_IDP_STATE_STORE__PROVIDER", "")
    # 分布式锁（02_02）：单测不连 Redis，回落 Null（JIT 用例显式注入 MemoryDistributedLock）
    monkeypatch.setenv("BMS_DISTRIBUTED_LOCK__PROVIDER", "")
    # 登录态依赖真实化（01_05）：注入测试用户令牌密钥，使受保护路由在真实鉴权下可验签
    configure_token_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """会话级平台库：临时 `sys_tenant` 种子库（建库 / 播种整个测试会话只做一次）。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    return platform_url


@pytest.fixture(autouse=True)
def platform_db(platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """平台库隔离：把平台库 URL 指向会话级种子库（用例间不重复建库，仅重置配置单例）。

    Yields:
        None: 用例运行期。
    """
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", platform_db_url)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
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


@pytest.fixture
async def service_app() -> AsyncIterator[FastAPI]:
    """本服务应用实例夹具（经 lifespan 装配；供探针 / 应用级断言与 `client` 共用）。

    Yields:
        object: FastAPI 应用实例。
    """
    app = ApplicationFactory().create(None)
    app.state.tenant_source = _SeedTenantSource()
    clear_tenant_cache(app)
    try:
        async with app.router.lifespan_context(app):
            yield app
    finally:
        clear_tenant_cache(app)


@pytest.fixture
async def client(service_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """ASGITransport 异步客户端夹具（复用 `service_app`）。

    平台库与租户种子由 autouse 的 `platform_db` 夹具提供；租户缓存用例前后清空。
    """
    async with AsyncClient(transport=ASGITransport(app=service_app), base_url="http://test") as c:
        c.headers.update(auth_headers(tenant=DEMO_TENANT_ID))
        yield c
