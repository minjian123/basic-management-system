"""pytest 公共夹具：ASGI 内存客户端（免启服务器）+ 配置环境隔离 + 平台库租户种子。"""

import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import get_settings
from bms_core.core.exceptions import MultipleActiveTenantsError
from bms_core.db.tenant import DEMO_TENANT, TenantContext, TenantNotFoundError
from bms_core.testing.fixtures import (
    clear_tenant_cache,
    platform_db,
    reset_request_context,
)
from bms_core.testing.fixtures import (
    isolate_settings as bms_isolate_settings,
)

__all__ = ("bms_isolate_settings", "platform_db", "reset_request_context")
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

    async def single_active(self) -> TenantContext | None:
        """唯一启用租户解析（本替身含 2 个租户 → 恒多启用）。"""
        raise MultipleActiveTenantsError("测试替身：多个启用租户")

    def _tenants(self) -> ConcurrentStableDict[str, TenantContext]:
        """演示 / 示例租户上下文（带雪花主键与固定库键）。"""
        return ConcurrentStableDict(
            {
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
        )


@pytest.fixture(autouse=True)
def _plugin_fixtures(  # pyright: ignore[reportUnusedFunction]
    platform_db: None, reset_request_context: None, reset_plugin_registry: None
) -> None:
    """启用测试公共基座的公共夹具（平台库 / 请求上下文 / 插件注册表复位）。

    夹具实现单源在 `bms_core.testing.fixtures`；本包装只负责在本套件启用
    （交易服务单测不依赖平台库，故不启用）。
    """


@pytest.fixture(autouse=True)
def isolate_settings(bms_isolate_settings: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """服务专属隔离：在公共隔离之后追加 SSO 状态存储关闭、fakeredis 与测试令牌密钥。

    Args:
        bms_isolate_settings: 公共隔离夹具（保证顺序）。
        monkeypatch: pytest monkeypatch 夹具。

    Yields:
        None: 用例运行期。
    """
    from tests_support.redis import install_process_fake_redis_client

    install_process_fake_redis_client()
    # SSO 流程状态存储（02_01）：单测不连 Redis，回落 Null
    monkeypatch.setenv("BMS_IDP_STATE_STORE__PROVIDER", "")
    # 登录态依赖真实化（01_05）：注入测试用户令牌密钥，使受保护路由在真实鉴权下可验签
    configure_token_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def platform_db_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """会话级平台库：临时 `sys_tenant` 种子库（建库 / 播种整个测试会话只做一次）。

    Args:
        tmp_path_factory: pytest 临时目录工厂。

    Returns:
        str: 会话级平台库连接串。
    """
    platform_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('platform') / 'app.db'}"
    asyncio.run(seed_tenants(platform_url))
    return platform_url


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
