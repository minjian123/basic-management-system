"""授权视图进程引导（07B `03_01`）：产品进程来源登记 + 承载域预热 + 降级语义。

覆盖详细设计 §3.8 / §6 用例 20 的基座部分：远端来源登记、只按承载域预热（不请求消费方维度）、
来源不可达时告警降级（不拒启）且首访仍 fail-closed、装配缺客户端按配置漂移拒启。
"""

from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI

from bms_core.collaboration import (
    bootstrap_remote_capability_grants,
    capability_grant_pairs,
    ensure_grant_view,
    reset_capability_grants,
    warm_capability_grant_views,
)
from bms_core.collaboration.bootstrap import GRANT_VIEW_DEGRADED_FLAG
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.services.module_registry import (
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)

SERVICE_KEY = "demo"
"""本服务标识（承载 `org` 域）。"""

GRANT_VIEW_PATH = "/api/v1/internal/capability-grants"
"""授权视图内部出口路径。"""


class _ClientStub(BaseServiceClient):
    """服务间调用替身：按预置状态码 / 响应体回放，并记录请求路径。"""

    plugin_name: str = "bootstrap_client_stub"

    def __init__(self, *, status_code: int = 200, content: bytes = b"") -> None:
        """初始化。

        Args:
            status_code: 回放的 HTTP 状态码。
            content: 回放的响应体字节。
        """
        self._status_code = status_code
        self._content = content
        self.paths: ConcurrentStableList[str] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """回放响应并记录请求路径。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 预置响应。
        """
        self.paths.add(request.path)
        return ServiceResponse(status_code=self._status_code, content=self._content)


def _app(*, client: object | None = None, service: str = SERVICE_KEY) -> FastAPI:
    """构造最小应用替身（只带引导用到的两处 state）。

    Args:
        client: 服务间调用客户端（None 表示装配缺失）。
        service: 本服务标识。

    Returns:
        FastAPI: 应用实例。
    """
    app = FastAPI()
    app.state.settings = cast("Settings", SimpleNamespace(app=SimpleNamespace(service=service)))
    if client is not None:
        app.state.service_client = client
    return app


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """隔离进程级视图：清来源 / 快照 / 域映射 / 能力记录。

    Yields:
        None: 用例运行期。
    """
    reset_capability_grants()
    reset_domain_services()
    reset_collaboration_records()
    yield
    reset_capability_grants()
    reset_domain_services()
    reset_collaboration_records()


async def test_bootstrap_registers_source_and_warms_carried_domain() -> None:
    """引导：登记远端来源并只预热本服务承载域的 `provider` 视图（不请求消费方维度）。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY, "peer": "other"}))
    client = _ClientStub(content=b'{"code":0,"data":{"grants":[]}}')

    await bootstrap_remote_capability_grants(_app(client=client))

    assert client.paths.to_list() == [GRANT_VIEW_PATH]


async def test_bootstrap_marks_not_degraded_on_success() -> None:
    """引导成功：`grant_view_degraded` 复位为 False（降级标记只在失败时置真）。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY}))
    app = _app(client=_ClientStub(content=b'{"code":0,"data":{"grants":[]}}'))

    await bootstrap_remote_capability_grants(app)

    assert app.state.grant_view_degraded is False


async def test_warm_views_skips_consumer_when_disabled() -> None:
    """预热：`consumer=False` 时消费方维度不加载（产品进程入站判定只需 `provider` 维）。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY}))
    client = _ClientStub(content=b'{"code":0,"data":{"grants":[]}}')
    app = _app(client=client)

    await bootstrap_remote_capability_grants(app)

    assert len(client.paths) == 1
    assert len(capability_grant_pairs(consumer=SERVICE_KEY)) == 0


async def test_warm_views_includes_consumer_by_default() -> None:
    """预热：缺省档（平台侧口径）在承载域之外并拉本服务作为消费方的视图。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY}))
    client = _ClientStub(content=b'{"code":0,"data":{"grants":[]}}')
    app = _app(client=client)
    await bootstrap_remote_capability_grants(app)

    await warm_capability_grant_views(SERVICE_KEY)

    assert len(client.paths) == 2


async def test_remote_grants_feed_provider_view() -> None:
    """远端来源：出口返回的授权记录进入承载域 `provider` 视图（入站判定可读）。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY}))
    content = (
        b'{"code":0,"data":{"grants":[{"capability_name":"demo.org.user-roles",'
        b'"consumer_key":"platform","expire_at":null}]}}'
    )
    app = _app(client=_ClientStub(content=content))

    await bootstrap_remote_capability_grants(app)
    snapshot = await ensure_grant_view(provider="org")

    assert [(grant.capability_name, grant.consumer_key) for grant in snapshot.grants] == [
        ("demo.org.user-roles", "platform")
    ]


async def test_bootstrap_degrades_when_source_unavailable() -> None:
    """来源不可达：告警降级（不拒启），且首访仍 fail-closed（抛 `CatalogError`）。"""
    register_domain_services(ConcurrentStableFrozenDict({"org": SERVICE_KEY}))
    app = _app(client=_ClientStub(status_code=503))

    await bootstrap_remote_capability_grants(app)

    assert getattr(app.state, GRANT_VIEW_DEGRADED_FLAG) is True
    with pytest.raises(CatalogError):
        await ensure_grant_view(provider="org")


async def test_bootstrap_requires_service_client() -> None:
    """装配缺服务间调用客户端：按配置漂移拒启（不静默跳过登记）。"""
    with pytest.raises(CatalogError):
        await bootstrap_remote_capability_grants(_app())
