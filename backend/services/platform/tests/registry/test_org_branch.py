"""组织域分支换算用例（07B `03_01`）。

覆盖 `bms_platform.services.org_branch` 的三个公开换算：分支三要素、分支动作名、内部写请求。
端点取自**真实注册视图**（conftest 已登记 mdm 对端能力），错误分支用 `dataclasses.replace` 构造，
避免手搓结构体与声明漂移。
"""

from dataclasses import replace

import pytest

from bms_core.collaboration.base import CapabilityEndpoint
from bms_core.collaboration.resolver import resolve_capability
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError
from bms_core.db.keys import TENANT_DB_KEY_PREFIX, build_tenant_db_key
from bms_platform.services.org_branch import branch_op, branch_target, internal_write_request

_POSTS = "mdm.org.user-posts.assign"
_DEPTS = "mdm.org.user-depts.assign"


@pytest.fixture
def endpoints() -> tuple[CapabilityEndpoint, CapabilityEndpoint]:
    """取组织域两段能力的真实取用结果（同一分支）。

    Returns:
        tuple[CapabilityEndpoint, CapabilityEndpoint]: 岗位段与部门段。
    """
    return resolve_capability(_POSTS), resolve_capability(_DEPTS)


def test_branch_target_returns_three_elements(endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint]) -> None:
    """同分支同承载服务：返回（分支标识, 承载服务, 租户库键），库键按服务键派生。"""
    branch_id, service_key, db_key = branch_target(
        ConcurrentStableList(endpoints), platform_db_key=f"{TENANT_DB_KEY_PREFIX}platform"
    )

    assert branch_id
    assert service_key == "mdm"
    assert db_key == build_tenant_db_key("platform", service="mdm")


def test_branch_target_prefers_declared_db_key(endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint]) -> None:
    """声明给了库键（拓扑解析有值）：直接用，不再派生。"""
    with_db_key = replace(endpoints[0], target=replace(endpoints[0].target, db_keys=("txn_org",)))

    _branch_id, _service_key, db_key = branch_target(
        ConcurrentStableList([with_db_key]), platform_db_key="platform_platform"
    )

    assert db_key == "txn_org"


def test_branch_target_rejects_split_branch(endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint]) -> None:
    """两段分支标识不一致：fail-closed（不得把一条事务拆成两个参与者）。"""
    other = replace(endpoints[1], branch_id="other")

    with pytest.raises(CatalogError, match="声明不一致"):
        branch_target(ConcurrentStableList([endpoints[0], other]), platform_db_key="platform_platform")


def test_branch_target_rejects_missing_branch_id(endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint]) -> None:
    """缺分支标识：fail-closed（写能力须声明事务分支）。"""
    empty = replace(endpoints[0], branch_id=None)

    with pytest.raises(CatalogError, match="缺少 branch_id"):
        branch_target(ConcurrentStableList([empty]), platform_db_key="platform_platform")


def test_branch_op_reads_declaration(endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint]) -> None:
    """分支动作名取自声明；缺失即拒。"""
    assert branch_op(endpoints[0])

    with pytest.raises(CatalogError, match="缺少 branch_op"):
        branch_op(replace(endpoints[0], branch_op=None))


def test_internal_write_request_passes_idempotency_header(
    endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint],
) -> None:
    """内部写请求：方法 PUT、路径按声明模板填充、幂等键经请求头透传。"""
    request = internal_write_request(
        endpoints[0],
        params=ConcurrentStableFrozenDict({"user_id": "42"}),
        body=ConcurrentStableFrozenDict({"post_ids": [1, 2]}),
        idempotency_key="k-1",
        tenant_id="1",
    )

    assert request.method == "PUT"
    assert request.service == "mdm"
    assert request.path.endswith("/42")
    assert request.headers is not None
    assert request.headers.get("Idempotency-Key") == "k-1"
    assert request.tenant_id == "1"


def test_internal_write_request_without_idempotency_key(
    endpoints: tuple[CapabilityEndpoint, CapabilityEndpoint],
) -> None:
    """无幂等键：仍传空头集合（不传 None），调用侧断言口径不变。"""
    request = internal_write_request(
        endpoints[0],
        params=ConcurrentStableFrozenDict({"user_id": "42"}),
        body=ConcurrentStableFrozenDict({}),
        idempotency_key=None,
        tenant_id=None,
    )

    assert request.headers is not None
    assert dict(request.headers) == {}
