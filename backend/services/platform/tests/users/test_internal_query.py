"""platform 内部用户只读出口测试（Kiwi 2257 / 2275）：服务层筛选 + 端点服务 JWT 鉴权 + 契约字段。

覆盖任务 `02_06 平台用户只读出口内部契约`——`POST /api/v1/platform/internal/users/query`
（`require_service("mdm")`，供 mdm 跨产品域只读出口取用户明细）；字段集断言随
`02_01` 嵌套子任务 `_01 平台用户只读出口字段收口` 收口（**Kiwi 2275**：响应不含 `dept_id`）。

跑共享租户库（`sys_user` 属 platform 服务租户库）：账号名带用例命名空间、查询用 `ids=` 收口；
端点用例走真实鉴权——`mdm` 按能力分配判定（令牌须声明 `user` 域）、`notification` 走白名单。
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.models.platform.user import SysUser
from bms_core.testing.namespace import Namespace
from bms_platform.domains.user.repositories.user import UserRepository
from bms_platform.domains.user.services.users import InternalUserQueryService
from tests_support.service_token import issue_service_token
from tests_support.shared_access import shared_write

API = "/api/v1/platform/internal/users/query"


async def _add_user(
    session: AsyncSession,
    username: str,
    *,
    name: str = "运营管理员",
    status: str = "enabled",
    phone: str | None = None,
    email: str | None = None,
    locale: str | None = None,
) -> SysUser:
    """插入一条测试用户。

    Args:
        session: 共享租户库会话。
        username: 登录账号。
        name: 显示名。
        status: 账号状态。
        phone: 手机号。
        email: 邮箱。
        locale: 语言偏好。

    Returns:
        SysUser: 持久化后的用户行。
    """
    user = SysUser(
        username=username,
        password_hash="hash",
        name=name,
        status=status,
        phone=phone,
        email=email,
        locale=locale,
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.kiwi_id(2257)
@pytest.mark.kiwi_id(2275)
async def test_internal_query_service_filters_and_paging(shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """服务层：关键字 / 状态 / 限定集合筛选与分页、总数同口径。

    共享库上「总数」只能是**本次造的行**的总数：每个查询用 `ids=` 限定到这三个账号，
    关键字用账号前缀（账号名带用例命名空间）。
    """
    alice_name, bob_name, carol_name = ns.code("alice"), ns.code("bob"), ns.code("carol")
    async with shared_write(shared_tenant_engine) as session:
        repo = UserRepository(session)
        alice = await _add_user(session, alice_name, name="爱丽丝", phone="13800000001", email="alice@example.com")
        bob = await _add_user(session, bob_name, name="鲍勃", status="disabled")
        carol = await _add_user(session, carol_name, name="卡罗尔")
        await session.commit()
        scope = ConcurrentStableList([alice.id, bob.id, carol.id])

        service = InternalUserQueryService(repo)

        rows, total = await service.query(ids=scope)
        assert total == 3
        assert [row.username for row in rows] == [alice_name, bob_name, carol_name]

        rows, total = await service.query(ids=scope, keyword=ns.code("ali"))
        assert total == 1
        assert rows[0].username == alice_name

        rows, total = await service.query(ids=scope, keyword=bob_name)
        assert total == 1
        assert rows[0].username == bob_name

        rows, total = await service.query(ids=scope, status="disabled")
        assert total == 1 and rows[0].username == bob_name

        rows, total = await service.query(ids=ConcurrentStableList([alice.id]))
        assert total == 1 and rows[0].username == alice_name

        rows, total = await service.query(ids=ConcurrentStableList([alice.id]), status="disabled")
        assert total == 0 and len(rows) == 0

        rows, total = await service.query(ids=ConcurrentStableList())
        assert total >= 0  # 空集合 = 不限范围（全表口径），只验不报错

        rows, total = await service.query(ids=scope, page=2, size=2)
        assert total == 3
        assert [row.username for row in rows] == [carol_name]


@pytest.mark.kiwi_id(2257)
@pytest.mark.kiwi_id(2275)
async def test_internal_query_endpoint_requires_mdm_service(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """端点：`mdm` 按能力分配放行、`notification` 走白名单；identity / 网关 / 无票据拒。

    鉴权是 `require_capability_or_service(platform.user.query, "notification")`：mdm 靠
    `default_consumers` 落库的声明授权（装配期由启动钩子补跑），notification 是白名单。
    能力判定第一道是域归属，故 mdm 令牌须声明 `user` 域。
    """
    alice_name, bob_name = ns.code("alice"), ns.code("bob")
    async with shared_write(shared_tenant_engine) as session:
        user = await _add_user(
            session,
            alice_name,
            name="爱丽丝",
            phone="13800000001",
            email="alice@example.com",
            locale="en-US",
        )
        bob = await _add_user(session, bob_name, name="鲍勃", status="disabled")
        await session.commit()
        scope = [user.id, bob.id]

    mdm = {"Authorization": f"Bearer {issue_service_token('mdm', domains=('user',))}"}
    notification = {"Authorization": f"Bearer {issue_service_token('notification', domains=('user',))}"}

    ok = await client.post(API, json={"ids": scope}, headers=mdm)
    assert ok.status_code == 200
    body = ok.json()["data"]
    assert body["total"] == 2 and body["page"] == 1 and body["size"] == 20

    internal = await client.post(API, json={"status": "enabled", "ids": scope}, headers=notification)
    assert internal.status_code == 200
    assert internal.json()["data"]["total"] == 1

    filtered = await client.post(API, json={"keyword": alice_name, "ids": [user.id]}, headers=mdm)
    assert filtered.status_code == 200
    data = filtered.json()["data"]
    assert data["total"] == 1
    item = data["list"][0]
    assert item["id"] == str(user.id)
    assert item["username"] == alice_name
    assert item["name"] == "爱丽丝"
    assert item["status"] == "enabled"
    assert item["phone"] == "13800000001"
    assert item["email"] == "alice@example.com"
    assert item["locale"] == "en-US"
    # 用户＝系统账号：不含部门 / 岗位字段（部门关系归 mdm，需求 07-11）
    assert "dept_id" not in item
    assert "password_hash" not in item and "locked_until" not in item

    for service in ("identity", "gateway"):
        denied = await client.post(
            API, json={"ids": scope}, headers={"Authorization": f"Bearer {issue_service_token(service)}"}
        )
        assert denied.status_code == 403

    bogus = await client.post(API, json={"ids": scope}, headers={"Authorization": "Bearer bogus"})
    assert bogus.status_code == 401

    anonymous = await client.post(API, json={"ids": scope})
    assert anonymous.status_code == 401


@pytest.mark.kiwi_id(2257)
async def test_internal_query_endpoint_rejects_invalid_status(client: AsyncClient) -> None:
    """端点：状态取值非法抛参数校验错误（10001，不 500）。"""
    bad = await client.post(
        API,
        json={"status": "unknown"},
        headers={"Authorization": f"Bearer {issue_service_token('mdm', domains=('user',))}"},
    )
    assert bad.status_code == 200
    assert bad.json()["code"] == 10001
