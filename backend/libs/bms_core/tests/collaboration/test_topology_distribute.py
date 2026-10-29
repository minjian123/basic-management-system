"""拓扑快照跨进程分发（07C `02_02`；Kiwi 2367）。

覆盖详细设计 §6 用例 11~16：成功装载、开关关闭、平台进程自跳过、装配缺客户端拒启、
拉取失败降级、应用关闭复位；另覆盖内部响应解析的非法分支。
"""

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI

from bms_core.collaboration import (
    DEFAULT_TOPOLOGY_TENANT,
    DomainLayoutTopologyResolver,
    TenantTopologyResolver,
    bootstrap_remote_topologies,
    instance_units,
    reset_instance_context,
    reset_topology_resolver,
    reset_topology_snapshots,
    resolve_for,
    resolve_topology,
    snapshots_from_payload,
    topology_snapshot,
)
from bms_core.collaboration.bootstrap import TOPOLOGY_SNAPSHOT_PATH
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import CatalogError
from bms_core.servicecall.base import BaseServiceClient, ServiceRequest, ServiceResponse
from bms_core.services.module_registry import register_domain_services, reset_domain_services

pytestmark = pytest.mark.kiwi_id(2367)

SERVICE_KEY = "demo"
"""本服务标识（非平台进程）。"""

_SNAPSHOT_PAYLOAD = {
    "code": 0,
    "message": "ok",
    "data": {
        "default_version": 1,
        "snapshots": [
            {
                "tenant_id": DEFAULT_TOPOLOGY_TENANT,
                "version": 1,
                "rows": [{"domain_key": "org", "unit_key": "mdm", "status": "enabled"}],
            },
            {"tenant_id": 7, "version": 2, "rows": [{"domain_key": "org", "unit_key": "grp-ops", "status": "enabled"}]},
        ],
    },
}
"""内部出口正常响应（默认拓扑 + 一个租户）。"""


class _ClientStub(BaseServiceClient):
    """服务间调用替身：回放预置响应并记录请求。"""

    plugin_name: str = "topology_client_stub"

    def __init__(self, *, status_code: int = 200, content: bytes = b"", error: Exception | None = None) -> None:
        """初始化。

        Args:
            status_code: 回放的 HTTP 状态码。
            content: 回放的响应体字节。
            error: 非空时调用即抛该异常（模拟出口不可达）。
        """
        self._status_code = status_code
        self._content = content
        self._error = error
        self.paths: ConcurrentStableList[str] = ConcurrentStableList()

    async def call(self, request: ServiceRequest) -> ServiceResponse:
        """回放响应并记录请求路径。

        Args:
            request: 调用请求。

        Returns:
            ServiceResponse: 预置响应。

        Raises:
            Exception: 构造时给定的异常（模拟不可达）。
        """
        self.paths.add(request.path)
        if self._error is not None:
            raise self._error
        return ServiceResponse(status_code=self._status_code, content=self._content)


class _ResourceStub:
    """资源管理器替身：记录登记的资源。"""

    def __init__(self) -> None:
        """初始化空资源清单。"""
        self.registered: ConcurrentStableList[object] = ConcurrentStableList()

    def register(self, resource: object) -> None:
        """登记资源（与 `ResourceManager.register` 同签名）。

        Args:
            resource: 资源实例。
        """
        self.registered.add(resource)


def _settings(*, service: str = SERVICE_KEY, distribute: bool = True, units: object = None) -> Settings:
    """构造只带分发相关字段的配置替身。

    Args:
        service: 本服务标识。
        distribute: 分发开关。
        units: 承载单元集合（None 表示未声明）。

    Returns:
        Settings: 配置替身。
    """
    return cast(
        "Settings",
        SimpleNamespace(
            app=SimpleNamespace(service=service),
            topology=SimpleNamespace(distribute=distribute, units=units),
        ),
    )


def _app(client: object | None = None, *, settings: Settings | None = None) -> FastAPI:
    """构造最小应用替身（配置 + 服务间客户端 + 资源管理器）。

    Args:
        client: 服务间调用客户端（None 表示装配缺失）。
        settings: 配置替身（None 取缺省）。

    Returns:
        FastAPI: 应用实例。
    """
    app = FastAPI()
    app.state.settings = settings or _settings()
    app.state.resources = _ResourceStub()
    if client is not None:
        app.state.service_client = client
    return app


@pytest.fixture(autouse=True)
def _isolate() -> Iterator[None]:
    """每例复位拓扑进程态与域映射，并登记一个域（`org`）。

    Yields:
        None: 用例运行期。
    """
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))
    yield
    reset_topology_snapshots()
    reset_topology_resolver()
    reset_instance_context()
    reset_domain_services()


async def test_bootstrap_registers_snapshots_and_resolver() -> None:
    """用例 11：拉取成功——按租户登记快照、替换解析实现、登记本实例身份与释放器。"""
    client = _ClientStub(content=json.dumps(_SNAPSHOT_PAYLOAD).encode())
    app = _app(client)

    await bootstrap_remote_topologies(app)

    assert client.paths.to_list() == [TOPOLOGY_SNAPSHOT_PATH]
    assert isinstance(resolve_topology(), TenantTopologyResolver)
    assert topology_snapshot(7) is not None
    assert resolve_for(7, "org").unit_key == "grp-ops"
    assert app.state.topology_degraded is False
    resource_stub = cast("_ResourceStub", app.state.resources)
    assert len(resource_stub.registered) == 1


async def test_bootstrap_skips_when_switch_off() -> None:
    """用例 12：开关关闭（单测环境）——不发起调用，保留 07B 过渡实现。"""
    client = _ClientStub(content=json.dumps(_SNAPSHOT_PAYLOAD).encode())
    app = _app(client, settings=_settings(distribute=False))

    await bootstrap_remote_topologies(app)

    assert list(client.paths) == []
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)


async def test_bootstrap_skips_on_platform_process() -> None:
    """用例 13：平台进程自跳过（本库即权威，由启动钩子装载，不自调自身端点）。"""
    client = _ClientStub(content=json.dumps(_SNAPSHOT_PAYLOAD).encode())
    app = _app(client, settings=_settings(service="platform"))

    await bootstrap_remote_topologies(app)

    assert list(client.paths) == []
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)


async def test_bootstrap_requires_service_client() -> None:
    """用例 14：装配缺服务间客户端 → `CatalogError` 拒启（配置漂移，不隐式降级）。"""
    with pytest.raises(CatalogError, match="缺少服务间调用客户端"):
        await bootstrap_remote_topologies(_app())


async def test_bootstrap_degrades_when_endpoint_unreachable() -> None:
    """用例 15：出口不可达 → 告警降级、保留过渡实现（行为等同改造前，不会错址）。"""
    client = _ClientStub(error=RuntimeError("connect refused"))
    app = _app(client)

    await bootstrap_remote_topologies(app)

    assert app.state.topology_degraded is True
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)


async def test_bootstrap_degrades_on_non_200() -> None:
    """出口返回非 200 同样降级（平台重启窗口内不把产品拖下水）。"""
    app = _app(_ClientStub(status_code=503))

    await bootstrap_remote_topologies(app)

    assert app.state.topology_degraded is True


async def test_bootstrap_degrades_on_empty_snapshot() -> None:
    """平台尚未自举（空快照）→ 降级而非装载一个恒报错的解析器。"""
    empty = {"code": 0, "data": {"default_version": 0, "snapshots": []}}
    app = _app(_ClientStub(content=json.dumps(empty).encode()))

    await bootstrap_remote_topologies(app)

    assert app.state.topology_degraded is True
    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)


async def test_bootstrap_rejects_unregistered_declared_units() -> None:
    """承载集合含未登记单元 → 拒启（配置漂移，不随降级口径放行）。"""
    client = _ClientStub(content=json.dumps(_SNAPSHOT_PAYLOAD).encode())
    app = _app(client, settings=_settings(units=ConcurrentStableList(("ghost",))))

    with pytest.raises(CatalogError, match="未在默认拓扑登记"):
        await bootstrap_remote_topologies(app)


async def test_resource_release_resets_process_state() -> None:
    """用例 16：应用关闭复位解析器、快照与本实例身份（同进程再次装配不残留）。"""
    client = _ClientStub(content=json.dumps(_SNAPSHOT_PAYLOAD).encode())
    app = _app(client)
    await bootstrap_remote_topologies(app)
    resource_stub = cast("_ResourceStub", app.state.resources)
    resource = resource_stub.registered[0]

    await cast("object", resource).aclose()  # pyright: ignore[reportAttributeAccessIssue]

    assert isinstance(resolve_topology(), DomainLayoutTopologyResolver)
    assert topology_snapshot(7) is None
    assert list(instance_units()) == []


def test_snapshot_payload_parsed() -> None:
    """正常响应：按租户建快照，状态与版本原样保留。"""
    snapshots = snapshots_from_payload(_SNAPSHOT_PAYLOAD)

    assert [snapshot.tenant_id for snapshot in snapshots] == [DEFAULT_TOPOLOGY_TENANT, 7]
    assert snapshots[1].version == 2
    assert snapshots[1].entries["org"].unit_key == "grp-ops"
    assert snapshots[1].entries["org"].enabled is True


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        {"code": 0},
        {"code": 0, "data": {"snapshots": "oops"}},
        {"code": 0, "data": {"snapshots": ["oops"]}},
        {"code": 0, "data": {"snapshots": [{"tenant_id": 0, "version": 1}]}},
        {"code": 0, "data": {"snapshots": [{"tenant_id": 0, "version": 1, "rows": ["oops"]}]}},
        {"code": 0, "data": {"snapshots": [{"tenant_id": 0, "version": 1, "rows": [{"domain_key": ""}]}]}},
    ],
)
def test_snapshot_payload_rejected(payload: object) -> None:
    """非法响应（非对象 / 缺 data / 结构错）→ `CatalogError`，不装载半份快照。"""
    with pytest.raises(CatalogError, match="拓扑出口响应非法"):
        snapshots_from_payload(payload)


def test_snapshot_payload_tolerates_illegal_numbers() -> None:
    """租户 / 版本非数字时取缺省（不因单个脏字段丢掉整份快照）。"""
    payload = {
        "code": 0,
        "data": {"snapshots": [{"tenant_id": "oops", "version": "", "rows": []}]},
    }

    snapshots = snapshots_from_payload(payload)

    assert snapshots[0].tenant_id == DEFAULT_TOPOLOGY_TENANT
    assert snapshots[0].version == 0
