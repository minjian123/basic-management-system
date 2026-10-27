"""由能力取用结果构造服务间调用请求（07B `02_02`；Kiwi 编号归 `05_01` 统一登记）。

覆盖：目标服务取第二段解析结果、路径按模板填充、`codes` 类不得发起调用、路径参数缺失即拒、
查询 / 请求体 / 租户 / 韧性策略透传。
"""

import re
from collections.abc import Iterator

import pytest

from bms_core.collaboration import build_capability_request, resolve_capability
from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList
from bms_core.core.exceptions import ParamError
from bms_core.servicecall.base import ServiceCallPolicy
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    register_domain_services,
    reset_collaboration_records,
    reset_domain_services,
)


def _record(
    *, kind: str = "txn-branch", path: str | None = "/api/v1/demo/internal/user-posts/{user_id}"
) -> CollaborationRecord:
    """构造能力记录（缺省事务分支类）。

    Args:
        kind: 访问面类别。
        path: 访问面路径模板（`codes` 类为 None）。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name="demo.org.user-posts.assign",
        domain="org",
        kind=kind,
        contract_version="0.1.0",
        path=path,
        product_key="demo",
        branch_id="d",
        branch_op="demo.user-posts.assign",
        permission_codes=ConcurrentStableFrozenList(("demo:update",))
        if kind == "codes"
        else ConcurrentStableFrozenList(),
        frontend_prefix="demo",
    )


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例前后复位能力记录与域→服务键映射。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_domain_services()
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))
    yield
    reset_collaboration_records()
    reset_domain_services()


def test_build_request_fills_service_and_path() -> None:
    """请求目标取第二段解析的服务标识，路径按模板填充（消费方不自拼服务键与路径）。"""
    register_collaboration_records((_record(),))

    request = build_capability_request(
        resolve_capability("demo.org.user-posts.assign"),
        method="POST",
        params=ConcurrentStableFrozenDict({"user_id": 42}),
        tenant_id="1001",
    )

    assert request.service == "mdm"
    assert request.method == "POST"
    assert request.path == "/api/v1/demo/internal/user-posts/42"
    assert request.tenant_id == "1001"
    assert request.policy.timeout == ServiceCallPolicy().timeout


def test_build_request_passes_query_body_and_policy() -> None:
    """查询串 / 请求体 / 韧性策略原样透传（不改变既有调用链语义）。"""
    register_collaboration_records((_record(path="/api/v1/demo/user-posts"),))
    policy = ServiceCallPolicy(timeout=1.5, max_retries=0)

    request = build_capability_request(
        resolve_capability("demo.org.user-posts.assign"),
        method="POST",
        query=ConcurrentStableFrozenDict({"dry_run": "1"}),
        json_body=ConcurrentStableFrozenDict({"post_ids": ("p1",)}),
        policy=policy,
    )

    assert request.path == "/api/v1/demo/user-posts"
    assert request.query == {"dry_run": "1"}
    assert request.json_body == {"post_ids": ("p1",)}
    assert request.policy is policy


def test_build_request_rejects_codes_capability() -> None:
    """`codes` 类无访问面 → 抛 `ParamError`，不得据此发起调用。"""
    register_collaboration_records((_record(kind="codes", path=None),))

    with pytest.raises(ParamError, match=re.escape("能力无访问面（kind=codes）：demo.org.user-posts.assign")):
        build_capability_request(resolve_capability("demo.org.user-posts.assign"), method="GET")


def test_build_request_rejects_missing_path_parameter() -> None:
    """路径参数缺失即拒（不静默留占位符到远端）。"""
    register_collaboration_records((_record(),))

    with pytest.raises(ParamError, match="访问面缺少路径参数（user_id）"):
        build_capability_request(resolve_capability("demo.org.user-posts.assign"), method="POST")
