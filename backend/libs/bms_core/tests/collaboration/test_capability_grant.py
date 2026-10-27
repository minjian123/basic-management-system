"""跨产品能力分配与授权（07B `02_04`；Kiwi 编号归 `05_01` 统一登记）。

覆盖详细设计 §5 用例 1~14 的内核部分：声明默认与差异计划（幂等 / 移除 / 回归 / 人工覆盖）、
有效性边界、scope 派生（含类别映射与去重）、入站判定与拒绝语义（指标 + 日志）、
授权视图 TTL 与刷新失败兜底、远端来源解析、请求构造自动带 scope。
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from bms_core.collaboration import (
    CALL_RESULT_ALLOWED,
    CALL_RESULT_DENIED,
    CALL_RESULT_EXPIRED,
    METRIC_CAPABILITY_CALL,
    METRIC_CAPABILITY_DENIED,
    SCOPE_PREFIX,
    CapabilityGrant,
    build_capability_request,
    capability_grant_pairs,
    check_capability_access,
    declare_capability_grants,
    ensure_grant_view,
    granted_consumers,
    granted_scopes,
    invalidate_capability_grants,
    is_grant_effective,
    plan_grant_sync,
    register_capability_grant_source,
    reset_capability_grants,
    resolve_capability,
    scope_action_of,
)
from bms_core.collaboration.grant import RemoteCapabilityGrantSource
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import CatalogError, PermissionError
from bms_core.models.platform.capability_grant import (
    GRANT_NOTE_DECLARED,
    GRANT_NOTE_REMOVED,
    GRANT_SOURCE_MANUAL,
    GRANT_STATUS_DISABLED,
    GRANT_STATUS_ENABLED,
)
from bms_core.servicecall.base import ServiceResponse
from bms_core.services.module_registry import (
    CollaborationRecord,
    register_collaboration_records,
    reset_collaboration_records,
    reset_domain_services,
)
from tests_support.metrics import RecordingMetrics

_NOW = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)


class _FakeSource:
    """授权视图来源替身：按维度返回预置记录并计数加载次数。"""

    def __init__(self, grants: ConcurrentStableList[CapabilityGrant]) -> None:
        """初始化。

        Args:
            grants: 每次加载返回的授权记录。
        """
        self._grants = grants
        self.loads = 0
        self.fail = False

    async def load(
        self, *, provider: str | None = None, consumer: str | None = None
    ) -> ConcurrentStableList[CapabilityGrant]:
        """返回预置记录（`fail` 为真时抛错，用于刷新失败分支）。

        Args:
            provider: 提供方业务域（未使用）。
            consumer: 消费方服务键（未使用）。

        Returns:
            ConcurrentStableList[CapabilityGrant]: 授权记录。

        Raises:
            CatalogError: `fail` 为真时模拟来源不可用。
        """
        del provider, consumer
        self.loads += 1
        if self.fail:
            raise CatalogError("来源不可用")
        return self._grants


def _record(
    name: str = "demo.org.user-roles",
    *,
    kind: str = "read",
    domain: str = "org",
    consumers: ConcurrentStableFrozenList[str] | None = None,
) -> CollaborationRecord:
    """构造能力记录（缺省读出口 + 平台为默认消费方）。

    Args:
        name: 能力名。
        kind: 访问面类别。
        domain: 提供方业务域。
        consumers: 默认消费方。

    Returns:
        CollaborationRecord: 能力记录。
    """
    return CollaborationRecord(
        name=name,
        domain=domain,
        kind=kind,
        contract_version="0.1.0",
        path=None if kind == "codes" else "/api/v1/demo/read",
        product_key="demo",
        branch_id="d" if kind == "txn-branch" else None,
        branch_op="demo.op" if kind == "txn-branch" else None,
        data_source_key="demo_dept" if kind == "dataset" else None,
        permission_codes=(
            ConcurrentStableFrozenList(("demo:query",)) if kind == "codes" else ConcurrentStableFrozenList()
        ),
        frontend_prefix="demo",
        default_consumers=(
            ConcurrentStableFrozenList(("platform",)) if consumers is None else ConcurrentStableFrozenList(consumers)
        ),
    )


def _grant(
    capability: str = "demo.org.user-roles",
    consumer: str = "platform",
    *,
    source: str = "declared",
    status: str = GRANT_STATUS_ENABLED,
    expire_at: datetime | None = None,
    note: str = "",
) -> CapabilityGrant:
    """构造授权记录。

    Args:
        capability: 能力名。
        consumer: 消费方标识。
        source: 来源。
        status: 状态。
        expire_at: 有效期。
        note: 说明。

    Returns:
        CapabilityGrant: 授权记录。
    """
    return CapabilityGrant(
        capability_name=capability,
        consumer_key=consumer,
        source=source,
        status=status,
        expire_at=expire_at,
        note=note,
    )


@pytest.fixture(autouse=True)
def _isolate_state() -> Iterator[None]:
    """每例前后复位能力记录与授权视图状态。

    Yields:
        None: 用例运行期。
    """
    reset_collaboration_records()
    reset_capability_grants()
    reset_domain_services()
    yield
    reset_collaboration_records()
    reset_capability_grants()
    reset_domain_services()


def test_declare_grants_follows_manifest_default_consumers() -> None:
    """声明基线＝各能力 `default_consumers` 展开（`declared` / `enabled` / 默认说明）。"""
    register_collaboration_records((_record(consumers=ConcurrentStableFrozenList(("platform", "mdm"))),))

    declared = declare_capability_grants()

    assert [(item.consumer_key, item.source, item.status) for item in declared] == [
        ("platform", "declared", "enabled"),
        ("mdm", "declared", "enabled"),
    ]
    assert declared[0].note == GRANT_NOTE_DECLARED


def test_plan_creates_missing_and_is_idempotent() -> None:
    """库中无记录→新建；已启用的声明记录不重复新建（幂等）。"""
    declared = ConcurrentStableList([_grant()])

    first = plan_grant_sync(declared, ConcurrentStableList())
    assert [item.consumer_key for item in first.creates] == ["platform"]
    assert list(first.restores) == [] and list(first.revokes) == []

    second = plan_grant_sync(declared, ConcurrentStableList([_grant()]))
    assert list(second.creates) == [] and list(second.restores) == [] and list(second.revokes) == []


def test_plan_revokes_removed_consumer_and_restores_on_return() -> None:
    """声明移除→置撤销并记「声明移除」；声明回归→恢复有效（人工介入过的记录除外）。"""
    current = ConcurrentStableList([_grant()])

    removed = plan_grant_sync(ConcurrentStableList(), current)
    assert [item.status for item in removed.revokes] == [GRANT_STATUS_DISABLED]
    assert removed.revokes[0].note == GRANT_NOTE_REMOVED

    disabled = ConcurrentStableList([_grant(status=GRANT_STATUS_DISABLED, note=GRANT_NOTE_REMOVED)])
    restored = plan_grant_sync(ConcurrentStableList([_grant()]), disabled, now=_NOW)
    assert [item.status for item in restored.restores] == [GRANT_STATUS_ENABLED]
    assert restored.restores[0].note == GRANT_NOTE_DECLARED


def test_plan_keeps_manual_override_and_warns() -> None:
    """人工记录不被声明覆盖：人工撤销时输出不一致警示、不禁用也不恢复。"""
    manual_revoked = ConcurrentStableList([_grant(source=GRANT_SOURCE_MANUAL, status=GRANT_STATUS_DISABLED)])

    plan = plan_grant_sync(ConcurrentStableList([_grant()]), manual_revoked, now=_NOW)

    assert list(plan.creates) == [] and list(plan.restores) == [] and list(plan.revokes) == []
    assert "声明与人工不一致" in plan.warnings[0]


def test_plan_leaves_manual_grant_outside_declaration_untouched() -> None:
    """人工授予（声明里没有该消费方）既不撤销也不告警（人工覆盖属正常态）。"""
    current = ConcurrentStableList([_grant(consumer="mdm", source=GRANT_SOURCE_MANUAL)])

    plan = plan_grant_sync(ConcurrentStableList([_grant()]), current)

    assert list(plan.revokes) == [] and list(plan.warnings) == []
    assert [item.consumer_key for item in plan.creates] == ["platform"]


def test_grant_effective_boundary() -> None:
    """有效性边界：`expire_at == now` 视为无效，晚一毫秒有效；撤销即无效。"""
    assert is_grant_effective(_grant(expire_at=_NOW + timedelta(seconds=1)), now=_NOW) is True
    assert is_grant_effective(_grant(expire_at=_NOW), now=_NOW) is False
    assert is_grant_effective(_grant(status=GRANT_STATUS_DISABLED), now=_NOW) is False
    assert is_grant_effective(_grant(), now=_NOW) is True


def test_scope_action_mapping() -> None:
    """类别 → scope 动作：读 / 数据集为 `read`，写 / 事务分支为 `write`，`codes` 不产生。"""
    assert scope_action_of("read") == "read"
    assert scope_action_of("dataset") == "read"
    assert scope_action_of("write") == "write"
    assert scope_action_of("txn-branch") == "write"
    assert scope_action_of("codes") is None


async def test_granted_scopes_cover_kinds_and_dedupe() -> None:
    """出站 scope：按授权派生 `svc:{业务域}:{read|write}`、同域去重、`codes` 与禁用能力不产生。"""
    register_collaboration_records(
        (
            _record("demo.org.user-roles", kind="read"),
            _record("demo.org.user-posts.assign", kind="txn-branch"),
            _record("demo.org.dept-data", kind="dataset"),
            _record("demo.org.admin-codes", kind="codes", consumers=ConcurrentStableFrozenList()),
        )
    )
    register_capability_grant_source(
        _FakeSource(
            ConcurrentStableList(
                [
                    _grant("demo.org.user-roles"),
                    _grant("demo.org.user-posts.assign"),
                    _grant("demo.org.dept-data"),
                    _grant("demo.org.admin-codes"),
                ]
            )
        )
    )
    await ensure_grant_view(consumer="platform", now=_NOW)

    scopes = granted_scopes("platform")

    assert list(scopes) == [f"{SCOPE_PREFIX}:org:read", f"{SCOPE_PREFIX}:org:write"]


async def test_granted_consumers_filters_effective_rows() -> None:
    """入站允许集合：仅有效分配（撤销与过期不计入）。"""
    register_collaboration_records((_record(consumers=ConcurrentStableFrozenList(("platform", "mdm"))),))
    register_capability_grant_source(
        _FakeSource(
            ConcurrentStableList(
                [
                    _grant(consumer="platform"),
                    _grant(consumer="mdm", status=GRANT_STATUS_DISABLED),
                ]
            )
        )
    )
    await ensure_grant_view(provider="org", now=_NOW)

    assert list(granted_consumers("demo.org.user-roles")) == ["platform"]


async def test_check_access_allowed_counts_call() -> None:
    """有有效分配：放行并计 `call_total{result=allowed}`（不计越权）。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant()])))
    metrics = RecordingMetrics()

    await check_capability_access("demo.org.user-roles", "platform", metrics=metrics)

    assert metrics.counter_values(METRIC_CAPABILITY_CALL) == [1.0]
    assert metrics.labels_of(METRIC_CAPABILITY_CALL)[0] == {
        "capability": "demo.org.user-roles",
        "consumer": "platform",
        "result": CALL_RESULT_ALLOWED,
    }
    assert list(metrics.counter_values(METRIC_CAPABILITY_DENIED)) == []


async def test_check_access_denied_raises_permission_error_and_counts() -> None:
    """无分配：`PermissionError`（30001 / 403），消息含能力名与消费方，并计越权。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant(consumer="mdm")])))
    metrics = RecordingMetrics()

    with pytest.raises(PermissionError) as excinfo:
        await check_capability_access("demo.org.user-roles", "platform", metrics=metrics)

    assert "demo.org.user-roles" in str(excinfo.value) and "platform" in str(excinfo.value)
    labels = metrics.labels_of(METRIC_CAPABILITY_CALL)[0]
    assert labels is not None and labels["result"] == CALL_RESULT_DENIED
    assert metrics.counter_values(METRIC_CAPABILITY_DENIED) == [1.0]


async def test_check_access_expired_is_rejected_with_reason() -> None:
    """已过期：按未授权拒绝并在消息中标注「已过期」，`result=expired`。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(
        _FakeSource(ConcurrentStableList([_grant(expire_at=datetime(2020, 1, 1, tzinfo=UTC))]))
    )
    metrics = RecordingMetrics()

    with pytest.raises(PermissionError) as excinfo:
        await check_capability_access("demo.org.user-roles", "platform", metrics=metrics)

    assert "授权已过期" in str(excinfo.value)
    labels = metrics.labels_of(METRIC_CAPABILITY_CALL)[0]
    assert labels is not None and labels["result"] == CALL_RESULT_EXPIRED


async def test_ensure_view_caches_within_ttl_and_refreshes_after() -> None:
    """视图快照：TTL 内命中缓存（不重复加载），超时后重拉。"""
    source = _FakeSource(ConcurrentStableList([_grant()]))
    register_capability_grant_source(source)

    await ensure_grant_view(provider="org", now=_NOW)
    await ensure_grant_view(provider="org", now=_NOW + timedelta(seconds=10))
    assert source.loads == 1

    await ensure_grant_view(provider="org", now=_NOW + timedelta(seconds=120))
    assert source.loads == 2


async def test_ensure_view_keeps_snapshot_when_refresh_fails() -> None:
    """刷新失败：保留旧快照（有界过期），不抛错、不放行未加载视图。"""
    source = _FakeSource(ConcurrentStableList([_grant()]))
    register_capability_grant_source(source)
    await ensure_grant_view(provider="org", now=_NOW)

    source.fail = True
    snapshot = await ensure_grant_view(provider="org", now=_NOW + timedelta(seconds=120))

    assert [item.consumer_key for item in snapshot.grants] == ["platform"]


async def test_ensure_view_requires_registered_source() -> None:
    """来源未登记：首访即抛 `CatalogError`（fail-closed，不静默放行）。"""
    with pytest.raises(CatalogError):
        await ensure_grant_view(provider="org")


async def test_view_requires_exactly_one_dimension() -> None:
    """视图维度：`provider` / `consumer` 未二选一即拒（内部契约错误）。"""
    register_capability_grant_source(_FakeSource(ConcurrentStableList()))
    with pytest.raises(CatalogError):
        await ensure_grant_view()
    with pytest.raises(CatalogError):
        await ensure_grant_view(provider="org", consumer="platform")
    assert list(capability_grant_pairs(provider="org")) == []


async def test_remote_source_parses_internal_view_payload() -> None:
    """远端来源：按 `{capability_name, consumer_key, expire_at}` 解析内部出口响应。"""
    from bms_core.collaboration.grant import RemoteCapabilityGrantSource

    class _Client:
        async def call(self, request: object) -> ServiceResponse:
            del request
            body = (
                b'{"code":0,"data":{"provider":"org","consumer":null,"grants":['
                b'{"capability_name":"demo.org.user-roles","consumer_key":"platform","domain":"org",'
                b'"kind":"read","expire_at":null}]}}'
            )
            response = ServiceResponse(status_code=200, content=body)
            return response

    source = RemoteCapabilityGrantSource(_Client())  # pyright: ignore[reportArgumentType]  # 结构替身
    grants = await source.load(provider="org")

    assert [(item.capability_name, item.consumer_key, item.expire_at) for item in grants] == [
        ("demo.org.user-roles", "platform", None)
    ]


async def test_plan_ignores_duplicate_declared_entries() -> None:
    """声明基线重复声明同一「能力 × 消费方」时只算一次（幂等键唯一）。"""
    plan = plan_grant_sync(ConcurrentStableList([_grant(), _grant()]), ConcurrentStableList())

    assert len(plan.creates) == 1


class _ClientStub:
    """服务间调用客户端替身：按预置状态码与响应体返回（覆盖出口非法响应分支）。"""

    def __init__(self, *, status_code: int = 200, body: bytes = b"") -> None:
        """初始化。

        Args:
            status_code: 响应状态码。
            body: 响应体字节。
        """
        self._status_code = status_code
        self._body = body

    async def call(self, request: object) -> ServiceResponse:
        """返回预置响应。

        Args:
            request: 调用请求（未使用）。

        Returns:
            ServiceResponse: 预置响应。
        """
        del request
        return ServiceResponse(status_code=self._status_code, content=self._body)


def _remote_source(*, status_code: int = 200, body: bytes = b"") -> RemoteCapabilityGrantSource:
    """构造远端来源（缺省 200 空体）。

    Args:
        status_code: 预置状态码。
        body: 预置响应体。

    Returns:
        RemoteCapabilityGrantSource: 远端来源实例。
    """
    return RemoteCapabilityGrantSource(_ClientStub(status_code=status_code, body=body))  # pyright: ignore[reportArgumentType]


async def test_remote_source_rejects_unavailable_and_malformed_payloads() -> None:
    """远端来源：HTTP 非 200 / 非 JSON / 缺 data / 缺 grants / 元素非对象一律 `CatalogError`。"""
    cases = [
        (500, b""),
        (200, b"not-json"),
        (200, b'{"data":null}'),
        (200, b'{"data":{"grants":null}}'),
        (200, b'{"data":{"grants":[1]}}'),
    ]
    for status_code, body in cases:
        source = _remote_source(status_code=status_code, body=body)
        with pytest.raises(CatalogError):
            await source.load(provider="org")


async def test_remote_source_parses_expire_at_variants() -> None:
    """远端来源：有效期按 ISO 8601 解析（带时区 / 无时区补 UTC / 非法告警视为长期有效）。"""
    body = (
        b'{"data":{"grants":['
        b'{"capability_name":"a","consumer_key":"p","expire_at":"2030-01-01T00:00:00+00:00"},'
        b'{"capability_name":"b","consumer_key":"p","expire_at":"2030-01-01T00:00:00"},'
        b'{"capability_name":"c","consumer_key":"p","expire_at":"not-a-date"}]}}'
    )
    source = _remote_source(body=body)

    grants = await source.load(consumer="platform")

    assert [g.expire_at for g in grants] == [
        datetime(2030, 1, 1, tzinfo=UTC),
        datetime(2030, 1, 1, tzinfo=UTC),
        None,
    ]


async def test_invalidate_snapshots_all_or_specific() -> None:
    """快照失效：给维度只失效该维度（不存在的键安全跳过），不给维度清空全部。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant()])))
    await ensure_grant_view(provider="org", now=_NOW)
    await ensure_grant_view(consumer="platform", now=_NOW)

    invalidate_capability_grants(provider="org")
    assert list(capability_grant_pairs(provider="org")) == []
    assert len(capability_grant_pairs(consumer="platform")) == 1

    invalidate_capability_grants(provider="ghost")
    invalidate_capability_grants()
    assert list(capability_grant_pairs(consumer="platform")) == []


async def test_ensure_view_raises_when_first_load_fails() -> None:
    """来源首次加载失败且无旧快照：抛错（fail-closed，不以空视图冒充已加载）。"""
    source = _FakeSource(ConcurrentStableList())
    source.fail = True
    register_capability_grant_source(source)

    with pytest.raises(CatalogError):
        await ensure_grant_view(provider="org", now=_NOW)


async def test_granted_scopes_skips_disabled_capability_and_codes() -> None:
    """出站 scope：禁用能力与 `codes` 类不产生 scope。"""
    from bms_core.services.module_registry import CollaborationStatus

    disabled = _record("demo.org.legacy")
    register_collaboration_records(
        (
            _record(),
            _record("demo.org.codes", kind="codes"),
            CollaborationRecord(
                name=disabled.name,
                domain=disabled.domain,
                kind=disabled.kind,
                contract_version=disabled.contract_version,
                path=None,
                product_key="demo",
                frontend_prefix="demo",
                status=CollaborationStatus.DISABLED,
            ),
        )
    )
    register_capability_grant_source(
        _FakeSource(
            ConcurrentStableList(
                [
                    _grant("demo.org.codes"),
                    _grant("demo.org.legacy"),
                    _grant("demo.org.user-roles"),
                ]
            )
        )
    )
    await ensure_grant_view(consumer="platform", now=_NOW)

    assert list(granted_scopes("platform")) == [f"{SCOPE_PREFIX}:org:read"]


async def test_granted_consumers_skips_other_capability() -> None:
    """入站允许集合：只回本能力的授权（同域其他能力的记录不计入）。"""
    register_collaboration_records((_record(), _record("demo.org.other")))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant("demo.org.other", "mdm"), _grant()])))
    await ensure_grant_view(provider="org", now=_NOW)

    assert list(granted_consumers("demo.org.user-roles")) == ["platform"]


async def test_check_access_unknown_capability_and_blank_consumer() -> None:
    """入站校验前置：能力未登记（`CatalogError`）/ 调用方缺失（`PermissionError`）。"""
    with pytest.raises(PermissionError):
        await check_capability_access("demo.org.user-roles", "")

    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList()))
    with pytest.raises(CatalogError):
        await check_capability_access("demo.org.ghost", "platform")


async def test_granted_scopes_skips_expired_and_disabled_grants() -> None:
    """出站 scope：消费方视图中已过期 / 已撤销的记录不产生 scope。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(
        _FakeSource(
            ConcurrentStableList(
                [
                    _grant(expire_at=datetime(2020, 1, 1, tzinfo=UTC)),
                    _grant(status=GRANT_STATUS_DISABLED),
                ]
            )
        )
    )
    await ensure_grant_view(consumer="platform", now=_NOW)

    assert list(granted_scopes("platform")) == []


async def test_granted_consumers_dedupes_repeated_rows() -> None:
    """入站允许集合：来源返回重复行时按消费方去重（幂等视图，不重复列示）。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant(), _grant()])))
    await ensure_grant_view(provider="org", now=_NOW)

    assert list(granted_consumers("demo.org.user-roles")) == ["platform"]


async def test_check_access_without_metrics_passes_silently() -> None:
    """无指标器（测试 / 无观测环境）：判定照常，打点跳过。"""
    register_collaboration_records((_record(),))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant()])))
    await ensure_grant_view(provider="org", now=_NOW)

    await check_capability_access("demo.org.user-roles", "platform")


async def test_build_request_fills_scopes_from_grants(monkeypatch: pytest.MonkeyPatch) -> None:
    """请求构造：缺省 policy 的 `scopes` 由当前服务的有效授权派生（显式 policy 原样尊重）。"""
    from types import SimpleNamespace

    from bms_core.collaboration import request as request_module
    from bms_core.servicecall.base import ServiceCallPolicy
    from bms_core.services.module_registry import register_domain_services

    register_collaboration_records((_record(kind="write"),))
    register_domain_services(ConcurrentStableFrozenDict({"org": "mdm"}))
    register_capability_grant_source(_FakeSource(ConcurrentStableList([_grant()])))
    await ensure_grant_view(consumer="platform", now=_NOW)
    monkeypatch.setattr(
        request_module,
        "get_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(service="platform")),
    )

    endpoint = resolve_capability("demo.org.user-roles")
    auto = build_capability_request(endpoint, method="GET")
    explicit = build_capability_request(
        endpoint, method="GET", policy=ServiceCallPolicy(timeout=1.5, scopes=ConcurrentStableFrozenList(["x:y"]))
    )

    assert list(auto.policy.scopes) == [f"{SCOPE_PREFIX}:org:write"]
    assert list(explicit.policy.scopes) == ["x:y"] and explicit.policy.timeout == 1.5
