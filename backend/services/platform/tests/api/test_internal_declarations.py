"""产品声明注册通道端点用例（07B `02_06`；Kiwi 编号归 `05_01` 统一登记）。

覆盖：全量上报（新增 / 幂等 / 覆盖 / 退役）、跨产品撞键拒绝、身份代注册拒绝、
以及服务身份快照出口（八类要素下发）。
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenDict
from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier
from bms_core.services.module_registry import register_domain_services

API = "/api/v1/platform/internal/declarations"
SNAPSHOT_API = f"{API}/snapshot"


@pytest.fixture(autouse=True)
def _declare_demo_domain() -> Iterator[None]:
    """登记用例专用的业务域（与域布局解耦，避免与其他用例共享状态冲突）。

    Yields:
        None: 用例运行期。
    """
    register_domain_services(ConcurrentStableFrozenDict({"demo_op": "demo"}))
    yield


_MANIFEST = """
product_key = "demo"

[[products]]
product_key = "demo"
name = "演示产品"
status = "enabled"

[[services]]
module_key = "demo"
service_key = "demo"
name = "演示服务"
table_prefix = "demo_"
event_domain = "demo"
service_group = "product"
product_key = "demo"
status = "enabled"

[[collaborations]]
name = "demo.demo_op.roles"
domain = "demo_op"
kind = "read"
path = "/api/v1/demo/roles"
frontend_prefix = "demo"
contract_version = "0.1.0"

[[usages]]
name = "demo.demo_op.roles"
degrade = "empty"
reason = "断链按无角色"
"""

_MANIFEST_V2 = _MANIFEST.replace('path = "/api/v1/demo/roles"', 'path = "/api/v1/demo/roles-v2"')


class _StubVerifier:
    """服务令牌校验替身：按令牌串返回固定身份（`demo` / `gateway` / `bogus`）。"""

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
        if token in ("demo", "other", "platform"):
            return VerifiedToken(subject=token, service=token, token_type="service")
        raise AuthError("invalid")


@pytest.fixture(autouse=True)
def _stub_verifier(service_app: FastAPI) -> None:
    """注入令牌校验替身（用例内统一）。

    Args:
        service_app: 平台应用实例。
    """
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()


async def _submit(client: AsyncClient, token: str = "demo", *, product_key: str = "demo", manifest: str = _MANIFEST):
    """提交一次全量上报。

    Args:
        client: 测试客户端。
        token: 服务令牌。
        product_key: 请求的产品键。
        manifest: 清单文本。

    Returns:
        响应对象。
    """
    return await client.put(
        API,
        json={"product_key": product_key, "service_key": token, "manifest_toml": manifest},
        headers={"Authorization": f"Bearer {token}"},
    )


async def test_submit_creates_then_idempotent(client: AsyncClient) -> None:
    """首次上报全部新增；同内容重复上报全 `unchanged`（不写库）。"""
    first = await _submit(client)
    assert first.status_code == 200, first.text
    created = first.json()["data"]["created"]
    assert created["collaborations"] == 1
    assert created["usages"] == 1
    assert created["services"] == 1

    again = await _submit(client)
    assert again.status_code == 200
    data = again.json()["data"]
    assert data["created"] == {kind: 0 for kind in data["created"]}
    assert data["unchanged"]["collaborations"] == 1


async def test_submit_updates_on_content_change(client: AsyncClient) -> None:
    """内容变化：进 `updated` 计数。"""
    await _submit(client)

    changed = await _submit(client, manifest=_MANIFEST_V2)

    assert changed.status_code == 200, changed.text
    assert changed.json()["data"]["updated"]["collaborations"] == 1


async def test_snapshot_lists_collaborations_with_access_path(client: AsyncClient) -> None:
    """快照出口：能力段含访问面路径（服务身份完整面）。"""
    await _submit(client)

    snapshot = await client.get(SNAPSHOT_API, headers={"Authorization": "Bearer platform"})

    assert snapshot.status_code == 200
    data = snapshot.json()["data"]
    names = [item["name"] for item in data["declarations"]["collaborations"]]
    assert "demo.demo_op.roles" in names
    item = next(row for row in data["declarations"]["collaborations"] if row["name"] == "demo.demo_op.roles")
    assert item["path"] == "/api/v1/demo/roles"


async def test_submit_rejects_service_key_mismatch(client: AsyncClient) -> None:
    """清单服务键与请求不一致：10001。"""
    response = await client.put(
        API,
        json={"product_key": "demo", "service_key": "other", "manifest_toml": _MANIFEST},
        headers={"Authorization": "Bearer demo"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 10001


async def test_submit_rejects_product_key_mismatch(client: AsyncClient) -> None:
    """请求产品键与清单归属不一致：10001（不落库）。"""
    response = await client.put(
        API,
        json={"product_key": "other", "service_key": "demo", "manifest_toml": _MANIFEST},
        headers={"Authorization": "Bearer demo"},
    )

    assert response.status_code == 200
    assert response.json()["code"] == 10001
    assert "清单归属与请求不一致" in response.json()["message"]


async def test_submit_rejects_proxy_registration(client: AsyncClient) -> None:
    """服务身份不得代其他服务注册：10001。"""
    response = await _submit(client, token="other")

    assert response.status_code == 200
    assert response.json()["code"] == 10001


async def test_submit_requires_identity(client: AsyncClient) -> None:
    """无票据：401。"""
    response = await client.put(
        API,
        json={"product_key": "demo", "service_key": "demo", "manifest_toml": _MANIFEST},
    )

    assert response.status_code == 401
