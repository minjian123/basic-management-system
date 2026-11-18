"""产品声明注册通道端点用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖：全量上报（新增 / 幂等 / 覆盖 / 退役）、跨产品撞键拒绝、身份代注册拒绝、
以及服务身份快照出口（八类要素下发）。

测试库：共享平台库 + 回滚会话；产品键按命名空间生成，全量上报的退役只在本用例事务内可见。
"""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.testing.namespace import Namespace

API = "/api/v1/platform/internal/declarations"
SNAPSHOT_API = f"{API}/snapshot"


def _manifest(ns: Namespace, *, path: str = "/api/v1/demo/roles") -> str:
    """构造本用例独占产品的声明清单。

    Args:
        ns: 本用例命名空间。
        path: 协作能力访问路径。

    Returns:
        str: 清单文本。
    """
    return f"""
product_key = "{ns.prefix}"

[[products]]
product_key = "{ns.prefix}"
name = "演示产品"
status = "enabled"

[[services]]
module_key = "{ns.prefix}"
service_key = "{ns.prefix}"
name = "演示服务"
table_prefix = "{ns.prefix}_"
event_domain = "{ns.prefix}"
service_group = "product"
product_key = "{ns.prefix}"
status = "enabled"

[[collaborations]]
name = "{ns.prefix}.demo_op.roles"
domain = "{ns.prefix}_demo_op"
kind = "read"
path = "{path}"
frontend_prefix = "{ns.prefix}"
contract_version = "0.1.0"

[[usages]]
name = "{ns.prefix}.demo_op.roles"
degrade = "empty"
reason = "断链按无角色"

# 第九类：业务域声明（07B `04_02` 重开——域随声明到达，不再靠内存登记）
[[domains]]
domain_key = "{ns.prefix}_demo_op"
service_key = "{ns.prefix}"
status = "planned"
"""


class _StubVerifier:
    """服务令牌校验替身：任意非空令牌返回同名服务身份。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001 / 401）。
        """
        del audience
        if token:
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


@pytest.fixture(autouse=True)
def _stub_verifier(service_app: FastAPI) -> None:
    """注入令牌校验替身（用例内统一）。

    Args:
        service_app: 平台应用实例。
    """
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()


async def _submit(
    client: AsyncClient,
    ns: Namespace,
    *,
    token: str | None = None,
    service_key: str | None = None,
    product_key: str | None = None,
    manifest: str | None = None,
):
    """提交一次全量上报。

    Args:
        client: 测试客户端。
        ns: 本用例命名空间。
        token: 服务令牌（缺省用命名空间键）。
        service_key: 请求的服务键（缺省同令牌）。
        product_key: 请求的产品键（缺省用命名空间键）。
        manifest: 清单文本（缺省按命名空间生成）。

    Returns:
        响应对象。
    """
    resolved_token = token or ns.prefix
    resolved_service = service_key or resolved_token
    return await client.put(
        API,
        json={
            "product_key": product_key or ns.prefix,
            "service_key": resolved_service,
            "manifest_toml": manifest or _manifest(ns),
        },
        headers={"Authorization": f"Bearer {resolved_token}"},
    )


async def test_submit_creates_then_idempotent(client: AsyncClient, ns: Namespace) -> None:
    """首次上报全部新增；同内容重复上报全 `unchanged`（不写库）。"""
    first = await _submit(client, ns)
    assert first.status_code == 200, first.text
    created = first.json()["data"]["created"]
    assert created["collaborations"] == 1
    assert created["usages"] == 1
    assert created["services"] == 1

    again = await _submit(client, ns)
    assert again.status_code == 200
    data = again.json()["data"]
    assert data["created"] == {kind: 0 for kind in data["created"]}
    assert data["unchanged"]["collaborations"] == 1


async def test_submit_updates_on_content_change(client: AsyncClient, ns: Namespace) -> None:
    """内容变化：进 `updated` 计数。"""
    await _submit(client, ns)

    changed = await _submit(client, ns, manifest=_manifest(ns, path="/api/v1/demo/roles-v2"))

    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["updated"]["collaborations"] == 1


async def test_snapshot_lists_collaborations_with_access_path(client: AsyncClient, ns: Namespace) -> None:
    """快照出口：能力段含访问面路径（服务身份完整面）。"""
    await _submit(client, ns)
    name = f"{ns.prefix}.demo_op.roles"

    snapshot = await client.get(SNAPSHOT_API, headers={"Authorization": "Bearer platform"})

    assert snapshot.status_code == 200
    data = snapshot.json()["data"]
    names = [item["name"] for item in data["declarations"]["collaborations"]]
    assert name in names
    item = next(row for row in data["declarations"]["collaborations"] if row["name"] == name)
    assert item["path"] == "/api/v1/demo/roles"


async def test_snapshot_roundtrip_projects_and_resolves(client: AsyncClient, ns: Namespace) -> None:
    """端到端：产品注册 → 拉快照 → 还原投影 → `resolve_capability` 取到该能力。

    这条链路横跨两端：平台落库 `PUT`，产品侧 `GET` 后按快照整体重建视图，消费方取址无需再装载对端清单。
    """
    from bms_core.collaboration.resolver import resolve_capability
    from bms_core.registry.projection import project_registry
    from bms_core.registry.remote import snapshot_from_wire

    await _submit(client, ns)
    snapshot = await client.get(SNAPSHOT_API, headers={"Authorization": "Bearer platform"})
    assert snapshot.status_code == 200

    view = await snapshot_from_wire(snapshot.json()["data"])
    project_registry(view)

    endpoint = resolve_capability(f"{ns.prefix}.demo_op.roles")
    assert endpoint.path == "/api/v1/demo/roles"
    assert endpoint.target.service_key == ns.prefix


async def test_submit_rejects_service_key_mismatch(client: AsyncClient, ns: Namespace) -> None:
    """清单服务键与请求不一致：10001。"""
    response = await _submit(client, ns, service_key="other")

    assert response.status_code == 200
    assert response.json()["code"] == 10001


async def test_submit_rejects_product_key_mismatch(client: AsyncClient, ns: Namespace) -> None:
    """请求产品键与清单归属不一致：10001（不落库）。"""
    response = await _submit(client, ns, product_key="other")

    assert response.status_code == 200
    assert response.json()["code"] == 10001
    assert "清单归属与请求不一致" in response.json()["message"]


async def test_submit_rejects_proxy_registration(client: AsyncClient, ns: Namespace) -> None:
    """服务身份不得代其他服务注册：10001。"""
    response = await _submit(client, ns, token="other")

    assert response.status_code == 200
    assert response.json()["code"] == 10001


async def test_submit_requires_identity(client: AsyncClient) -> None:
    """无票据：401。"""
    token = client.headers.pop("Authorization", None)
    try:
        response = await client.put(
            API,
            json={"product_key": "demo", "service_key": "demo", "manifest_toml": 'product_key = "demo"\n'},
        )
    finally:
        if token is not None:
            client.headers["Authorization"] = token

    assert response.status_code == 401
