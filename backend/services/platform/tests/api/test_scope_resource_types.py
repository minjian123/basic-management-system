"""作用域资源类型运营面端点（07D `01_01`）：查询 / 停用恢复 / 快照段。

覆盖详细设计 §5 用例 13~15 的端到端部分：
- 查询：未退役全量、`effective_status` 由两态派生；
- 停用：只写运营态、幂等、恢复可用；变更后重建进程内视图，快照段随即可见；
- 失败分支：未登记（10002）、已退役（10001）、运营态取值非法（10001）；
- 快照：`?with=resource_types` 段要素齐备、`snapshot_version = "3"`。

测试库：共享平台库 + 回滚会话；资源类型键按命名空间生成，写入不提交。
"""

from collections.abc import AsyncIterator, Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.platform.declaration import SysScopeResourceType
from bms_core.resource_scope import SCOPE_RESOURCE_DISABLED, reset_scope_resource_types
from bms_core.testing.namespace import Namespace
from bms_core.testing.transaction import rollback_session
from tests_support.auth import auth_headers

API = "/api/v1/scope-resource-types"
SNAPSHOT = "/api/v1/modules/snapshot"


@pytest.fixture(autouse=True)
async def _shared_rollback(
    service_app: FastAPI,
    shared_platform_engine: AsyncEngine,
    platform_db_write: None,
) -> AsyncIterator[None]:
    """共享平台库回滚会话（整条用例持写锁；应用装配完成后再开事务）。

    Args:
        service_app: 平台应用实例（先装配，启动期写入先落库）。
        shared_platform_engine: 共享平台库引擎。
        platform_db_write: 平台库整条用例写锁。

    Yields:
        None: 回滚会话区间。
    """
    del service_app, platform_db_write
    async with rollback_session(shared_platform_engine):
        yield


@pytest.fixture(autouse=True)
def _null_permission(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """权限校验改用占位实现（恒放行）：权限码判定归权限引擎专项，本套只验端点语义。

    Args:
        monkeypatch: 环境变量覆盖夹具。

    Yields:
        None: 用例运行期。
    """
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_PERMISSION__PROVIDER", "null")
    get_settings.cache_clear()
    reset_scope_resource_types()
    yield
    get_settings.cache_clear()
    reset_scope_resource_types()


async def _seed(service_app: FastAPI, ns: Namespace, *, status: str = "enabled") -> None:
    """向共享平台库种两行（一条正常类型、一条退役类型）。

    Args:
        service_app: 应用实例（取引擎与会话工厂）。
        ns: 本用例命名空间。
        status: 正常类型的声明态。
    """
    async with (
        session_scope(
            service_app.state.engine_registry,
            db_key=PLATFORM_DB_KEY,
            factory=service_app.state.session_factory,
        ) as session,
        session.begin(),
    ):
        session.add(
            SysScopeResourceType(
                resource_type_key=f"{ns.prefix}.topic",
                name="主题",
                name_pattern=r"^[a-z][a-z0-9_]{0,63}$",
                max_length=64,
                retention_days=30,
                removal_policy="purge",
                product_key=ns.prefix,
                status=status,
                admin_status="enabled",
                declaration_version=2,
                content_hash="a" * 64,
            )
        )
        session.add(
            SysScopeResourceType(
                resource_type_key=f"{ns.prefix}.old_bucket",
                name="旧存储桶",
                name_pattern=r"^[a-z][a-z0-9_]{0,63}$",
                max_length=64,
                retention_days=0,
                removal_policy="archive",
                product_key=ns.prefix,
                status="retired",
                admin_status="enabled",
                declaration_version=1,
                content_hash="b" * 64,
            )
        )


async def test_list_returns_declared_types(client: AsyncClient, service_app: FastAPI, ns: Namespace) -> None:
    """查询：列出未退役类型，`effective_status` 由声明态 + 运营态派生。"""
    await _seed(service_app, ns)
    client.headers.update(auth_headers())
    key = f"{ns.prefix}.topic"

    response = await client.get(API)

    assert response.status_code == 200
    rows = [row for row in response.json()["data"] if row["resource_type_key"] == key]
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "enabled"
    assert row["admin_status"] == "enabled"
    assert row["effective_status"] == "enabled"
    assert row["product_key"] == ns.prefix
    assert row["declaration_version"] == 2


async def test_patch_disable_is_idempotent_and_reaches_snapshot(
    client: AsyncClient, service_app: FastAPI, ns: Namespace
) -> None:
    """停用：只写运营态、幂等；视图重建后快照段随即可见；恢复写回启用。"""
    await _seed(service_app, ns)
    client.headers.update(auth_headers())
    key = f"{ns.prefix}.topic"

    first = await client.patch(f"{API}/{key}", json={"admin_status": SCOPE_RESOURCE_DISABLED})
    assert first.status_code == 200
    payload = first.json()["data"]
    assert payload["admin_status"] == SCOPE_RESOURCE_DISABLED
    assert payload["status"] == "enabled", "声明态不被运营期动作改写"
    assert payload["effective_status"] == "disabled"

    again = await client.patch(f"{API}/{key}", json={"admin_status": SCOPE_RESOURCE_DISABLED})
    assert again.status_code == 200
    assert again.json()["data"]["effective_status"] == "disabled"

    snapshot = await client.get(SNAPSHOT, params={"with": "resource_types"})
    data = snapshot.json()["data"]
    assert data["snapshot_version"] == "3"
    item = next(row for row in data["resource_types"] if row["resource_type_key"] == key)
    assert item["admin_status"] == SCOPE_RESOURCE_DISABLED
    assert set(item) == {
        "resource_type_key",
        "name",
        "name_pattern",
        "max_length",
        "retention_days",
        "removal_policy",
        "product_key",
        "status",
        "admin_status",
        "declaration_version",
    }

    restored = await client.patch(f"{API}/{key}", json={"admin_status": "enabled"})
    assert restored.json()["data"]["effective_status"] == "enabled"


async def test_patch_rejects_unknown_retired_and_invalid_value(
    client: AsyncClient, service_app: FastAPI, ns: Namespace
) -> None:
    """失败分支：未登记 10002、已退役 10001、运营态取值非法 10001。"""
    await _seed(service_app, ns)
    client.headers.update(auth_headers())
    key = f"{ns.prefix}.topic"

    missing = await client.patch(f"{API}/{ns.prefix}.missing", json={"admin_status": "disabled"})
    assert missing.json()["code"] == 10002

    retired = await client.patch(f"{API}/{ns.prefix}.old_bucket", json={"admin_status": "disabled"})
    assert retired.json()["code"] == 10001

    invalid = await client.patch(f"{API}/{key}", json={"admin_status": "paused"})
    assert invalid.json()["code"] == 10001


async def test_snapshot_segment_empty_when_not_requested(client: AsyncClient) -> None:
    """未请求该段：`resource_types` 为空数组（不额外查询、不多暴露）。"""
    client.headers.update(auth_headers())

    response = await client.get(SNAPSHOT, params={"with": "products"})

    data = response.json()["data"]
    assert data["resource_types"] == []
    assert data["snapshot_version"] == "3"
