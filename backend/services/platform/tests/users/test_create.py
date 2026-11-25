"""platform 内部 JIT 建号接口测试（Kiwi 2198）：服务层建号 + 撞名语义 + 端点服务 JWT 鉴权。

跑共享租户库（`sys_user` 属 platform 服务租户库 `bms_platform_{code}`）：账号名带用例命名空间；
端点用例走真实鉴权（服务令牌由测试助手签发），不再替换 `get_token_verifier` / `get_uow`。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.unit_of_work import DbUnitOfWork
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users import SSO_PASSWORD_PLACEHOLDER, UserCreateService
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/users/create"
PBKDF2_PREFIX = "pbkdf2_sha256$"


@pytest.mark.kiwi_id(2198)
async def test_service_create_user_and_conflict(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：建号成功（占位口令 + 启用）；同名撞名返回 `created=false`。"""
    account = ns.code("alice")
    async with shared_write(shared_tenant_engine) as session:
        service = UserCreateService(UserRepository(session), DbUnitOfWork(session))

        created = await service.create_user(username=account, name="爱丽丝", locale="zh-cn", timezone="Asia/Shanghai")
        assert created.created is True and created.user is not None
        assert created.user.username == account and created.user.status == "enabled"

        conflict = await service.create_user(username=account, name="另一个")
        assert conflict.created is False and conflict.reason == "username_conflict" and conflict.user is None

        row = await UserRepository(session).get_by_username(account)
        assert row is not None
        assert row.password_hash == SSO_PASSWORD_PLACEHOLDER
        assert not row.password_hash.startswith(PBKDF2_PREFIX)


@pytest.mark.kiwi_id(2198)
async def test_service_create_integrity_conflict(
    shared_tenant_engine: AsyncEngine, ns: Namespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """并发撞名：仓储 flush 触发唯一约束 → 返回 `created=false`（不抛错）。"""
    async with shared_write(shared_tenant_engine) as session:
        service = UserCreateService(UserRepository(session), DbUnitOfWork(session))

        async def fake_create(self: UserRepository, **values: object) -> object:
            raise IntegrityError("stmt", {}, Exception("duplicate"))

        monkeypatch.setattr(UserRepository, "create", fake_create)
        result = await service.create_user(username=ns.code("bob"), name="鲍勃")
        assert result.created is False and result.reason == "username_conflict"


@pytest.mark.kiwi_id(2198)
async def test_internal_create_endpoint_requires_identity_service(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：仅放行 `sub=identity` 服务票据；建号成功 / 撞名 / 鉴权分支。"""
    account = ns.code("alice")
    identity = issue_service_token("identity")
    auth = {"Authorization": f"Bearer {identity}"}

    ok = await client.post(
        API,
        json={"username": account, "name": "爱丽丝", "locale": "zh-cn", "timezone": "Asia/Shanghai"},
        headers=auth,
    )
    assert ok.status_code == 200
    assert ok.json()["data"]["created"] is True
    assert ok.json()["data"]["user"]["username"] == account

    conflict = await client.post(API, json={"username": account, "name": "重复"}, headers=auth)
    assert conflict.status_code == 200
    assert conflict.json()["data"]["created"] is False
    assert conflict.json()["data"]["reason"] == "username_conflict"

    # 白名单只放行 identity：gateway 是**合法签名的服务令牌**，仍须拒
    gateway = issue_service_token("gateway")
    denied = await client.post(
        API, json={"username": ns.code("bob"), "name": "b"}, headers={"Authorization": f"Bearer {gateway}"}
    )
    assert denied.status_code == 401

    anonymous = await client.post(API, json={"username": ns.code("bob"), "name": "b"})
    assert anonymous.status_code == 401
