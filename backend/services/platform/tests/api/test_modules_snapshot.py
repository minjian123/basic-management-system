"""目录快照带参分支（`?with=`）：产品段与能力段一并下发，缺省契约不变（07B `02_02`）。

Kiwi 2363（07B `03_02` 前端目录消费）：能力段含 `kind`（前端按「业务域 + 种类」取址）。
覆盖详细设计 §5 用例 13~15、18：
无参仍是数组、带参三段 + `snapshot_version`、能力段含 `kind` 且不含 `path` 与授权信息、`codes` / `disabled` 不下发、
`deprecated` 带 `replacement`、未装载时 `warnings` 非空、非法段名报 10001。
"""

from collections.abc import Iterator
from typing import cast

import pytest
from httpx import AsyncClient

from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.schemas.module import ModuleResponse
from bms_core.services.module_registry import (
    CollaborationRecord,
    CollaborationStatus,
    ProductRecord,
    register_collaboration_records,
    register_product_records,
    reset_collaboration_records,
    reset_product_records,
    service_catalog_view,
)
from tests_support.auth import auth_headers

pytestmark = pytest.mark.kiwi_id(2363)

_DEMO_RECORDS: ConcurrentStableList[CollaborationRecord] = ConcurrentStableList(
    (
        CollaborationRecord(
            name="demo.org.user-roles",
            domain="org",
            kind="read",
            contract_version="0.1.0",
            path="/api/v1/demo/user-roles",
            product_key="demo",
            frontend_prefix="demo",
        ),
        CollaborationRecord(
            name="demo.org.dept-data",
            domain="org",
            kind="dataset",
            contract_version="0.1.0",
            path="/api/v1/demo/data-source/dept-tree",
            product_key="demo",
            data_source_key="demo_dept",
            frontend_prefix="demo",
        ),
        CollaborationRecord(
            name="demo.org.admin-codes",
            domain="org",
            kind="codes",
            contract_version="0.1.0",
            product_key="demo",
            permission_codes=ConcurrentStableFrozenList(("demo:query",)),
        ),
        CollaborationRecord(
            name="demo.org.legacy-roles",
            domain="org",
            kind="read",
            contract_version="0.1.0",
            path="/api/v1/demo/legacy-roles",
            product_key="demo",
            frontend_prefix="demo",
            status=CollaborationStatus.DEPRECATED,
            replacement="demo.org.user-roles",
        ),
        CollaborationRecord(
            name="demo.org.retired-roles",
            domain="org",
            kind="read",
            contract_version="0.1.0",
            path="/api/v1/demo/retired-roles",
            product_key="demo",
            frontend_prefix="demo",
            status=CollaborationStatus.DISABLED,
        ),
    )
)
"""夹具能力集：读 / 数据集 / `codes` / `deprecated` / `disabled` 各一条（覆盖下发过滤口径）。"""


@pytest.fixture
def demo_catalog_entries() -> Iterator[None]:
    """登记夹具产品档案与能力集；用例结束清空（后续用例的清单夹具会重新装载）。

    Yields:
        None: 用例运行期。
    """
    register_product_records((ProductRecord(product_key="demo", name="演示产品", status="enabled"),))
    register_collaboration_records(_DEMO_RECORDS)
    yield
    reset_product_records()
    reset_collaboration_records()


async def test_snapshot_without_params_keeps_array_contract(client: AsyncClient) -> None:
    """无参 / 仅逗号：仍是 `ModuleResponse` 数组（缺省契约逐字段不变，用例 13）。"""
    client.headers.update(auth_headers())
    expected = [module.module_key for module in service_catalog_view()]

    plain = await client.get("/api/v1/modules/snapshot")
    commas = await client.get("/api/v1/modules/snapshot", params={"with": ",,"})

    assert plain.status_code == 200
    assert commas.status_code == 200
    for response in (plain, commas):
        payload = response.json()["data"]
        assert isinstance(payload, list)
        rows = cast("list[dict[str, object]]", payload)
        assert [item["module_key"] for item in rows] == expected
        assert set(rows[0]) == set(ModuleResponse.model_fields)


async def test_snapshot_with_segments_returns_products_and_collaborations(
    client: AsyncClient, demo_catalog_entries: None
) -> None:
    """带参：三段 + `snapshot_version`；能力段不含 `path` 与授权信息，`codes` / `disabled` 不下发。"""
    client.headers.update(auth_headers())

    response = await client.get("/api/v1/modules/snapshot", params={"with": "products,collaborations"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert set(data) == {"modules", "products", "collaborations", "snapshot_version", "warnings"}
    assert data["snapshot_version"] == "2"
    assert [item["module_key"] for item in data["modules"]] == [module.module_key for module in service_catalog_view()]

    demo_products = [item for item in data["products"] if item["product_key"] == "demo"]
    assert demo_products == [{"product_key": "demo", "name": "演示产品", "status": "enabled"}]
    assert set(data["products"][0]) == {"product_key", "name", "status"}

    names = [item["name"] for item in data["collaborations"]]
    assert "demo.org.user-roles" in names
    assert "demo.org.dept-data" in names
    assert "demo.org.legacy-roles" in names
    assert "demo.org.admin-codes" not in names
    assert "demo.org.retired-roles" not in names

    first = next(item for item in data["collaborations"] if item["name"] == "demo.org.user-roles")
    assert set(first) == {
        "name",
        "domain",
        "kind",
        "product_key",
        "frontend_prefix",
        "contract_version",
        "status",
        "replacement",
    }
    assert first["frontend_prefix"] == "demo"
    assert first["kind"] == "read"

    dataset = next(item for item in data["collaborations"] if item["name"] == "demo.org.dept-data")
    assert dataset["kind"] == "dataset"

    legacy = next(item for item in data["collaborations"] if item["name"] == "demo.org.legacy-roles")
    assert legacy["status"] == "deprecated"
    assert legacy["replacement"] == "demo.org.user-roles"


async def test_snapshot_subset_only_returns_requested_segments(client: AsyncClient, demo_catalog_entries: None) -> None:
    """多值子集：未请求的段为空数组（不额外查询、不多暴露）。"""
    client.headers.update(auth_headers())

    only_collaborations = await client.get("/api/v1/modules/snapshot", params={"with": "collaborations"})
    only_products = await client.get("/api/v1/modules/snapshot", params={"with": "products"})

    collaborations_data = only_collaborations.json()["data"]
    assert collaborations_data["products"] == []
    assert [item["name"] for item in collaborations_data["collaborations"]] != []

    products_data = only_products.json()["data"]
    assert products_data["collaborations"] == []
    assert [item["product_key"] for item in products_data["products"]] != []


async def test_snapshot_rejects_unknown_segment(client: AsyncClient) -> None:
    """`with` 出现未支持的段名 → 参数非法（10001），不静默回退数组契约（用例 18）。"""
    client.headers.update(auth_headers())

    response = await client.get("/api/v1/modules/snapshot", params={"with": "collaborations,unknown"})

    assert response.status_code == 200
    assert response.json()["code"] == 10001
    assert "快照附带段不支持：unknown" in response.json()["message"]


async def test_snapshot_warns_when_collaborations_not_loaded(client: AsyncClient) -> None:
    """未装载能力声明：`collaborations` 为空数组且 `warnings` 非空（用例 15，不静默）。"""
    client.headers.update(auth_headers())
    reset_collaboration_records()

    response = await client.get("/api/v1/modules/snapshot", params={"with": "collaborations"})

    data = response.json()["data"]
    assert data["collaborations"] == []
    assert data["warnings"] == ["能力目录为空（产品清单未装载或未声明 [[collaborations]] 段）"]
