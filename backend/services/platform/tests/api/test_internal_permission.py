"""平台内部权限端点：能力分配鉴权、版本递增、数据来源只读出口（`02_04` / `04_01`）。

三条端点一律按**能力分配**判定（07B `03_01` 收编）：

- `POST .../permissions/invalidate`（`platform.permission_meta.invalidate`）：仅放行已分配消费方；
  `user_ids` 非空 / 为空两条入参路径均返回递增后的版本号；
- `POST .../permissions/subject`（`platform.permission_meta.subject`）：按用户返回聚合所需原始数据；
- `GET  .../permissions/metadata`（`platform.permission_meta.metadata`）：菜单 → 表单、权限码 id → 权限码。

拒绝码口径：无票据 / 无效票据 → **401**；已认证但无有效分配（或网关代发）→ **403**。

重写口径（13_11）：复用会话级装配实例；令牌校验替身用 `monkeypatch.setitem` 统一挂载、用例结束
自动卸载；断言只依赖本用例可控数据（版本号只判递增，主体空断言用库内恒无授权的主键）。
"""

# pyright: reportPrivateUsage=false

from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.core.exceptions import AuthError
from bms_core.oauth.verify import VerifiedToken, get_token_verifier

API = "/api/v1/platform/internal/permissions/invalidate"
SUBJECT_API = "/api/v1/platform/internal/permissions/subject"
METADATA_API = "/api/v1/platform/internal/permissions/metadata"

_DOMAINS = ConcurrentStableFrozenList(("permission_meta",))
"""服务票据声明的承载域（07C `04_03`：入站第一道按域归属判定）。"""

_EMPTY_SUBJECT = 7_900_001
"""断言「空主体」用的用户主键：任何用例都不给它授角色 / 授权，共享库里恒无数据。"""


async def _ensure_grants(app: FastAPI) -> None:
    """确保能力默认分配在库（并行批次下「声明同步」用例会把清单外声明判移除并撤销分配）。

    本文件三条端点一律按**能力分配**判定；不补跑钩子时会在共享库上偶发 403「无有效分配（越界）」。
    钩子幂等：无差异不开写事务。

    Args:
        app: 平台应用实例。
    """
    from bms_core.collaboration.grant import invalidate_capability_grants
    from bms_platform.domains.platform_registry.services.capability_grant_bootstrap import (
        bootstrap_capability_grants,
    )

    await bootstrap_capability_grants(app)
    # 写库后必须清授权视图快照（TTL 内的旧快照仍判「无分配」），否则补回的分配不生效。
    invalidate_capability_grants()


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
        if token in ("mdm", "identity", "gateway"):
            return VerifiedToken(
                subject=token,
                service=token,
                token_type="service",
                domains=_DOMAINS,  # pyright: ignore[reportArgumentType]
            )
        raise AuthError("invalid")


@pytest.fixture(autouse=True)
def _stub_verifier(service_app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    """统一挂载令牌校验替身（三条用例共用；`monkeypatch` 退出自动卸载）。

    Args:
        service_app: 平台服务应用。
        monkeypatch: 补丁夹具。
    """
    monkeypatch.setitem(service_app.dependency_overrides, get_token_verifier, lambda: _StubVerifier())


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_requires_mdm_service(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：仅放行 `sub=mdm` 服务票据；网关 / 未知 / 无票据一律拒（401）。"""
    await _ensure_grants(service_app)

    ok = await client.post(API, json={}, headers={"Authorization": "Bearer mdm"})
    assert ok.status_code == 200, ok.text
    # 共享库叠加：版本号全租户累计（别的用例 / worker 也会推进），只判非空。
    assert int(ok.json()["data"]["version"]) >= 1

    assert (await client.post(API, json={}, headers={"Authorization": "Bearer gateway"})).status_code == 403
    assert (await client.post(API, json={}, headers={"Authorization": "Bearer bogus"})).status_code == 401
    assert (await client.post(API, json={})).status_code == 401


@pytest.mark.kiwi_id(2269)
async def test_invalidate_endpoint_scopes_users(client: AsyncClient, service_app: FastAPI) -> None:
    """端点：`user_ids` 非空按用户清理旧版本键、为空只做全租户版本 +1（均返回递增版本）。"""
    await _ensure_grants(service_app)

    scoped = await client.post(API, json={"user_ids": [7, 8]}, headers={"Authorization": "Bearer mdm"})
    assert scoped.status_code == 200
    # 版本号是全租户累计的：只判「非空，且本用例两次调用严格递增」。
    first = int(scoped.json()["data"]["version"])
    assert first >= 1

    whole_tenant = await client.post(API, json={}, headers={"Authorization": "Bearer mdm"})
    assert int(whole_tenant.json()["data"]["version"]) > first


@pytest.mark.kiwi_id(2320)
async def test_subject_endpoint_requires_identity_capability(client: AsyncClient, service_app: FastAPI) -> None:
    """`subject` 出口：仅放行持有该能力有效分配的 `identity`；mdm / 网关 / 无票据一律拒。"""
    await _ensure_grants(service_app)

    # 「空主体」用库内没有授权数据的主键：共享库叠加后测试主体（1001）会被其它用例授权，
    # 拿它断言空角色等于假设「库里只有我的数据」。
    ok = await client.post(SUBJECT_API, json={"user_id": _EMPTY_SUBJECT}, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200, ok.text
    body = ok.json()["data"]
    # 「无主体数据」统一返回五个契约字段齐全的空主体（不透 `null`，消费方无需特判分支）
    assert set(body) == {"role_ids", "role_types", "grants", "data_scope_rules", "field_perms"}
    assert body["role_ids"] == [] and body["role_types"] == {}
    assert body["grants"] == [] and body["data_scope_rules"] == [] and body["field_perms"] == []

    # 已认证但无有效分配（mdm 未获授权）/ 网关代发票据 → 403；伪造票据 → 401；无票据 → 401
    for token in ("mdm", "gateway"):
        denied = await client.post(SUBJECT_API, json={"user_id": 1}, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 403

    bogus = await client.post(SUBJECT_API, json={"user_id": 1}, headers={"Authorization": "Bearer bogus"})
    assert bogus.status_code == 401
    assert (await client.post(SUBJECT_API, json={"user_id": 1})).status_code == 401


@pytest.mark.kiwi_id(2320)
async def test_metadata_endpoint_requires_identity_capability(
    client: AsyncClient, service_app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`metadata` 出口：仅放行持有该能力有效分配的 `identity`；返回元数据索引；`locale` 缺省可取。"""
    from bms_platform.domains.permission_meta.permission import source as source_module

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
    await _ensure_grants(service_app)

    ok = await client.get(METADATA_API, headers={"Authorization": "Bearer identity"})
    assert ok.status_code == 200, ok.text
    body = ok.json()["data"]
    assert body["version"] == 0
    assert body["menu_forms"] == {}
    assert body["permission_codes"] == {}

    with_locale = await client.get(
        METADATA_API, params={"locale": "en-US"}, headers={"Authorization": "Bearer identity"}
    )
    assert with_locale.status_code == 200

    # 已认证但无有效分配 / 网关代发 → 403；伪造票据 → 401
    for token in ("mdm", "gateway"):
        denied = await client.get(METADATA_API, headers={"Authorization": f"Bearer {token}"})
        assert denied.status_code == 403

    bogus = await client.get(METADATA_API, headers={"Authorization": "Bearer bogus"})
    assert bogus.status_code == 401


class _EmptySnapshot:
    """菜单元数据空快照替身。"""

    version: int = 0

    def __init__(self) -> None:
        """初始化（无菜单）。"""
        from bms_core.core.concurrent import ConcurrentStableList

        self.menus: Any = ConcurrentStableList()


def test_to_subject_result_handles_missing_data() -> None:
    """无主体数据（未知用户）：返回空聚合输入（契约字段齐全），不透 `null`。"""
    from bms_platform.domains.permission_meta.api.permission import _to_subject_result

    result = _to_subject_result(None)

    assert list(result.role_ids) == []
    assert dict(result.role_types) == {}
    assert list(result.grants) == []


def test_read_role_ids_tolerates_non_mapping_payload() -> None:
    """主体链取数回来的载荷不是对象（异常形态）：返回空集而不是崩。"""
    from bms_platform.domains.role.services.permission_subject import _read_role_ids

    assert list(_read_role_ids(None)) == []
    assert list(_read_role_ids([1, 2])) == []
    assert list(_read_role_ids({"data": None})) == []
