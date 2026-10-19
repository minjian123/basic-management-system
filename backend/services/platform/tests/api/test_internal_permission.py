"""平台内部权限端点测试（`02_04` / `04_01`）：服务 JWT 白名单鉴权 + 版本递增 + 数据来源只读出口。

覆盖三条端点：

- `POST /api/v1/platform/internal/permissions/invalidate`（`require_service("org")`）：
  仅放行 `sub=org` 服务票据；`user_ids` 非空 / 为空两条入参路径均返回递增后的版本号；
- `POST /api/v1/platform/internal/permissions/subject`（`require_service("identity")`）：
  按用户返回聚合所需原始数据（`04_01` 下沉后 identity 经契约取数）；
- `GET /api/v1/platform/internal/permissions/metadata`（`require_service("identity")`）：
  返回菜单 → 表单、权限码 id → 权限码两类索引。
"""

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier

API = "/api/v1/platform/internal/permissions/invalidate"
SUBJECT_API = "/api/v1/platform/internal/permissions/subject"
METADATA_API = "/api/v1/platform/internal/permissions/metadata"


class _StubVerifier:
    """测试替身：按令牌串返回服务身份（无签名）。"""

    async def verify(self, token: str, *, audience: str) -> VerifiedToken:
        """按令牌串返回固定身份声明。

        Args:
            token: 令牌串。
            audience: 期望受众（未使用）。

        Returns:
            VerifiedToken: 身份声明。

        Raises:
            AuthError: 未知令牌（20001/401）。
        """
        del audience
        if token == "org":
            return VerifiedToken(subject="org", service="org", token_type="service")
        if token == "identity":
            return VerifiedToken(subject="identity", service="identity", token_type="service")
        if token == "gateway":
            return VerifiedToken(subject="gateway", service="gateway", token_type="service")
        raise AuthError("invalid")


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_requires_org_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=org` 服务票据；网关 / 未知 / 无票据一律拒（401）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    ok = await client.post(API, json={}, headers={"Authorization": "Bearer org"})
    assert ok.status_code == 200
    assert ok.json()["data"]["version"] == 1

    for token in ("gateway", "bogus"):
        denied = await client.post(API, json={}, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401

    anonymous = await client.post(API, json={})
    assert anonymous.status_code == 401


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_scopes_users(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：`user_ids` 非空按用户清理旧版本键、为空只做全租户版本 +1（均返回递增版本）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    scoped = await client.post(API, json={"user_ids": [7, 8]}, headers={"Authorization": "Bearer org"})
    assert scoped.status_code == 200
    assert scoped.json()["data"]["version"] == 1

    whole_tenant = await client.post(API, json={}, headers={"Authorization": "Bearer org"})
    assert whole_tenant.json()["data"]["version"] == 2


@pytest.mark.kiwi_id(2320)
async def test_subject_endpoint_requires_identity_service(client: AsyncClient, service_app: FastAPI) -> None:
    """`subject` 出口：仅放行 `sub=identity`；org / 网关 / 无票据一律拒（401）。"""
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    ok = await client.post(SUBJECT_API, json={"user_id": 1001}, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert set(body) == {"role_ids", "role_types", "grants", "data_scope_rules", "field_perms"}

    for token in ("org", "gateway", "bogus"):
        denied = await client.post(SUBJECT_API, json={"user_id": 1}, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401

    anonymous = await client.post(SUBJECT_API, json={"user_id": 1})
    assert anonymous.status_code == 401


@pytest.mark.kiwi_id(2320)
async def test_metadata_endpoint_requires_identity_service(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`metadata` 出口：仅放行 `sub=identity`；返回元数据索引；`locale` 缺省可取。"""
    from bms_platform.permission import source as source_module

    class _Builder:
        """元数据服务替身（空快照）。"""

        async def load_snapshot(self, **kwargs: object) -> object:
            """返回空快照。

            Args:
                kwargs: 调用参数（忽略）。

            Returns:
                object: 快照替身。
            """
            del kwargs
            return _EmptySnapshot()

    def _factory(session: object, cache: object) -> _Builder:
        """替身服务构造器。

        Args:
            session: 平台库会话（忽略）。
            cache: 缓存域（忽略）。

        Returns:
            _Builder: 替身服务。
        """
        del session, cache
        return _Builder()

    monkeypatch.setattr(source_module, "build_menu_metadata_service", _factory)
    service_app.dependency_overrides[get_token_verifier] = lambda: _StubVerifier()

    ok = await client.get(METADATA_API, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["version"] == 0
    assert body["menu_forms"] == {}
    assert body["permission_codes"] == {}

    with_locale = await client.get(
        METADATA_API, params={"locale": "en-US"}, headers={"Authorization": "Bearer identity"}
    )
    assert with_locale.status_code == 200

    for token in ("org", "gateway", "bogus"):
        denied = await client.get(METADATA_API, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 401


class _EmptySnapshot:
    """菜单元数据空快照替身。"""

    version: int = 0

    def __init__(self) -> None:
        """初始化（无菜单）。"""
        from bms_core.core.concurrent import ConcurrentStableList

        self.menus: Any = ConcurrentStableList()
