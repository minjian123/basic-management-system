"""作用域资源类型运营面端点（07D `01_01`）：查询 / 停用恢复 / 快照段。

覆盖详细设计 §5 用例 13~15 的端到端部分：
- 查询：未退役全量、`effective_status` 由两态派生；
- 停用：只写运营态、幂等、恢复可用；变更后重建进程内视图，快照段随即可见；
- 失败分支：未登记（10002）、已退役（10001）、运营态取值非法（10001）；
- 快照：`?with=resource_types` 段要素齐备、`snapshot_version = "3"`。
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from bms_core.db.keys import PLATFORM_DB_KEY
from bms_core.db.session import session_scope
from bms_core.models.platform.declaration import SysScopeResourceType
from bms_core.resource_scope import SCOPE_RESOURCE_DISABLED, reset_scope_resource_types
from tests_support.auth import auth_headers

pytestmark = pytest.mark.own_db(
    "被测对象是「运营态写入 → 视图重建 → 快照可见」的链路，需要空库起步逐例种子；"
    "共享库上整表清场会破坏并行中他人用例的数据"
)

API = "/api/v1/scope-resource-types"
SNAPSHOT = "/api/v1/modules/snapshot"

TYPE_KEY = "demo.topic"
RETIRED_KEY = "demo.old_bucket"


@pytest.fixture(autouse=True)
def _isolated_platform(platform_db: None, isolated_platform_db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:  # pyright: ignore[reportUnusedFunction]
    """独占平台库（逐例一份 tmp 库），避免清场影响并行 worker。

    Args:
        platform_db: 套件平台库夹具（仅用于排序：旧夹具先设置）。
        isolated_platform_db_url: 独占平台库连接串。
        monkeypatch: 环境变量覆盖夹具。
    """
    from bms_core.core.config import get_settings

    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", isolated_platform_db_url)
    get_settings.cache_clear()


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


async def _seed(service_app: FastAPI, *, status: str = "enabled") -> None:
    """向独占平台库种两行（一条正常类型、一条退役类型）。

    Args:
        service_app: 应用实例（取引擎与会话工厂）。
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
                resource_type_key=TYPE_KEY,
                name="主题",
                name_pattern=r"^[a-z][a-z0-9_]{0,63}$",
                max_length=64,
                retention_days=30,
                removal_policy="purge",
                product_key="demo",
                status=status,
                admin_status="enabled",
                declaration_version=2,
                content_hash="a" * 64,
            )
        )
        session.add(
            SysScopeResourceType(
                resource_type_key=RETIRED_KEY,
                name="旧存储桶",
                name_pattern=r"^[a-z][a-z0-9_]{0,63}$",
                max_length=64,
                retention_days=0,
                removal_policy="archive",
                product_key="demo",
                status="retired",
                admin_status="enabled",
                declaration_version=1,
                content_hash="b" * 64,
            )
        )


async def test_list_returns_declared_types(client: AsyncClient, service_app: FastAPI) -> None:
    """查询：列出未退役类型，`effective_status` 由声明态 + 运营态派生。"""
    await _seed(service_app)
    client.headers.update(auth_headers())

    response = await client.get(API)

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [row["resource_type_key"] for row in rows] == [TYPE_KEY]
    assert rows[0]["status"] == "enabled"
    assert rows[0]["admin_status"] == "enabled"
    assert rows[0]["effective_status"] == "enabled"
    assert rows[0]["product_key"] == "demo"
    assert rows[0]["declaration_version"] == 2


async def test_patch_disable_is_idempotent_and_reaches_snapshot(client: AsyncClient, service_app: FastAPI) -> None:
    """停用：只写运营态、幂等；视图重建后快照段随即可见；恢复写回启用。"""
    await _seed(service_app)
    client.headers.update(auth_headers())

    first = await client.patch(f"{API}/{TYPE_KEY}", json={"admin_status": SCOPE_RESOURCE_DISABLED})
    assert first.status_code == 200
    payload = first.json()["data"]
    assert payload["admin_status"] == SCOPE_RESOURCE_DISABLED
    assert payload["status"] == "enabled", "声明态不被运营期动作改写"
    assert payload["effective_status"] == "disabled"

    again = await client.patch(f"{API}/{TYPE_KEY}", json={"admin_status": SCOPE_RESOURCE_DISABLED})
    assert again.status_code == 200
    assert again.json()["data"]["effective_status"] == "disabled"

    snapshot = await client.get(SNAPSHOT, params={"with": "resource_types"})
    data = snapshot.json()["data"]
    assert data["snapshot_version"] == "3"
    item = next(row for row in data["resource_types"] if row["resource_type_key"] == TYPE_KEY)
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

    restored = await client.patch(f"{API}/{TYPE_KEY}", json={"admin_status": "enabled"})
    assert restored.json()["data"]["effective_status"] == "enabled"


async def test_patch_rejects_unknown_retired_and_invalid_value(client: AsyncClient, service_app: FastAPI) -> None:
    """失败分支：未登记 10002、已退役 10001、运营态取值非法 10001。"""
    await _seed(service_app)
    client.headers.update(auth_headers())

    missing = await client.patch(f"{API}/demo.missing", json={"admin_status": "disabled"})
    assert missing.json()["code"] == 10002

    retired = await client.patch(f"{API}/{RETIRED_KEY}", json={"admin_status": "disabled"})
    assert retired.json()["code"] == 10001

    invalid = await client.patch(f"{API}/{TYPE_KEY}", json={"admin_status": "paused"})
    assert invalid.json()["code"] == 10001


async def test_snapshot_segment_empty_when_not_requested(client: AsyncClient) -> None:
    """未请求该段：`resource_types` 为空数组（不额外查询、不多暴露）。"""
    client.headers.update(auth_headers())

    response = await client.get(SNAPSHOT, params={"with": "products"})

    data = response.json()["data"]
    assert data["resource_types"] == []
    assert data["snapshot_version"] == "3"
